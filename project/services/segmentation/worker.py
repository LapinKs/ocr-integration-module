
import sys
import os
import io
import cv2
import numpy as np
import time
from pathlib import Path
from typing import List, Dict

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from shared.infrastructure.redis_client import create_redis_client
from shared.infrastructure.minio_client import create_minio_client
from shared.merge.bbox_utils import MaskUtils
from .client import FinetunedUNetFormer, UNetFormerConfig
from services.celery_app import celery_app
from shared.metrics.production_metrics import metrics

MODEL_PATH = Path(__file__).parent / "models" / "weights.pth"
BUCKET_MASKS = "formula-masks"

redis_url = os.environ.get('REDIS_URL', 'redis://redis:6379/0')
minio_endpoint = os.environ.get('MINIO_ENDPOINT', 'minio:9000')
minio_access = os.environ.get('MINIO_ACCESS_KEY', 'minioadmin')
minio_secret = os.environ.get('MINIO_SECRET_KEY', 'minioadmin')

redis_client = create_redis_client(redis_url)
minio_client = create_minio_client(minio_endpoint, minio_access, minio_secret)

segmentator = None

from shared.metrics.production_metrics import (
    metrics, error_counter, push_metrics_to_gateway,
pages_processed,)

@celery_app.on_after_configure.connect
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



