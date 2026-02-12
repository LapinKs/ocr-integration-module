from infrastructure.ocr.client import OCRClient
from infrastructure.formula.localization_client import DocLayoutYOLOClient
from infrastructure.formula.recognition_client import LatexOCRClient
from pathlib import Path
import json
from application.merge_formulas import merge_formulas_into_ocr
from config import OCR_API_KEY, OCR_BASE_URL, IMAGE, OCR_JSON_PATH, MODEL, OUT_JSON_PATH, OUT_PDF_PATH
from infrastructure.pdf.ocr_json_to_pdf import ocr_json_to_pdf

def main():
    with open(OCR_JSON_PATH, "r", encoding="utf-8") as f:
        ocr = json.load(f)
    # ocr = OCRClient(OCR_API_KEY, OCR_BASE_URL)
    # await OCRClient(OCR_API_KEY, OCR_BASE_URL)
    # layout = LocalizationClient()
    # latex_ocr = RecognitionClient()
    # regions = layout.detect_formulas(IMAGE)
    # results = latex_ocr.recognize(IMAGE,regions)
    # merged = merge_formulas_into_ocr(ocr, results)
    layout = DocLayoutYOLOClient(
        model_path=MODEL,
        device="cpu"
    )

    latex_ocr = LatexOCRClient(device="cpu")

    regions = layout.detect_formulas(IMAGE)

    results = latex_ocr.recognize(
        image_path=IMAGE,
        regions=regions
    )

    merged = merge_formulas_into_ocr(ocr, results)

    with open(OUT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    ocr_json_to_pdf(json.dumps(merged, ensure_ascii=False), OUT_PDF_PATH)

    print("PDF создан")


if __name__ == "__main__":
    main()
