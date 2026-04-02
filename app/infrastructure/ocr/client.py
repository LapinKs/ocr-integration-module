import base64
import asyncio
import json
from typing import Optional
import httpx


class OCRClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        fallback_json_path: Optional[str] = None,
    ):
        self.base_url = base_url
        self.headers = {"X-Api-Key": api_key}
        self.fallback_json_path = fallback_json_path

    async def recognize_many(self, images: list[bytes]) -> list[dict]:
        try:
            images_b64 = [
                base64.b64encode(img).decode()
                for img in images
            ]

            async with httpx.AsyncClient(timeout=30) as client:
                task_id = await self._create_task(client, images_b64)
                status = await self._wait_for_task(client, task_id)

                if status != "success":
                    raise RuntimeError("OCR failed")

                raw = await self._fetch_result(client, task_id)

            return self._decode_pages(raw)

        except Exception as e:
            print(f"OCR API failed: {e}")

            return self._fallback(len(images))

    async def _create_task(self, client: httpx.AsyncClient, images_b64: list[str]) -> str:
        resp = await client.post(
            f"{self.base_url}/tasks",
            headers=self.headers,
            json={"image": images_b64, "return_type": "json"},
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 0:
            raise RuntimeError(f"OCR error: {data}")

        return data["task_id"]

    async def _wait_for_task(self, client: httpx.AsyncClient, task_id: str) -> str:
        for _ in range(20):
            resp = await client.get(
                f"{self.base_url}/tasks/{task_id}/status",
                headers=self.headers,
            )
            resp.raise_for_status()

            status = resp.json()["task_status"]

            if status in ("success", "error"):
                return status

            await asyncio.sleep(0.5)

        raise TimeoutError("OCR timeout")

    async def _fetch_result(self, client: httpx.AsyncClient, task_id: str) -> list[str]:
        resp = await client.get(
            f"{self.base_url}/tasks/{task_id}/result",
            headers=self.headers,
        )
        resp.raise_for_status()
        return resp.json()["recognition_result"]

    def _decode_pages(self, data: list[str]) -> list[dict]:
        pages = []
        for page in data:
            decoded = base64.b64decode(page).decode("utf-8")
            pages.append(json.loads(decoded))
        return pages

    def _fallback(self, count: int) -> list[dict]:
        if not self.fallback_json_path:
            raise RuntimeError("No fallback configured")

        with open(self.fallback_json_path, "r", encoding="utf-8") as f:
            fallback = json.load(f)

        return [json.loads(json.dumps(fallback)) for _ in range(count)]
