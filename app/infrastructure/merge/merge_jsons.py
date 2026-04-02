from app.infrastructure.merge.domain.formula import Formula
from app.infrastructure.merge.domain.page import Page

def merge(page: Page, formulas: list[Formula]) -> Page:

    for f in formulas:
        added = False
        for line in page.lines:
            if not line.bbox.intersects(f.bbox):
                continue
            original_count = len(line.words)
            line.words = [
                w for w in line.words
                if w.bbox.intersection_area(f.bbox) == 0
            ]
            added = True
        if added:
            page.formulas.append(f)
        else:
            page.formulas.append(f)

    return page
