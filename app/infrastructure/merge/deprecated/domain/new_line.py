from dataclasses import dataclass, field
from typing import List, Union
from ...domain.bbox import BBox
from .word import Word
from .rle_formula import TextFragment, InlineFormula

LineElement = Union[TextFragment, InlineFormula, Word]

@dataclass
class Line:
    bbox: BBox
    words: List[Word] = field(default_factory=list)
    elements: List[LineElement] = field(default_factory=list)
    angle: float = 0.0

    @property
    def words(self) -> List[Word]:
        return [e for e in self.elements if isinstance(e, Word)]

    @words.setter
    def words(self, value: List[Word]):
        self.elements = value
