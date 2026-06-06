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
from shared.merge.smart_mergerv2 import TreeMerger, FormulaNodeBuilder
from shared.metrics.production_metrics import metrics
from services.celery_app import celery_app
from shared.metrics.production_metrics import push_metrics_to_gateway
BUCKET_OCR = "ocr-results"
BUCKET_TREES = "merged-trees"
BUCKET_MASKS = "formula-masks"

redis_url = os.environ.get('REDIS_URL', 'redis://redis:6379/0')
minio_endpoint = os.environ.get('MINIO_ENDPOINT', 'minio:9000')
minio_access = os.environ.get('MINIO_ACCESS_KEY', 'minioadmin')
minio_secret = os.environ.get('MINIO_SECRET_KEY', 'minioadmin')

redis_client = create_redis_client(redis_url)
minio_client = create_minio_client(minio_endpoint, minio_access, minio_secret)
from shared.metrics.production_metrics import (
    metrics, push_metrics_to_gateway,
    merge_time,pages_processed,
)

@celery_app.task(queue='merge', bind=True, max_retries=3)
def merge_sync(self, task_id: str, page_index: int):
    start_time = time.time()
    with metrics.measure("merge_total", task_id, page_index, worker_type="merge"):
        try:
            print(f"[Merge] ========== STARTING MERGE ==========")
            print(f"[Merge] task_id: {task_id}, page_index: {page_index}")

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


            formula_ids_key = f"page_formulas:{task_id}:{page_index}"
            formula_ids = redis_client.smembers(formula_ids_key)
            total_formulas = len(formula_ids)
            print(f"[Merge] Total formulas: {total_formulas}")


            print(f"[Merge] Waiting for recognition to complete...")
            recognized_count = 0

            while recognized_count < total_formulas:
                time.sleep(1)
                recognized_count = int(redis_client.hget(f"page:{task_id}:{page_index}", "recognized_count") or 0)
                print(f"[Merge]   Recognized: {recognized_count}/{total_formulas}")

            print(f"[Merge] All formulas recognized! Proceeding with merge...")


            formulas_data = []
            for formula_id_bytes in formula_ids:
                formula_id = int(formula_id_bytes)
                key = f"formula:{task_id}:{page_index}:{formula_id}"

                bbox = (
                    int(redis_client.hget(key, "bbox_x1") or 0),
                    int(redis_client.hget(key, "bbox_y1") or 0),
                    int(redis_client.hget(key, "bbox_x2") or 0),
                    int(redis_client.hget(key, "bbox_y2") or 0)
                )
                latex = redis_client.hget(key, "latex")
                latex_str = latex.decode() if latex else ""


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

                formulas_data.append({
                    "id": formula_id,
                    "bbox": bbox,
                    "latex": latex_str,
                    "mask": mask
                })


            formulas_data.sort(key=lambda f: (f['bbox'][1], f['bbox'][0]))
            print(f"[Merge] Formulas sorted: {len(formulas_data)}")


            with metrics.measure("merge_execute", task_id, page_index, worker_type="merge"):
                merger = TreeMerger(use_adaptive_index=True)

                for f in formulas_data:
                    formula_node = FormulaNodeBuilder.create_node(
                        f["id"], f["bbox"], latex=f["latex"], recognition_status="completed"
                    )
                    merger._merge_one_formula(tree, formula_node, f.get("mask"), use_mask=True)

                merger._sort_tree(tree)
                print(f"[Merge] Merge completed for {len(formulas_data)} formulas")


            with metrics.measure("merge_save_tree", task_id, page_index, worker_type="merge"):
                tree_bytes = pickle.dumps(tree)
                tree_path = f"{task_id}/{page_index}/tree_merged.pkl"
                minio_client.put_object(BUCKET_TREES, tree_path, io.BytesIO(tree_bytes), len(tree_bytes))
                redis_client.hset(f"page:{task_id}:{page_index}", "tree_path", tree_path)
                print(f"[Merge] Tree saved to {tree_path}")


            redis_client.hset(f"page:{task_id}:{page_index}", "status", "completed")
            redis_client.hset(f"page:{task_id}:{page_index}", "completed_at", str(time.time()))

            from services.task_starter import start_pdf_task
            start_pdf_task(task_id, page_index)
            print(f"[Merge] PDF generation triggered")

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
                metrics.save_task_completion_sync(task_id, redis_client)
                print(f"[Merge] Task {task_id} marked as completed")

            print(f"[Merge] ========== MERGE COMPLETED ==========")
            duration = time.time() - start_time
            merge_time.labels(task_id=task_id, page_index=str(page_index)).observe(duration)
            pages_processed.labels(worker_type='merge', status='success').inc()
            push_metrics_to_gateway('merge-worker', task_id, page_index)
            return {
                "task_id": task_id,
                "page_index": page_index,
                "formulas": len(formulas_data),
                "merge_time_s": round(duration, 2)
            }

        except Exception as e:
            print(f"[Merge]  ERROR: {e}")
            import traceback
            traceback.print_exc()
            redis_client.hset(f"page:{task_id}:{page_index}", "status", "merge_failed")
            pages_processed.labels(worker_type='merge', status='failed').inc()
            push_metrics_to_gateway('merge-worker', task_id, page_index)
            metrics.save_error_sync(task_id, "merge", str(e), page_index, "error")
            raise self.retry(exc=e, countdown=10, max_retries=3)
