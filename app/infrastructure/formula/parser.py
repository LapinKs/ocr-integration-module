from app.domain.formula import Formula
from app.domain.bbox import BoundingBox


def parse_formula_regions(raw: list[dict]) -> list[Formula]:
    formulas = []

    for r in raw:
        bbox = BoundingBox(*r["bbox"])

        formulas.append(
            Formula(
                bbox=bbox,
                latex=r["latex"],
                confidence=r.get("confidence", 1.0)
            )
        )

    return formulas
