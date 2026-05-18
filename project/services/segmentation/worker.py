#!/usr/bin/env python3
import sys
import os
import io
import cv2
import numpy as np
from pathlib import Path
from typing import List, Dict
from celery import Celery
import time
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.infrastructure.redis_client import redis_client
from shared.infrastructure.minio_client import minio_client
from .bbox_utils import MaskUtils

# Импорт сегментатора
from app.infrastructure.formula.segmentators.client import FinetunedUNetFormer, UNetFormerConfig

MODEL_PATH = Path(__file__).parent / "models" / "weights.pth"
BUCKET_MASKS = "formula-masks"

app = Celery('segmentation', broker=os.environ.get('REDIS_URL', 'redis://redis:6379/0'))

segmentator = None

@app.on_after_configure.connect
def setup_segmentator(sender, **kwargs):
    global segmentator
    print("[Segmentation] Loading model...")
    config = UNetFormerConfig(device="cpu", postprocess_threshold=0.45)
    segmentator = FinetunedUNetFormer(
        model_path=str(MODEL_PATH),
        config=config,
        backbone_name="tf_efficientnet_b5",
        num_classes=2
    )
    print("[Segmentation] Model loaded")

@app.task(queue='segmentation', bind=True, max_retries=3)
def process_segmentation(self, task_id: str, page_index: int, image_bytes: bytes):
    """Сегментация формул на странице"""
    try:
        # Декодируем изображение
        nparr = np.frombuffer(image_bytes, np.uint8)
        image_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        h, w = image_rgb.shape[:2]

        print(f"[Segmentation] Page {page_index}: {w}x{h}")

        # Сегментация
        formulas = segmentator.extract_formula_regions(image_rgb, margin=10, use_dsu=True)

        # Сохраняем метаданные страницы
        redis_client.hset(f"page:{task_id}:{page_index}", "width", w)
        redis_client.hset(f"page:{task_id}:{page_index}", "height", h)
        redis_client.hset(f"page:{task_id}:{page_index}", "total_formulas", len(formulas))
        redis_client.hset(f"page:{task_id}:{page_index}", "status", "segmented")
        redis_client.hset(f"page:{task_id}:{page_index}", "segmented_at", str(time.time()))

        # Сохраняем каждую формулу
        for f in formulas:
            formula_id = f['id']
            key = f"formula:{task_id}:{page_index}:{formula_id}"

            redis_client.hset(key, "bbox_x1", f['bbox'][0])
            redis_client.hset(key, "bbox_y1", f['bbox'][1])
            redis_client.hset(key, "bbox_x2", f['bbox'][2])
            redis_client.hset(key, "bbox_y2", f['bbox'][3])
            redis_client.hset(key, "status", "segmented")
            redis_client.hset(key, "confidence", f.get('confidence', 0.0))
            redis_client.hset(key, "created_at", str(time.time()))

            # Сохраняем маску в MinIO
            mask_bytes = f['mask'].tobytes()
            mask_path = f"{task_id}/{page_index}/mask_{formula_id}.npy"
            minio_client.put_object(
                BUCKET_MASKS, mask_path,
                io.BytesIO(mask_bytes), len(mask_bytes)
            )
            redis_client.hset(key, "mask_path", mask_path)

        print(f"[Segmentation] Page {page_index}: found {len(formulas)} formulas")

        # Проверяем, можно ли запускать MERGE (если OCR уже готов)
        # Это можно сделать через отдельный триггер или periodic task

        return {
            "task_id": task_id,
            "page_index": page_index,
            "formulas_count": len(formulas),
            "image_size": (w, h)
        }

    except Exception as e:
        redis_client.hset(f"page:{task_id}:{page_index}", "status", "segmentation_failed")
        raise self.retry(exc=e, countdown=10, max_retries=3)


# Для тестирования (можно убрать)
if __name__ == '__main__':
    print('Segmentation worker started')
    while True:
        time.sleep(60)
