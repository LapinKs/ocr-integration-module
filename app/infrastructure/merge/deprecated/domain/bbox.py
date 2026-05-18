from dataclasses import dataclass
@dataclass
class BBox:
    x1: int
    y1: int
    x2: int
    y2: int
    @property
    def w(self):
        return self.x2 - self.x1
    @property
    def h(self):
        return self.y2 - self.y1
    @property
    def area(self):
        return max(0, self.w) * max(0, self.h)

    def intersects(self, other: "BBox") -> bool:
        return not (
            self.x2 <= other.x1 or
            self.x1 >= other.x2 or
            self.y2 <= other.y1 or
            self.y1 >= other.y2
        )
    def intersection_area(self, other: "BBox") -> int:
        if not self.intersects(other):
            return 0
        x1 = max(self.x1, other.x1)
        y1 = max(self.y1, other.y1)
        x2 = min(self.x2, other.x2)
        y2 = min(self.y2, other.y2)
        return max(0, x2 - x1) * max(0, y2 - y1)

    def iou(self, other: "BBox") -> float:
        inter = self.intersection_area(other)
        union = self.area + other.area - inter
        return inter / union if union > 0 else 0.0
