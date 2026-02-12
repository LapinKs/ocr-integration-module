from typing import Optional
from .localization_client import DocLayoutYOLOClient
from .recognition_client import LatexOCRClient


class FormulaClient:
    def __init__(self, yolo_weights: str, latex_model=None, device: str = "cpu", conf_threshold: float = 0.6):
        self.loc = DocLayoutYOLOClient(yolo_weights, device=device)
        self.rec = LatexOCRClient(latex_model) if latex_model is not None else None
        self.conf_threshold = conf_threshold

    def detect(self, image_path: str) -> list[dict]:
        regions = self.loc.detect(image_path)
        results = []

        for r in regions:
            entry = {"bbox": r["bbox"], "confidence": r.get("confidence", 0.0)}

            if self.rec and entry["confidence"] >= self.conf_threshold:
                recog = self._recognize_box(image_path, entry["bbox"])
                entry.update(recog)

            results.append(entry)

        return results

    def _recognize_box(self, image_path: str, bbox: list[int]) -> dict:
        try:
            res = self.rec.recognize(image_path, bbox)
            return {
                "latex": res.get("latex"),
                "latex_confidence": res.get("confidence", 0.0)
            }
        except Exception:
            return {"latex": None, "latex_confidence": 0.0}


    def recognize_via_client(self, image_path: str, bbox: list[int]) -> dict:
        return self.rec.recognize(image_path, bbox)


class FormulaClientStub:
    def detect(self, image_path: str) -> list[dict]:
        return [
            {
                "bbox": [100, 200, 400, 280],
                "confidence": 0.95,
                "latex": "E=mc^2",
                "latex_confidence": 0.99
            }
        ]
