from dataclasses import dataclass
from typing import List
from .page import Page

@dataclass
class Document:
    pages: List[Page]
