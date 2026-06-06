from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routes import router
from shared.metrics.production_metrics import metrics_endpoint


app = FastAPI(
    title="Formula OCR API",
    description="API for processing documents with formula recognition. Upload images and get PDF with recognized formulas.",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_api_route("/metrics", metrics_endpoint, methods=["GET"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.on_event("startup")
async def startup_event():
    print("=" * 50)
    print("Starting Formula OCR API v2.0.0")
    print("Using SQLite database (no PostgreSQL)")
    print("Swagger UI: http://localhost:8000/docs")
    print("ReDoc: http://localhost:8000/redoc")
    print("Health: http://localhost:8000/health")
    print("Metrics: http://localhost:8000/metrics")
    print("=" * 50)


@app.get("/")
async def root():
    return {
        "message": "Formula OCR API",
        "version": "2.0.0",
        "status": "running",
        "endpoints": {
            "docs": "/docs",
            "health": "/health",
            "metrics": "/metrics",
            "process": "POST /process",
            "result": "GET /result/{task_id}"
        }
    }
