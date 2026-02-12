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

def intersects(a: dict, b: dict) -> bool:
    return not (
        a["x2"] <= b["x1"] or
        a["x1"] >= b["x2"] or
        a["y2"] <= b["y1"] or
        a["y1"] >= b["y2"]
    )

def merge_formulas_into_ocr(ocr: dict, formulas: list[dict]) -> dict:
    page = ocr["node"]
    nodes = page["node"]

    remaining_nodes = nodes[:]
    formula_nodes = []

    for f in formulas:
        fb = {
            "x1": f["bbox"][0],
            "y1": f["bbox"][1],
            "x2": f["bbox"][2],
            "y2": f["bbox"][3],
        }

        remaining_nodes = [
            n for n in remaining_nodes
            if not (
                n.get("@type") in {"RIL_TEXTLINE", "RIL_WORD"} and
                intersects(
                    {
                        "x1": int(n["@X"]),
                        "y1": int(n["@Y"]),
                        "x2": int(n["@X"]) + int(n["@W"]),
                        "y2": int(n["@Y"]) + int(n["@H"]),
                    },
                    fb
                )
            )
        ]

        formula_nodes.append({
            "@type": "RIL_FORMULA",
            "@X": str(fb["x1"]),
            "@Y": str(fb["y1"]),
            "@W": str(fb["x2"] - fb["x1"]),
            "@H": str(fb["y2"] - fb["y1"]),
            "@cnf": str(int(f["confidence"] * 100)),
            "#latex": f["latex"]
        })

    page["node"] = sorted(
        remaining_nodes + formula_nodes,
        key=lambda n: (int(n["@Y"]), int(n["@X"]))
    )

    return ocr
