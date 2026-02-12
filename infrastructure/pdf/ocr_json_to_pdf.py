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


def render_latex_to_image(latex: str, dpi=200) -> Image.Image:
    fig = plt.figure()
    fig.patch.set_alpha(0)

    text = fig.text(
        0,
        0,
        f"${latex}$",
        fontsize=20
    )

    fig.canvas.draw()
    bbox = text.get_window_extent()

    width, height = bbox.size / dpi
    fig.set_size_inches(width, height)

    buf = BytesIO()
    plt.axis("off")
    plt.savefig(buf, dpi=dpi, format="png", bbox_inches="tight", pad_inches=0.05, transparent=True)
    plt.close(fig)

    buf.seek(0)
    return Image.open(buf)


def sanitize_latex(latex: str) -> str:
    latex = latex.strip()
    while latex.startswith("{") and latex.endswith("}"):
        latex = latex[1:-1].strip()

    latex = latex.replace(r"\left\{", r"\left\{")
    if r"\left\{" in latex and r"\right\}" not in latex:
        latex = latex.replace(r"\left\{", r"\left\{") + r"\right\}"

    latex = latex.replace(r"\right.", r"\right\}")

    latex = re.sub(r"\{\s*\}", "", latex)

    latex = re.sub(r"\{\s*_\{\s*\}\s*\}", "", latex)
    latex = re.sub(r"\{\s*\^\{\s*\}\s*\}", "", latex)

    latex = latex.replace(r"\mathrm{sin}", r"\sin")
    latex = latex.replace(r"\mathrm{cos}", r"\cos")

    latex = latex.replace(r"{}_{}", "")
    latex = latex.replace(r"{}_{}", "")

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



def normalize_latex_for_mathtext(latex: str) -> list[str]:
    if "\\begin{array}" not in latex:
        return [latex]

    body = re.search(
        r"\\begin\{array\}\{.*?\}(.*?)\\end\{array\}",
        latex,
        re.S
    )

    if not body:
        return [latex]

    content = body.group(1)

    lines = [
        l.strip("{} ")
        for l in content.split("\\\\")
        if l.strip()
    ]

    return lines


def draw_formula_image(c, img, x, y, w, h):
    img = img.resize((int(w), int(h)))
    c.drawImage(
        ImageReader(img),
        x,
        y,
        width=w,
        height=h,
        mask="auto"
    )


def ocr_json_to_pdf(json_text: str, output_path: str):
    data = json.loads(json_text)
    page = data["node"]

    ocr_w = float(page["@W"])
    ocr_h = float(page["@H"])

    pdf_w, pdf_h = A4
    scale_x = pdf_w / ocr_w
    scale_y = pdf_h / ocr_h

    c = canvas.Canvas(output_path, pagesize=A4)
    def draw_formula(node):
        latex = node.get("#latex", "")
        latex = sanitize_latex(latex)
        if not latex:
            return

        x = float(node["@X"]) * scale_x
        y = pdf_h - (float(node["@Y"]) + float(node["@H"])) * scale_y
        w = float(node["@W"]) * scale_x
        h = float(node["@H"]) * scale_y

        if "\\begin{array}" in latex:
            lines = normalize_latex_for_mathtext(latex)
            line_h = h / max(len(lines), 1)

            for i, line in enumerate(lines):
                try:
                    img = render_latex_block(sanitize_latex(line))
                    draw_formula_image(
                        c,
                        img,
                        x,
                        y + h - (i + 1) * line_h,
                        w,
                        line_h
                    )
                except Exception as e:
                    print("LATEX LINE ERROR:", line)
            return

        try:
            img = render_latex_block(latex)
            draw_formula_image(c, img, x, y, w, h)
        except Exception as e:
            print("LATEX ERROR:", latex)
            c.setFont("DejaVu", 8)
            c.drawString(x, y, "[LATEX ERR]")




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
