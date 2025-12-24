class FormulaClientStub:
    def detect(self, image_path: str) -> list[dict]:
        return [
            {
                "bbox": [400, 1000, 800, 1100],
                "confidence": 0.93,
                "latex": "12 + 14 = 26"
            }
        ]
