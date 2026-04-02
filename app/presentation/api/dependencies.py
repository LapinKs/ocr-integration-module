from app.application.pipeline import build_pipeline

_pipeline = None

def set_pipeline(pipeline):
    global _pipeline
    _pipeline = pipeline

def get_pipeline():
    global _pipeline
    return _pipeline
