from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import StreamingResponse
from typing import List
import io

from app.presentation.api.dependencies import get_pipeline

router = APIRouter()


@router.post("/process")
async def process_images(
    files: List[UploadFile],
    pipeline = Depends(get_pipeline)
):

    images = []

    for file in files:

        if not file.content_type.startswith("image"):
            raise HTTPException(400, "Файл должен быть изображением")

        images.append(await file.read())

    pdf_bytes = await pipeline.process(images)

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": "attachment; filename=result.pdf"
        }
    )
