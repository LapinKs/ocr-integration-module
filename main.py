from pathlib import Path
import json
from application.merge_formulas import merge_formulas_into_ocr
from config import OCR_API_KEY, OCR_BASE_URL, IMAGE, OCR_JSON_PATH, OUT_JSON_PATH, OUT_PDF_PATH
from infrastructure.pdf.ocr_json_to_pdf import ocr_json_to_pdf
from infrastructure.providers import create_formula_service
def main():
    with open(OCR_JSON_PATH, "r", encoding="utf-8") as f:
        json_ocr = json.load(f)
    formula_service = create_formula_service()

    formulas = formula_service.process(IMAGE)

    merged = merge_formulas_into_ocr(json_ocr, formulas)

    with open(OUT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    ocr_json_to_pdf(json.dumps(merged, ensure_ascii=False), OUT_PDF_PATH)

    print("PDF создан")


if __name__ == "__main__":
    main()
