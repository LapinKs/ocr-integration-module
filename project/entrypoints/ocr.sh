echo "Starting OCR Worker..."
exec celery -A services.ocr.worker worker -Q ocr --concurrency=2 --prefetch-multiplier=1
