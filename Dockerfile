FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    build-essential \
    libjpeg-dev zlib1g-dev libfreetype6-dev libopenjp2-7-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.presentation.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
