"""BBox utilities for merge operations."""
import numpy as np
from typing import Tuple
from shared.domain.node import Node
from shared.domain.bbox import BBox


class BBoxUtils:
    @staticmethod
    def intersects(b1: BBox, b2: BBox) -> bool:
        return not (b1.x2 <= b2.x1 or b1.x1 >= b2.x2 or b1.y2 <= b2.y1 or b1.y1 >= b2.y2)

    @staticmethod
    def intersection_area(b1: BBox, b2: BBox) -> int:
        if not BBoxUtils.intersects(b1, b2):
            return 0
        x1 = max(b1.x1, b2.x1)
        y1 = max(b1.y1, b2.y1)
        x2 = min(b1.x2, b2.x2)
        y2 = min(b1.y2, b2.y2)
        return max(0, x2 - x1) * max(0, y2 - y1)


class MaskUtils:
    @staticmethod
    def word_intersects_mask(
        word: Node,
        formula_bbox: Tuple[int, int, int, int],
        formula_mask: np.ndarray,
        threshold_ratio: float = 0.05
    ) -> bool:
        if formula_mask is None:
            return BBoxUtils.intersects(word.bbox, BBox(*formula_bbox))

        fx1, fy1, fx2, fy2 = formula_bbox
        wx1, wy1, wx2, wy2 = word.bbox.x1, word.bbox.y1, word.bbox.x2, word.bbox.y2

        ix1 = max(wx1, fx1)
        iy1 = max(wy1, fy1)
        ix2 = min(wx2, fx2)
        iy2 = min(wy2, fy2)

        if ix2 <= ix1 or iy2 <= iy1:
            return False

        local_x1 = int(ix1 - fx1)
        local_y1 = int(iy1 - fy1)
        local_x2 = int(ix2 - fx1)
        local_y2 = int(iy2 - fy1)

        mask_h, mask_w = formula_mask.shape
        local_x1 = max(0, min(local_x1, mask_w))
        local_x2 = max(0, min(local_x2, mask_w))
        local_y1 = max(0, min(local_y1, mask_h))
        local_y2 = max(0, min(local_y2, mask_h))

        if local_x2 <= local_x1 or local_y2 <= local_y1:
            return False

        submask = formula_mask[local_y1:local_y2, local_x1:local_x2]
        if submask.size == 0:
            return False

        intersection = np.count_nonzero(submask)
        area = submask.shape[0] * submask.shape[1]
        ratio = intersection / max(area, 1)
        return ratio > threshold_ratio
