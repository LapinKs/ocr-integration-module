from dataclasses import dataclass
from typing import List, Tuple
from ...domain.bbox import BBox

@dataclass
class Point:
    x: int
    y: int

@dataclass
class Polygon:
    points: List[Point]

    def to_bbox(self) -> BBox:
        xs = [p.x for p in self.points]
        ys = [p.y for p in self.points]
        return BBox(min(xs), min(ys), max(xs), max(ys))

    def intersects_bbox(self, bbox: BBox) -> bool:
        poly_bbox = self.to_bbox()
        return poly_bbox.intersects(bbox)

    def contains_point(self, point: Point) -> bool:
        inside = False
        n = len(self.points)
        for i in range(n):
            x1, y1 = self.points[i].x, self.points[i].y
            x2, y2 = self.points[(i + 1) % n].x, self.points[(i + 1) % n].y

            if ((y1 > point.y) != (y2 > point.y)) and \
               (point.x < (x2 - x1) * (point.y - y1) / (y2 - y1) + x1):
                inside = not inside
        return inside

    def to_json(self) -> List[List[int]]:
        return [[p.x, p.y] for p in self.points]

    @staticmethod
    def from_json(data: List[List[int]]) -> 'Polygon':
        return Polygon(points=[Point(x, y) for x, y in data])
