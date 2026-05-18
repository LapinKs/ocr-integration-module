FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем shared модули
COPY shared/ /app/shared/

# Копируем код воркера и модели
COPY services/segmentation/worker.py /app/worker.py
COPY services/segmentation/requirements.txt /app/requirements.txt
COPY services/segmentation/models/ /app/models/

# Копируем сегментатор
COPY app/infrastructure/formula/segmentators/ /app/app/infrastructure/formula/segmentators/

# Клонируем GeoSeg для UNetFormer
RUN git clone https://github.com/GeoSeg/GeoSeg.git /app/geoseg

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

ENV PYTHONPATH="/app:/app/geoseg:${PYTHONPATH}"

WORKDIR /app

CMD ["celery", "-A", "worker", "worker", "-Q", "segmentation", "--concurrency=1", "--prefetch-multiplier=1"]
