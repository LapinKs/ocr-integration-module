from dataclasses import dataclass
from .bbox import BBox

@dataclass
class Formula:
    bbox: BBox
    latex: str
    confidence: float
