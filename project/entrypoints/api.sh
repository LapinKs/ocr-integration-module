echo "Starting API server..."
exec uvicorn services.api.app.main:app --host 0.0.0.0 --port 8000
