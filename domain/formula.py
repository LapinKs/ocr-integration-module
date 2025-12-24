from dataclasses import dataclass
from domain.bbox import BoundingBox

@dataclass
class Formula:
    bbox: BoundingBox
    latex: str
