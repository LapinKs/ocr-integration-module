from infrastructure.ocr.parser import parse_ocr_page
from infrastructure.formula.parser import parse_formula_candidates
from application.merge_formulas import merge_text_and_formulas

def process_image(image_path, ocr_client, formula_client):
    ocr_pages = ocr_client.recognize(image_path)

    texts = []
    for page in ocr_pages:
        texts.extend(parse_ocr_page(page))

    raw_formulas = formula_client.detect(image_path)

    formulas = parse_formula_candidates(raw_formulas)

    return merge_text_and_formulas(texts, formulas)
