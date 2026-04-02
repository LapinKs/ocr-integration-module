from shapely import box

from app.application.ports.formula_localizer import FormulaLocalizer
from doclayout_yolo import YOLOv10
from app.core.config import MODEL
from PIL import Image
FORMULA_CLASS_NAMES = {
    "isolate_formula",
    "formula",
    "display_formula"
}

class DocLayoutYOLOClient(FormulaLocalizer):
    def __init__(self, model_path: str = MODEL, device: str = "cuda"):
        self.model = YOLOv10(model_path)
        self.device = device

    def detect(self, images: list[Image.Image]) -> list[list[dict]]:
        results = self.model.predict(
            images,
            imgsz=1024,
            conf=0.5,
            device=self.device
        )

        all_regions = []

        for img, result in zip(images, results):
            regions = []

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


    def detect_formulas_batch(self, images: list[Image.Image]) -> list[list[dict]]:
        all_regions = self.detect(images)

        result = []

        for regions in all_regions:
            formulas = [
                r for r in regions
                if "formula" in r["class_name"].lower()
                and r["confidence"] > 0.7
            ]
            result.append(formulas)

        return result
