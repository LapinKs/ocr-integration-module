#!/usr/bin/env python3
import sys
import os
import io
import json
import base64
import asyncio
from pathlib import Path
from celery import Celery
import httpx

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.infrastructure.redis_client import redis_client
from shared.infrastructure.minio_client import minio_client

BUCKET_OCR = "ocr-results"
BUCKET_IMAGES = "source-images"

app = Celery('ocr', broker=os.environ.get('REDIS_URL', 'redis://redis:6379/0'))

# Конфигурация OCR API
OCR_API_KEY = os.environ.get('OCR_API_KEY', '')
OCR_BASE_URL = os.environ.get('OCR_BASE_URL', 'https://api.ocr.space/parse/image')

async def call_ocr_api(image_bytes: bytes) -> dict:
    """Вызов внешнего OCR API"""
    # Кодируем изображение в base64
    image_b64 = base64.b64encode(image_bytes).decode()

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            OCR_BASE_URL,
            data={
                'apikey': OCR_API_KEY,
                'base64Image': f'data:image/jpeg;base64,{image_b64}',
                'language': 'rus',
                'isTable': 'true'
            }
        )
        result = response.json()

        if result.get('IsErroredOnProcessing'):
            raise Exception(f"OCR Error: {result.get('ErrorMessage')}")

        # Конвертируем результат в нужный формат
        return convert_ocr_result(result)

def convert_ocr_result(api_result: dict) -> dict:
    """Конвертирует результат OCR API в формат RIL_PAGE"""
    # Создаём базовую структуру RIL_PAGE
    page_node = {
        "@type": "RIL_PAGE",
        "@W": "0",
        "@H": "0",
        "node": []
    }

    # Парсим текст из результата
    if 'ParsedResults' in api_result:
        for parsed in api_result['ParsedResults']:
            text = parsed.get('ParsedText', '')
            # Создаём простую структуру из текста
            if text:
                page_node["node"].append({
                    "@type": "RIL_TEXT",
                    "@X": "0",
                    "@Y": "0",
                    "@W": "0",
                    "@H": "0",
                    "node": [{
                        "@type": "RIL_TEXTLINE",
                        "@X": "0",
                        "@Y": "0",
                        "@W": "0",
                        "@H": "0",
                        "node": [{
                            "@type": "RIL_WORD",
                            "@X": "0",
                            "@Y": "0",
                            "@W": "0",
                            "@H": "0",
                            "#text": text
                        }]
                    }]
                })

    return {"node": page_node}

@app.task(queue='ocr', bind=True, max_retries=3)
def process_ocr(self, task_id: str, page_index: int, image_bytes: bytes):
    """Обработка OCR для страницы"""
    try:
        # Вызываем OCR API
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        ocr_result = loop.run_until_complete(call_ocr_api(image_bytes))
        loop.close()

        # Сохраняем результат в MinIO
        ocr_json = json.dumps(ocr_result)
        ocr_path = f"{task_id}/{page_index}/ocr.json"
        minio_client.put_object(
            BUCKET_OCR,
            ocr_path,
            io.BytesIO(ocr_json.encode()),
            len(ocr_json),
            content_type="application/json"
        )

        # Обновляем статус в Redis
        redis_client.hset(f"page:{task_id}:{page_index}", "ocr_path", ocr_path)
        redis_client.hset(f"page:{task_id}:{page_index}", "status", "ocr_ready")

        # Проверяем, можно ли запускать MERGE
        page_status = redis_client.hget(f"page:{task_id}:{page_index}", "status")
        if page_status == b"segmented":
            from services.merge.worker import merge_with_placeholders
            merge_with_placeholders.delay(task_id, page_index)

        return {"task_id": task_id, "page_index": page_index, "status": "ocr_completed"}

    except Exception as e:
        raise self.retry(exc=e, countdown=10, max_retries=3)

# Для тестирования
if __name__ == '__main__':
    print('OCR worker started')
    while True:
        time.sleep(60)
