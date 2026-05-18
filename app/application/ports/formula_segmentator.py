from abc import ABC, abstractmethod
from typing import List, Dict

class FormulaSegmentator(ABC):

    @abstractmethod
    def detect(self, image_path: str) -> List[Dict]:
        pass
