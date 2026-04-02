from app.infrastructure.formula.localizers.localization_client import DocLayoutYOLOClient
from app.infrastructure.formula.recognizers.recognition_client import LatexOCRClient
from app.application.services.formula_service import FormulaService
from app.infrastructure.ocr.client import OCRClient
from app.application.ports.ocr_client import OCRClientPort
from app.infrastructure.formula.localizers.todo_yolo11_seg_client import YOLO11SegClient
from app.core.config import MODEL, OCR_API_KEY, OCR_BASE_URL, OCR_JSON_PATH,MODEL_SEGMENTATION

def create_localizer():
    return DocLayoutYOLOClient(
        model_path=MODEL,
        device="cpu"
    )
# def create_localizer():

#     return YOLO11SegClient(
#         model_path=MODEL_SEGMENTATION,
#         device="cpu",
#         conf_threshold=0.5
#     )


def create_recognizer():
    return LatexOCRClient(device="cpu")


def create_formula_service():
    localizer = create_localizer()
    recognizer = create_recognizer()
    return FormulaService(localizer, recognizer)

def create_ocr_client() -> OCRClientPort:
    return OCRClient(
        api_key=OCR_API_KEY,
        base_url=OCR_BASE_URL,
        fallback_json_path=OCR_JSON_PATH,
        )
