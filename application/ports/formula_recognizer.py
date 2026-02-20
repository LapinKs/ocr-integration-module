from abc import ABC, abstractmethod
from typing import List, Dict


class FormulaRecognizer(ABC):

    @abstractmethod
    def recognize(self, image_path: str, regions: List[Dict]) -> List[Dict]:
        """
        Принимает регионы формул.
        Возвращает список формул:
        {bbox: ..., latex: ...}
        """
        pass
