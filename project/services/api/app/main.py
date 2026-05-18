from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routes import router
import os

app = FastAPI(
    title="Formula OCR API",
    description="API for processing documents with formula recognition",
    version="2.0.0"
)

# CORS middleware
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
    print("Starting Formula OCR API...")
    # Проверка подключений будет в роутах

@app.get("/")
async def root():
    return {"message": "Formula OCR API", "status": "running"}
