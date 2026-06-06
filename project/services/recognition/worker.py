

import sys
import os
import io
import time
import cv2
import numpy as np
from pathlib import Path
from typing import List, Dict
from PIL import Image
from shared.metrics.production_metrics import metrics, error_counter
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.infrastructure.redis_client import create_redis_client
from shared.infrastructure.minio_client import create_minio_client
from shared.image_utils import crop_with_mask
from shared.metrics.production_metrics import metrics
from .new_client import FinetunedLatexOCRClient
from services.celery_app import celery_app
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
import concurrent.futures
from shared.metrics.production_metrics import (
    metrics, error_counter, push_metrics_to_gateway,pages_processed,
    recognition_batch_time
)
def recognize_with_timeout(recognizer, crops, timeout_seconds=120):
    if not crops:
        return []

    print(f"[Recognition] Starting recognition with timeout {timeout_seconds}s for {len(crops)} crops")

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(recognizer.recognize_batch, crops)
        try:
            result = future.result(timeout=timeout_seconds)
            print(f"[Recognition] Recognition completed successfully in time")
            return result
        except concurrent.futures.TimeoutError:
            print(f"[Recognition]  RECOGNITION TIMEOUT after {timeout_seconds}s! Waiting for completion anyway...")

            result = future.result()
            print(f"[Recognition] Recognition completed after timeout, got {len(result)} results")
            return result
        except Exception as e:
            print(f"[Recognition] Recognition error: {e}")
            return [""] * len(crops)



@celery_app.on_after_configure.connect
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


