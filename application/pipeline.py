from infrastructure.ocr.parser import parse_ocr_page
from infrastructure.formula.parser import parse_formula_regions
from application.merge_formulas import merge_text_and_formulas


def process_image(
    image_path: str,
    ocr_client,
    layout_client,
    latex_ocr_client
):
    ocr_pages = ocr_client.recognize(image_path)

    texts = []
    for page in ocr_pages:
        texts.extend(parse_ocr_page(page))

    formula_regions = layout_client.detect_formulas(image_path)

    latex_results = latex_ocr_client.recognize(
        image_path,
        formula_regions
    )

    formulas = parse_formula_regions(latex_results)

    return merge_text_and_formulas(texts, formulas)
