from dataclasses import dataclass
from typing import Literal
from .bbox import BoundingBox

NodeType = Literal["text", "formula"]

@dataclass
class Node:
    type: NodeType
    bbox: BoundingBox
