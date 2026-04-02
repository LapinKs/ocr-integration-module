def rescale_formulas(formulas, img_size, ocr_size):
    img_w, img_h = img_size
    ocr_w, ocr_h = ocr_size

    scale_x = ocr_w / img_w
    scale_y = ocr_h / img_h

    rescaled = []

    for f in formulas:
        x1, y1, x2, y2 = f["bbox"]

        new_bbox = [
            int(x1 * scale_x),
            int(y1 * scale_y),
            int(x2 * scale_x),
            int(y2 * scale_y),
        ]

        rescaled.append({
            **f,
            "bbox": new_bbox
        })

    return rescaled

# def rescale_formulas(formulas, img_size, ocr_size):
#     img_w, img_h = img_size
#     ocr_w, ocr_h = ocr_size

#     scale_x = ocr_w / img_w
#     scale_y = ocr_h / img_h

#     rescaled = []
#     for f in formulas:
#         x1, y1, x2, y2 = f["bbox"]
#         new_bbox = [
#             int(x1 * scale_x),
#             int(y1 * scale_y),
#             int(x2 * scale_x),
#             int(y2 * scale_y),
#         ]

#         result = {**f, "bbox": new_bbox}


#         if "mask" in f:
#             result["mask"] = f["mask"]
#             result["mask_shape"] = (img_h, img_w)

#         rescaled.append(result)

#     return rescaled
