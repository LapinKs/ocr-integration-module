import uuid
import io
import os
import json
import sys
from pathlib import Path
from typing import List, Tuple, Optional, Union
import httpx
from datetime import datetime, timedelta

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from shared.infrastructure.redis_client import create_redis_client
from shared.infrastructure.minio_client import create_minio_client
from shared.database.sqlite_client import get_sqlite_client
from services.task_starter import start_segmentation_task, start_ocr_task

router = APIRouter()

redis_url = os.environ.get('REDIS_URL', 'redis://redis:6379/0')
minio_endpoint = os.environ.get('MINIO_ENDPOINT', 'minio:9000')
minio_access = os.environ.get('MINIO_ACCESS_KEY', 'minioadmin')
minio_secret = os.environ.get('MINIO_SECRET_KEY', 'minioadmin')

redis_client = create_redis_client(redis_url)
minio_client = create_minio_client(minio_endpoint, minio_access, minio_secret)

BUCKET_IMAGES = "source-images"
BUCKET_PDFS = "result-pdfs"

REQUIRED_BUCKETS = ["source-images", "formula-masks", "ocr-results", "merged-trees", "result-pdfs"]


def ensure_buckets():
    for bucket in REQUIRED_BUCKETS:
        if not minio_client.bucket_exists(bucket):
            minio_client.make_bucket(bucket)
            print(f"Created bucket: {bucket}")

ensure_buckets()


async def get_task_status(task_id: str) -> Tuple[bool, Optional[dict], Optional[int]]:

    total = redis_client.hget(f"task:{task_id}", "total_pages")
    if total is None:
        raise HTTPException(404, f"Task {task_id} not found")

    total_pages = int(total)
    status = redis_client.hget(f"task:{task_id}", "status")
    status_str = status.decode() if isinstance(status, bytes) else "pending"


    if status_str == "completed":
        return True, None, total_pages

    pages_completed = 0
    pages_status = []

    for i in range(total_pages):
        page_status = redis_client.hget(f"page:{task_id}:{i}", "status") or b"pending"
        page_status_str = page_status.decode() if isinstance(page_status, bytes) else page_status
        pages_status.append({"page": i, "status": page_status_str})
        if page_status_str in ["completed", "merged"]:
            pages_completed += 1

    status_info = {
        "task_id": task_id,
        "status": "pending",
        "total_pages": total_pages,
        "pages_completed": pages_completed,
        "pages": pages_status,
        "message": "Task is still processing. Please check again later."
    }

    return False, status_info, total_pages


@router.post("/process")
async def process_images(
    files: List[UploadFile] = File(..., description="Список изображений (JPG, PNG)")
):
    task_id = str(uuid.uuid4())
    total_pages = len(files)

    db = get_sqlite_client()
    await db.create_task(task_id, total_pages)

    redis_client.hset(f"task:{task_id}", "total_pages", total_pages)
    redis_client.hset(f"task:{task_id}", "status", "pending")
    redis_client.hset(f"task:{task_id}", "created_at", datetime.now().isoformat())

    for i, file in enumerate(files):
        if not file.content_type or not file.content_type.startswith('image/'):
            continue

        content = await file.read()

        image_path = f"{task_id}/{i}/image.jpg"
        minio_client.put_object(
            BUCKET_IMAGES,
            image_path,
            io.BytesIO(content),
            len(content),
            content_type=file.content_type
        )

        redis_client.hset(f"page:{task_id}:{i}", "started_at", datetime.now().isoformat())
        redis_client.hset(f"page:{task_id}:{i}", "status", "pending")

        start_segmentation_task(task_id, i, content)
        start_ocr_task(task_id, i, content)

    return {
        "task_id": task_id,
        "total_pages": total_pages,
        "status": "pending",
        "message": f"Get result at /result/{task_id}/pdf or /result/{task_id}/json"
    }


@router.get("/result/{task_id}/pdf")
async def get_result_pdf(task_id: str):
    is_ready, status_info, total_pages = await get_task_status(task_id)

    if not is_ready:
        return JSONResponse(
            status_code=200,
            content=status_info
        )

    try:
        pdf_path = f"{task_id}/result.pdf"
        pdf_data = minio_client.get_object(BUCKET_PDFS, pdf_path)
        pdf_bytes = pdf_data.read()
        pdf_data.close()

        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=result_{task_id}.pdf"}
        )
    except Exception:
        from PyPDF2 import PdfWriter, PdfReader

        writer = PdfWriter()
        for i in range(total_pages):
            try:
                page_pdf = minio_client.get_object(BUCKET_PDFS, f"{task_id}/{i}/page.pdf")
                reader = PdfReader(io.BytesIO(page_pdf.read()))
                for page in reader.pages:
                    writer.add_page(page)
                page_pdf.close()
            except:
                continue

        output = io.BytesIO()
        writer.write(output)
        output.seek(0)

        return StreamingResponse(
            io.BytesIO(output.getvalue()),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=result_{task_id}.pdf"}
        )


