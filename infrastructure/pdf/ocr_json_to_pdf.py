from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.ttfonts import TTFont
from pathlib import Path
import json
FONT_PATH = Path(__file__).parent.parent.parent / "fonts" / "DejaVuSans.ttf"

pdfmetrics.registerFont(TTFont("DejaVu", str(FONT_PATH)))

def ocr_json_to_pdf(json_text: str, output_path: str):
    data = json.loads(json_text)
    page = data["node"]

    ocr_w = float(page["@W"])
    ocr_h = float(page["@H"])

    pdf_w, pdf_h = A4
    scale_x = pdf_w / ocr_w
    scale_y = pdf_h / ocr_h

    c = canvas.Canvas(output_path, pagesize=A4)

    def draw_word(word):
        text = word.get("#text", "")
        if not text:
            return

        x = float(word["@X"]) * scale_x
        y_ocr = float(word["@Y"])
        h = float(word["@H"])

        y = pdf_h - (y_ocr + h) * scale_y

        c.setFont("DejaVu", 8)
        c.drawString(x, y, text)

    def walk(node):
        if isinstance(node, dict):
            if node.get("@type") == "RIL_WORD":
                draw_word(node)

            for v in node.values():
                walk(v)

        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(page)
    c.save()
