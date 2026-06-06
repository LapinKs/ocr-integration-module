import torch
from pathlib import Path
from typing import List, Dict, Union
from PIL import Image
import os


os.environ['DOCLAYOUT_NO_AUTO_DOWNLOAD'] = '1'

FORMULA_CLASS_NAMES = {
    "isolate_formula",
    "formula",
    "display_formula",
    "equation",
    "math"
}

class DocLayoutYOLOClient:
    def __init__(self, model_path: Union[str, Path] = None, device: str = None):
        if model_path is None:
            model_path = Path(__file__).parent / "models" / "doclayout_yolo.pt"
        else:
            model_path = Path(model_path)

        if device is None:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device

        if not model_path.exists():
            raise FileNotFoundError(
                f"Model not found at {model_path}\n"
                f"Please download from: https://github.com/opendatalab/DocLayout-YOLO"
            )
        print(f"[DocLayoutYOLO] Loading model from {model_path}")

        from doclayout_yolo import YOLOv10

        self.model = YOLOv10(str(model_path))
        print(f"[DocLayoutYOLO] Model loaded on {self.device}")


    def detect(self, images: List[Image.Image]) -> List[List[Dict]]:

        if not images:
            return []
        results = self.model.predict(
            images,
            imgsz=1024,
            conf=0.5,
            device=self.device,
            verbose=False
        )
        all_regions = []
        for result in results:
            regions = []
            if result.boxes is not None:
                for box in result.boxes:
                    cls_id = int(box.cls[0])
                    cls_name = result.names[cls_id]

                    regions.append({
                        "bbox": [int(x) for x in box.xyxy[0].tolist()],
                        "class_id": cls_id,
                        "class_name": cls_name,
                        "confidence": float(box.conf[0])
                    })
            all_regions.append(regions)
        return all_regions


    def detect_formulas_batch(self, images: List[Image.Image]) -> List[List[Dict]]:

        all_regions = self.detect(images)
        result = []
        for regions in all_regions:
            formulas = [
                r for r in regions
                if any(formula_type in r["class_name"].lower()
                      for formula_type in ["formula", "equation"])
                and r["confidence"] > 0.7
            ]
            result.append(formulas)

        return result
