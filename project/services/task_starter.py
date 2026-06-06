from .celery_app import celery_app

def start_segmentation_task(task_id: str, page_index: int, image_bytes: bytes):
    celery_app.send_task(
        # 'services.segmentation_alt.worker.process_segmentation',
        'services.segmentation.worker.process_segmentation',
        args=[task_id, page_index, image_bytes],
        queue='segmentation'
    )


def start_ocr_task(task_id: str, page_index: int, image_bytes: bytes):
    celery_app.send_task(
        'services.ocr.worker.process_ocr',
        args=[task_id, page_index, image_bytes],
        queue='ocr'
    )


def start_merge_task(task_id: str, page_index: int):
    celery_app.send_task(
        'services.merge.worker.merge_sync',
        args=[task_id, page_index],
        queue='merge'
    )


def start_pdf_task(task_id: str, page_index: int):
    celery_app.send_task(
        'services.pdf.worker.generate_pdf',
        args=[task_id, page_index],
        queue='pdf'
    )


def start_recognition_task(task_id: str, page_index: int):
    celery_app.send_task(
        # 'services.recognition_old.worker.process_segmentation',
        'services.recognition.worker.recognize_batch',
        args=[task_id, page_index],
        queue='recognition'
    )
