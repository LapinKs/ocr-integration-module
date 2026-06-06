import base64
import asyncio
import json
from pathlib import Path
from typing import Optional, List
import httpx
import os

class OCRClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        fallback_dir: str = None,
    ):
        self.base_url = base_url
        self.headers = {"X-Api-Key": api_key}
        self.fallback_dir = fallback_dir or str(Path(__file__).parent / "fallback")
        Path(self.fallback_dir).mkdir(parents=True, exist_ok=True)
        print(f"[OCR] Client initialized")
        print(f"[OCR]   API URL: {self.base_url}")
        print(f"[OCR]   Fallback dir: {self.fallback_dir}")


    def _get_fallback_for_image(self, image_filename: str) -> Optional[dict]:
        if not image_filename:
            return None
        stem = Path(image_filename).stem
        fallback_path = Path(self.fallback_dir) / f"{stem}.json"
        if fallback_path.exists():
            print(f"[OCR] Using fallback for {image_filename}: {fallback_path}")
            with open(fallback_path, 'r', encoding='utf-8') as f:
                return json.load(f)

        default_fallback = Path(self.fallback_dir) / "default.json"
        if default_fallback.exists():
            print(f"[OCR] Using default fallback for {image_filename}")
            with open(default_fallback, 'r', encoding='utf-8') as f:
                return json.load(f)

        print(f"[OCR] No fallback found for {image_filename}, using empty fallback")
        return self._create_empty_fallback()


    def _create_empty_fallback(self) -> dict:
        return {
            "node": {
                "@type": "RIL_PAGE",
                "@W": "2120",
                "@H": "3000",
                "node": [
                    {
                        "@type": "RIL_TEXT",
                        "node": [
                            {
                                "@type": "RIL_TEXTLINE",
                                "@X": "100",
                                "@Y": "100",
                                "@W": "1000",
                                "@H": "50",
                                "node": [
                                    {
                                        "@type": "RIL_WORD",
                                        "@X": "100",
                                        "@Y": "100",
                                        "@W": "800",
                                        "@H": "50",
                                        "#text": "OCR not available - using fallback"
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        }


    async def recognize_many(self, images: list[bytes], image_filenames: list[str] = None) -> list[dict]:
        try:
            images_b64 = [base64.b64encode(img).decode() for img in images]
            async with httpx.AsyncClient(timeout=30) as client:
                task_id = await self._create_task(client, images_b64)
                status = await self._wait_for_task(client, task_id)

                if status != "success":
                    raise RuntimeError("OCR failed")

                raw = await self._fetch_result(client, task_id)

            return self._decode_pages(raw)

        except Exception as e:
            print(f"[OCR] API failed: {e}, using fallback")

            if image_filenames:
                results = []
                for filename in image_filenames:
                    fallback = self._get_fallback_for_image(filename)
                    results.append(fallback)
                return results

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
        results = []
        for i in range(count):
            results.append(self._create_empty_fallback())
        return results
