from shared.infrastructure.redis_client import get_redis_client
from shared.infrastructure.minio_client import get_minio_client

def get_redis():
    return get_redis_client()

def get_minio():
    return get_minio_client()
