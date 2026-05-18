"""Utility functions for domain models."""
from typing import Tuple, List, Optional
from .bbox import BBox


def normalize_bbox(x1: int, y1: int, x2: int, y2: int) -> Tuple[int, int, int, int]:
    """
    Нормализует координаты bbox (x1 <= x2, y1 <= y2).

    Args:
        x1, y1: Координаты левого верхнего угла
        x2, y2: Координаты правого нижнего угла

    Returns:
        Нормализованные координаты (x1, y1, x2, y2)
    """
    return (
        min(x1, x2),
        min(y1, y2),
        max(x1, x2),
        max(y1, y2)
    )


def scale_bbox(bbox: BBox, scale_x: float, scale_y: float) -> BBox:
    """
    Масштабирует bbox.

    Args:
        bbox: Исходный bbox
        scale_x: Масштаб по X
        scale_y: Масштаб по Y

    Returns:
        Масштабированный bbox
    """
    return BBox(
        x1=int(bbox.x1 * scale_x),
        y1=int(bbox.y1 * scale_y),
        x2=int(bbox.x2 * scale_x),
        y2=int(bbox.y2 * scale_y)
    )


def merge_bboxes(bboxes: List[BBox]) -> Optional[BBox]:
    """
    Объединяет несколько bbox в один, охватывающий все.

    Args:
        bboxes: Список bbox для объединения

    Returns:
        Объединённый bbox или None, если список пуст
    """
    if not bboxes:
        return None

    x1 = min(b.x1 for b in bboxes)
    y1 = min(b.y1 for b in bboxes)
    x2 = max(b.x2 for b in bboxes)
    y2 = max(b.y2 for b in bboxes)

    return BBox(x1, y1, x2, y2)


def bbox_to_tuple(bbox: BBox) -> Tuple[int, int, int, int]:
    """Преобразует BBox в кортеж (x1, y1, x2, y2)."""
    return (bbox.x1, bbox.y1, bbox.x2, bbox.y2)


def tuple_to_bbox(bbox_tuple: Tuple[int, int, int, int]) -> BBox:
    """Преобразует кортеж в BBox."""
    return BBox(*bbox_tuple)


def is_valid_bbox(bbox: BBox, min_area: int = 1) -> bool:
    """
    Проверяет валидность bbox.

    Args:
        bbox: Проверяемый bbox
        min_area: Минимальная допустимая площадь

    Returns:
        True если bbox валидный
    """
    return bbox.w > 0 and bbox.h > 0 and bbox.area >= min_area


def calculate_center(bbox: BBox) -> Tuple[float, float]:
    """Вычисляет центр bbox."""
    return ((bbox.x1 + bbox.x2) / 2, (bbox.y1 + bbox.y2) / 2)


def calculate_distance(bbox1: BBox, bbox2: BBox) -> float:
    """
    Вычисляет евклидово расстояние между центрами двух bbox.

    Args:
        bbox1: Первый bbox
        bbox2: Второй bbox

    Returns:
        Расстояние между центрами
    """
    cx1, cy1 = calculate_center(bbox1)
    cx2, cy2 = calculate_center(bbox2)
    return ((cx1 - cx2) ** 2 + (cy1 - cy2) ** 2) ** 0.5
