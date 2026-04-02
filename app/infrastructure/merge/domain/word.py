from dataclasses import dataclass
from .bbox import BBox

@dataclass
class Word:
    bbox: BBox
    text: str
