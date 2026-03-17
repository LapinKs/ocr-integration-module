import json
import io
from PyPDF2 import PdfReader, PdfWriter

from app.application.merge.merge_formulas import merge_formulas_into_ocr
from app.infrastructure.pdf.ocr_json_to_pdf import ocr_json_to_pdf
from app.infrastructure.providers import create_formula_service
from app.core.config import OCR_JSON_PATH


class Pipeline:

    def __init__(self):
        self.formula_service = create_formula_service()

    def process(self, images: list[bytes]) -> bytes:

        writer = PdfWriter()

        for image_bytes in images:

            page_pdf = self._process_single(image_bytes)

            reader = PdfReader(io.BytesIO(page_pdf))

            for page in reader.pages:
                writer.add_page(page)

        output = io.BytesIO()
        writer.write(output)
        output.seek(0)

        return output.read()

    def _process_single(self, image_bytes: bytes) -> bytes:

        # OCR JSON заглушка
        with open(OCR_JSON_PATH, "r", encoding="utf-8") as f:
            json_ocr = json.load(f)

        formulas = self.formula_service.process_bytes(image_bytes)

        merged = merge_formulas_into_ocr(json_ocr, formulas)

        pdf_bytes = ocr_json_to_pdf(
            json.dumps(merged, ensure_ascii=False)
        )

        return pdf_bytes


def build_pipeline():
    return Pipeline()



# import tempfile
# import os

# class Pipeline:

#     def process_bytes(self, image_bytes: bytes) -> bytes:

#         with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
#             tmp.write(image_bytes)
#             image_path = tmp.name

#         pdf_path = self.process(image_path)

#         with open(pdf_path, "rb") as f:
#             pdf_bytes = f.read()

#         os.remove(image_path)

#         return pdf_bytes
