import sys
import os
import pickle
import json
import io
import time
from pathlib import Path
from typing import List, Dict
import uuid
import asyncio
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from shared.infrastructure.redis_client import create_redis_client
from shared.infrastructure.minio_client import create_minio_client
from shared.merge.optimized_parser import OptimizedPageParser
from shared.merge.smart_mergerv2 import SpatialIndex, TreeMerger, FormulaNodeBuilder
from shared.merge.tree_utils import get_node_path
from shared.metrics.production_metrics import metrics
from services.celery_app import celery_app
BUCKET_OCR = "ocr-results"
BUCKET_TREES = "merged-trees"
BUCKET_MASKS = "formula-masks"

redis_url = os.environ.get('REDIS_URL', 'redis://redis:6379/0')
minio_endpoint = os.environ.get('MINIO_ENDPOINT', 'minio:9000')
minio_access = os.environ.get('MINIO_ACCESS_KEY', 'minioadmin')
minio_secret = os.environ.get('MINIO_SECRET_KEY', 'minioadmin')

redis_client = create_redis_client(redis_url)
minio_client = create_minio_client(minio_endpoint, minio_access, minio_secret)
from shared.merge.lock_utils import try_acquire_merge_lock, release_merge_lock, check_lock_owner

def check_and_update_task_status(task_id: str):
    total_pages = int(redis_client.hget(f"task:{task_id}", "total_pages") or 1)
    all_completed = True

    for i in range(total_pages):
        page_status = redis_client.hget(f"page:{task_id}:{i}", "status")
        if page_status not in (b"completed", b"merged"):
            all_completed = False
            break

    if all_completed:
        redis_client.hset(f"task:{task_id}", "status", "completed")
        redis_client.hset(f"task:{task_id}", "completed_at", str(time.time()))
        print(f"[Merge] Task {task_id} marked as completed")

        metrics.save_task_completion_sync(task_id, redis_client)
        return True
    return False





