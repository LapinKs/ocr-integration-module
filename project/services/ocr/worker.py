import sys
import os
import io
import json
import asyncio
from pathlib import Path
import time
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from shared.metrics.production_metrics import metrics, error_counter
from shared.infrastructure.redis_client import create_redis_client
from shared.infrastructure.minio_client import create_minio_client
from .client import OCRClient
from services.celery_app import celery_app

BUCKET_OCR = "ocr-results"
BUCKET_IMAGES = "source-images"
from shared.merge.lock_utils import try_acquire_merge_lock, release_merge_lock
from services.task_starter import start_merge_task
redis_url = os.environ.get('REDIS_URL', 'redis://redis:6379/0')
minio_endpoint = os.environ.get('MINIO_ENDPOINT', 'minio:9000')
minio_access = os.environ.get('MINIO_ACCESS_KEY', 'minioadmin')
minio_secret = os.environ.get('MINIO_SECRET_KEY', 'minioadmin')

redis_client = create_redis_client(redis_url)
minio_client = create_minio_client(minio_endpoint, minio_access, minio_secret)
from shared.metrics.production_metrics import push_metrics_to_gateway, pages_processed, merge_time
OCR_API_KEY = os.environ.get('OCR_API_KEY', 'iACQFtrNBObX0RwjYA_UVmFqxt7lSIqOu_QR7UK0Syk')
OCR_BASE_URL = os.environ.get('OCR_BASE_URL', 'https://ocrbot.ru/api/v1')
OCR_JSON_PATH = os.environ.get('OCR_JSON_PATH', '/app/services/ocr/fallback.json')
OCR_FALLBACK_DIR = Path(__file__).parent / "fallback"
ocr_client = OCRClient(
    api_key=OCR_API_KEY,
    base_url=OCR_BASE_URL,
    fallback_json_path=OCR_FALLBACK_DIR
)

