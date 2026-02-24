from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
import shutil
import os
import json
from infrastructure.pdf.ocr_json_to_pdf import ocr_json_to_pdf
from application.merge_formulas import merge_formulas_into_ocr
from infrastructure.providers import create_formula_service
from config import OCR_API_KEY, OCR_BASE_URL, IMAGE, OCR_JSON_PATH, OUT_JSON_PATH, OUT_PDF_PATH

from infrastructure.ocr_client import OCRClient

app = FastAPI()

UPLOAD_DIR = "temp"
os.makedirs(UPLOAD_DIR, exist_ok=True)

ocr_client = OCRClient(
    api_key=OCR_API_KEY,
    base_url=OCR_BASE_URL,
    fallback_json_path=OCR_JSON_PATH,
)


@app.post("/process")
async def process_image(file: UploadFile = File(...)):
    file_path = os.path.join(UPLOAD_DIR, file.filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    ocr_pages = ocr_client.recognize_one(file_path)

    formula_service = create_formula_service()

    formulas = formula_service.process(IMAGE)

    merged = merge_formulas_into_ocr(ocr_pages, formulas)

    pdf = ocr_json_to_pdf(json.dumps(merged, ensure_ascii=False))

    return JSONResponse(content=[merged,pdf])
