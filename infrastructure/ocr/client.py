import base64
import pathlib
import time
import requests
import json


class OCRClient:
    def __init__(self, api_key: str, base_url: str):
        self.base_url = base_url
        self.headers = {"X-Api-Key": api_key}

    def recognize_many(self, image_paths: list[str | pathlib.Path]) -> list[dict]:
        images_b64 = [self._encode_image(p) for p in image_paths]

        task_id = self._create_task(images_b64)
        self._wait_for_task(task_id)
        raw = self._fetch_result(task_id)

        return self._decode_pages(raw)

    def recognize_one(self, image_path: str | pathlib.Path) -> dict:
        result = self.recognize_many([image_path])
        return result[0] if result else {}

    def _encode_image(self, path: str | pathlib.Path) -> str:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()

    def _create_task(self, images_b64: list[str]) -> str:
        resp = requests.post(
            f"{self.base_url}/tasks",
            headers=self.headers,
            json={"image": images_b64, "return_type": "json"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 0:
            raise RuntimeError(f"OCR error: {data}")

        return data["task_id"]

    def _wait_for_task(self, task_id: str):
        for _ in range(20):
            resp = requests.get(
                f"{self.base_url}/tasks/{task_id}/status",
                headers=self.headers,
                timeout=10,
            )
            resp.raise_for_status()
            status = resp.json()["task_status"]

            if status == "success":
                return
            if status == "error":
                raise RuntimeError("OCR processing error")

            time.sleep(0.5)

        raise TimeoutError("OCR timeout")

    def _fetch_result(self, task_id: str) -> list[str]:
        resp = requests.get(
            f"{self.base_url}/tasks/{task_id}/result",
            headers=self.headers,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["recognition_result"]

    def _decode_pages(self, data: list[str]) -> list[dict]:
        pages = []
        for page in data:
            decoded = base64.b64decode(page).decode("utf-8")
            pages.append(json.loads(decoded))
        return pages