@router.get("/result/{task_id}/json")
async def get_result_json(task_id: str):
    is_ready, status_info, _ = await get_task_status(task_id)

    if not is_ready:
        return JSONResponse(
            status_code=202,
            content=status_info
        )

    try:
        json_path = f"{task_id}/result.json"
        json_data = minio_client.get_object(BUCKET_PDFS, json_path)
        json_bytes = json_data.read()
        json_data.close()

        return StreamingResponse(
            io.BytesIO(json_bytes),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=result_{task_id}.json"}
        )
    except Exception as e:
        raise HTTPException(404, f"JSON result not found: {e}")


@router.get("/health")
async def health_check():
    checks = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "components": {}
    }

    try:
        redis_client.ping()
        checks["components"]["redis"] = {"status": "up"}
    except Exception as e:
        checks["components"]["redis"] = {"status": "down", "error": str(e)}
        checks["status"] = "degraded"

    try:
        minio_client.bucket_exists(BUCKET_IMAGES)
        checks["components"]["minio"] = {"status": "up"}
    except Exception as e:
        checks["components"]["minio"] = {"status": "down", "error": str(e)}
        checks["status"] = "degraded"

    try:
        db = get_sqlite_client()
        await db.health_check()
        checks["components"]["sqlite"] = {"status": "up"}
    except Exception as e:
        checks["components"]["sqlite"] = {"status": "down", "error": str(e)}
        checks["status"] = "degraded"

    return checks


@router.get("/statistics")
async def get_statistics(
    task_id: Optional[str] = None,
    hours: int = 168
):

    result = {
        "generated_at": datetime.now().isoformat(),
        "pages": []
    }

    prometheus_url = "http://prometheus:9090"

    label_filter = f'{{task_id="{task_id}"}}' if task_id else ""

    metric_queries = {
        "segmentation_time": f'segmentation_time_seconds{label_filter}',
        "recognition_time": f'recognition_time_seconds{label_filter}',
        "ocr_time": f'ocr_time_seconds{label_filter}',
        "merge_time": f'merge_time_seconds{label_filter}',
        "pdf_time": f'pdf_time_seconds{label_filter}',
        "formulas_found": f'segmentation_formulas_found{label_filter}',
        "formulas_recognized": f'recognition_formulas_processed{label_filter}',
    }

    pages_dict = {}

    async with httpx.AsyncClient(timeout=30.0) as client:
        for metric_name, query in metric_queries.items():
            try:
                end_time = datetime.now()
                start_time = end_time - timedelta(hours=hours)

                response = await client.get(
                    f"{prometheus_url}/api/v1/query_range",
                    params={
                        "query": query,
                        "start": start_time.isoformat(),
                        "end": end_time.isoformat(),
                        "step": "3600s"
                    },
                    timeout=30.0
                )

                if response.status_code == 200:
                    data = response.json()
                    if data.get("status") == "success":
                        for result_item in data.get("data", {}).get("result", []):
                            metric = result_item.get("metric", {})
                            tid = metric.get("task_id")
                            page_idx = metric.get("page_index")

                            if not tid or page_idx is None:
                                continue

                            key = f"{tid}:{page_idx}"
                            if key not in pages_dict:
                                pages_dict[key] = {
                                    "task_id": tid,
                                    "page_index": int(page_idx),
                                    "segmentation_time": None,
                                    "recognition_time": None,
                                    "ocr_time": None,
                                    "merge_time": None,
                                    "pdf_time": None,
                                    "formulas_found": None,
                                    "formulas_recognized": None
                                }

                            values = result_item.get("values", [])
                            if values:
                                last_value = float(values[-1][1]) if len(values[-1]) > 1 else None
                                if last_value is not None:
                                    pages_dict[key][metric_name] = round(last_value, 3)

            except Exception as e:
                print(f"[Statistics] Prometheus error for {metric_name}: {e}")

    pages = list(pages_dict.values())
    pages.sort(key=lambda x: (x["task_id"], x["page_index"]), reverse=True)

    result["pages"] = pages[:500]

    return result
