from dataclasses import dataclass
from app.domain.bbox import BoundingBox

@dataclass
class TextBlock:
    text: str
    bbox: BoundingBox
