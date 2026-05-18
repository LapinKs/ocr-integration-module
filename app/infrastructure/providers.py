from app.infrastructure.formula.localizers.localization_client import DocLayoutYOLOClient
from app.application.services.formula_service import FormulaService
from app.infrastructure.formula.recognizers.old_client import LatexOCRClient
from app.infrastructure.ocr.client import OCRClient
from typing import List, Dict, Tuple, Optional, Union
from app.infrastructure.formula.segmentators.client import FinetunedUNetFormer, UNetFormerConfig
import torch
from app.application.ports.ocr_client import OCRClientPort
from app.core.config import MODEL, OCR_API_KEY, OCR_BASE_URL, OCR_JSON_PATH
from pathlib import Path

def create_localizer():
    return DocLayoutYOLOClient(
        model_path=MODEL,
        device="cpu"
    )

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

def create_recognizer():
    return LatexOCRClient(device="cpu")

# def create_recognizer(use_finetuned: bool = True):
#     if use_finetuned:
#         from app.infrastructure.formula.recognizers.new_client import FinetunedLatexOCRClient
#         MODEL_PATH = Path(__file__).parent/"formula"/"recognizers"/"new_weights.pth"
#         TOKENIZER_PATH = Path(__file__).parent/"formula"/"recognizers"/"tokenizer.json"
#         return FinetunedLatexOCRClient(
#             model_path=MODEL_PATH,
#             tokenizer_path=str(TOKENIZER_PATH),
#             device="cuda" if torch.cuda.is_available() else "cpu"
#         )
#     else:
#         from app.infrastructure.formula.recognizers.recognition_client import LatexOCRClient
#         return LatexOCRClient(device="cpu")


def create_segmentator(model_path: Union[str, Path] = None,
                                 device: str = "cuda") -> FinetunedUNetFormer:
    if model_path is None:
        model_path = Path(__file__).parent / "formula"/ "segmentators" / "weights.pth"
    config = UNetFormerConfig(device=device)
    return FinetunedUNetFormer(
        model_path=model_path,
        config=config,
        backbone_name="tf_efficientnet_b5",
        num_classes=2
    )
