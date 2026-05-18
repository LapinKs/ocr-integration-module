from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Union
from ...domain.bbox import BBox
import numpy as np

class FormulaType(Enum):
    INLINE = "inline"
    BLOCK = "block"

@dataclass
class TextFragment:
    text: str
    bbox: BBox

@dataclass
class InlineFormula:
    latex: str
    bbox: BBox
    confidence: float

@dataclass
class RleFormula:
    latex: str
    confidence: float
    bbox: BBox
    mask_rle: Dict[str, Any]
    formula_type: FormulaType = FormulaType.BLOCK

    def _get_mask(self) -> np.ndarray:
        if not hasattr(self, '_cached_mask'):
            import pycocotools.mask as mask_utils
            self._cached_mask = mask_utils.decode(self.mask_rle)
        return self._cached_mask

    def intersects_word(self, word_bbox: BBox) -> bool:
        if not self.bbox.intersects(word_bbox):
            return False

        mask = self._get_mask()
        x1 = max(0, word_bbox.x1)
        y1 = max(0, word_bbox.y1)
        x2 = min(mask.shape[1], word_bbox.x2)
        y2 = min(mask.shape[0], word_bbox.y2)

        if x1 >= x2 or y1 >= y2:
            return False

        crop = mask[y1:y2, x1:x2]
        return np.any(crop > 0)

    def to_renderable(self) -> dict:
        return {
            "latex": self.latex,
            "bbox": (self.bbox.x1, self.bbox.y1, self.bbox.x2, self.bbox.y2),
            "confidence": self.confidence
        }

# @dataclass
# class RleFormula:
#     latex: str
#     confidence: float
#     bbox: BBox                      # для быстрого поиска
#     mask_rle: Dict[str, Any]        # RLE в формате COCO
#     formula_type: FormulaType = FormulaType.BLOCK

#     def intersects_word(self, word_bbox: BBox) -> bool:
#         if not self.bbox.intersects(word_bbox):
#             return False

#         mask = self._get_mask()
#         x1 = max(0, word_bbox.x1)
#         y1 = max(0, word_bbox.y1)
#         x2 = min(mask.shape[1], word_bbox.x2)
#         y2 = min(mask.shape[0], word_bbox.y2)

#         if x1 >= x2 or y1 >= y2:
#             return False

#         crop = mask[y1:y2, x1:x2]
#         return np.any(crop > 0)

#     def _get_mask(self):
#         if not hasattr(self, '_cached_mask'):
#             from pycocotools import mask as mask_utils
#             self._cached_mask = mask_utils.decode(self.mask_rle)
#         return self._cached_mask
