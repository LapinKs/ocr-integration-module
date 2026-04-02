#mask commit
import numpy as np
import cv2
from typing import Tuple, Dict, Any, List

def mask_to_bbox(mask: np.ndarray) -> Tuple[int, int, int, int]:
    y_indices, x_indices = np.where(mask > 0)
    if len(x_indices) == 0:
        return (0, 0, 0, 0)
    return (
        int(x_indices.min()),
        int(y_indices.min()),
        int(x_indices.max()),
        int(y_indices.max())
    )

def mask_to_rle(mask: np.ndarray) -> Dict:
    from pycocotools import mask as mask_utils
    return mask_utils.encode(np.asfortranarray(mask.astype(np.uint8)))

def rle_to_mask(rle: Dict) -> np.ndarray:
    from pycocotools import mask as mask_utils
    return mask_utils.decode(rle)

def apply_nms_masks(masks: List[np.ndarray], scores: List[float],
                    classes: List[int], iou_threshold: float = 0.5) -> List[int]:
    if not masks:
        return []

    idx = np.argsort(scores)[::-1]
    keep = []

    while len(idx) > 0:
        i = idx[0]
        keep.append(i)
        if len(idx) == 1:
            break

        mask_i = masks[i] > 0.5
        ious = []

        for j in idx[1:]:
            if classes[i] != classes[j]:
                ious.append(0.0)
                continue
            mask_j = masks[j] > 0.5
            inter = np.logical_and(mask_i, mask_j).sum()
            union = np.logical_or(mask_i, mask_j).sum()
            ious.append(inter / (union + 1e-6))

        idx = idx[1:][np.array(ious) < iou_threshold]

    return keep

def postprocess_mask(mask: np.ndarray, close_kernel: int = 3, min_area: int = 100) -> np.ndarray:
    if close_kernel > 0:
        kernel = np.ones((close_kernel, close_kernel), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    if min_area > 0:
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        filtered = np.zeros_like(mask)
        for cnt in contours:
            if cv2.contourArea(cnt) >= min_area:
                cv2.drawContours(filtered, [cnt], -1, 1, thickness=cv2.FILLED)
        mask = filtered

    return mask
