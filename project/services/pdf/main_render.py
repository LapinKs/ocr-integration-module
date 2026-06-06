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
import numpy as np

DRAW_FORMULA_BORDER = False
DRAW_FORMULA_PLACEHOLDER = False
DRAW_PICTURES = False
DRAW_TABLES = False
DRAW_TABLE_CELL_BACKGROUND = False
DRAW_WORD_BBOX = False

DEFAULT_FONT = "DejaVu"
FONT_PATH = Path(__file__).parent.parent.parent / "fonts" / "DejaVuSans.ttf"
pdfmetrics.registerFont(TTFont("DejaVu", str(FONT_PATH)))

mpl.rcParams["text.usetex"] = True
mpl.rcParams["text.latex.preamble"] = r"""
\usepackage{amsmath}
\usepackage{amssymb}
"""


class TreePDFRenderer:

    def __init__(self, font_name: str = "DejaVu"):
        self.font_name = font_name
        self.page_width = 0
        self.page_height = 0
        self.scale = 1.0
        self.offset_x = 0
        self.offset_y = 0

    def render(self, page_node, page_width: int, page_height: int) -> bytes:
        buffer = BytesIO()
        pdf_w, pdf_h = A4

        self.page_width = page_width
        self.page_height = page_height
        self.scale = min(pdf_w / page_width, pdf_h / page_height)
        self.offset_x = (pdf_w - page_width * self.scale) / 2
        self.offset_y = (pdf_h - page_height * self.scale) / 2

        c = canvas.Canvas(buffer, pagesize=(pdf_w, pdf_h))

        self._render_node(c, page_node)

        c.save()
        buffer.seek(0)
        return buffer.read()

    def _render_node(self, c: canvas.Canvas, node):
        node_type = node.type

        if node_type == "RIL_WORD":
            self._render_word(c, node)

        elif node_type == "RIL_TEXTLINE":
            self._render_textline(c, node)

        elif node_type == "RIL_FORMULA":
            self._render_formula(c, node)

        elif node_type in ["RIL_PAGE", "RIL_TEXT", "RIL_BLOCK", "RIL_LIST_ITEM",
                          "RIL_SECTION_HEADER", "RIL_PAGE_HEADER", "RIL_PAGE_FOOTER"]:
            sorted_children = sorted(node.children, key=lambda n: n.bbox.y1)
            for child in sorted_children:
                self._render_node(c, child)

        elif node_type == "RIL_TABLE" and DRAW_TABLES:
            self._render_table(c, node)

        elif node_type == "RIL_TABLE_CELL" and DRAW_TABLES:
            self._render_table_cell(c, node)

        elif node_type == "RIL_PICTURE" and DRAW_PICTURES:
            self._render_picture(c, node)

        else:
            for child in node.children:
                self._render_node(c, child)

    def _render_word_bbox(self, c: canvas.Canvas, word_node):

        x = self.offset_x + word_node.bbox.x1 * self.scale
        y = self.offset_y + (self.page_height - word_node.bbox.y2) * self.scale
        w = (word_node.bbox.x2 - word_node.bbox.x1) * self.scale
        h = (word_node.bbox.y2 - word_node.bbox.y1) * self.scale


        c.setStrokeColorRGB(1, 0, 0)
        c.setLineWidth(1)
        c.rect(x, y, w, h)
        c.setStrokeColorRGB(0, 0, 0)


    def _render_word(self, c: canvas.Canvas, word_node):
        text = word_node.data.get("#text", "")
        if not text:
            return

        x = self.offset_x + word_node.bbox.x1 * self.scale
        y = self.offset_y + (self.page_height - word_node.bbox.y2) * self.scale
        if DRAW_WORD_BBOX:
            w = (word_node.bbox.x2 - word_node.bbox.x1) * self.scale
            h = (word_node.bbox.y2 - word_node.bbox.y1) * self.scale
            c.setStrokeColorRGB(0, 1, 0)
            c.setLineWidth(1)
            c.rect(x, y, w, h)
            c.setStrokeColorRGB(0, 0, 0)
        word_width_px = word_node.bbox.x2 - word_node.bbox.x1
        bbox_w = word_width_px * self.scale
        font_size = max(6, int(bbox_w / max(len(text), 1) * 1.3))

        c.setFillColorRGB(0, 0, 0)
        c.setFont("DejaVu", font_size)
        c.drawString(x, y, text)


    def _render_textline(self, c: canvas.Canvas, line_node):
        if not line_node.children:
            return
        words = sorted([w for w in line_node.children if w.type == "RIL_WORD"],
                    key=lambda w: w.bbox.x1)
        if not words:
            return
        for word in words:
            if word.type == "RIL_WORD":
                self._render_word(c, word)


    def _render_mask_overlay(self, mask: np.ndarray) -> Image.Image:
        from PIL import Image
        rgba = np.zeros((mask.shape[0], mask.shape[1], 4), dtype=np.uint8)
        rgba[..., 0] = 255
        rgba[..., 3] = (mask > 0) * 120
        return Image.fromarray(rgba, 'RGBA')


    def _render_formula(self, c: canvas.Canvas, formula_node):
        x = self.offset_x + formula_node.bbox.x1 * self.scale
        y = self.offset_y + (self.page_height - formula_node.bbox.y2) * self.scale
        w = (formula_node.bbox.x2 - formula_node.bbox.x1) * self.scale
        h = (formula_node.bbox.y2 - formula_node.bbox.y1) * self.scale
        mask = formula_node.data.get("mask")
        if mask is not None:
            img = self._render_mask_overlay(mask)
            c.drawImage(
                ImageReader(img),
                self.offset_x,
                self.offset_y,
                width=self.page_width * self.scale,
                height=self.page_height * self.scale,
                mask='auto'
            )
        latex = formula_node.data.get('latex') or formula_node.data.get('LaTeX')

        if latex:
            try:
                img = self._render_latex_block(latex)
                if DRAW_FORMULA_BORDER:
                    c.setStrokeColorRGB(0, 0, 0)
                c.drawImage(
                    ImageReader(img),
                    x, y,
                    width=w * 0.95,
                    height=h * 0.95,
                    preserveAspectRatio=True,
                    mask='auto'
                )
            except Exception:
                if DRAW_FORMULA_PLACEHOLDER:
                    self._render_formula_placeholder(c, x, y, w, h, latex)
        else:
            if DRAW_FORMULA_PLACEHOLDER:
                self._render_formula_placeholder(c, x, y, w, h)

    def _render_formula_placeholder(self, c: canvas.Canvas, x: float, y: float,
                                     w: float, h: float, latex: str = None):
        c.setFillColorRGB(0, 0, 0)
        c.setFont("DejaVu", 10)

        if latex:
            display_text = latex[:40] + "..." if len(latex) > 40 else latex
            c.drawCentredString(x + w/2, y + h/2, f"[Formula: {display_text}]")
        else:
            c.drawCentredString(x + w/2, y + h/2, "[Formula]")

    def _render_latex_block(self, latex: str, dpi: int = 150) -> Image.Image:
        fig = plt.figure(figsize=(0.01, 0.01))
        fig.patch.set_alpha(0)

        if not (latex.startswith("$") or latex.startswith(r"\[")):
            if any(c in latex for c in ['\\int', '\\sum', '\\frac', '\\begin', '\\lim']):
                latex = r"\[ " + latex + r" \]"
            else:
                latex = r"$" + latex + r"$"

        text = fig.text(0, 0, latex, fontsize=14, color='black')

        fig.canvas.draw()
        bbox = text.get_window_extent()

        width, height = bbox.width / dpi, bbox.height / dpi
        fig.set_size_inches(width + 0.1, height + 0.1)

        buf = BytesIO()
        plt.axis("off")
        plt.savefig(buf, dpi=dpi, bbox_inches="tight", pad_inches=0.02, transparent=True)
        plt.close(fig)

        buf.seek(0)
        return Image.open(buf)


    def _render_table(self, c: canvas.Canvas, table_node):
        x = self.offset_x + table_node.bbox.x1 * self.scale
        y = self.offset_y + (self.page_height - table_node.bbox.y2) * self.scale
        w = (table_node.bbox.x2 - table_node.bbox.x1) * self.scale
        h = (table_node.bbox.y2 - table_node.bbox.y1) * self.scale

        c.setStrokeColorRGB(0, 0, 0)
        c.setLineWidth(1)
        c.rect(x, y, w, h)

        cells = [c for c in table_node.children if c.type == "RIL_TABLE_CELL"]
        for cell in cells:
            self._render_node(c, cell)


    def _render_table_cell(self, c: canvas.Canvas, cell_node):
        x = self.offset_x + cell_node.bbox.x1 * self.scale
        y = self.offset_y + (self.page_height - cell_node.bbox.y2) * self.scale
        w = (cell_node.bbox.x2 - cell_node.bbox.x1) * self.scale
        h = (cell_node.bbox.y2 - cell_node.bbox.y1) * self.scale

        if DRAW_TABLE_CELL_BACKGROUND:
            c.setFillColorRGB(0.98, 0.98, 0.98)
            c.rect(x, y, w, h, fill=1)

        for child in cell_node.children:
            self._render_node(c, child)


    def _render_picture(self, c: canvas.Canvas, picture_node):
        x = self.offset_x + picture_node.bbox.x1 * self.scale
        y = self.offset_y + (self.page_height - picture_node.bbox.y2) * self.scale
        w = (picture_node.bbox.x2 - picture_node.bbox.x1) * self.scale
        h = (picture_node.bbox.y2 - picture_node.bbox.y1) * self.scale

        c.setFillColorRGB(0.9, 0.95, 1.0)
        c.rect(x, y, w, h, fill=1)

        c.setStrokeColorRGB(0, 0, 0)
        c.setLineWidth(1)
        c.rect(x, y, w, h)

        c.setFillColorRGB(0, 0, 0)
        c.setFont("DejaVu", 12)
        c.drawCentredString(x + w/2, y + h/2, "[Image]")


