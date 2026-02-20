from infrastructure.formula.localizers.localization_client import DocLayoutYOLOClient
from infrastructure.formula.recognizers.recognition_client import LatexOCRClient
from application.services.formula_service import FormulaService
from infrastructure.ocr.client import OCRClient
from application.ports.ocr_client import OCRClientPort
from config import MODEL, OCR_API_KEY, OCR_BASE_URL


def create_localizer():
    return DocLayoutYOLOClient(
        model_path=MODEL,
        device="cpu"
    )


def create_recognizer():
    return LatexOCRClient(device="cpu")


def create_formula_service():
    localizer = create_localizer()
    recognizer = create_recognizer()
    return FormulaService(localizer, recognizer)

def create_ocr_client() -> OCRClientPort:
    return OCRClient(
        api_key=OCR_API_KEY,
        base_url=OCR_BASE_URL)
