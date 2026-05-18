import uuid
import io
import json
import os
from pathlib import Path
from typing import List
from datetime import datetime

from fastapi import APIRouter, UploadFile, File, HTTPException, Query, BackgroundTasks
from fastapi.responses import StreamingResponse

# Добавляем путь для импорта shared
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from shared.infrastructure.redis_client import get_redis_client, create_redis_client
from shared.infrastructure.minio_client import get_minio_client, create_minio_client

router = APIRouter()

# Инициализация клиентов (будет вызвано при старте)
redis_client = None
minio_client = None

def init_clients():
    global redis_client, minio_client
    redis_url = os.environ.get('REDIS_URL', 'redis://redis:6379/0')
    minio_endpoint = os.environ.get('MINIO_ENDPOINT', 'minio:9000')
    minio_access = os.environ.get('MINIO_ACCESS_KEY', 'minioadmin')
    minio_secret = os.environ.get('MINIO_SECRET_KEY', 'minioadmin')

    redis_client = create_redis_client(redis_url)
    minio_client = create_minio_client(minio_endpoint, minio_access, minio_secret)

# Вызываем при первом импорте
init_clients()

BUCKET_IMAGES = "source-images"
BUCKET_OCR = "ocr-results"
BUCKET_TREES = "merged-trees"
BUCKET_PDFS = "result-pdfs"


@router.post("/process")
async def process_document(
    files: List[UploadFile] = File(..., description="List of images to process"),
    background_tasks: BackgroundTasks = None
):
    """Запуск асинхронной обработки документов"""
    task_id = str(uuid.uuid4())
    total_pages = len(files)

    # Сохраняем метаданные задачи в Redis
    redis_client.hset(f"task:{task_id}", "total_pages", total_pages)
    redis_client.hset(f"task:{task_id}", "status", "pending")
    redis_client.hset(f"task:{task_id}", "created_at", datetime.now().isoformat())
    redis_client.hset(f"task:{task_id}", "pages_processed", 0)

    # Сохраняем изображения в MinIO и запускаем задачи
    for i, file in enumerate(files):
        content = await file.read()

        # Сохраняем изображение
        image_path = f"{task_id}/{i}/image.jpg"
        minio_client.put_object(
            BUCKET_IMAGES,
            image_path,
            io.BytesIO(content),
            len(content),
            content_type="image/jpeg"
        )

        # Запускаем сегментацию
        from services.segmentation.worker import process_segmentation
        process_segmentation.delay(task_id, i, content)

        # Запускаем OCR (через background task или отдельный worker)
        from services.ocr.worker import process_ocr
        process_ocr.delay(task_id, i, content)

    return {
        "task_id": task_id,
        "total_pages": total_pages,
        "status": "pending",
        "message": "Processing started. Use /task/{task_id}/status to check progress"
    }


@router.get("/task/{task_id}/status")
async def get_task_status(task_id: str):
    """Получение статуса задачи"""
    # Проверяем существование задачи
    total = redis_client.hget(f"task:{task_id}", "total_pages")
    if total is None:
        raise HTTPException(404, f"Task {task_id} not found")

    total_pages = int(total)
    pages_processed = int(redis_client.hget(f"task:{task_id}", "pages_processed") or 0)
    status = redis_client.hget(f"task:{task_id}", "status") or b"pending"

    # Собираем статус по страницам
    pages_status = []
    for i in range(total_pages):
        page_status = redis_client.hget(f"page:{task_id}:{i}", "status") or b"pending"
        page_status_str = page_status.decode() if isinstance(page_status, bytes) else page_status

        pages_status.append({
            "page": i,
            "status": page_status_str
        })

    return {
        "task_id": task_id,
        "status": status.decode() if isinstance(status, bytes) else status,
        "total_pages": total_pages,
        "pages_processed": pages_processed,
        "pages": pages_status,
        "created_at": redis_client.hget(f"task:{task_id}", "created_at")
    }


@router.get("/task/{task_id}/result")
async def get_task_result(task_id: str):
    """Скачивание результата (PDF)"""
    status = redis_client.hget(f"task:{task_id}", "status")
    if status is None:
        raise HTTPException(404, f"Task {task_id} not found")

    status_str = status.decode() if isinstance(status, bytes) else status
    if status_str != "completed":
        raise HTTPException(400, f"Task not completed yet. Current status: {status_str}")

    # Загружаем объединённый PDF или собираем по страницам
    try:
        # Пытаемся загрузить объединённый PDF
        pdf_path = f"{task_id}/result.pdf"
        pdf_data = minio_client.get_object(BUCKET_PDFS, pdf_path)
        pdf_bytes = pdf_data.read()
        pdf_data.close()
    except:
        # Если нет объединённого PDF, собираем постранично
        total_pages = int(redis_client.hget(f"task:{task_id}", "total_pages") or 0)
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
        pdf_bytes = output.getvalue()

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=result_{task_id}.pdf"}
    )


@router.get("/task/{task_id}/pages/{page_index}/pdf")
async def get_page_pdf(task_id: str, page_index: int):
    """Скачивание PDF отдельной страницы"""
    pdf_path = redis_client.hget(f"page:{task_id}:{page_index}", "pdf_path")
    if not pdf_path:
        raise HTTPException(404, f"PDF for page {page_index} not found")

    pdf_path_str = pdf_path.decode() if isinstance(pdf_path, bytes) else pdf_path
    pdf_data = minio_client.get_object(BUCKET_PDFS, pdf_path_str)
    pdf_bytes = pdf_data.read()
    pdf_data.close()

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={task_id}_page_{page_index}.pdf"}
    )


@router.get("/health")
async def health_check():
    """Проверка здоровья сервиса"""
    checks = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "components": {}
    }

    # Проверка Redis
    try:
        redis_client.ping()
        checks["components"]["redis"] = {"status": "up"}
    except Exception as e:
        checks["components"]["redis"] = {"status": "down", "error": str(e)}
        checks["status"] = "degraded"

    # Проверка MinIO
    try:
        minio_client.bucket_exists(BUCKET_IMAGES)
        checks["components"]["minio"] = {"status": "up"}
    except Exception as e:
        checks["components"]["minio"] = {"status": "down", "error": str(e)}
        checks["status"] = "degraded"

    return checks


@router.delete("/task/{task_id}")
async def delete_task(task_id: str):
    """Удаление задачи и всех связанных данных"""
    # Очищаем Redis
    redis_client.delete(f"task:{task_id}")

    # Очищаем MinIO (опционально)
    # minio_client.remove_object(BUCKET_IMAGES, f"{task_id}/")

    return {"status": "deleted", "task_id": task_id}
