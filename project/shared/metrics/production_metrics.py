from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST, CollectorRegistry, push_to_gateway
from fastapi import Response
import time
from functools import wraps
from typing import Optional
import os


WORKER_REGISTRY = CollectorRegistry()


segmentation_time = Histogram(
    'segmentation_time_seconds',
    'Time for segmentation per page',
    buckets=[0.5, 1, 2, 5, 10, 20, 30, 60],
    labelnames=['task_id', 'page_index'],
    registry=WORKER_REGISTRY
)

segmentation_formulas_found = Gauge(
    'segmentation_formulas_found',
    'Number of formulas found by segmentation',
    labelnames=['task_id', 'page_index'],
    registry=WORKER_REGISTRY
)

recognition_time = Histogram(
    'recognition_time_seconds',
    'Total time for recognition per page',
    buckets=[1, 2, 5, 10, 20, 30, 60, 120],
    labelnames=['task_id', 'page_index'],
    registry=WORKER_REGISTRY
)

recognition_formulas_processed = Gauge(
    'recognition_formulas_processed',
    'Number of formulas processed by recognition',
    labelnames=['task_id', 'page_index'],
    registry=WORKER_REGISTRY
)

ocr_time = Histogram(
    'ocr_time_seconds',
    'Time for OCR per page',
    buckets=[0.5, 1, 2, 5, 10, 20],
    labelnames=['task_id', 'page_index'],
    registry=WORKER_REGISTRY
)

merge_time = Histogram(
    'merge_time_seconds',
    'Time for merge per page',
    buckets=[0.1, 0.2, 0.5, 1, 2, 5],
    labelnames=['task_id', 'page_index'],
    registry=WORKER_REGISTRY
)

pdf_time = Histogram(
    'pdf_time_seconds',
    'Time for PDF generation per page',
    buckets=[0.5, 1, 2, 5, 10],
    labelnames=['task_id', 'page_index'],
    registry=WORKER_REGISTRY
)

error_counter = Counter(
    'errors_total',
    'Total errors by worker type',
    labelnames=['worker_type', 'error_type'],
    registry=WORKER_REGISTRY
)


recognition_batch_time = Histogram(
    'recognition_batch_time_ms',
    'Time for recognition batch in milliseconds',
    buckets=[100, 500, 1000, 2000, 5000, 10000, 30000],
    labelnames=['task_id'],
    registry=WORKER_REGISTRY
)


pages_processed = Counter(
    'pages_processed_total',
    'Total pages processed by worker type',
    labelnames=['worker_type', 'status'],
    registry=WORKER_REGISTRY
)

class MetricsCollector:
    @staticmethod
    def measure_segmentation(task_id: str, page_index: int):
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                start = time.time()
                try:
                    result = func(*args, **kwargs)
                    duration = time.time() - start
                    segmentation_time.labels(task_id=task_id, page_index=str(page_index)).observe(duration)
                    return result
                except Exception as e:
                    error_counter.labels(worker_type='segmentation', error_type=type(e).__name__).inc()
                    raise
            return wrapper
        return decorator

    @staticmethod
    def measure_recognition(task_id: str, page_index: int):
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                start = time.time()
                try:
                    result = func(*args, **kwargs)
                    duration = time.time() - start
                    recognition_time.labels(task_id=task_id, page_index=str(page_index)).observe(duration)
                    return result
                except Exception as e:
                    error_counter.labels(worker_type='recognition', error_type=type(e).__name__).inc()
                    raise
            return wrapper
        return decorator

metrics = MetricsCollector()


def push_metrics_to_gateway(job_name: str, task_id: str = None, page_index: int = None):

    pushgateway_url = os.environ.get('PUSHGATEWAY_URL', 'pushgateway:9091')


    grouping_key = {}
    if task_id:
        grouping_key['task_id'] = task_id
    if page_index is not None:
        grouping_key['page_index'] = str(page_index)

    try:
        push_to_gateway(
            pushgateway_url,
            job=job_name,
            registry=WORKER_REGISTRY,
            grouping_key=grouping_key
        )
        print(f"[Metrics] Pushed to {pushgateway_url}, job={job_name}")
    except Exception as e:
        print(f"[Metrics] Failed to push to PushGateway: {e}")

def save_error_sync(task_id: str, worker_type: str, error_msg: str, page_index: int, error_type: str):
    error_counter.labels(worker_type=worker_type, error_type=error_type).inc()
    push_metrics_to_gateway(f"{worker_type}-worker", task_id, page_index)

async def metrics_endpoint():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
