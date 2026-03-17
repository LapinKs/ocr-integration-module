from app.application.ports.formula_localizer import FormulaLocalizer
from app.application.ports.formula_recognizer import FormulaRecognizer
import tempfile

class FormulaService:

    def __init__(self, localizer: FormulaLocalizer, recognizer: FormulaRecognizer):
        self.localizer = localizer
        self.recognizer = recognizer

    def process_bytes(self, image_bytes: bytes):

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name

        regions = self.localizer.detect(tmp_path)
        formulas = self.recognizer.recognize(tmp_path, regions)

        return formulas

        # regions = self.localizer.detect(image_path)
        # formulas = []

        # for region in regions:
        #     crop = region_to_crop(image_path, region)

        #     latex = self.recognizer.recognize(crop)

        #     formulas.append({
        #         "bbox": region["bbox"],
        #         "latex": latex,
        #         "confidence": region["confidence"]
        #     })
