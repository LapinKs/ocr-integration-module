FROM python:3.11-slim

WORKDIR /app

# Копируем shared модули
COPY shared/ /app/shared/

# Копируем код воркера
COPY services/merge/worker.py /app/worker.py
COPY services/merge/requirements.txt /app/requirements.txt

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

ENV PYTHONPATH="/app:${PYTHONPATH}"

# Добавляем недостающий импорт io
RUN echo "import io" >> /app/worker.py

CMD ["celery", "-A", "worker", "worker", "-Q", "merge", "--concurrency=1", "--prefetch-multiplier=1"]
