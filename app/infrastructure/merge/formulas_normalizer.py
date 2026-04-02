from app.infrastructure.merge.domain.formula import Formula
from app.infrastructure.merge.domain.bbox import BBox
def normalize_formulas(formulas_raw) -> list[Formula]:
    return [
        Formula(
            bbox=BBox(*f["bbox"]),
            latex=f["latex"],
            confidence=f["confidence"]
        )
        for f in formulas_raw
    ]
