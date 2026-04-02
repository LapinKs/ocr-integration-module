import uuid
import pickle
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from typing import List
import io
from PyPDF2 import PdfReader, PdfWriter

from app.infrastructure.ocr.client import OCRClient
from app.infrastructure.redis_client import redis_client
from app.infrastructure.celery.tasks import process_formulas_only
from app.core.config import OCR_API_KEY, OCR_BASE_URL

router = APIRouter()

ocr_service = OCRClient(
    api_key=OCR_API_KEY,
    base_url=OCR_BASE_URL,
    fallback_json_path=None
)

@router.post("/process")
async def process_images(files: List[UploadFile]):
    task_id = str(uuid.uuid4())
    images = [await file.read() for file in files]

    redis_client.hset(f"task:{task_id}", "total_pages", len(images))
    redis_client.hset(f"task:{task_id}", "formulas_done", 0)
    redis_client.hset(f"task:{task_id}", "status", "pending")

    print(f"[API] Отправляем {len(images)} страниц в OCR API...")
    ocr_results = await ocr_service.recognize_many(images)
    print(f"[API] OCR API вернул {len(ocr_results)} результатов")

    for i, ocr_result in enumerate(ocr_results):
        redis_client.hset(f"task:{task_id}:ocr", i, pickle.dumps(ocr_result))

    for i, img_bytes in enumerate(images):
        process_formulas_only.delay(img_bytes, i, task_id)

    return {"task_id": task_id, "total_pages": len(images)}

@router.get("/task/{task_id}/status")
async def get_status(task_id: str):
    total = redis_client.hget(f"task:{task_id}", "total_pages")
    if total is None:
        raise HTTPException(404, "Task not found")

    formulas_done = redis_client.hget(f"task:{task_id}", "formulas_done") or 0
    status = redis_client.hget(f"task:{task_id}", "status") or b"pending"

    return {
        "task_id": task_id,
        "pages_done": int(formulas_done),
        "total_pages": int(total),
        "status": status.decode()
    }

@router.get("/task/{task_id}/result")
async def get_result(task_id: str):
    status = redis_client.hget(f"task:{task_id}", "status")
    if status != b"completed":
        raise HTTPException(404, "Result not ready yet")

    pdf_bytes = redis_client.get(f"task:{task_id}:result")
    if not pdf_bytes:
        raise HTTPException(404, "Result not found")

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=result_{task_id}.pdf"}
    )
