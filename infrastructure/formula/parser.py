from domain.formula import Formula
from domain.bbox import BoundingBox

def parse_formula_candidates(raw: list[dict]) -> list[Formula]:
    formulas = []

    for item in raw:
        formulas.append(
            Formula(
                bbox=BoundingBox(*item["bbox"]),
                latex=item.get("latex", "[FORMULA]")
            )
        )

    return formulas
