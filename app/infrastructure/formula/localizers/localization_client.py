from app.application.ports.formula_localizer import FormulaLocalizer
from doclayout_yolo import YOLOv10
from app.core.config import MODEL
FORMULA_CLASS_NAMES = {
    "isolate_formula",
    "formula",
    "display_formula"
}

class DocLayoutYOLOClient(FormulaLocalizer):
    def __init__(self, model_path: str = MODEL, device: str = "cpu"):
        self.model = YOLOv10(model_path)
        self.device = device

    def detect(self, image_path: str) -> list[dict]:
        results = self.model.predict(
            image_path,
            imgsz=1024,
            conf=0.2,
            device=self.device
        )[0]

        regions = []

        for box in results.boxes:
            cls_id = int(box.cls[0])
            cls_name = results.names[cls_id]

            regions.append({
                "bbox": [int(x) for x in box.xyxy[0].tolist()],
                "class_id": cls_id,
                "class_name": cls_name,
                "confidence": float(box.conf[0])
            })

        return regions
    def detect_formulas(self, image_path: str) -> list[dict]:
        regions = self.detect(image_path)

        formulas = []
        for r in regions:
            cls_name = r["class_name"].lower()

            if "formula" in cls_name and r["confidence"] > 0.3:
                formulas.append(r)

        return formulas
