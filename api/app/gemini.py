"""Minimal Gemini REST client (JSON generation + embeddings)."""
from __future__ import annotations

import json
from typing import Any, Protocol

import httpx

BASE = "https://generativelanguage.googleapis.com/v1beta"
EMBED_DIM = 768


class LLM(Protocol):
    def generate_json(self, system: str, prompt: str) -> Any: ...
    def embed(self, texts: list[str]) -> list[list[float]]: ...
    def extract_image_text(self, image_bytes: bytes, mime_type: str = "image/png") -> str: ...


class GeminiError(RuntimeError):
    pass


class GeminiClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        embed_model: str,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.model = model
        self.embed_model = embed_model
        self._http = httpx.Client(timeout=timeout, headers={"x-goog-api-key": api_key}, transport=transport)

    def generate_json(self, system: str, prompt: str) -> Any:
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
        }
        last_error: Exception | None = None
        for _ in range(2):  # one retry on bad JSON or a transient error
            try:
                r = self._http.post(f"{BASE}/models/{self.model}:generateContent", json=body)
                r.raise_for_status()
                data = r.json()
                text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
                return json.loads(text)
            except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError) as exc:
                last_error = exc
        raise GeminiError(f"Gemini generate failed: {last_error}")

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        body = {
            "requests": [
                {
                    "model": f"models/{self.embed_model}",
                    "content": {"parts": [{"text": t}]},
                    "outputDimensionality": EMBED_DIM,
                }
                for t in texts
            ]
        }
        try:
            r = self._http.post(f"{BASE}/models/{self.embed_model}:batchEmbedContents", json=body)
            r.raise_for_status()
            vectors = [e["values"] for e in r.json()["embeddings"]]
        except (httpx.HTTPError, KeyError) as exc:
            raise GeminiError(f"Gemini embed failed: {exc}") from exc
        if any(len(v) != EMBED_DIM for v in vectors):
            raise GeminiError("Gemini returned embeddings of the wrong size")
        return vectors

    def extract_image_text(self, image_bytes: bytes, mime_type: str = "image/png") -> str:
        """Extract visible text from an image using Gemini multimodal vision."""
        import base64

        body = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "inlineData": {
                                "mimeType": mime_type,
                                "data": base64.b64encode(image_bytes).decode("ascii"),
                            }
                        },
                        {
                            "text": (
                                "Read all text from this design or post image. "
                                "Return every readable word, preserving line breaks. "
                                "Output only the raw extracted text, with no markdown fences, no preface, and no explanations."
                            )
                        },
                    ],
                }
            ],
            "generationConfig": {"temperature": 0},
        }
        try:
            r = self._http.post(f"{BASE}/models/{self.model}:generateContent", json=body)
            r.raise_for_status()
            data = r.json()
            return "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"]).strip()
        except Exception as exc:
            raise GeminiError(f"Gemini image text extraction failed: {exc}") from exc