from shared.metrics.production_metrics import (
    metrics, error_counter, push_metrics_to_gateway, pages_processed,
)
@celery_app.task(queue='ocr', bind=True, max_retries=1)
def process_ocr(self, task_id: str, page_index: int, image_bytes: bytes, image_filename: str = None):
    start_time = time.time()
    print(f"[OCR Worker] Starting processing for task {task_id}, page {page_index}")

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        print(f"[OCR Worker] Calling OCR client...")
        ocr_results = loop.run_until_complete(
            ocr_client.recognize_many([image_bytes], image_filenames=[image_filename] if image_filename else None)
        )
        loop.close()
        # duration = time.time() - start_time
        # metrics.ocr_time.labels(task_id=task_id, page_index=str(page_index)).observe(duration)
        print(f"[OCR Worker] Got {len(ocr_results)} results")

        if not ocr_results or len(ocr_results) == 0:
            raise RuntimeError("No OCR results returned")

        ocr_result = ocr_results[0]

        result_str = json.dumps(ocr_result).lower()
        is_fallback = "fallback" in result_str or "ocr fallback" in result_str

        print(f"[OCR Worker] Result type: {'FALLBACK' if is_fallback else 'API'}")

        ocr_json = json.dumps(ocr_result, ensure_ascii=False, indent=2)
        ocr_path = f"{task_id}/{page_index}/ocr.json"

        print(f"[OCR Worker] Saving OCR result to MinIO: {ocr_path}")
        minio_client.put_object(
            BUCKET_OCR,
            ocr_path,
            io.BytesIO(ocr_json.encode('utf-8')),
            len(ocr_json.encode('utf-8')),
            content_type="application/json"
        )

        redis_client.hset(f"page:{task_id}:{page_index}", "ocr_path", ocr_path)
        redis_client.hset(f"page:{task_id}:{page_index}", "ocr_status", "completed")

        # current_status = redis_client.hget(f"page:{task_id}:{page_index}", "status")
        # current_status = current_status.decode() if isinstance(current_status, bytes) else current_status

        # print(f"[OCR Worker] Page {page_index} current status: {current_status}")
        # if current_status == "segmented":
        #     print(f"[OCR Worker] Segmentation ready, triggering MERGE...")
        #     from services.merge.worker import merge_with_placeholders
        #     merge_with_placeholders.delay(task_id, page_index)
        #     print(f"[OCR Worker] MERGE triggered for page {page_index}")
        # else:
        #     redis_client.hset(f"page:{task_id}:{page_index}", "status", "ocr_ready")
        #     print(f"[OCR Worker] Page {page_index} set to ocr_ready")
        current_status = redis_client.hget(f"page:{task_id}:{page_index}", "status")
        current_status = current_status.decode() if isinstance(current_status, bytes) else current_status

        if current_status == "segmented":
            # from services.merge.worker import try_acquire_merge_lock, merge_with_placeholders

            # if try_acquire_merge_lock(task_id, page_index):
            #     print(f"[OCR] Acquired merge lock for {task_id}:{page_index}")
            #     merge_with_placeholders.delay(task_id, page_index)
            from shared.merge.lock_utils import try_acquire_merge_lock, release_merge_lock
            if try_acquire_merge_lock(redis_client, task_id, page_index):
                print(f"[OCR] Acquired merge lock for {task_id}:{page_index}")
                start_merge_task(task_id, page_index)
            else:
                print(f"[OCR] Merge already scheduled for {task_id}:{page_index}")
        duration = time.time() - start_time
        metrics.ocr_time.labels(task_id=task_id, page_index=str(page_index)).observe(duration)
        pages_processed.labels(worker_type='ocr', status='success').inc()
        push_metrics_to_gateway('ocr-worker', task_id, page_index)
        redis_client.hset(f"page:{task_id}:{page_index}", "ocr_time_ms", int(duration * 1000))
        return {
            "task_id": task_id,
            "page_index": page_index,
            "status": "ocr_completed",
            "used_fallback": is_fallback,
            "ocr_time_s": round(duration, 2)
        }

    except Exception as e:
        pages_processed.labels(worker_type='ocr', status='failed').inc()
        push_metrics_to_gateway('ocr-worker', task_id, page_index)
        error_counter.labels(worker_type='ocr', error_type=type(e).__name__).inc()
        print(f"[OCR Worker] Error processing page {page_index}: {e}")
        import traceback
        traceback.print_exc()

        if self.request.retries < self.max_retries:
            print(f"[OCR Worker] Retrying... (attempt {self.request.retries + 1}/{self.max_retries})")
            raise self.retry(exc=e, countdown=5, max_retries=self.max_retries)

        print(f"[OCR Worker] Max retries reached, creating fallback")

        fallback_result = None
        fallback_path = "/app/services/ocr/fallback.json"

        if os.path.exists(fallback_path):
            try:
                with open(fallback_path, "r", encoding="utf-8") as f:
                    fallback_result = json.load(f)
                print(f"[OCR Worker] Loaded fallback from {fallback_path}")
            except Exception as fe:
                print(f"[OCR Worker] Error loading fallback file: {fe}")

        if not fallback_result:
            fallback_result = {
                "node": {
                    "@type": "RIL_PAGE",
                    "@W": "2120",
                    "@H": "3000",
                    "node": [
                        {
                            "@type": "RIL_TEXT",
                            "node": [
                                {
                                    "@type": "RIL_TEXTLINE",
                                    "@X": "100",
                                    "@Y": "100",
                                    "@W": "1000",
                                    "@H": "50",
                                    "node": [
                                        {
                                            "@type": "RIL_WORD",
                                            "@X": "100",
                                            "@Y": "100",
                                            "@W": "800",
                                            "@H": "50",
                                            "#text": f"OCR fallback for page {page_index}"
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            }

        ocr_json = json.dumps(fallback_result, ensure_ascii=False, indent=2)
        ocr_path = f"{task_id}/{page_index}/ocr.json"

        print(f"[OCR Worker] Saving fallback result to MinIO: {ocr_path}")
        minio_client.put_object(
            BUCKET_OCR,
            ocr_path,
            io.BytesIO(ocr_json.encode('utf-8')),
            len(ocr_json.encode('utf-8')),
            content_type="application/json"
        )

        redis_client.hset(f"page:{task_id}:{page_index}", "ocr_path", ocr_path)
        redis_client.hset(f"page:{task_id}:{page_index}", "ocr_status", "completed")

        current_status = redis_client.hget(f"page:{task_id}:{page_index}", "status")
        current_status = current_status.decode() if isinstance(current_status, bytes) else current_status

        if current_status == "segmented":
            # from services.merge.worker import try_acquire_merge_lock, merge_with_placeholders

            # if try_acquire_merge_lock(task_id, page_index):
            #     print(f"[OCR]  Acquired merge lock for {task_id}:{page_index}")
            #     try:
            #         result = merge_with_placeholders.delay(task_id, page_index)
            #         print(f"[OCR]  merge task submitted, id: {result.id}")
            #     except Exception as e:
            #         print(f"[OCR]  Failed to submit merge: {e}")
            #         from services.merge.worker import release_merge_lock
            #         release_merge_lock(task_id, page_index)
            # else:
            #     print(f"[OCR] Merge lock already held for {task_id}:{page_index}")
            if current_status == "segmented":
                if try_acquire_merge_lock(redis_client, task_id, page_index):
                    print(f"[OCR] Acquired merge lock for {task_id}:{page_index}")
                    start_merge_task(task_id, page_index)
                else:
                    print(f"[OCR] Merge already scheduled")
        return {
            "task_id": task_id,
            "page_index": page_index,
            "status": "ocr_completed_with_fallback"
        }


if __name__ == '__main__':
    import time
    print('OCR worker started')
    while True:
        time.sleep(60)
