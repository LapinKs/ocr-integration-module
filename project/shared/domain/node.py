from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from .bbox import BBox


@dataclass(eq=False)
class Node:
    type: str
    bbox: BBox
    children: List["Node"] = field(default_factory=list)
    parent: Optional["Node"] = None
    data: Dict[str, Any] = field(default_factory=dict)


    def __hash__(self):
        return id(self)


    def add_child(self, child: "Node"):
        child.parent = self
        self.children.append(child)


    def remove_child(self, child: "Node"):
        if child in self.children:
            self.children.remove(child)
            child.parent = None


    def get_words(self) -> List["Node"]:
        words = []
        if self.type == "RIL_WORD":
            words.append(self)
        for child in self.children:
            words.extend(child.get_words())
        return words


    def get_text_lines(self) -> List["Node"]:
        lines = []
        if self.type == "RIL_TEXTLINE":
            lines.append(self)
        for child in self.children:
            lines.extend(child.get_text_lines())
        return lines


    def to_dict(self) -> Dict[str, Any]:
        result = dict(self.data)
        result["@X"] = str(self.bbox.x1)
        result["@Y"] = str(self.bbox.y1)
        result["@W"] = str(self.bbox.w)
        result["@H"] = str(self.bbox.h)
        if self.children:
            result["node"] = [child.to_dict() for child in self.children]
        return result
