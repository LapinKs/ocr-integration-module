from dataclasses import dataclass
from typing import List
from .block import Block

@dataclass
class Page:
    number: int
    width: int
    height: int
    blocks: List[Block]
