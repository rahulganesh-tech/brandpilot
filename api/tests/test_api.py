"""End-to-end API tests. They need a real Postgres with pgvector:

    TEST_DATABASE_URL=postgresql://... pytest
"""
import os
from pathlib import Path

import psycopg
import pytest

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from app import db
    from app.main import app

    schema = (Path(__file__).parents[1] / "sql" / "schema.sql").read_text()
    with psycopg.connect(URL, autocommit=True) as conn:
        conn.execute("drop table if exists reviews, issues, versions, scans, rules, facts, brands cascade")
        conn.execute(schema)
    db.open_pool(URL)
    from app import pipeline
    from seed.seed import seed

    pipeline.llm_provider = lambda: None  # rules only unless a test opts in

    seed()
    with TestClient(app) as c:
        yield c
    db.close_pool()


def brand_id(client):
    return client.get("/brands").json()[0]["id"]


def new_scan(client, text):
    r = client.post("/scans", json={"brand_id": brand_id(client), "content": text, "channel": "instagram"})
    assert r.status_code == 201, r.text
    return r.json()


def issue(bundle, code):
    return next(i for i in bundle["issues"] if i["source_code"] == code)


def test_health(client):
    assert client.get("/health").json()["ok"] is True


def test_brand_vault(client):
    b = client.get(f"/brands/{brand_id(client)}").json()
    assert b["name"] == "NutriCrunch"
    assert len(b["facts"]) == 15 and len(b["rules"]) == 18


def test_bad_rule_is_rejected(client):
    r = client.post(f"/brands/{brand_id(client)}/rules",
                    json=[{"code": "R-x", "kind": "tone", "pattern": "(", "message": "m"}])
    assert r.status_code == 400


def test_full_workflow(client):
    b = new_scan(client, "Meet India's #1 protein bar — 100% sugar-free! Grab yours now, guys!!")
    sid = b["scan"]["id"]
    assert len(b["versions"]) == 1

    # Submitting is blocked while normal issues are open.
    assert client.post(f"/scans/{sid}/submit").status_code == 409

    # Accept automatic fixes.
    for code in ["R-4.5", "R-1.2a", "R-2.3a"]:
        r = client.patch(f"/issues/{issue(b, code)['id']}", json={"decision": "accepted"})
        assert r.status_code == 200, r.text
        b = r.json()
    assert b["scan"]["content"] == "Meet India's #1 protein bar — no added sugar! Grab yours now, everyone!"
    assert len(b["versions"]) == 4

    # Ignoring needs a reason.
    rank = issue(b, "R-4.1")
    assert client.patch(f"/issues/{rank['id']}", json={"decision": "ignored"}).status_code == 400
    # Accept without a fix is refused; edit works.
    assert client.patch(f"/issues/{rank['id']}", json={"decision": "accepted"}).status_code == 400
    b = client.patch(f"/issues/{rank['id']}",
                     json={"decision": "edited", "edited_text": "loved"}).json()
    assert b["scan"]["content"].startswith("Meet India's loved protein bar")

    b = client.post(f"/scans/{sid}/submit").json()
    assert b["scan"]["status"] == "in_review"
    assert client.patch(f"/issues/{rank['id']}", json={"decision": "open"}).status_code == 400

    assert client.post(f"/scans/{sid}/review", json={"action": "send_back"}).status_code == 400
    b = client.post(f"/scans/{sid}/review", json={"action": "approve", "comment": "Looks good"}).json()
    assert b["scan"]["status"] == "approved"
    assert b["reviews"][0]["action"] == "approve"


def test_rewrite_rescans(client):
    b = new_scan(client, "Hey guys!!")
    sid = b["scan"]["id"]
    r = client.put(f"/scans/{sid}/content", json={"content": "Hello, NutriCrunch fans."})
    b = r.json()
    assert [i for i in b["issues"] if i["decision"] == "open"] == []
    assert len(b["versions"]) == 2


def test_gap_radar(client):
    for _ in range(2):
        b = new_scan(client, "The best bar.")
        best = issue(b, "R-4.3")
        client.patch(f"/issues/{best['id']}", json={"decision": "ignored", "reason": "Quoting a customer review"})
    data = client.get(f"/brands/{brand_id(client)}/insights").json()
    radar = {r["source_code"]: r for r in data["gap_radar"]}
    assert "R-4.3" in radar and radar["R-4.3"]["override_rate"] == 1.0
    assert radar["R-4.3"]["sample_reasons"][0] == "Quoting a customer review"


