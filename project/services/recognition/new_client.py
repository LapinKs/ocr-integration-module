import os
import torch
import numpy as np
from PIL import Image
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Union
import asyncio
from dataclasses import dataclass
from pix2tex.models import get_model
from transformers import PreTrainedTokenizerFast
from pix2tex.utils import token2str, post_process
import re

os.environ["NO_ALBUMENTATIONS_UPDATE"] = "1"


from pathlib import Path

class FinetunedLatexOCRClient:
    def __init__(self,
                 model_path: str = None,
                 tokenizer_path: str = None,
                 device: str = "cuda",
                 max_width: int = 672,
                 max_height: int = 192,
                 min_width: int = 32,
                 min_height: int = 32,
                 temperature: float = 0.2,
                 batch_size: int = 8):

        if model_path is None:
            model_path = str(Path(__file__).parent / "models" / "new_weights.pth")
        if tokenizer_path is None:
            tokenizer_path = str(Path(__file__).parent / "models" / "tokenizer.json")

        self.device = device if torch.cuda.is_available() else "cpu"
        self.max_width = max_width
        self.max_height = max_height
        self.min_width = min_width
        self.min_height = min_height
        self.temperature = temperature
        self.batch_size = batch_size

        print(f"[LaTeX-OCR] Загрузка токенизатора из {tokenizer_path}")
        self.tokenizer = PreTrainedTokenizerFast(tokenizer_file=tokenizer_path)

        self.args = self._get_model_args()

        print(f"[LaTeX-OCR] Загрузка модели из {model_path}")
        self.model = get_model(self.args)
        self.model.load_state_dict(torch.load(model_path, map_location=self.device))
        self.model = self.model.to(self.device)
        self.model.eval()
        print(f"[LaTeX-OCR] Модель загружена на {self.device}")

    def _get_model_args(self):
        from munch import Munch

        return Munch({
            "device": self.device,
            "no_cuda": True,
            "gpu_devices": [],
            "dim": 256,
            "encoder_depth": 4,
            "num_layers": 4,
            "heads": 8,
            "patch_size": 16,
            "max_height": self.max_height,
            "max_width": self.max_width,
            "min_height": self.min_height,
            "min_width": self.min_width,
            "num_tokens": 8000,
            "bos_token": 1,
            "eos_token": 2,
            "pad_token": 0,
            "max_seq_len": 512,
            "backbone_layers": [2, 3, 7],
            "channels": 1,
            "encoder_structure": "hybrid",
            "temperature": self.temperature,
            "wandb": False,
            "decoder_args": {
                "attn_on_attn": True,
                "cross_attend": True,
                "ff_glu": True,
                "rel_pos_bias": False,
                "use_scalenorm": False
            }
        })

    def _soft_pad(self, img: Image.Image, divable: int = 16) -> Image.Image:
        data = np.array(img.convert("L"))
        h, w = data.shape
        new_w = ((w + divable - 1) // divable) * divable
        new_h = ((h + divable - 1) // divable) * divable
        padded = np.ones((new_h, new_w), dtype=np.uint8) * 255
        padded[:h, :w] = data
        return Image.fromarray(padded)

    def _minmax_size(self, img: Image.Image) -> Image.Image:
        from pix2tex.cli import minmax_size
        return minmax_size(
            img,
            max_dimensions=(self.max_width, self.max_height),
            min_dimensions=(self.min_width, self.min_height)
        )

    def _preprocess_image(self, image: Image.Image) -> torch.Tensor:
        from pix2tex.dataset.transforms import test_transform
        img = self._minmax_size(image)
        img = self._soft_pad(img)
        img = np.array(img.convert("RGB"))
        t = test_transform(image=img)["image"][:1].unsqueeze(0)
        return t.to(self.device)

    # def _preprocess_batch(self, images: List[Image.Image]) -> torch.Tensor:
    #     tensors = [self._preprocess_image(img).squeeze(0) for img in images]
    #     return torch.stack(tensors).to(self.device)
    def _preprocess_batch(self, images: List[Image.Image]) -> torch.Tensor:
        tensors = []
        max_h = 0
        max_w = 0

        for img in images:
            t = self._preprocess_image(img).squeeze(0)
            tensors.append(t)
            _, h, w = t.shape
            max_h = max(max_h, h)
            max_w = max(max_w, w)

        padded = []
        for t in tensors:
            _, h, w = t.shape
            if h < max_h or w < max_w:
                t = torch.nn.functional.pad(
                    t,
                    (0, max_w - w, 0, max_h - h),
                    mode='constant',
                    value=0
                )
            padded.append(t)

        return torch.stack(padded).to(self.device)
    def _normalize_latex(self, latex: str) -> str:
        if not isinstance(latex, str):
            return ""
        spacing_cmds = [r"\\;", r"\\,", r"\\quad", r"\\qquad", r"\\!", r"\\:"]
        for cmd in spacing_cmds:
            latex = re.sub(cmd, "", latex)
        latex = re.sub(r"\s*([\{\}\[\]\(\)=+\-/,])\s*", r"\1", latex)
        latex = re.sub(r"\s+", " ", latex)
        return latex.strip()

    def _decode_single(self, image_tensor: torch.Tensor) -> str:
        with torch.no_grad():
            dec = self.model.generate(image_tensor, temperature=self.temperature)
        pred = token2str(dec, self.tokenizer)[0]
        pred = post_process(pred)
        pred = self._normalize_latex(pred)
        return pred

    # def _decode_batch(self, batch_tensor: torch.Tensor) -> List[str]:
    #     with torch.no_grad():
    #         dec = self.model.generate(batch_tensor, temperature=self.temperature)
    #     preds = token2str(dec, self.tokenizer)
    #     preds = [self._normalize_latex(post_process(p)) for p in preds]
    #     return preds

    def _decode_batch(self, batch_tensor: torch.Tensor) -> List[str]:
        print(f"[LaTeX-OCR] _decode_batch: starting generation...")
        with torch.no_grad():
            dec = self.model.generate(batch_tensor, temperature=self.temperature)
        print(f"[LaTeX-OCR] _decode_batch: generation completed")
        preds = token2str(dec, self.tokenizer)
        print(f"[LaTeX-OCR] _decode_batch: token2str completed")
        preds = [self._normalize_latex(post_process(p)) for p in preds]
        print(f"[LaTeX-OCR] _decode_batch: post-processing completed")
        return preds

    def recognize_crop(self, image: Image.Image) -> str:
        try:
            input_tensor = self._preprocess_image(image)
            return self._decode_single(input_tensor)
        except Exception as e:
            print(f"[LaTeX-OCR] Ошибка распознавания: {e}")
            return ""

    # def recognize_batch(self, crops: List[Image.Image]) -> List[str]:
    #     if not crops:
    #         return []

    #     try:
    #         batch_tensor = self._preprocess_batch(crops)
    #         return self._decode_batch(batch_tensor)
    #     except Exception as e:
    #         print(f"[LaTeX-OCR] Ошибка батчевого распознавания: {e}")
    #         return [""] * len(crops)
    def recognize_batch(self, crops: List[Image.Image]) -> List[str]:
        if not crops:
            return []

        print(f"[LaTeX-OCR] Starting batch recognition of {len(crops)} crops")

        try:
            print(f"[LaTeX-OCR] Preprocessing batch...")
            batch_tensor = self._preprocess_batch(crops)
            print(f"[LaTeX-OCR] Batch tensor shape: {batch_tensor.shape}")

            print(f"[LaTeX-OCR] Running model inference...")
            result = self._decode_batch(batch_tensor)
            print(f"[LaTeX-OCR] Batch recognition completed, got {len(result)} results")
            return result
        except Exception as e:
            print(f"[LaTeX-OCR] Ошибка батчевого распознавания: {e}")
            import traceback
            traceback.print_exc()
            return [""] * len(crops)
    async def recognize(self, image: Image.Image, regions: List[Dict]) -> List[Dict]:

        if not regions:
            return []

        crops = []
        valid_indices = []

        for i, r in enumerate(regions):
            try:
                crop = image.crop(r["bbox"])
                if crop.size[0] > 0 and crop.size[1] > 0:
                    crops.append(crop)
                    valid_indices.append(i)
                else:
                    print(f"   Пропущен пустой кроп для региона {i}")
            except Exception as e:
                print(f"   Ошибка вырезания кропа {i}: {e}")

        if not crops:
            return [{"bbox": r["bbox"], "latex": "", "confidence": 0.0} for r in regions]

        latex_list = await asyncio.to_thread(self.recognize_batch_auto, crops)

        results = []
        latex_idx = 0
        for i, r in enumerate(regions):
            if i in valid_indices:
                results.append({
                    "bbox": r["bbox"],
                    "latex": latex_list[latex_idx],
                    "confidence": r.get("confidence", 0.0)
                })
                latex_idx += 1
            else:
                results.append({
                    "bbox": r["bbox"],
                    "latex": "",
                    "confidence": 0.0
                })

        return results
    async def recognize_async_batch(self, formulas: List[Dict]) -> List[Dict]:

        if not formulas:
            return []

        crops = []
        for f in formulas:
            if 'crop' in f and f['crop'] is not None:
                if isinstance(f['crop'], np.ndarray):
                    crops.append(Image.fromarray(f['crop']))
                else:
                    crops.append(f['crop'])
            else:
                return [{"error": "No crop data"}] * len(formulas)

        latex_list = await asyncio.to_thread(self.recognize_batch, crops)

        for f, latex in zip(formulas, latex_list):
            f['latex'] = latex

        return formulas

    def recognize_batch_auto(self, crops: List[Image.Image]) -> List[str]:
        if not crops:
            return []

        total = len(crops)
        results = [''] * total

        num_batches = (total + self.batch_size - 1) // self.batch_size

        print(f"   [Batch] Всего кропов: {total}, батчей: {num_batches}, размер батча: {self.batch_size}")

        for batch_idx in range(num_batches):
            start_idx = batch_idx * self.batch_size
            end_idx = min(start_idx + self.batch_size, total)
            batch = crops[start_idx:end_idx]

            print(f"   [Batch {batch_idx + 1}/{num_batches}] "
                f"Обработка {len(batch)} кропов ({start_idx + 1}-{end_idx})")

            batch_results = self.recognize_batch(batch)

            for i, res in enumerate(batch_results):
                results[start_idx + i] = res

        return results
