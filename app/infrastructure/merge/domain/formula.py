from dataclasses import dataclass
from .bbox import BBox

@dataclass
class Formula:
    bbox: BBox
    latex: str
    confidence: float

# from dataclasses import dataclass
# from typing import Optional, Dict, Any
# from .bbox import BBox

# @dataclass
# class Formula:
#     bbox: BBox
#     latex: str
#     confidence: float
#     mask: Optional[Dict[str, Any]] = None
#     mask_shape: Optional[tuple] = None
