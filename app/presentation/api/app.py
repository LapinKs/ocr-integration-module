from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.presentation.api.routes import router
from app.presentation.api.dependencies import set_pipeline
from app.application.pipeline import build_pipeline
from contextlib import asynccontextmanager
import logging

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Загрузка пайплайна и моделей...")
    pipeline = build_pipeline()
    set_pipeline(pipeline)
    logger.info("Пайплайн загружен, сервер готов к работе")
    yield
    logger.info("Выключение сервера")

app = FastAPI(
    title="Formula OCR API",
    debug=True,
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["content-disposition"],
)

app.include_router(router)
