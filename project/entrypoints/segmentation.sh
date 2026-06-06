echo "Starting Segmentation Worker..."
exec celery -A services.segmentation.worker worker -Q segmentation --concurrency=1 --prefetch-multiplier=1
