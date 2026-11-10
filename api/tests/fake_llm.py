"""A scripted stand-in for Gemini, so AI logic is tested without network calls."""
from __future__ import annotations

import hashlib
import math
import re
from typing import Any, Callable

from app.ai import CLAIM_SYSTEM, JUDGE_SYSTEM, TONE_SYSTEM
from app.gemini import EMBED_DIM


def bag_of_words(text: str) -> list[float]:
    v = [0.0] * EMBED_DIM
    for w in re.findall(r"[a-z0-9]+", text.lower()):
        v[int(hashlib.md5(w.encode()).hexdigest(), 16) % EMBED_DIM] += 1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


class FakeLLM:
    def __init__(
        self,
        claims: list[dict] | None = None,
        judge: Callable[[dict], list[dict]] | None = None,
        tone: list[dict] | None = None,
        fail: set[str] | None = None,
    ):
        self.claims = claims or []
        self.judge = judge or (lambda payload: [])
        self.tone = tone or []
        self.fail = fail or set()
        self.prompts: list[str] = []

    def generate_json(self, system: str, prompt: str) -> Any:
        import json

        self.prompts.append(prompt)
        if system == CLAIM_SYSTEM:
            if "claims" in self.fail:
                raise RuntimeError("claims down")
            return {"claims": self.claims}
        if system == JUDGE_SYSTEM:
            return {"results": self.judge(json.loads(prompt))}
        if system == TONE_SYSTEM:
            if "tone" in self.fail:
                raise RuntimeError("tone down")
            return {"issues": self.tone}
        raise AssertionError("unexpected prompt")

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [bag_of_words(t) for t in texts]
