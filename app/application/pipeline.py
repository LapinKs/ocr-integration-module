from app.infrastructure.providers import create_formula_service
from app.infrastructure.providers import create_ocr_client
from app.infrastructure.merge.ocr_json_normalizer import ocr_json_to_page
from app.infrastructure.merge.formulas_normalizer import normalize_formulas
from app.infrastructure.merge.merge_jsons import merge
from app.infrastructure.pdf.serializer import render_page_to_pdf
from app.infrastructure.merge.coordinate_normalizer import rescale_formulas
from PyPDF2 import PdfReader, PdfWriter
import asyncio
import io
import time


class Pipeline:

    def __init__(self):
        self.formula_service = create_formula_service()
        self.ocr_service = create_ocr_client()

    async def process(self, images: list[bytes]) -> bytes:

        writer = PdfWriter()
        time_start = time.time()
        ocr_results, (formulas_list,sizes) = await asyncio.gather(
            self.ocr_service.recognize_many(images),
            self.formula_service.process_batch(images)
        )
        for formulas, json_ocr, (img_w, img_h) in zip(formulas_list, ocr_results, sizes):

            page = ocr_json_to_page(json_ocr)
            ocr_w, ocr_h = page.width, page.height
            formulas = rescale_formulas(formulas, (img_w,img_h),(ocr_w,ocr_h))
            formulas_domain = normalize_formulas(formulas)

            merged_page = merge(page, formulas_domain)

            pdf_bytes = render_page_to_pdf(merged_page)

            reader = PdfReader(io.BytesIO(pdf_bytes))

            for p in reader.pages:
                writer.add_page(p)

        output = io.BytesIO()
        writer.write(output)
        output.seek(0)
        print(f"Total time: {time.time() - time_start:.2f} seconds")
        return output.read()

def build_pipeline():
    return Pipeline()
