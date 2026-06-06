echo "Starting PDF Worker..."
exec celery -A services.pdf.worker worker -Q pdf --concurrency=1 --prefetch-multiplier=1
