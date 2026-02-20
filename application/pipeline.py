from application.services.formula_service import FormulaService
from application.merge_formulas import merge_formulas_into_ocr


def process_image(image_path: str, ocr_json: dict, formula_service: FormulaService):
    formulas = formula_service.process(image_path)
    merged = merge_formulas_into_ocr(ocr_json, formulas)
    return merged
