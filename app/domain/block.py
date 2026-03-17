from dataclasses import dataclass
from typing import List
from .node import Node

@dataclass
class Block:
    type: str
    nodes: List[Node]
