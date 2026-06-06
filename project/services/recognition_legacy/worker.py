import sys
import os
import io
import time
import cv2
import numpy as np
from pathlib import Path
from typing import List, Dict
from PIL import Image
import asyncio
import re
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from shared.infrastructure.redis_client import create_redis_client
from shared.infrastructure.minio_client import create_minio_client
from shared.image_utils import crop_with_mask
from services.celery_app import celery_app
from .latex_ocr_client import LegacyLatexOCRClient

MODEL_DIR = Path(__file__).parent / "models"
WEIGHTS_PATH = MODEL_DIR / "new_weights.pth"
TOKENIZER_PATH = MODEL_DIR / "tokenizer.json"
BUCKET_IMAGES = "source-images"
BUCKET_MASKS = "formula-masks"

redis_url = os.environ.get('REDIS_URL', 'redis://redis:6379/0')
minio_endpoint = os.environ.get('MINIO_ENDPOINT', 'minio:9000')
minio_access = os.environ.get('MINIO_ACCESS_KEY', 'minioadmin')
minio_secret = os.environ.get('MINIO_SECRET_KEY', 'minioadmin')

redis_client = create_redis_client(redis_url)
minio_client = create_minio_client(minio_endpoint, minio_access, minio_secret)
recognizer = None

from shared.metrics.production_metrics import (
    metrics, error_counter, push_metrics_to_gateway,pages_processed,
    recognition_batch_time
)

def get_recognizer():
    global recognizer
    if recognizer is None:
        print("[LegacyOCR Worker] Loading legacy model...")
        recognizer = LegacyLatexOCRClient(device="cpu", max_concurrent=4)
        print("[LegacyOCR Worker] Model loaded")
    return recognizer


@celery_app.task(queue='recognition', bind=True, max_retries=3)
def recognize_batch_legacy(self, task_id: str, page_index: int, batch_size: int = 8):
    start_time = time.time()
    with metrics.measure("recognition_total", task_id, page_index, worker_type="recognition"):
        try:
            print(f"[LegacyOCR] ========== STARTING RECOGNITION ==========")
            print(f"[LegacyOCR] task_id: {task_id}, page_index: {page_index}")

            formula_ids_key = f"page_formulas:{task_id}:{page_index}"
            formula_ids = redis_client.smembers(formula_ids_key)
            print(f"[LegacyOCR] Found {len(formula_ids)} formula IDs in Set")

            pending = []
            for formula_id_bytes in formula_ids:
                formula_id = int(formula_id_bytes)
                key = f"formula:{task_id}:{page_index}:{formula_id}"
                status = redis_client.hget(key, "status")
                latex = redis_client.hget(key, "latex")
                if status == b"segmented" and not latex:
                    pending.append((key, formula_id))

            if not pending:
                print(f"[LegacyOCR] No pending formulas, exiting")
                return {"status": "no_pending", "task_id": task_id, "page_index": page_index}

            print(f"[LegacyOCR] Page {page_index}: {len(pending)} formulas to recognize")

            with metrics.measure("recognition_load_image", task_id, page_index):
                image_data = minio_client.get_object(BUCKET_IMAGES, f"{task_id}/{page_index}/image.jpg")
                image_bytes = image_data.read()
                image_data.close()
                nparr = np.frombuffer(image_bytes, np.uint8)
                image_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
                print(f"[LegacyOCR] Image loaded: {image_rgb.shape}")

            results = []
            all_formula_ids = []
            recognizer_instance = get_recognizer()

            crops = []
            batch_formulas = []

            for key, formula_id in pending:
                x1 = int(redis_client.hget(key, "bbox_x1"))
                y1 = int(redis_client.hget(key, "bbox_y1"))
                x2 = int(redis_client.hget(key, "bbox_x2"))
                y2 = int(redis_client.hget(key, "bbox_y2"))
                bbox = (x1, y1, x2, y2)

                mask_path = redis_client.hget(key, "mask_path")
                mask = None
                if mask_path:
                    mask_path_str = mask_path.decode() if isinstance(mask_path, bytes) else mask_path
                    mask_data = minio_client.get_object(BUCKET_MASKS, mask_path_str)
                    mask_bytes = mask_data.read()
                    mask_data.close()
                    import numpy as np
                    import io
                    mask = np.load(io.BytesIO(mask_bytes), allow_pickle=True)

                crop_pil = crop_with_mask(image_rgb, bbox, mask)
                crops.append(crop_pil)
                batch_formulas.append((key, formula_id))

            batch_start = time.time()

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            batch_latex = loop.run_until_complete(recognizer_instance.recognize_batch_async(crops))
            loop.close()

            batch_time = (time.time() - batch_start) * 1000
            print(f"[LegacyOCR] Batch: {len(crops)} crops, {batch_time:.0f}ms")
            metrics.gauge("recognition_batch_time_ms", batch_time, task_id)
            recognition_batch_time.labels(task_id=task_id).observe(batch_time)

            for (key, formula_id), latex in zip(batch_formulas, batch_latex):
                if latex:
                    redis_client.hset(key, "latex", latex)
                    redis_client.hset(key, "status", "latex_ready")
                    redis_client.hincrby(f"page:{task_id}:{page_index}", "recognized_count", 1)
                    results.append({"formula_id": formula_id, "latex": latex})
                    all_formula_ids.append(formula_id)
                else:
                    print(f"[LegacyOCR] Empty latex for formula {formula_id}")

            metrics.increment_counter("formulas_recognized", task_id, len(results))

            print(f"[LegacyOCR] ========== ALL BATCHES COMPLETED ==========")
            print(f"[LegacyOCR] Total recognized: {len(results)}")
            print(f"[LegacyOCR] all_formula_ids: {all_formula_ids}")
            duration = time.time() - start_time
            metrics.recognition_time.labels(task_id=task_id, page_index=str(page_index)).observe(duration)
            metrics.recognition_formulas_processed.labels(task_id=task_id, page_index=str(page_index)).set(len(results))
            pages_processed.labels(worker_type='recognition_legacy', status='success').inc()
            push_metrics_to_gateway('recognition-legacy-worker', task_id, page_index)

            redis_client.hset(f"page:{task_id}:{page_index}", "recognition_time_ms", int(duration * 1000))
            return {
                "task_id": task_id,
                "page_index": page_index,
                "recognized": len(results),
                "formula_ids": all_formula_ids,
                "recognition_time_s": round(duration, 2),
                "formulas_recognized": len(results)
            }

        except Exception as e:
            pages_processed.labels(worker_type='recognition_legacy', status='failed').inc()
            push_metrics_to_gateway('recognition-legacy-worker', task_id, page_index)
            error_counter.labels(worker_type='recognition_legacy', error_type=type(e).__name__).inc()
            print(f"[LegacyOCR] FATAL ERROR: {e}")
            import traceback
            traceback.print_exc()
            metrics.save_error_sync(task_id, "recognition", str(e), page_index, "error")
            raise self.retry(exc=e, countdown=10, max_retries=self.max_retries)
