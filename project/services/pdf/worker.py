import sys
import os
import io
import pickle
import asyncio
import json
import time
from pathlib import Path
from typing import List
from shared.infrastructure.redis_client import create_redis_client
from shared.infrastructure.minio_client import create_minio_client
from .main_render import render_page_to_pdf
from services.celery_app import celery_app
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from shared.database.sqlite_client import get_sqlite_client
BUCKET_TREES = "merged-trees"
BUCKET_PDFS = "result-pdfs"
redis_url = os.environ.get('REDIS_URL', 'redis://redis:6379/0')
minio_endpoint = os.environ.get('MINIO_ENDPOINT', 'minio:9000')
minio_access = os.environ.get('MINIO_ACCESS_KEY', 'minioadmin')
minio_secret = os.environ.get('MINIO_SECRET_KEY', 'minioadmin')
redis_client = create_redis_client(redis_url)
minio_client = create_minio_client(minio_endpoint, minio_access, minio_secret)

from shared.metrics.production_metrics import (
    metrics, push_metrics_to_gateway,pdf_time, pages_processed, error_counter
)
@celery_app.task(queue='pdf', bind=True, max_retries=3)
def generate_pdf(self, task_id: str, page_index: int):
    start_time = time.time()
    with metrics.measure("pdf_total", task_id, page_index, worker_type="pdf"):
        try:
            tree_path_bytes = redis_client.hget(f"page:{task_id}:{page_index}", "tree_path")
            if not tree_path_bytes:
                return {"status": "tree_not_found"}

            tree_path = tree_path_bytes.decode()
            tree_data = minio_client.get_object(BUCKET_TREES, tree_path)
            tree = pickle.loads(tree_data.read())
            tree_data.close()

            width = int(redis_client.hget(f"page:{task_id}:{page_index}", "width") or 2120)
            height = int(redis_client.hget(f"page:{task_id}:{page_index}", "height") or 3000)

            with metrics.measure("pdf_render", task_id, page_index, worker_type="pdf"):
                pdf_bytes = render_page_to_pdf(tree, width, height)

            pdf_path = f"{task_id}/{page_index}/page_{int(time.time())}.pdf"
            minio_client.put_object(
                BUCKET_PDFS,
                pdf_path,
                io.BytesIO(pdf_bytes),
                len(pdf_bytes),
                content_type="application/pdf"
            )

            redis_client.hset(f"page:{task_id}:{page_index}", "pdf_path", pdf_path)
            check_and_assemble_document(task_id)
            duration = time.time() - start_time
            pdf_time.labels(task_id=task_id, page_index=str(page_index)).observe(duration)
            pages_processed.labels(worker_type='pdf', status='success').inc()
            push_metrics_to_gateway('pdf-worker', task_id, page_index)

            return {"task_id": task_id, "page_index": page_index, "pdf_path": pdf_path, "pdf_time_s": round(duration, 2)}

        except Exception as e:
            pages_processed.labels(worker_type='pdf', status='failed').inc()
            push_metrics_to_gateway('pdf-worker', task_id, page_index)
            # import asyncio
            # asyncio.create_task(metrics.save_error(task_id, "pdf", str(e), page_index, "error"))
            metrics.save_error_sync(task_id, "pdf", str(e), page_index, "error")
            raise self.retry(exc=e, countdown=10, max_retries=3)




async def check_and_assemble_document(task_id: str):
    total_pages = int(redis_client.hget(f"task:{task_id}", "total_pages") or 0)
    all_pages_ready = True
    for i in range(total_pages):
        pdf_path = redis_client.hget(f"page:{task_id}:{i}", "pdf_path")
        if not pdf_path:
            all_pages_ready = False
            break

    if not all_pages_ready:
        return

    print(f"[PDF] All {total_pages} pages ready for task {task_id}, assembling...")

    async def update_sqlite():
        db = get_sqlite_client()
        await db.update_task_result(task_id, f"{task_id}/result.pdf", f"{task_id}/result.json")

    result_pdf_path = assemble_pdf(task_id, total_pages)
    result_json_path = assemble_json(task_id, total_pages)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(update_sqlite())
    loop.close()

    redis_client.hset(f"task:{task_id}", "status", "completed")
    redis_client.hset(f"task:{task_id}", "completed_at", str(time.time()))

    print(f"[PDF] Document assembly completed for task {task_id}")

def assemble_pdf(task_id: str, total_pages: int):
    from PyPDF2 import PdfWriter, PdfReader
    writer = PdfWriter()

    for i in range(total_pages):
        pdf_path_bytes = redis_client.hget(f"page:{task_id}:{i}", "pdf_path")
        if not pdf_path_bytes:
            continue
        pdf_path = pdf_path_bytes.decode() if isinstance(pdf_path_bytes, bytes) else pdf_path_bytes
        pdf_data = minio_client.get_object(BUCKET_PDFS, pdf_path)
        reader = PdfReader(io.BytesIO(pdf_data.read()))
        for page in reader.pages:
            writer.add_page(page)
        pdf_data.close()
    output = io.BytesIO()
    writer.write(output)
    output.seek(0)

    result_pdf_path = f"{task_id}/result.pdf"
    minio_client.put_object(
        BUCKET_PDFS,
        result_pdf_path,
        output,
        output.getbuffer().nbytes,
        content_type="application/pdf"
    )
    print(f"[PDF] Assembled PDF saved to {result_pdf_path}")


def assemble_json(task_id: str, total_pages: int):
    all_pages_data = []

    for i in range(total_pages):
        tree_path_bytes = redis_client.hget(f"page:{task_id}:{i}", "tree_path")
        if not tree_path_bytes:
            continue

        tree_path = tree_path_bytes.decode() if isinstance(tree_path_bytes, bytes) else tree_path_bytes
        tree_data = minio_client.get_object(BUCKET_TREES, tree_path)
        tree = pickle.loads(tree_data.read())
        tree_data.close()

        page_json = tree.to_dict()

        def convert_bytes_to_str(obj):
            if isinstance(obj, bytes):
                return obj.decode('utf-8', errors='replace')
            elif isinstance(obj, dict):
                return {k: convert_bytes_to_str(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_bytes_to_str(item) for item in obj]
            return obj

        page_json = convert_bytes_to_str(page_json)

        all_pages_data.append({
            "page_index": i,
            "data": page_json
        })

    result_json_path = f"{task_id}/result.json"
    json_data = json.dumps({
        "task_id": task_id,
        "total_pages": total_pages,
        "pages": all_pages_data,
        "created_at": redis_client.hget(f"task:{task_id}", "created_at"),
        "completed_at": str(time.time())
    }, ensure_ascii=False, indent=2)

    minio_client.put_object(
        BUCKET_PDFS,
        result_json_path,
        io.BytesIO(json_data.encode('utf-8')),
        len(json_data.encode('utf-8')),
        content_type="application/json"
    )

    print(f"[PDF] Assembled JSON saved to {result_json_path}")
