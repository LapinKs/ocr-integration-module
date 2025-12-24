from infrastructure.ocr.client import OCRClient
from infrastructure.formula.client import FormulaClientStub
from infrastructure.xml.serializer import Serializer
from application.pipline import process_image
from pathlib import Path
from config import OCR_API_KEY, OCR_BASE_URL, IMAGE
from domain.text import TextBlock
from domain.formula import Formula
from domain.bbox import BoundingBox
from application.merge_formulas import merge_text_and_formulas, document_items_to_pdf
import json
from infrastructure.pdf.ocr_json_to_pdf import ocr_json_to_pdf


# def load_stub_for_merge(path: str):
#     with open(path, "r", encoding="utf-8") as f:
#         raw = json.load(f)

#     texts = [
#         TextBlock(
#             text=t["text"],
#             bbox=BoundingBox(**t["bbox"])
#         )
#         for t in raw["texts"]
#     ]

#     formulas = [
#         Formula(
#             latex=f["latex"],
#             bbox=BoundingBox(**f["bbox"])
#         )
#         for f in raw["formulas"]
#     ]

#     return texts, formulas


# def save_text(path: str | Path, content: str):
#     Path(path).parent.mkdir(parents=True, exist_ok=True)
#     with open(path, "w", encoding="utf-8") as f:
#         f.write(content)




def main():
    # ocr = OCRClient(OCR_API_KEY, OCR_BASE_URL)
    # formula = FormulaClientStub()
    # serializer = Serializer()

    # items = process_image(IMAGE, ocr, formula)

    # json_data = serializer.to_json(items)
    # ocr_json_to_pdf(json_data, "out/result.pdf")
    # xml_data = serializer.to_xml(items)
    # save_text("out/result.json", json_data)
    # save_text("out/result.xml", xml_data)
    serializer = Serializer()
    json_path = Path(__file__).parent / "result.json"
    pdf_path = Path(__file__).parent / "result.pdf"

    with open(json_path, "r", encoding="utf-8") as f:
        json_text = f.read()

    ocr_json_to_pdf(json_text, str(pdf_path))
    print("PDF создан:", pdf_path)
    # texts, formulas = load_stub_for_merge("merge.json")
    # items = merge_text_and_formulas(texts, formulas)
    # json_data = serializer.to_json(items)
    # save_text("out/result.json", json_data)
    # document_items_to_pdf(json_data, "result2.pdf")



if __name__ == "__main__":
    main()
