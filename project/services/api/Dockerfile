FROM python:3.11-slim

WORKDIR /app

# Копируем shared модули
COPY shared/ /app/shared/

# Копируем код API
COPY services/api/requirements.txt /app/requirements.txt
COPY services/api/app/ /app/app/

# Копируем celery задачи (если нужны)
# COPY services/api/tasks/ /app/tasks/

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

ENV PYTHONPATH="/app:${PYTHONPATH}"

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
