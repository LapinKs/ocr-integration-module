FROM python:3.11-slim

# Установка системных зависимостей для LaTeX и matplotlib
RUN apt-get update && apt-get install -y \
    texlive-latex-base \
    texlive-latex-extra \
    texlive-fonts-recommended \
    texlive-fonts-extra \
    dvipng \
    cm-super \
    libfreetype6-dev \
    libpng-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем shared модули
COPY shared/ /app/shared/

# Копируем код воркера и рендерер
COPY services/pdf/worker.py /app/worker.py
COPY services/pdf/requirements.txt /app/requirements.txt
COPY app/infrastructure/pdf/ /app/app/infrastructure/pdf/

# Копируем шрифты
COPY fonts/ /app/fonts/

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

ENV PYTHONPATH="/app:${PYTHONPATH}"

WORKDIR /app

CMD ["celery", "-A", "worker", "worker", "-Q", "pdf", "--concurrency=1", "--prefetch-multiplier=1"]
