from ultralytics import YOLO
from application.ports.formula_localizer import FormulaLocalizer
from app.core.config import MODEL_seg
FORMULA_CLASS_NAME = "Formula"

class DocLayNetSegClient(FormulaLocalizer):

    def __init__(self, model_path: str = MODEL_seg, device: str = "cpu"):
        self.model = YOLO(model_path)
        self.device = device

    def detect(self, image_path: str) -> list[dict]:

        results = self.model(
            image_path,
            imgsz=1024,
            conf=0.25,
            device=self.device
        )[0]

        regions = []

        if results.boxes is None:
            return regions

        for i, box in enumerate(results.boxes):

            cls_id = int(box.cls[0])
            class_name = self.model.names[cls_id]

            if "formula" not in class_name.lower():
                continue

            confidence = float(box.conf[0])

            bbox = box.xyxy[0].cpu().numpy().astype(int).tolist()

            polygon = None
            if results.masks is not None:
                polygon = [
                    [int(x), int(y)]
                    for x, y in results.masks.xy[i]
                ]

            regions.append({
                "bbox": bbox,
                "polygon": polygon,
                "class_name": class_name,
                "confidence": confidence
            })

        return regions
