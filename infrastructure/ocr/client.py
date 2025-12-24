
import base64
import pathlib
import time
import requests


class OCRClient:
    def __init__(self, api_key: str, base_url: str):
        self.base_url = base_url
        self.headers = {"X-Api-Key": api_key}

    def _encode_image(self, path: str | pathlib.Path) -> str:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()

    def recognize(self, image_path: str) -> list[dict]:
        image_b64 = self._encode_image(image_path)

        task_id = self._create_task(image_b64)
        self._wait_for_task(task_id)
        raw = self._fetch_result(task_id)
        return self._decode_pages(raw)

    def _create_task(self, image_b64: str) -> str:
        resp = requests.post(
            f"{self.base_url}/tasks",
            headers=self.headers,
            json={"image": [image_b64], "return_type": "json"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 0:
            raise RuntimeError(f"Ошибка создания задачи: {data}")

        task_id = data.get("task_id")
        if not task_id:
            raise RuntimeError(f"Не удалось получить task_id: {data}")

        return task_id

    def _wait_for_task(self, task_id: str):
        for _ in range(10):
            status = requests.get(
                f"{self.base_url}/tasks/{task_id}/status",
                headers=self.headers,
            ).json()["task_status"]

            if status == "success":
                return
            if status == "error":
                raise RuntimeError("OCR error")

            time.sleep(0.5)

        raise TimeoutError("OCR timeout")

    def _fetch_result(self, task_id: str) -> list[str]:
        resp = requests.get(
            f"{self.base_url}/tasks/{task_id}/result",
            headers=self.headers,
        )
        resp.raise_for_status()
        return resp.json()["recognition_result"]

    def _decode_pages(self, data: list[str]) -> list[dict]:
        import json, base64

        pages = []
        for page in data:
            decoded = base64.b64decode(page).decode("utf-8")
            pages.append(json.loads(decoded))
        return pages
