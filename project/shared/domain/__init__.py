"""Domain models for OCR and formula processing."""

from .bbox import BBox
from .node import Node
from .utils import (
    normalize_bbox,
    scale_bbox,
    merge_bboxes,
    bbox_to_tuple,
    tuple_to_bbox,
    is_valid_bbox,
    calculate_center,
    calculate_distance
)

__all__ = [
    'BBox',
    'Node',
    'normalize_bbox',
    'scale_bbox',
    'merge_bboxes',
    'bbox_to_tuple',
    'tuple_to_bbox',
    'is_valid_bbox',
    'calculate_center',
    'calculate_distance',
]
