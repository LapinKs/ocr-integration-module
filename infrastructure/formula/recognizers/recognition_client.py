from application.ports.formula_recognizer import FormulaRecognizer
from PIL import Image
from pix2tex.cli import LatexOCR

class LatexOCRClient(FormulaRecognizer):
    def __init__(self, device: str = "cpu"):
        self.model = LatexOCR()
        self.device = device

    def recognize_crop(self, image: Image.Image) -> str:
        return self.model(image)

    def recognize(
        self,
        image_path: str,
        regions: list[dict]
    ) -> list[dict]:

        image = Image.open(image_path).convert("RGB")
        results = []

        for region in regions:
            crop = image.crop(region["bbox"])

            latex = self.recognize_crop(crop)

            results.append({
                "bbox": region["bbox"],
                "latex": latex,
                "confidence": region["confidence"]
            })

        return results
