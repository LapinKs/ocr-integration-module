from abc import ABC, abstractmethod

class OCRClientPort(ABC):

    @abstractmethod
    async def recognize_many(self, images: list[bytes]) -> list[dict]:
        pass