def test_reviewer_must_decide_flags_before_approving(client):
    b = new_scan(client, "Guaranteed results.")
    sid = b["scan"]["id"]
    b = client.post(f"/scans/{sid}/submit").json()  # needs-human flags may stay open
    assert b["scan"]["status"] == "in_review"
    assert client.post(f"/scans/{sid}/review", json={"action": "approve"}).status_code == 409
    for i in [i for i in b["issues"] if i["decision"] == "open"]:
        r = client.patch(f"/issues/{i['id']}", json={"decision": "edited", "edited_text": "Real", "author": "Manager"})
        assert r.status_code == 200, r.text
    b = client.post(f"/scans/{sid}/review", json={"action": "approve"}).json()
    assert b["scan"]["status"] == "approved"
    assert b["scan"]["content"] == "Real results."
    assert client.patch(f"/issues/{b['issues'][0]['id']}", json={"decision": "ignored", "reason": "late"}).status_code == 409


def test_ai_claim_check_uses_pgvector_facts(client):
    from app import pipeline

    from .fake_llm import FakeLLM

    def judge(payload):
        c = payload["claims"][0]
        assert c["facts"][0]["code"] == "F-01"  # nearest approved fact, found by pgvector
        return [{"id": 0, "verdict": "contradicted", "fact_code": "F-01", "why": "Label says 20 g.",
                 "fix": "20 g of protein", "confidence": 0.95}]

    pipeline.llm_provider = lambda: FakeLLM(
        claims=[{"quote": "25 g of protein", "claim": "Each bar has 25 g of protein."}], judge=judge
    )
    b = new_scan(client, "Each NutriCrunch bar packs 25 g of protein.")
    assert b["scan"]["ai_status"] == "ok"
    [f] = [i for i in b["issues"] if i["engine"] == "ai"]
    assert f["source_code"] == "F-01" and f["fix"] == "20 g of protein" and f["needs_human"]
    facts = client.get(f"/brands/{brand_id(client)}").json()["facts"]
    assert all(x["indexed"] for x in facts)

    # Accepting the AI fix rewrites the text like any other fix.
    b = client.patch(f"/issues/{f['id']}", json={"decision": "accepted"}).json()
    assert b["scan"]["content"] == "Each NutriCrunch bar packs 20 g of protein."


def test_ai_outage_still_saves_rule_findings(client):
    from app import pipeline

    from .fake_llm import FakeLLM

    pipeline.llm_provider = lambda: FakeLLM(fail={"claims", "tone"})
    b = new_scan(client, "Hey guys!!")
    assert b["scan"]["ai_status"] == "error"
    assert {i["source_code"] for i in b["issues"]} == {"R-1.2a", "R-2.3a"}


@pytest.mark.skipif(__import__("shutil").which("tesseract") is None, reason="tesseract not installed")
def test_image_scan_end_to_end(client):
    from .images import poster

    png = poster([("Guaranteed results, guys!!", "#121933"), ("Only Rs 99 per bar", "#C8C8C8")], block="#1E90FF")
    r = client.post(
        "/scans/image",
        data={"brand_id": brand_id(client), "channel": "instagram", "author": "Creator"},
        files={"file": ("poster.png", png, "image/png")},
    )
    assert r.status_code == 201, r.text
    b = r.json()
    sid = b["scan"]["id"]
    assert b["scan"]["has_image"] is True and "Guaranteed results" in b["scan"]["content"]
    codes = {i["source_code"] for i in b["issues"]}
    assert {"R-4.2", "R-1.2a", "R-2.3a", "WCAG 1.4.3", "Brand colours"} <= codes

    img = client.get(f"/scans/{sid}/image")
    assert img.status_code == 200 and img.headers["content-type"] == "image/png" and img.content == png

    # Image issues are marked fixed (not accepted) and survive a text re-check.
    contrast = issue(b, "WCAG 1.4.3")
    assert client.patch(f"/issues/{contrast['id']}", json={"decision": "accepted"}).status_code == 400
    b = client.put(f"/scans/{sid}/content", json={"content": "Real results for everyone!"}).json()
    assert issue(b, "Brand colours")["decision"] == "open"
    b = client.patch(f"/issues/{contrast['id']}", json={"decision": "edited"}).json()
    assert issue(b, "WCAG 1.4.3")["decision"] == "edited"
    assert issue(b, "WCAG 1.4.3")["decision_reason"] == "Fixed in the design"


def test_image_upload_rejects_wrong_type(client):
    r = client.post(
        "/scans/image",
        data={"brand_id": brand_id(client)},
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 400
