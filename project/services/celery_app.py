from celery import Celery
import os
REDIS_URL = os.environ.get('REDIS_URL', 'redis://redis:6379/0')
celery_app = Celery('formula_ocr', broker=REDIS_URL, backend=REDIS_URL)

celery_app.conf.task_queues = {
    'segmentation': {'exchange': 'segmentation', 'routing_key': 'segmentation'},
    'recognition': {'exchange': 'recognition', 'routing_key': 'recognition'},
    'merge': {'exchange': 'merge', 'routing_key': 'merge'},
    'ocr': {'exchange': 'ocr', 'routing_key': 'ocr'},
    'pdf': {'exchange': 'pdf', 'routing_key': 'pdf'},
}

celery_app.conf.task_routes = {
    'services.segmentation.worker.process_segmentation': {'queue': 'segmentation'},
    # 'services.segmentation_alt.worker.process_segmentation': {'queue': 'segmentation'},
    'services.recognition.worker.recognize_batch': {'queue': 'recognition'},
    # 'services.recognition_legacy.worker.recognize_batch_legacy': {'queue': 'recognition'},
    'services.merge.worker.merge_sync': {'queue': 'merge'},
    'services.ocr.worker.process_ocr': {'queue': 'ocr'},
    'services.pdf.worker.generate_pdf': {'queue': 'pdf'},
}

celery_app.conf.task_serializer = 'pickle'
celery_app.conf.result_serializer = 'pickle'
celery_app.conf.accept_content = ['pickle', 'json']
celery_app.conf.result_expires = 3600
celery_app.conf.worker_prefetch_multiplier = 1
