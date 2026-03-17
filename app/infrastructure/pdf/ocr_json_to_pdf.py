from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.ttfonts import TTFont
from pathlib import Path
import json
from reportlab.lib.utils import ImageReader
import re
import matplotlib.pyplot as plt
from io import BytesIO
from PIL import Image
FONT_PATH = Path(__file__).parent.parent.parent / "fonts" / "DejaVuSans.ttf"
import matplotlib as mpl
pdfmetrics.registerFont(TTFont("DejaVu", str(FONT_PATH)))
mpl.rcParams["text.usetex"] = True
mpl.rcParams["text.latex.preamble"] = r"""
\usepackage{amsmath}
\usepackage{amssymb}
"""

def sanitize_latex(latex: str) -> str:
    latex = latex.strip()

    if len(latex) > 1000:
        return ""

    if latex.count("{") != latex.count("}"):
        return ""

    if latex.count("\\begin") != latex.count("\\end"):
        return ""

    return latex


def render_latex_block(latex: str, w_px=800, h_px=200, dpi=300):
    fig = plt.figure(figsize=(w_px / dpi, h_px / dpi), dpi=dpi)
    fig.patch.set_alpha(0)

    if not (latex.startswith("$") or latex.startswith(r"\[")):
        latex = rf"\[{latex}\]"

    fig.text(0.5, 0.5, latex, ha="center", va="center", fontsize=20)
    plt.axis("off")

    buf = BytesIO()
    plt.savefig(buf, dpi=dpi, bbox_inches="tight", pad_inches=0.02, transparent=True)
    plt.close(fig)

    buf.seek(0)
    return Image.open(buf)

def draw_formula_image(c, img, x, y, w, h):
    c.drawImage(
        ImageReader(img),
        x,
        y,
        width=w,
        height=h,
        mask="auto"
    )
    img.close()


def ocr_json_to_pdf(json_text: str) -> bytes:
    data = json.loads(json_text)
    page = data["node"]

    ocr_w = float(page["@W"])
    ocr_h = float(page["@H"])

    pdf_w, pdf_h = A4
    scale_x = pdf_w / ocr_w
    scale_y = pdf_h / ocr_h

    buffer = BytesIO()

    c = canvas.Canvas(buffer, pagesize=A4)

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

    def draw_formula(node):
        latex = node.get("#latex", "")
        latex = sanitize_latex(latex)

        if not latex:
            return

        x = float(node["@X"]) * scale_x
        y = pdf_h - (float(node["@Y"]) + float(node["@H"])) * scale_y
        w = float(node["@W"]) * scale_x
        h = float(node["@H"]) * scale_y

        is_inline = float(node["@H"]) < 120

        try:
            if is_inline:
                img = render_latex_inline(latex)
            else:
                img = render_latex_block(latex)

            draw_formula_image(c, img, x, y, w, h)

        except Exception:
            print("LATEX ERROR:", latex)
            c.setFont("DejaVu", 8)
            c.drawString(x, y, "[LATEX ERR]")

    def walk(node):
        if isinstance(node, dict):
            t = node.get("@type")

            if t == "RIL_WORD":
                draw_word(node)

            elif t == "RIL_FORMULA":
                draw_formula(node)

            for v in node.values():
                walk(v)

        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(page)

    c.save()

    buffer.seek(0)

    return buffer.read()

def render_latex_inline(latex: str, dpi=200):
    fig = plt.figure()
    fig.patch.set_alpha(0)

    text = fig.text(0, 0, f"${latex}$", fontsize=14)

    fig.canvas.draw()
    bbox = text.get_window_extent()

    width, height = bbox.size / dpi
    fig.set_size_inches(width, height)

    buf = BytesIO()
    plt.axis("off")
    plt.savefig(buf, dpi=dpi, format="png",
                bbox_inches="tight",
                pad_inches=0.02,
                transparent=True)
    plt.close(fig)

    buf.seek(0)
    return Image.open(buf)
