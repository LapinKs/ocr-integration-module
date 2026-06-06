import os
import asyncio
from PIL import Image
from typing import List, Dict
import re
os.environ["NO_ALBUMENTATIONS_UPDATE"] = "1"
from pix2tex.cli import LatexOCR


class LegacyLatexOCRClient:


    def __init__(self, device: str = "cpu", max_concurrent: int = 4):
        print("[LegacyOCR] Loading pix2tex model...")
        self.model = LatexOCR()
        self.device = device
        self.max_concurrent = max_concurrent
        print("[LegacyOCR] Model loaded")

    def _clean_latex(self, latex: str) -> str:

        if not latex:
            return ""

        latex = latex.strip()
        latex = re.sub(r'\\hat\{\\hat\{', r'\\hat{', latex)
        latex = latex.replace(r"\\", "")
        latex = re.sub(r'\^\{+', '^{', latex)
        latex = re.sub(r'\{+', '{', latex)
        latex = re.sub(r'\}+', '}', latex)

        if latex.count("\\begin") != latex.count("\\end"):
            return ""
        if latex.count("{") != latex.count("}"):
            return ""
        return latex

    def recognize_crop_sync(self, image: Image.Image) -> str:

        try:
            raw_latex = self.model(image)
            return self._clean_latex(raw_latex)
        except Exception as e:
            print(f"[LegacyOCR] Error: {e}")
            return ""

    def recognize_batch(self, crops: List[Image.Image]) -> List[str]:

        results = []
        for crop in crops:
            results.append(self.recognize_crop_sync(crop))
        return results

    async def recognize_batch_async(self, crops: List[Image.Image]) -> List[str]:

        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def process_crop(crop):
            async with semaphore:
                return await asyncio.to_thread(self.recognize_crop_sync, crop)

        tasks = [process_crop(crop) for crop in crops]
        return await asyncio.gather(*tasks)
