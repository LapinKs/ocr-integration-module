from dataclasses import dataclass
from domain.bbox import BoundingBox

@dataclass
class TextBlock:
    text: str
    bbox: BoundingBox
