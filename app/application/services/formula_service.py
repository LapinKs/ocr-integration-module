from app.application.ports.formula_localizer import FormulaLocalizer
from app.application.ports.formula_recognizer import FormulaRecognizer
from PIL import Image
import io
class FormulaService:

    def __init__(self, localizer: FormulaLocalizer, recognizer: FormulaRecognizer):
        self.localizer = localizer
        self.recognizer = recognizer

    async def process_batch(self, images_bytes: list[bytes]):
        images = [
            Image.open(io.BytesIO(b)).convert("RGB")
            for b in images_bytes
        ]

        regions_batch = self.localizer.detect_formulas_batch(images)
        sizes = [(x.width, x.height) for x in images]
        results = []

        for image, regions in zip(images, regions_batch):
            formulas = await self.recognizer.recognize(image, regions)
            results.append(formulas)

        return results,sizes
