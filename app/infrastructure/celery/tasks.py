import asyncio
import pickle
from celery import Celery
from app.infrastructure.redis_client import redis_client
from app.infrastructure.providers import create_formula_service
from app.core.config import REDIS_URL

app = Celery('pipeline', broker=REDIS_URL)

app.conf.task_queues = {
    'formula': {'exchange': 'formula', 'routing_key': 'formula'},
    'merge': {'exchange': 'merge', 'routing_key': 'merge'},
}

_formula_service = None

def get_formula_service():
    global _formula_service
    if _formula_service is None:
        _formula_service = create_formula_service()
    return _formula_service

@app.task(queue='formula', bind=True, max_retries=3)
def process_formulas_only(self, image_bytes: bytes, page_index: int, task_id: str):
    try:
        formula_service = get_formula_service()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        formulas, size = loop.run_until_complete(
            formula_service.process_batch([image_bytes])
        )
        loop.close()

        redis_client.hset(f"task:{task_id}:formulas", page_index, pickle.dumps(formulas[0]))
        redis_client.hset(f"task:{task_id}:sizes", page_index, pickle.dumps(size[0]))

        total = int(redis_client.hget(f"task:{task_id}", "total_pages"))
        current = redis_client.hincrby(f"task:{task_id}", "formulas_done", 1)

        print(f"[Worker] Страница {page_index+1}/{total} обработана. Готово: {current}/{total}")

        if current == total:
            print(f"[Worker] Все страницы готовы! Запускаем мердж...")
            merge_all_pages.delay(task_id)

        return {"page": page_index, "status": "done"}

    except Exception as e:
        print(f"[Worker] Ошибка на странице {page_index}: {e}")
        raise self.retry(exc=e, countdown=5)

@app.task(queue='merge')
def merge_all_pages(task_id: str):
    from PyPDF2 import PdfReader, PdfWriter
    from app.infrastructure.merge.ocr_json_normalizer import ocr_json_to_page
    from app.infrastructure.merge.formulas_normalizer import normalize_formulas
    from app.infrastructure.merge.merge_jsons import merge
    from app.infrastructure.pdf.serializer import render_page_to_pdf
    from app.infrastructure.merge.coordinate_normalizer import rescale_formulas
    import io

    print(f"[Merge] Начинаем сборку PDF для задачи {task_id}")

    writer = PdfWriter()
    total = int(redis_client.hget(f"task:{task_id}", "total_pages"))

    for i in range(total):
        ocr = pickle.loads(redis_client.hget(f"task:{task_id}:ocr", i))
        formulas = pickle.loads(redis_client.hget(f"task:{task_id}:formulas", i))
        size = pickle.loads(redis_client.hget(f"task:{task_id}:sizes", i))

        page = ocr_json_to_page(ocr)
        formulas_scaled = rescale_formulas(formulas, size, (page.width, page.height))
        formulas_domain = normalize_formulas(formulas_scaled)
        merged_page = merge(page, formulas_domain)
        pdf_bytes = render_page_to_pdf(merged_page)

        reader = PdfReader(io.BytesIO(pdf_bytes))
        for p in reader.pages:
            writer.add_page(p)

        print(f"[Merge] Страница {i+1}/{total} добавлена")

    output = io.BytesIO()
    writer.write(output)
    output.seek(0)
    redis_client.setex(f"task:{task_id}:result", 3600, output.read())
    redis_client.hset(f"task:{task_id}", "status", "completed")

    print(f"[Merge] PDF готов для задачи {task_id}")
