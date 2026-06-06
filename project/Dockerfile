FROM python:3.11-slim AS base

RUN apt-get update && apt-get install -y \
    build-essential \
    libjpeg-dev zlib1g-dev libfreetype6-dev libopenjp2-7-dev \
    libgl1 libglib2.0-0 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements/base.txt /tmp/base.txt
RUN pip install --no-cache-dir -r /tmp/base.txt
RUN pip install prometheus-client
COPY . /app/
ENV PYTHONPATH="/app:${PYTHONPATH}"


FROM base AS api
COPY requirements/api.txt /tmp/api.txt
RUN pip install --no-cache-dir -r /tmp/api.txt

EXPOSE 8000
COPY entrypoints/api.sh /entrypoint.sh
CMD ["uvicorn", "services.api.app.main:app", "--host", "0.0.0.0", "--port", "8000"]


FROM base AS segmentation
COPY requirements/segmentation.txt /tmp/segmentation.txt
RUN pip install --no-cache-dir -r /tmp/segmentation.txt

COPY services/segmentation /app/services/segmentation
COPY entrypoints/segmentation.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
CMD ["celery", "-A", "services.segmentation.worker", "worker", "-Q", "segmentation", "--concurrency=1", "--prefetch-multiplier=1"]


FROM base AS recognition
COPY requirements/recognition.txt /tmp/recognition.txt
RUN pip install --no-cache-dir -r /tmp/recognition.txt

COPY services/recognition/ /app/services/recognition/
COPY services/recognition/models/ /app/services/recognition/models/
ENV PYTHONPATH="/app:${PYTHONPATH}"
COPY entrypoints/recognition.sh /entrypoint.sh
CMD ["celery", "-A", "services.recognition.worker", "worker", "-Q", "recognition", "--concurrency=2", "--prefetch-multiplier=1"]


FROM base AS merge
COPY requirements/merge.txt /tmp/merge.txt
RUN pip install --no-cache-dir -r /tmp/merge.txt

COPY entrypoints/merge.sh /entrypoint.sh
CMD ["celery", "-A", "services.merge.worker", "worker", "-Q", "merge", "--concurrency=1", "--prefetch-multiplier=1"]


FROM base AS ocr
COPY requirements/ocr.txt /tmp/ocr.txt
RUN pip install --no-cache-dir -r /tmp/ocr.txt

COPY services/ocr/fallback/ /app/services/ocr/fallback/
COPY entrypoints/ocr.sh /entrypoint.sh
CMD ["celery", "-A", "services.ocr.worker", "worker", "-Q", "ocr", "--concurrency=2", "--prefetch-multiplier=1"]


FROM base AS pdf
RUN apt-get update && apt-get install -y \
    texlive-latex-base \
    texlive-latex-extra \
    dvipng \
    cm-super \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
COPY requirements/pdf.txt /tmp/pdf.txt
RUN pip install --no-cache-dir -r /tmp/pdf.txt

COPY services/pdf/DejaVuSans.ttf /app/services/pdf/DejaVuSans.ttf
COPY entrypoints/pdf.sh /entrypoint.sh
CMD ["celery", "-A", "services.pdf.worker", "worker", "-Q", "pdf", "--concurrency=1", "--prefetch-multiplier=1"]
