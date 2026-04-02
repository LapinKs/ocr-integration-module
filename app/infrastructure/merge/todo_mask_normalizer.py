
from app.infrastructure.merge.domain.formula import Formula
from app.infrastructure.merge.domain.bbox import BBox

def normalize_formulas_with_masks(formulas_raw: list[dict]) -> list[Formula]:

    result = []
    for f in formulas_raw:
        bbox = f["bbox"]
        formula = Formula(
            bbox=BBox(bbox[0], bbox[1], bbox[2], bbox[3]),
            latex=f["latex"],
            confidence=f["confidence"]
        )

        if "mask" in f:
            formula.mask = f["mask"]
            formula.mask_shape = f.get("mask_shape", (bbox[3], bbox[2]))
        result.append(formula)
    return result
