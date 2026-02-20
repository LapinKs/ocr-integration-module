from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import shutil
import os
import json

from infrastructure.providers import (
    create_formula_service,
    create_ocr_client,
)
from application.merge_formulas import merge_formulas_into_ocr

app = FastAPI()

UPLOAD_DIR = "out"
os.makedirs(UPLOAD_DIR, exist_ok=True)

formula_service = create_formula_service()
ocr_client = create_ocr_client()


@app.post("/process")
def process_image(file: UploadFile = File(...)):

    try:
        file_path = os.path.join(UPLOAD_DIR, file.filename)

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        try:
            ocr_json = ocr_client.recognize(file_path)
        except Exception:
            with open("out/page_0.json", "r", encoding="utf-8") as f:
                ocr_json = json.load(f)

        formulas = formula_service.process(file_path)

        merged = merge_formulas_into_ocr(ocr_json, formulas)

        return JSONResponse(content=merged)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
