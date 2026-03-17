from dataclasses import dataclass
from app.domain.bbox import BoundingBox

@dataclass
class Formula:
    bbox: BoundingBox
    latex: str
