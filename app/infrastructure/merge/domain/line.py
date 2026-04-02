from dataclasses import dataclass, field
from .bbox import BBox
from .word import Word
@dataclass
class Line:
    bbox: BBox
    words: list[Word] = field(default_factory=list)
    angle: float = 0.0
