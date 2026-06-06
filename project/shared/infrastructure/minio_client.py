from minio import Minio
from typing import Optional, BinaryIO
import io

_minio_client: Optional[Minio] = None


def create_minio_client(
    endpoint: str,
    access_key: str,
    secret_key: str,
    secure: bool = False
) -> Minio:
    global _minio_client
    _minio_client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)
    return _minio_client


def get_minio_client() -> Minio:
    if _minio_client is None:
        raise RuntimeError("MinIO client not initialized. Call create_minio_client first.")
    return _minio_client


class MinIOStorage:

    def __init__(self, client: Minio = None, bucket: str = "formula-tasks"):
        self.client = client or get_minio_client()
        self.bucket = bucket
        self._ensure_bucket()


    def _ensure_bucket(self):

        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)


    def upload_bytes(self, path: str, data: bytes, content_type: str = "application/octet-stream"):

        self.client.put_object(
            self.bucket, path,
            io.BytesIO(data), len(data),
            content_type=content_type
        )


    def download_bytes(self, path: str) -> bytes:

        response = self.client.get_object(self.bucket, path)
        try:
            return response.read()
        finally:
            response.close()


    def upload_json(self, path: str, data: dict):

        import json
        json_str = json.dumps(data, ensure_ascii=False, indent=2)
        self.upload_bytes(path, json_str.encode('utf-8'), "application/json")


    def download_json(self, path: str) -> dict:

        import json
        data = self.download_bytes(path)
        return json.loads(data.decode('utf-8'))


    def upload_pickle(self, path: str, obj):

        import pickle
        data = pickle.dumps(obj)
        self.upload_bytes(path, data, "application/octet-stream")


    def download_pickle(self, path: str):

        import pickle
        data = self.download_bytes(path)
        return pickle.loads(data)


    def delete_path(self, path: str):

        self.client.remove_object(self.bucket, path)


    def list_paths(self, prefix: str) -> list:

        objects = self.client.list_objects(self.bucket, prefix=prefix)
        return [obj.object_name for obj in objects]
