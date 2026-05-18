from app.application.ports.formula_recognizer import FormulaRecognizer
from app.infrastructure.formula.recognizers.latex_postprocessor import clean_latex, is_valid_latex
from PIL import Image
import os
os.environ["NO_ALBUMENTATIONS_UPDATE"] = "1"
from pix2tex.cli import LatexOCR
import asyncio


class LatexOCRClient(FormulaRecognizer):
    def __init__(self, device: str = "cuda"):
        self.model = LatexOCR()
        self.device = device

    def recognize_crop(self, image: Image.Image) -> str:
        return self.model(image)

    async def recognize(
        self,
        image: Image.Image,
        regions: list[dict]
    ) -> list[dict]:
        semaphore = asyncio.Semaphore(4)
        async def process_region(region):
            async with semaphore:
                crop = image.crop(region["bbox"])
                latex = await asyncio.to_thread(self.recognize_crop, crop)
                return {
                    "bbox": region["bbox"],
                    "latex": latex,
                    "confidence": region["confidence"]
                }

        tasks = [process_region(r) for r in regions]


        return await asyncio.gather(*tasks)
