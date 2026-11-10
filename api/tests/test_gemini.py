import json

import httpx
import pytest

from app.gemini import EMBED_DIM, GeminiClient, GeminiError


def client_with(handler):
    return GeminiClient("KEY", "gemini-2.5-flash", "gemini-embedding-001", transport=httpx.MockTransport(handler))


def test_generate_json_request_and_parse():
    seen = {}

    def handler(req: httpx.Request):
        seen["url"] = str(req.url)
        seen["key"] = req.headers["x-goog-api-key"]
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": '{"claims": []}'}]}}]})

    assert client_with(handler).generate_json("sys", "hello") == {"claims": []}
    assert seen["url"].endswith("/v1beta/models/gemini-2.5-flash:generateContent")
    assert seen["key"] == "KEY"
    assert seen["body"]["generationConfig"] == {"temperature": 0, "responseMimeType": "application/json"}
    assert seen["body"]["systemInstruction"]["parts"][0]["text"] == "sys"


def test_generate_retries_once_on_bad_json():
    calls = []

    def handler(req):
        calls.append(1)
        text = "not json" if len(calls) == 1 else '{"ok": true}'
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": text}]}}]})

    assert client_with(handler).generate_json("s", "p") == {"ok": True}
    assert len(calls) == 2


def test_generate_raises_after_two_failures():
    with pytest.raises(GeminiError):
        client_with(lambda req: httpx.Response(500)).generate_json("s", "p")


def test_embed_batch():
    def handler(req):
        body = json.loads(req.content)
        assert req.url.path.endswith("gemini-embedding-001:batchEmbedContents")
        assert all(r["outputDimensionality"] == EMBED_DIM for r in body["requests"])
        return httpx.Response(200, json={"embeddings": [{"values": [0.1] * EMBED_DIM} for _ in body["requests"]]})

    vecs = client_with(handler).embed(["a", "b"])
    assert len(vecs) == 2 and len(vecs[0]) == EMBED_DIM


def test_embed_rejects_wrong_size():
    with pytest.raises(GeminiError):
        client_with(lambda req: httpx.Response(200, json={"embeddings": [{"values": [0.1, 0.2]}]})).embed(["a"])