@celery_app.task(queue='merge', bind=True, max_retries=3)
def merge_with_placeholders(self, task_id: str, page_index: int):
    with metrics.measure("merge_total", task_id, page_index, worker_type="merge"):
        if not check_lock_owner(redis_client, task_id, page_index):
            print(f"[Merge] No valid lock for {task_id}:{page_index}, skipping")
            return {"status": "no_lock"}

        print(f"[Merge] Lock verified, starting merge for {task_id}:{page_index}")

        lock_owner = redis_client.hget(f"page:{task_id}:{page_index}", "merge_lock_owner")

        try:
            status = redis_client.hget(f"page:{task_id}:{page_index}", "status")
            if status == b"merged":
                print(f"[Merge] Already merged, skipping")
                return {"status": "already_merged"}

            with metrics.measure("merge_load_ocr", task_id, page_index, worker_type="merge"):
                ocr_path = f"{task_id}/{page_index}/ocr.json"
                ocr_data = minio_client.get_object(BUCKET_OCR, ocr_path)
                ocr_json = json.loads(ocr_data.read())
                ocr_data.close()
                print(f"[Merge] OCR loaded from {ocr_path}")

            with metrics.measure("merge_parse_ocr", task_id, page_index, worker_type="merge"):
                parser = OptimizedPageParser()
                tree, width, height = parser.parse(ocr_json)
                print(f"[Merge] Tree parsed: {width}x{height}")

            with metrics.measure("merge_load_formulas", task_id, page_index, worker_type="merge"):
                formula_ids_key = f"page_formulas:{task_id}:{page_index}"
                formula_ids = redis_client.smembers(formula_ids_key)
                print(f"[Merge] Found {len(formula_ids)} formula IDs in Set")

                formulas_data = []
                for formula_id_bytes in formula_ids:
                    formula_id = int(formula_id_bytes)
                    key = f"formula:{task_id}:{page_index}:{formula_id}"

                    if not redis_client.exists(key):
                        print(f"[Merge] Warning: Formula key {key} not found, skipping")
                        continue

                    bbox = (
                        int(redis_client.hget(key, "bbox_x1") or 0),
                        int(redis_client.hget(key, "bbox_y1") or 0),
                        int(redis_client.hget(key, "bbox_x2") or 0),
                        int(redis_client.hget(key, "bbox_y2") or 0)
                    )
                    latex = redis_client.hget(key, "latex")
                    status = redis_client.hget(key, "status")

                    formulas_data.append({
                        "id": formula_id,
                        "bbox": bbox,
                        "latex": latex.decode() if latex else None,
                        "status": status.decode() if status else "segmented"
                    })

                formulas_data.sort(key=lambda f: f["id"])
                print(f"[Merge] Loaded {len(formulas_data)} formulas")

                if not formulas_data:
                    print(f"[Merge] No formulas found for {task_id}:{page_index}")
                    return {"status": "no_formulas"}

            with metrics.measure("merge_execute", task_id, page_index, worker_type="merge"):
                merger = TreeMerger(use_adaptive_index=True)
                placeholder_count = 0

                for f in formulas_data:
                    mask_path = redis_client.hget(f"formula:{task_id}:{page_index}:{f['id']}", "mask_path")
                    mask = None
                    if mask_path:
                        mask_path_str = mask_path.decode() if isinstance(mask_path, bytes) else mask_path
                        mask_data = minio_client.get_object(BUCKET_MASKS, mask_path_str)
                        mask_bytes = mask_data.read()
                        mask_data.close()
                        import numpy as np
                        import io
                        mask = np.load(io.BytesIO(mask_bytes), allow_pickle=True)

                    if f["latex"]:
                        formula_node = FormulaNodeBuilder.create_node(
                            f["id"], f["bbox"], latex=f["latex"], recognition_status="completed"
                        )
                    else:
                        placeholder_latex = f"[FORMULA_{f['id']}_PENDING]"
                        formula_node = FormulaNodeBuilder.create_node(
                            f["id"], f["bbox"], latex=placeholder_latex, recognition_status="pending"
                        )
                        placeholder_count += 1

                    merger._merge_one_formula(tree, formula_node, mask, use_mask=True)

                    if not f["latex"]:
                        path = get_node_path(tree, formula_node)
                        if path:
                            redis_client.hset(f"formula:{task_id}:{page_index}:{f['id']}",
                                             "placeholder_path", json.dumps(path))

                merger._sort_tree(tree)
                print(f"[Merge] Merge completed, placeholders: {placeholder_count}")

            with metrics.measure("merge_save_tree", task_id, page_index, worker_type="merge"):
                tree_bytes = pickle.dumps(tree)
                tree_path = f"{task_id}/{page_index}/tree_with_placeholders.pkl"
                minio_client.put_object(BUCKET_TREES, tree_path, io.BytesIO(tree_bytes), len(tree_bytes))

                redis_client.hset(f"page:{task_id}:{page_index}", "tree_path", tree_path)

                if placeholder_count == 0:
                    redis_client.hset(f"page:{task_id}:{page_index}", "status", "completed")
                else:
                    redis_client.hset(f"page:{task_id}:{page_index}", "status", "merged")

                print(f"[Merge] Tree saved to {tree_path}")


            metrics.gauge("placeholders_count", placeholder_count, task_id)
            metrics.increment_counter("formulas_total", task_id, len(formulas_data))


            ready_formulas = [f["id"] for f in formulas_data if f["latex"]]
            if ready_formulas:
                print(f"[Merge] Triggering update for {len(ready_formulas)} ready formulas")
                from services.task_starter import start_update_task
                start_update_task(task_id, page_index, ready_formulas)

            check_and_update_task_status(task_id)

            print(f"[Merge] Successfully completed for {task_id}:{page_index}")
            return {"task_id": task_id, "page_index": page_index, "formulas": len(formulas_data)}

        except Exception as e:

            redis_client.hset(f"page:{task_id}:{page_index}", "status", "merge_failed")

            metrics.save_error_sync(task_id, "merge", str(e), page_index, "error")
            print(f"[Merge] Error for task {task_id}, page {page_index}: {e}")
            import traceback
            traceback.print_exc()
            raise e
        finally:
            release_merge_lock(redis_client, task_id, page_index)
            print(f"[Merge] Released lock for {task_id}:{page_index}")
