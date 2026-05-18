#!/usr/bin/env python3
import sys
import os
import io
import time
import cv2
import numpy as np
from pathlib import Path
from typing import List, Dict
from PIL import Image
from celery import Celery

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.infrastructure.redis_client import redis_client
from shared.infrastructure.minio_client import minio_client

# Правильный импорт распознавателя
from .new_client import FinetunedLatexOCRClient

MODEL_DIR = Path(__file__).parent / "models"
WEIGHTS_PATH = MODEL_DIR / "new_weights.pth"
TOKENIZER_PATH = MODEL_DIR / "tokenizer.json"
BUCKET_IMAGES = "source-images"
BUCKET_MASKS = "formula-masks"

app = Celery('recognition', broker=os.environ.get('REDIS_URL', 'redis://redis:6379/0'))

recognizer = None

@app.on_after_configure.connect
def setup_recognizer(sender, **kwargs):
    global recognizer
    print("[Recognition] Loading model...")
    recognizer = FinetunedLatexOCRClient(
        model_path=str(WEIGHTS_PATH),
        tokenizer_path=str(TOKENIZER_PATH),
        device="cuda" if os.environ.get('CUDA_VISIBLE_DEVICES') else "cpu",
        batch_size=8
    )
    print(f"[Recognition] Model loaded on {recognizer.device}")

@app.task(queue='recognition', bind=True, max_retries=3)
def recognize_batch(self, task_id: str, page_index: int, batch_size: int = 8):
    """Батчевое распознавание формул на странице"""
    try:
        # Получаем список формул без LaTeX
        pattern = f"formula:{task_id}:{page_index}:*"
        keys = redis_client.keys(pattern)

        pending = []
        for key in keys:
            status = redis_client.hget(key, "status")
            latex = redis_client.hget(key, "latex")
            if status == b"segmented" and not latex:
                formula_id = int(key.decode().split(':')[-1])
                pending.append((key, formula_id))

        if not pending:
            return {"status": "no_pending", "task_id": task_id, "page_index": page_index}

        print(f"[Recognition] Page {page_index}: {len(pending)} formulas to recognize")

        # Загружаем оригинальное изображение
        image_data = minio_client.get_object(BUCKET_IMAGES, f"{task_id}/{page_index}/image.jpg")
        image_bytes = image_data.read()
        image_data.close()

        nparr = np.frombuffer(image_bytes, np.uint8)
        image_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)

        # Батчевая обработка
        results = []
        all_formula_ids = []

        for i in range(0, len(pending), batch_size):
            batch = pending[i:i+batch_size]
            crops = []
            batch_formulas = []

            for key, formula_id in batch:
                x1 = int(redis_client.hget(key, "bbox_x1"))
                y1 = int(redis_client.hget(key, "bbox_y1"))
                x2 = int(redis_client.hget(key, "bbox_x2"))
                y2 = int(redis_client.hget(key, "bbox_y2"))

                crop = image_rgb[y1:y2, x1:x2].copy()

                # Загружаем маску и применяем её
                mask_path = redis_client.hget(key, "mask_path")
                if mask_path:
                    mask_path_str = mask_path.decode() if isinstance(mask_path, bytes) else mask_path
                    mask_data = minio_client.get_object(BUCKET_MASKS, mask_path_str)
                    mask = np.load(io.BytesIO(mask_data.read()))
                    mask_data.close()

                    if mask.shape != crop.shape[:2]:
                        mask = cv2.resize(mask, (crop.shape[1], crop.shape[0]))
                    mask_3ch = np.stack([mask] * 3, axis=-1)
                    crop = np.where(mask_3ch > 0, crop, 255)

                crops.append(Image.fromarray(crop))
                batch_formulas.append((key, formula_id))

            # Распознаем батч
            batch_start = time.time()
            batch_latex = recognizer.recognize_batch(crops)
            batch_time = (time.time() - batch_start) * 1000

            print(f"[Recognition] Batch {i//batch_size + 1}: {len(batch)} crops, {batch_time:.0f}ms")

            for (key, formula_id), latex in zip(batch_formulas, batch_latex):
                redis_client.hset(key, "latex", latex)
                redis_client.hset(key, "status", "latex_ready")
                redis_client.hincrby(f"page:{task_id}:{page_index}", "recognized_count", 1)
                results.append({"formula_id": formula_id, "latex": latex})
                all_formula_ids.append(formula_id)

        # Проверяем, нужно ли триггерить UPDATE
        page_status = redis_client.hget(f"page:{task_id}:{page_index}", "status")
        if page_status == b"merged":
            # Дерево уже есть, обновляем сразу
            from services.update.worker import update_placeholders
            update_placeholders.delay(task_id, page_index, all_formula_ids)

        return {
            "task_id": task_id,
            "page_index": page_index,
            "recognized": len(results),
            "formula_ids": all_formula_ids
        }

    except Exception as e:
        raise self.retry(exc=e, countdown=10, max_retries=3)
