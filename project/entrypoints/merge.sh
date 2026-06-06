echo "Starting Merge Worker..."
exec celery -A services.merge.worker worker -Q merge --concurrency=1 --prefetch-multiplier=1