@celery_app.task(queue='segmentation', bind=True, max_retries=3)
def process_segmentation(self, task_id: str, page_index: int, image_bytes: bytes):
    start_time = time.time()
    print("=" * 70)
    print(f"[Segmentation] STARTING task {task_id}, page {page_index}")
    print(f"[Segmentation] Image bytes size: {len(image_bytes)} bytes")
    print("=" * 70)

    overall_start = time.time()

    with metrics.measure("segmentation_total", task_id, page_index, worker_type="segmentation"):
        try:

            print(f"[Segmentation] Step 1/5: Decoding image...")
            decode_start = time.time()

            nparr = np.frombuffer(image_bytes, np.uint8)
            image_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if image_bgr is None:
                raise ValueError("Failed to decode image - invalid image format")

            image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
            h, w = image_rgb.shape[:2]

            decode_time = time.time() - decode_start
            print(f"[Segmentation] ✓ Image decoded: {w}x{h} in {decode_time:.2f}s")
            print(f"[Segmentation]   - Channels: {image_rgb.shape[2]}")
            print(f"[Segmentation]   - Data type: {image_rgb.dtype}")


            print(f"[Segmentation] Step 2/5: Running formula extraction...")
            print(f"[Segmentation]   - Margin: 10px")
            print(f"[Segmentation]   - DSU merging: enabled")
            print(f"[Segmentation]   - Min formula area: 50px")

            extract_start = time.time()

            with metrics.measure("segmentation_extract", task_id, page_index, worker_type="segmentation"):
                formulas = segmentator.extract_formula_regions(image_rgb, margin=10, use_dsu=True)

            extract_time = time.time() - extract_start
            print(f"[Segmentation]  Extraction completed in {extract_time:.2f}s")
            print(f"[Segmentation]   - Formulas found: {len(formulas)}")


            print(f"[Segmentation] Step 3/5: Saving page metadata to Redis...")
            redis_start = time.time()

            redis_client.hset(f"page:{task_id}:{page_index}", "width", w)
            redis_client.hset(f"page:{task_id}:{page_index}", "height", h)
            redis_client.hset(f"page:{task_id}:{page_index}", "total_formulas", len(formulas))
            redis_client.hset(f"page:{task_id}:{page_index}", "status", "segmented")
            redis_client.hset(f"page:{task_id}:{page_index}", "segmented_at", str(time.time()))

            redis_time = time.time() - redis_start
            print(f"[Segmentation]  Page metadata saved in {redis_time:.3f}s")


            print(f"[Segmentation] Step 4/5: Saving {len(formulas)} formulas and masks...")
            save_start = time.time()

            for idx, f in enumerate(formulas):
                formula_id = f['id']
                key = f"formula:{task_id}:{page_index}:{formula_id}"


                redis_client.hset(key, "bbox_x1", f['bbox'][0])
                redis_client.hset(key, "bbox_y1", f['bbox'][1])
                redis_client.hset(key, "bbox_x2", f['bbox'][2])
                redis_client.hset(key, "bbox_y2", f['bbox'][3])
                redis_client.hset(key, "status", "segmented")
                redis_client.hset(key, "confidence", f.get('confidence', 0.0))
                redis_client.hset(key, "created_at", str(time.time()))


                mask_bytes = f['mask'].tobytes()
                mask_path = f"{task_id}/{page_index}/mask_{formula_id}.npy"
                minio_client.put_object(
                    BUCKET_MASKS, mask_path,
                    io.BytesIO(mask_bytes), len(mask_bytes)
                )
                redis_client.hset(key, "mask_path", mask_path)


                if (idx + 1) % 20 == 0 or (idx + 1) == len(formulas):
                    print(f"[Segmentation]   - Saved {idx + 1}/{len(formulas)} formulas")

            save_time = time.time() - save_start
            print(f"[Segmentation]  All formulas saved in {save_time:.2f}s")


            print(f"[Segmentation] Step 5/5: Checking OCR status...")

            ocr_status = redis_client.hget(f"page:{task_id}:{page_index}", "ocr_status")
            ocr_status_str = ocr_status.decode() if isinstance(ocr_status, bytes) else str(ocr_status)

            print(f"[Segmentation]   - OCR status: {ocr_status_str}")

            if ocr_status == b"completed":
                print(f"[Segmentation]  OCR is ready! Triggering MERGE...")
                from services.merge.worker import merge_with_placeholders
                merge_with_placeholders.delay(task_id, page_index)
                print(f"[Segmentation]   - MERGE task queued")
            else:
                print(f"[Segmentation]  OCR not ready yet, setting page to 'segmented'")
                print(f"[Segmentation]   - MERGE will start when OCR completes")


            total_time = time.time() - overall_start


            metrics.gauge("segmentation_formulas_found", len(formulas), task_id)
            metrics.increment_counter("segmentation_pages_processed", task_id)

            print("=" * 70)
            print(f"[Segmentation] FINISHED task {task_id}, page {page_index}")
            print(f"[Segmentation] Total time: {total_time:.2f}s")
            print(f"[Segmentation]   - Decode: {decode_time:.2f}s ({decode_time/total_time*100:.1f}%)")
            print(f"[Segmentation]   - Extract: {extract_time:.2f}s ({extract_time/total_time*100:.1f}%)")
            print(f"[Segmentation]   - Redis: {redis_time:.2f}s ({redis_time/total_time*100:.1f}%)")
            print(f"[Segmentation]   - Save: {save_time:.2f}s ({save_time/total_time*100:.1f}%)")
            print(f"[Segmentation] Formulas: {len(formulas)}")
            print("=" * 70)
            duration = time.time() - start_time
            metrics.segmentation_time.labels(task_id=task_id, page_index=str(page_index)).observe(duration)
            metrics.segmentation_formulas_found.labels(task_id=task_id, page_index=str(page_index)).set(len(formulas))
            pages_processed.labels(worker_type='segmentation', status='success').inc()
            push_metrics_to_gateway('segmentation-worker', task_id, page_index)

            redis_client.hset(f"page:{task_id}:{page_index}", "segmentation_time_ms", int(duration * 1000))
            return {
                "task_id": task_id,
                "page_index": page_index,
                "formulas_count": len(formulas),
                "image_size": (w, h),
                "timing": {
                    "total_s": round(total_time, 2),
                    "decode_s": round(decode_time, 2),
                    "extract_s": round(extract_time, 2),
                    "redis_s": round(redis_time, 2),
                    "save_s": round(save_time, 2)
                }
            }

        except Exception as e:
            pages_processed.labels(worker_type='segmentation', status='failed').inc()
            push_metrics_to_gateway('segmentation-worker', task_id, page_index)
            error_counter.labels(worker_type='segmentation', error_type=type(e).__name__).inc()
            error_time = time.time() - overall_start
            print("=" * 70)
            print(f"[Segmentation]  ERROR in task {task_id}, page {page_index}")
            print(f"[Segmentation] Error after {error_time:.2f}s: {type(e).__name__}: {e}")
            print("=" * 70)

            import traceback
            traceback.print_exc()

            redis_client.hset(f"page:{task_id}:{page_index}", "status", "segmentation_failed")
            redis_client.hset(f"page:{task_id}:{page_index}", "error_message", str(e))

            import asyncio
            asyncio.create_task(metrics.save_error(
                task_id, "segmentation", str(e), page_index, "error"
            ))


            if self.request.retries < self.max_retries:
                print(f"[Segmentation] Will retry (attempt {self.request.retries + 1}/{self.max_retries})")
            else:
                print(f"[Segmentation] Max retries reached, giving up")

            raise self.retry(exc=e, countdown=10, max_retries=3)


if __name__ == '__main__':
    print('Segmentation worker started')
    while True:
        time.sleep(60)
