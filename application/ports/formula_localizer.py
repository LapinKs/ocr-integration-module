from abc import ABC, abstractmethod
from typing import List, Dict


class FormulaLocalizer(ABC):

    @abstractmethod
    def detect(self, image_path: str) -> List[Dict]:
        """
        Возвращает список регионов формул.
        Каждый регион: {x1, y1, x2, y2, confidence}
        """
        pass
