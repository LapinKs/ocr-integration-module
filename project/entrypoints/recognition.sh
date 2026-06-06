echo "Starting Recognition Worker..."
exec celery -A services.recognition.worker worker -Q recognition --concurrency=2 --prefetch-multiplier=1
