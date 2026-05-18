#!/usr/bin/env python3
import sys
import os
import io
import pickle
import time
from pathlib import Path
from celery import Celery

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.infrastructure.redis_client import redis_client
from shared.infrastructure.minio_client import minio_client

# Правильный импорт рендерера
from app.infrastructure.pdf.main_render import render_page_to_pdf

BUCKET_TREES = "merged-trees"
BUCKET_PDFS = "result-pdfs"

app = Celery('pdf', broker=os.environ.get('REDIS_URL', 'redis://redis:6379/0'))

@app.task(queue='pdf', bind=True, max_retries=3)
def generate_pdf(self, task_id: str, page_index: int):
    """Генерация PDF для страницы"""
    try:
        # Получаем путь к дереву
        tree_path_bytes = redis_client.hget(f"page:{task_id}:{page_index}", "tree_path")
        if not tree_path_bytes:
            return {"status": "tree_not_found", "task_id": task_id, "page_index": page_index}

        tree_path = tree_path_bytes.decode()

        # Загружаем дерево из MinIO
        tree_data = minio_client.get_object(BUCKET_TREES, tree_path)
        tree = pickle.loads(tree_data.read())
        tree_data.close()

        # Получаем размеры страницы
        width = int(redis_client.hget(f"page:{task_id}:{page_index}", "width") or 2120)
        height = int(redis_client.hget(f"page:{task_id}:{page_index}", "height") or 3000)

        print(f"[PDF] Page {page_index}: rendering {width}x{height}")

        # Генерируем PDF
        pdf_bytes = render_page_to_pdf(tree, width, height)

        # Сохраняем PDF в MinIO
        pdf_path = f"{task_id}/{page_index}/page_{int(time.time())}.pdf"
        minio_client.put_object(
            BUCKET_PDFS,
            pdf_path,
            io.BytesIO(pdf_bytes),
            len(pdf_bytes),
            content_type="application/pdf"
        )

        # Обновляем путь в Redis
        redis_client.hset(f"page:{task_id}:{page_index}", "pdf_path", pdf_path)
        redis_client.hset(f"page:{task_id}:{page_index}", "pdf_generated_at", str(time.time()))

        print(f"[PDF] Page {page_index}: PDF saved to {pdf_path}")

        return {
            "task_id": task_id,
            "page_index": page_index,
            "pdf_path": pdf_path,
            "size_bytes": len(pdf_bytes)
        }

    except Exception as e:
        raise self.retry(exc=e, countdown=10, max_retries=3)


# Для тестирования (можно убрать)
if __name__ == '__main__':
    print('PDF worker started')
    while True:
        time.sleep(60)
