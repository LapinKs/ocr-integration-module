from domain.item import DocumentItem
from domain.text import TextBlock
from domain.formula import Formula

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

def document_items_to_pdf(items, output_path):
    pdf_w, pdf_h = A4
    c = canvas.Canvas(output_path, pagesize=A4)
    c.setFont("Helvetica", 10)

    for item in items:
        x = item.bbox.x1
        y = pdf_h - item.bbox.y2
        text = getattr(item, "text", getattr(item, "latex", ""))
        c.drawString(x, y, text)

    c.save()



def merge_text_and_formulas(
    texts: list[TextBlock],
    formulas: list[Formula]
) -> list[DocumentItem]:

    items: list[DocumentItem] = texts[:]

    for formula in formulas:
        items = [
            item for item in items
            if not item.bbox.intersects(formula.bbox)
        ]
        items.append(formula)

    items.sort(key=lambda i: (i.bbox.y1, i.bbox.x1))

    return items
