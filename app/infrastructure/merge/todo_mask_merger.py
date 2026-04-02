#mask commit
from app.infrastructure.merge.domain.page import Page
from app.infrastructure.merge.domain.formula import Formula
from app.infrastructure.formula.localizers.todo_mask_utils import rle_to_mask
import numpy as np

def mask_iou(mask_rle: dict, word_bbox, image_shape: tuple) -> float:
    try:
        mask = rle_to_mask(mask_rle)
        h, w = mask.shape

        scale_x = w / image_shape[1]
        scale_y = h / image_shape[0]

        x1 = max(0, int(word_bbox.x1 * scale_x))
        y1 = max(0, int(word_bbox.y1 * scale_y))
        x2 = min(w, int(word_bbox.x2 * scale_x))
        y2 = min(h, int(word_bbox.y2 * scale_y))

        if x2 <= x1 or y2 <= y1:
            return 0.0

        word_mask = np.zeros((h, w), dtype=np.uint8)
        word_mask[y1:y2, x1:x2] = 1

        intersection = np.sum((mask > 0) & (word_mask > 0))
        union = np.sum((mask > 0) | (word_mask > 0))

        return intersection / union if union > 0 else 0.0
    except Exception:
        return 0.0

def merge_with_masks(page: Page, formulas: list[Formula], image_shape: tuple, iou_threshold: float = 0.3) -> Page:
    for f in formulas:
        for line in page.lines:
            if not line.bbox.intersects(f.bbox):
                continue

            if f.mask is not None:
                line.words = [
                    w for w in line.words
                    if mask_iou(f.mask, w.bbox, image_shape) < iou_threshold
                ]
            else:
                line.words = [
                    w for w in line.words
                    if w.bbox.intersection_area(f.bbox) == 0
                ]

        page.formulas.append(f)

    return page