def render_page_to_pdf(page_node, page_width: int, page_height: int) -> bytes:
    renderer = TreePDFRenderer()
    return renderer.render(page_node, page_width, page_height)


def render_legacy_page_to_pdf(page) -> bytes:
    from app.infrastructure.merge.domain.node import Node
    from app.infrastructure.merge.domain.bbox import BBox
    page_node = Node(
        type="RIL_PAGE",
        bbox=BBox(0, 0, page.width, page.height),
        data={"@W": str(page.width), "@H": str(page.height)}
    )

    for line in page.lines:
        line_node = Node(
            type="RIL_TEXTLINE",
            bbox=BBox(line.bbox.x1, line.bbox.y1, line.bbox.x2, line.bbox.y2),
            data={"@angle": str(line.angle)}
        )

        for word in line.words:
            word_node = Node(
                type="RIL_WORD",
                bbox=BBox(word.bbox.x1, word.bbox.y1, word.bbox.x2, word.bbox.y2),
                data={"#text": word.text}
            )
            line_node.add_child(word_node)

        page_node.add_child(line_node)

    for formula in page.formulas:
        formula_node = Node(
            type="RIL_FORMULA",
            bbox=BBox(formula.bbox.x1, formula.bbox.y1, formula.bbox.x2, formula.bbox.y2),
            data={"latex": formula.latex}
        )
        page_node.add_child(formula_node)

    return render_page_to_pdf(page_node, page.width, page.height)
