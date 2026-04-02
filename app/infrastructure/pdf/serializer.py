from reportlab.pdfgen import canvas
import warnings
warnings.filterwarnings("ignore", category=RuntimeWarning, module="matplotlib")
warnings.filterwarnings("ignore", category=UserWarning, module="matplotlib")
from reportlab.pdfbase import pdfmetrics
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.ttfonts import TTFont
from pathlib import Path
from reportlab.lib.utils import ImageReader
from io import BytesIO
from PIL import Image
import matplotlib as mpl
mpl.use('Agg')
mpl.rcParams['mathtext.fontset'] = 'stix'
import matplotlib.pyplot as plt
FONT_PATH = Path(__file__).parent.parent.parent / "fonts" / "DejaVuSans.ttf"
pdfmetrics.registerFont(TTFont("DejaVu", str(FONT_PATH)))
mpl.rcParams["text.usetex"] = True
mpl.rcParams["text.latex.preamble"] = r"""
\usepackage{amsmath}
\usepackage{amssymb}
"""

def render_page_to_pdf(page: Page) -> bytes:
    buffer = BytesIO()


    pdf_w, pdf_h = A4

    scale = min(
        pdf_w / page.width,
        pdf_h / page.height
    )

    offset_x = (pdf_w - page.width * scale) / 2
    offset_y = (pdf_h - page.height * scale) / 2
    c = canvas.Canvas(buffer, pagesize=(pdf_w, pdf_h))
    for line in page.lines:
        angle = line.angle
        if all(w.bbox.x1 == line.words[0].bbox.x1 for w in line.words):

            text = " ".join(w.text for w in line.words)
            x = offset_x + line.bbox.x1 * scale
            y = offset_y + (page.height - line.bbox.y2) * scale
            c.drawString(x, y, text)
            continue
        else:

            for w in line.words:
                x = offset_x + w.bbox.x1 * scale
                y = offset_y + (page.height - w.bbox.y2) * scale
                bbox_w = (w.bbox.x2 - w.bbox.x1) * scale
                font_size = max(6, int(bbox_w / max(len(w.text), 1) * 1.4))
                # font_size = max(6, int((w.bbox.y2 - w.bbox.y1) * scale * 0.45))
                c.setFont("DejaVu", font_size)
                c.drawString(x, y, w.text)

    # for f in page.formulas:
    #     x = offset_x + f.bbox.x1 * scale
    #     y = offset_y + (page.height - f.bbox.y2) * scale
    #     w = (f.bbox.x2 - f.bbox.x1) * scale
    #     h = (f.bbox.y2 - f.bbox.y1) * scale
    #     if f.latex not in "":
    #         c.setStrokeColorRGB(1, 0, 0)
    #         c.setLineWidth(1)
    #         c.rect(x, y, w, h)
    #         c.setStrokeColorRGB(0, 0, 0)

    #     img = render_latex_block(f.latex)

    #     c.drawImage(
    #         ImageReader(img),
    #         x,
    #         y,
    #         width=w*0.95,
    #         height=h*0.95,
    #         preserveAspectRatio=True,
    #         mask='auto'
    #     )
    for f in page.formulas:
        x = offset_x + f.bbox.x1 * scale
        y = offset_y + (page.height - f.bbox.y2) * scale
        w = (f.bbox.x2 - f.bbox.x1) * scale
        h = (f.bbox.y2 - f.bbox.y1) * scale

        # Пробуем отрендерить формулу
        try:
            img = render_latex_block(f.latex)
            # Если дошли сюда — ошибки нет, рисуем и рамку, и формулу
            c.setStrokeColorRGB(1, 0, 0)
            c.setLineWidth(1)
            c.rect(x, y, w, h)
            c.setStrokeColorRGB(0, 0, 0)
            c.drawImage(
                ImageReader(img),
                x, y,
                width=w*0.95, height=h*0.95,
                preserveAspectRatio=True,
                mask='auto'
            )
        except Exception:
            # Ошибка — ничего не рисуем (ни рамки, ни формулы)
            pass

    c.save()
    buffer.seek(0)
    return buffer.read()

def render_latex_block(latex: str, dpi=300):
    fig = plt.figure()
    fig.patch.set_alpha(0)

    if not (latex.startswith("$") or latex.startswith(r"\[")):
        latex = rf"\[{latex}\]"

    text = fig.text(0, 0, latex, fontsize=20)

    fig.canvas.draw()
    bbox = text.get_window_extent()

    width, height = bbox.size / dpi
    fig.set_size_inches(width, height)

    buf = BytesIO()
    plt.axis("off")
    plt.savefig(buf, dpi=dpi, bbox_inches="tight", pad_inches=0.01, transparent=True)
    plt.close(fig)

    buf.seek(0)
    return Image.open(buf)
