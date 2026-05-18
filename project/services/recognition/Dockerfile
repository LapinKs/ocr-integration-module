FROM pytorch/pytorch:2.0.1-cuda11.7-cudnn8-runtime

RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем shared модули
COPY shared/ /app/shared/

# Копируем код воркера и модели
COPY services/recognition/worker.py /app/worker.py
COPY services/recognition/requirements.txt /app/requirements.txt
COPY services/recognition/models/ /app/models/

# Копируем распознаватель (из вашей структуры)
COPY app/infrastructure/formula/recognizers/ /app/app/infrastructure/formula/recognizers/

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

ENV PYTHONPATH="/app:${PYTHONPATH}"

WORKDIR /app

CMD ["celery", "-A", "worker", "worker", "-Q", "recognition", "--concurrency=2", "--prefetch-multiplier=1"]
