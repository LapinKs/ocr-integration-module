FROM python:3.11-slim

WORKDIR /app

# Копируем shared модули
COPY shared/ /app/shared/

# Копируем код воркера
COPY services/update/worker.py /app/worker.py
COPY services/update/requirements.txt /app/requirements.txt

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Устанавливаем PYTHONPATH
ENV PYTHONPATH="/app:${PYTHONPATH}"

WORKDIR /app

CMD ["celery", "-A", "worker", "worker", "-Q", "update", "--concurrency=2", "--prefetch-multiplier=1"]
