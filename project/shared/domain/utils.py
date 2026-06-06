from typing import Tuple, List, Optional
from .bbox import BBox


def normalize_bbox(x1: int, y1: int, x2: int, y2: int) -> Tuple[int, int, int, int]:
    return (
        min(x1, x2),
        min(y1, y2),
        max(x1, x2),
        max(y1, y2)
    )


def scale_bbox(bbox: BBox, scale_x: float, scale_y: float) -> BBox:
    return BBox(
        x1=int(bbox.x1 * scale_x),
        y1=int(bbox.y1 * scale_y),
        x2=int(bbox.x2 * scale_x),
        y2=int(bbox.y2 * scale_y)
    )


def merge_bboxes(bboxes: List[BBox]) -> Optional[BBox]:
    if not bboxes:
        return None
    x1 = min(b.x1 for b in bboxes)
    y1 = min(b.y1 for b in bboxes)
    x2 = max(b.x2 for b in bboxes)
    y2 = max(b.y2 for b in bboxes)
    return BBox(x1, y1, x2, y2)


def bbox_to_tuple(bbox: BBox) -> Tuple[int, int, int, int]:
    return (bbox.x1, bbox.y1, bbox.x2, bbox.y2)


def tuple_to_bbox(bbox_tuple: Tuple[int, int, int, int]) -> BBox:
    return BBox(*bbox_tuple)


def is_valid_bbox(bbox: BBox, min_area: int = 1) -> bool:
    return bbox.w > 0 and bbox.h > 0 and bbox.area >= min_area


def calculate_center(bbox: BBox) -> Tuple[float, float]:
    return ((bbox.x1 + bbox.x2) / 2, (bbox.y1 + bbox.y2) / 2)


def calculate_distance(bbox1: BBox, bbox2: BBox) -> float:
    cx1, cy1 = calculate_center(bbox1)
    cx2, cy2 = calculate_center(bbox2)
    return ((cx1 - cx2) ** 2 + (cy1 - cy2) ** 2) ** 0.5
