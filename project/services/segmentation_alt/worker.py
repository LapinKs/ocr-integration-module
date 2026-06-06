import sys
import os
import io
import cv2
import numpy as np
import time
from pathlib import Path
from PIL import Image
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from services import task_starter
from shared.infrastructure.redis_client import create_redis_client
from shared.infrastructure.minio_client import create_minio_client
from services.celery_app import celery_app
from .client import DocLayoutYOLOClient
MODEL_PATH = os.environ.get('DOCLAYOUT_MODEL_PATH', '/app/models/doclayout_yolo.pt')
BUCKET_MASKS = "formula-masks"
redis_url = os.environ.get('REDIS_URL', 'redis://redis:6379/0')
minio_endpoint = os.environ.get('MINIO_ENDPOINT', 'minio:9000')
minio_access = os.environ.get('MINIO_ACCESS_KEY', 'minioadmin')
minio_secret = os.environ.get('MINIO_SECRET_KEY', 'minioadmin')
redis_client = create_redis_client(redis_url)
minio_client = create_minio_client(minio_endpoint, minio_access, minio_secret)
segmentator = None

from shared.metrics.production_metrics import (
    metrics, error_counter, push_metrics_to_gateway,pages_processed,
)


def get_segmentator():
    global segmentator
    if segmentator is None:
        print(f"[Segmentation] Loading DocLayout-YOLO from {MODEL_PATH}")
        segmentator = DocLayoutYOLOClient(model_path=MODEL_PATH)
        print("[Segmentation] Model loaded")
    return segmentator


@celery_app.task(queue='segmentation', bind=True, max_retries=3)
def process_segmentation(self, task_id: str, page_index: int, image_bytes: bytes):
    print(f"[Segmentation] Task {task_id}, page {page_index}")
    start_time = time.time()
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        image_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if image_bgr is None:
            raise ValueError("Failed to decode image")

        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        h, w = image_rgb.shape[:2]
        pil_image = Image.fromarray(image_rgb)

        segmentator_instance = get_segmentator()
        detect_start = time.time()
        results = segmentator_instance.detect([pil_image])
        detect_time = time.time() - detect_start
        duration = time.time() - start_time
        formulas = []
        formula_id = 0
        margin = 5

        formula_ids_key = f"page_formulas:{task_id}:{page_index}"

        for regions in results:
            for region in regions:
                if "formula" in region["class_name"].lower() and region["confidence"] > 0.5:
                    x1, y1, x2, y2 = region["bbox"]

                    x1 = max(0, x1 - margin)
                    y1 = max(0, y1 - margin)
                    x2 = min(w, x2 + margin)
                    y2 = min(h, y2 + margin)

                    key = f"formula:{task_id}:{page_index}:{formula_id}"
                    redis_client.hset(key, "bbox_x1", x1)
                    redis_client.hset(key, "bbox_y1", y1)
                    redis_client.hset(key, "bbox_x2", x2)
                    redis_client.hset(key, "bbox_y2", y2)
                    redis_client.hset(key, "status", "segmented")
                    redis_client.hset(key, "confidence", region["confidence"])

                    redis_client.sadd(formula_ids_key, formula_id)

                    mask = np.ones((y2 - y1, x2 - x1), dtype=np.uint8) * 255
                    mask_buffer = io.BytesIO()
                    np.save(mask_buffer, mask)
                    mask_bytes = mask_buffer.getvalue()
                    mask_path = f"{task_id}/{page_index}/mask_{formula_id}.npy"
                    minio_client.put_object(BUCKET_MASKS, mask_path, io.BytesIO(mask_bytes), len(mask_bytes))
                    redis_client.hset(key, "mask_path", mask_path)

                    formulas.append({
                        'id': formula_id,
                        'bbox': (x1, y1, x2, y2),
                        'confidence': region["confidence"]
                    })
                    formula_id += 1

        if formula_id > 0:
            redis_client.expire(formula_ids_key, 3600)
        redis_client.hset(f"page:{task_id}:{page_index}", "width", w)
        redis_client.hset(f"page:{task_id}:{page_index}", "height", h)
        redis_client.hset(f"page:{task_id}:{page_index}", "total_formulas", formula_id)
        redis_client.hset(f"page:{task_id}:{page_index}", "status", "segmented")

        from services.task_starter import start_recognition_task
        start_recognition_task(task_id, page_index)
        print(f"[Segmentation] Triggered recognition batch for {formula_id} formulas")
        total_time = time.time() - start_time
        print(f"[Segmentation] Found {formula_id} formulas in {total_time:.2f}s")

        ocr_status = redis_client.hget(f"page:{task_id}:{page_index}", "ocr_status")
        print(f"[Segmentation] DEBUG: ocr_status = {ocr_status}")

        if ocr_status == b"completed":
            from services.task_starter import start_merge_task
            start_merge_task(task_id, page_index)
        else:
            print(f"[Segmentation] OCR not ready (status={ocr_status}), merge not triggered")
        duration = time.time() - start_time
        metrics.segmentation_time.labels(task_id=task_id, page_index=str(page_index)).observe(duration)
        metrics.segmentation_formulas_found.labels(task_id=task_id, page_index=str(page_index)).set(formula_id)
        pages_processed.labels(worker_type='segmentation_alt', status='success').inc()
        push_metrics_to_gateway('segmentation-alt-worker', task_id, page_index)

        redis_client.hset(f"page:{task_id}:{page_index}", "segmentation_time_ms", int(duration * 1000))

        return {
            "task_id": task_id,
            "page_index": page_index,
            "formulas_count": formula_id,
            "detection_time_s": detect_time,
            "total_time_s": total_time,
            "segmentation_time_s": round(duration, 2),
            "formulas_found": formula_id
        }

    except Exception as e:
        pages_processed.labels(worker_type='segmentation_alt', status='failed').inc()
        push_metrics_to_gateway('segmentation-alt-worker', task_id, page_index)
        error_counter.labels(worker_type='segmentation_alt', error_type=type(e).__name__).inc()
        print(f"[Segmentation] Error: {e}")
        import traceback
        traceback.print_exc()
        redis_client.hset(f"page:{task_id}:{page_index}", "status", "segmentation_failed")
        raise self.retry(exc=e, countdown=10, max_retries=3)
