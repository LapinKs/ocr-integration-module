from abc import ABC, abstractmethod

class OCRClientPort(ABC):

    @abstractmethod
    def recognize_many(self, image_paths: list[str]) -> list[dict]:
        pass
