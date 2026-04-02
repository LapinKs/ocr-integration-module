from app.application.ports.formula_localizer import FormulaLocalizer
from app.application.ports.formula_recognizer import FormulaRecognizer
from PIL import Image
import io
import time
class FormulaService:

    def __init__(self, localizer: FormulaLocalizer, recognizer: FormulaRecognizer):
        self.localizer = localizer
        self.recognizer = recognizer

    async def process_batch(self, images_bytes: list[bytes]):
        images = [
            Image.open(io.BytesIO(b)).convert("RGB")
            for b in images_bytes
        ]
        loc_start = time.time()
        regions_batch = self.localizer.detect_formulas_batch(images)
        loc_time = time.time() - loc_start
        total_formulas = sum(len(r) for r in regions_batch)
        print(f"Локализация/сегментация: {loc_time:.2f} сек (найдено формул: {total_formulas})")
        sizes = [(x.width, x.height) for x in images]
        results = []
        rec_start = time.time()
        for image, regions in zip(images, regions_batch):
            formulas = await self.recognizer.recognize(image, regions)
            results.append(formulas)
        rec_time = time.time() - rec_start
        print(f"Распознавание: {rec_time:.2f} сек")
        return results,sizes
