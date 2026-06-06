import cv2
import numpy as np
from PIL import Image
from typing import Tuple, Optional


def crop_with_mask(
    image_rgb: np.ndarray,
    bbox: Tuple[int, int, int, int],
    mask: Optional[np.ndarray] = None,
    background_color: int = 255
) -> Image.Image:
    x1, y1, x2, y2 = bbox
    crop = image_rgb[y1:y2, x1:x2].copy()

    if mask is not None:
        if mask.shape != crop.shape[:2]:
            mask = cv2.resize(mask, (crop.shape[1], crop.shape[0]), interpolation=cv2.INTER_NEAREST)
        mask_3ch = np.stack([mask] * 3, axis=-1)
        crop = np.where(mask_3ch > 0, crop, background_color)

    return Image.fromarray(crop)


def rescale_bbox(
    bbox: Tuple[int, int, int, int],
    from_size: Tuple[int, int],
    to_size: Tuple[int, int]
) -> Tuple[int, int, int, int]:
    x1, y1, x2, y2 = bbox
    from_w, from_h = from_size
    to_w, to_h = to_size
    scale_x = to_w / from_w
    scale_y = to_h / from_h
    return (
        int(x1 * scale_x),
        int(y1 * scale_y),
        int(x2 * scale_x),
        int(y2 * scale_y)
    )
