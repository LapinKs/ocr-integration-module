from application.ports.formula_localizer import FormulaLocalizer
from application.ports.formula_recognizer import FormulaRecognizer


class FormulaService:

    def __init__(
        self,
        localizer: FormulaLocalizer,
        recognizer: FormulaRecognizer
    ):
        self.localizer = localizer
        self.recognizer = recognizer

    def process(self, image_path: str):
        regions = self.localizer.detect(image_path)
        formulas = self.recognizer.recognize(image_path, regions)
        return formulas