@celery_app.task(queue='recognition', bind=True, max_retries=3)
def recognize_batch(self, task_id: str, page_index: int, batch_size: int = 8):
    start_time = time.time()
    with metrics.measure("recognition_total", task_id, page_index, worker_type="recognition"):
        try:
            print(f"[Recognition] ========== STARTING RECOGNITION ==========")
            print(f"[Recognition] task_id: {task_id}, page_index: {page_index}")

            formula_ids_key = f"page_formulas:{task_id}:{page_index}"
            formula_ids = redis_client.smembers(formula_ids_key)
            print(f"[Recognition] Found {len(formula_ids)} formula IDs in Set")

            pending = []
            for formula_id_bytes in formula_ids:
                formula_id = int(formula_id_bytes)
                key = f"formula:{task_id}:{page_index}:{formula_id}"
                status = redis_client.hget(key, "status")
                latex = redis_client.hget(key, "latex")
                if status == b"segmented" and not latex:
                    pending.append((key, formula_id))

            if not pending:
                print(f"[Recognition] No pending formulas, exiting")
                return {"status": "no_pending", "task_id": task_id, "page_index": page_index}

            print(f"[Recognition] Page {page_index}: {len(pending)} formulas to recognize")

            with metrics.measure("recognition_load_image", task_id, page_index):
                image_data = minio_client.get_object(BUCKET_IMAGES, f"{task_id}/{page_index}/image.jpg")
                image_bytes = image_data.read()
                image_data.close()
                nparr = np.frombuffer(image_bytes, np.uint8)
                image_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
                print(f"[Recognition] Image loaded: {image_rgb.shape}")

            results = []
            all_formula_ids = []

            for i in range(0, len(pending), batch_size):
                batch_idx = i // batch_size + 1
                total_batches = (len(pending) + batch_size - 1) // batch_size
                print(f"[Recognition] ========== BATCH {batch_idx}/{total_batches} START ==========")

                batch = pending[i:i+batch_size]
                crops = []
                batch_formulas = []

                for key, formula_id in batch:
                    try:
                        x1 = int(redis_client.hget(key, "bbox_x1"))
                        y1 = int(redis_client.hget(key, "bbox_y1"))
                        x2 = int(redis_client.hget(key, "bbox_x2"))
                        y2 = int(redis_client.hget(key, "bbox_y2"))
                        bbox = (x1, y1, x2, y2)

                        mask_path = redis_client.hget(key, "mask_path")
                        mask = None
                        if mask_path:
                            try:
                                mask_path_str = mask_path.decode() if isinstance(mask_path, bytes) else mask_path
                                mask_data = minio_client.get_object(BUCKET_MASKS, mask_path_str)
                                mask_bytes = mask_data.read()
                                mask_data.close()
                                mask = np.load(io.BytesIO(mask_bytes), allow_pickle=True)
                                print(f"[Recognition] Mask loaded for formula {formula_id}")
                            except Exception as mask_err:
                                print(f"[Recognition] ⚠ Failed to load mask for formula {formula_id}: {mask_err}")
                                mask = None

                        crop_pil = crop_with_mask(image_rgb, bbox, mask)
                        crops.append(crop_pil)
                        batch_formulas.append((key, formula_id))
                    except Exception as prep_err:
                        print(f"[Recognition]  Failed to prepare formula {formula_id}: {prep_err}")
                        batch_formulas.append((key, formula_id))
                        crops.append(None)

                valid_crops = []
                valid_indices = []
                for idx, crop in enumerate(crops):
                    if crop is not None:
                        valid_crops.append(crop)
                        valid_indices.append(idx)
                    else:
                        batch_formulas[idx] = (batch_formulas[idx][0], batch_formulas[idx][1], "")

                batch_start = time.time()
                try:
                    if valid_crops:
                        # batch_latex = recognizer.recognize_batch(valid_crops)
                        batch_latex = recognize_with_timeout(recognizer, valid_crops, timeout_seconds=120)
                        print(f"[Recognition] Batch {batch_idx}: recognized {len(batch_latex)} crops")
                    else:
                        batch_latex = []
                        print(f"[Recognition] Batch {batch_idx}: no valid crops")
                except Exception as batch_err:
                    print(f"[Recognition]  Batch {batch_idx} recognition failed: {batch_err}")
                    import traceback
                    traceback.print_exc()
                    batch_latex = [""] * len(valid_crops)

                batch_time = (time.time() - batch_start) * 1000
                print(f"[Recognition] Batch {batch_idx}: {len(batch)} crops, {batch_time:.0f}ms")
                recognition_batch_time.labels(task_id=task_id).observe(batch_time)

                latex_idx = 0
                for idx, (key, formula_id) in enumerate(batch_formulas):
                    if idx in valid_indices and latex_idx < len(batch_latex):
                        latex = batch_latex[latex_idx]
                        latex_idx += 1
                    else:
                        latex = ""
                    if not latex:
                        print(f"[Recognition] ⚠ Empty latex for formula {formula_id}, keeping as pending")
                        continue
                    redis_client.hset(key, "latex", latex)
                    redis_client.hset(key, "status", "latex_ready")
                    redis_client.hincrby(f"page:{task_id}:{page_index}", "recognized_count", 1)
                    results.append({"formula_id": formula_id, "latex": latex})
                    all_formula_ids.append(formula_id)

                print(f"[Recognition] ========== BATCH {batch_idx}/{total_batches} END ==========")

            metrics.increment_counter("formulas_recognized", task_id, len(results))

            print(f"[Recognition] ========== ALL BATCHES COMPLETED ==========")
            print(f"[Recognition] Total recognized: {len(results)}")
            print(f"[Recognition] all_formula_ids: {all_formula_ids}")

            page_status = redis_client.hget(f"page:{task_id}:{page_index}", "status")
            print(f"[Recognition] page_status from Redis: {page_status}")

            if all_formula_ids:
                print(f"[Recognition]  Calling start_update_task for {len(all_formula_ids)} formulas")
                # from services.task_starter import start_update_task
                print(f"[Recognition]  BEFORE calling start_update_task")
                # start_update_task(task_id, page_index, all_formula_ids)
                print(f"[Recognition]  AFTER calling start_update_task")
                print(f"[Recognition]  start_update_task called")
            else:
                print(f"[Recognition] ⚠ No formulas to update")


            if page_status == b"merged" and len(results) > 0:

                total_formulas = int(redis_client.hget(f"page:{task_id}:{page_index}", "total_formulas") or 0)
                recognized_count = int(redis_client.hget(f"page:{task_id}:{page_index}", "recognized_count") or 0)
                if recognized_count >= total_formulas:
                    print(f"[Recognition] All formulas recognized ({recognized_count}/{total_formulas})")


            print(f"[Recognition] ========== TASK COMPLETED SUCCESSFULLY ==========")
            duration = time.time() - start_time
            metrics.recognition_time.labels(task_id=task_id, page_index=str(page_index)).observe(duration)
            metrics.recognition_formulas_processed.labels(task_id=task_id, page_index=str(page_index)).set(len(results))
            pages_processed.labels(worker_type='recognition', status='success').inc()
            push_metrics_to_gateway('recognition-worker', task_id, page_index)
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
            pages_processed.labels(worker_type='recognition', status='failed').inc()
            push_metrics_to_gateway('recognition-worker', task_id, page_index)
            error_counter.labels(worker_type='recognition', error_type=type(e).__name__).inc()
            print(f"[Recognition]  FATAL ERROR: {e}")
            import traceback
            traceback.print_exc()
            metrics.save_error_sync(task_id, "recognition", str(e), page_index, "error")


            if not all_formula_ids:
                try:
                    formula_ids_key = f"page_formulas:{task_id}:{page_index}"
                    formula_ids = redis_client.smembers(formula_ids_key)
                    all_formula_ids = [int(fid) for fid in formula_ids]
                    print(f"[Recognition] Recovered {len(all_formula_ids)} formula IDs from Redis")
                except Exception as recovery_err:
                    print(f"[Recognition] Failed to recover formula IDs: {recovery_err}")

            if all_formula_ids:
                print(f"[Recognition] FORCING update for {len(all_formula_ids)} formulas despite error")
                # from services.task_starter import start_update_task
                print(f"[Recognition]  BEFORE calling start_update_task")
                # start_update_task(task_id, page_index, all_formula_ids)
                print(f"[Recognition]  AFTER calling start_update_task")

            raise self.retry(exc=e, countdown=10, max_retries=self.max_retries)
