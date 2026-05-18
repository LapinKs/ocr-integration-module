from dataclasses import dataclass, field
from .line import Line
from .formula import Formula

@dataclass
class Page:
    width: int
    height: int
    lines: list[Line] = field(default_factory=list)
    formulas: list[Formula] = field(default_factory=list)
