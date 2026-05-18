from dataclasses import dataclass, field
from typing import Optional, List
from ...domain.bbox import BBox
from .polygon import Polygon

@dataclass
class Formula:
    bbox: BBox
    latex: str
    confidence: float
    polygon: Optional[Polygon] = None
    contours: Optional[List[List[int]]] = None

    def intersects_word(self, word_bbox: BBox) -> bool:
        if not self.bbox.intersects(word_bbox):
            return False

        if self.polygon:
            corners = [
                Point(word_bbox.x1, word_bbox.y1),
                Point(word_bbox.x2, word_bbox.y1),
                Point(word_bbox.x1, word_bbox.y2),
                Point(word_bbox.x2, word_bbox.y2),
            ]
            return any(self.polygon.contains_point(corner) for corner in corners)
        return True
