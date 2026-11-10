from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from . import config, db, repo
from .models import BrandIn, BrandUpdate, ContentIn, DecisionIn, FactIn, ReviewIn, RuleIn, ScanIn
from . import pipeline
from .pipeline import realign
from .rules_engine import Rule, apply_fix, validate_rule
from .vision import ImageError, analyze_image

EDITABLE = {"draft", "sent_back"}
IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024
GAP_MIN_FLAGS = 2
GAP_MIN_OVERRIDE_RATE = 0.5


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.open_pool()
    yield
    db.close_pool()


app = FastAPI(title="BrandPilot API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _404(what: str):
    raise HTTPException(status_code=404, detail=f"{what} not found")


def _scan_bundle(conn, scan_id: str) -> dict:
    scan = repo.get_scan(conn, scan_id)
    if scan is None:
        _404("Scan")
    return {
        "scan": scan,
        "issues": repo.list_issues(conn, scan_id),
        "versions": repo.list_versions(conn, scan_id),
        "reviews": repo.list_reviews(conn, scan_id),
    }


def _rescan(conn, scan: dict, content: str) -> None:
    brand = repo.get_brand(conn, str(scan["brand_id"]))
    findings, ai_status = pipeline.run_checks(conn, brand, content)
    repo.replace_open_issues(conn, str(scan["id"]), findings)
    repo.set_ai_status(conn, str(scan["id"]), ai_status)


@app.get("/health")
def health():
    db_ok = False
    try:
        with db.connection() as conn:
            conn.execute("select 1")
        db_ok = True
    except Exception as exc:
        return {"ok": False, "database": False, "error": str(exc)}
    import shutil
    has_tesseract = shutil.which("tesseract") is not None
    has_ai = pipeline.llm_provider() is not None
    ocr_mode = "tesseract" if has_tesseract else ("gemini" if has_ai else "none")
    return {
        "ok": True,
        "database": True,
        "ai": has_ai,
        "ocr": ocr_mode,
        "deployment": "vercel",
        "version": "0.2.0",
    }


@app.post("/seed")
def seed_demo_data(demo: bool = True):
    """Seed the database with the sample NutriCrunch brand kit and demo drafts."""
    from seed.seed import seed as run_seed

    try:
        brand_id = run_seed(demo=demo)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to seed brand kit: {exc}") from exc

    with db.connection() as conn:
        brand = repo.get_brand(conn, brand_id)
        return {
            "ok": True,
            "brand": brand,
            "message": f"Successfully loaded brand '{brand['name']}' with facts, rules, and demo content.",
        }


# ---------- brands ----------


@app.get("/brands")
def list_brands():
    with db.connection() as conn:
        return repo.list_brands(conn)


@app.post("/brands", status_code=201)
def create_brand(body: BrandIn):
    with db.connection() as conn:
        return repo.create_brand(conn, body.name, body.voice_guide, body.colors)


@app.get("/brands/{brand_id}")
def get_brand(brand_id: UUID):
    with db.connection() as conn:
        brand = repo.get_brand(conn, str(brand_id))
        if brand is None:
            _404("Brand")
        return {
            **brand,
            "facts": repo.list_facts(conn, str(brand_id)),
            "rules": repo.list_rules(conn, str(brand_id)),
        }


@app.patch("/brands/{brand_id}")
def update_brand(brand_id: UUID, body: BrandUpdate):
    with db.connection() as conn:
        brand = repo.update_brand(conn, str(brand_id), body.model_dump(exclude_none=True))
        if brand is None:
            _404("Brand")
        return brand


@app.post("/brands/{brand_id}/facts")
def add_facts(brand_id: UUID, body: list[FactIn]):
    with db.connection() as conn:
        if repo.get_brand(conn, str(brand_id)) is None:
            _404("Brand")
        n = repo.upsert_facts(conn, str(brand_id), [f.model_dump() for f in body])
        return {"saved": n}


@app.delete("/facts/{fact_id}", status_code=204)
def delete_fact(fact_id: UUID):
    with db.connection() as conn:
        if not repo.delete_fact(conn, str(fact_id)):
            _404("Fact")


@app.post("/brands/{brand_id}/rules")
def add_rules(brand_id: UUID, body: list[RuleIn]):
    for r in body:
        try:
            validate_rule(Rule(**r.model_dump()))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    with db.connection() as conn:
        if repo.get_brand(conn, str(brand_id)) is None:
            _404("Brand")
        n = repo.upsert_rules(conn, str(brand_id), [r.model_dump() for r in body])
        return {"saved": n}


@app.delete("/rules/{rule_id}", status_code=204)
def delete_rule(rule_id: UUID):
    with db.connection() as conn:
        if not repo.delete_rule(conn, str(rule_id)):
            _404("Rule")


@app.get("/brands/{brand_id}/insights")
def insights(brand_id: UUID):
    with db.connection() as conn:
        if repo.get_brand(conn, str(brand_id)) is None:
            _404("Brand")
        stats = repo.rule_stats(conn, str(brand_id))
        for s in stats:
            rate = s["ignored"] / s["total"] if s["total"] else 0.0
            s["override_rate"] = round(rate, 2)
            s["unclear"] = s["total"] >= GAP_MIN_FLAGS and rate >= GAP_MIN_OVERRIDE_RATE
        return {
            "scans_by_status": repo.scan_status_counts(conn, str(brand_id)),
            "rules": stats,
            "gap_radar": [s for s in stats if s["unclear"]],
        }


# ---------- scans ----------


@app.post("/scans", status_code=201)
def create_scan(body: ScanIn):
    with db.connection() as conn:
        if repo.get_brand(conn, str(body.brand_id)) is None:
            _404("Brand")
        scan = repo.create_scan(conn, str(body.brand_id), body.author, body.channel, body.content)
        repo.add_version(conn, str(scan["id"]), body.content, body.author, "First draft")
        _rescan(conn, scan, body.content)
        return _scan_bundle(conn, str(scan["id"]))


@app.post("/scans/image", status_code=201)
async def create_image_scan(
    brand_id: UUID = Form(...),
    file: UploadFile = File(...),
    channel: str = Form("social"),
    author: str = Form("creator"),
):
    if file.content_type not in IMAGE_TYPES:
        raise HTTPException(400, "Upload a PNG, JPEG or WebP image")
    data = await file.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(400, "Images must be 5 MB or smaller")
    return await run_in_threadpool(_image_scan, str(brand_id), data, file.content_type, channel[:40], author[:80])


def _image_scan(brand_id: str, data: bytes, image_type: str, channel: str, author: str) -> dict:
    with db.connection() as conn:
        brand = repo.get_brand(conn, brand_id)
        if brand is None:
            _404("Brand")
        try:
            report = analyze_image(
                data,
                brand["colors"],
                image_type=image_type,
                llm=pipeline.llm_provider(),
            )
        except ImageError as exc:
            raise HTTPException(400, str(exc)) from exc
        scan = repo.create_image_scan(conn, brand_id, author, channel, report.text, data, image_type)
        repo.add_version(conn, str(scan["id"]), report.text, author, "Text read from the image")
        repo.add_issues(conn, str(scan["id"]), report.findings)
        if report.text.strip():
            _rescan(conn, scan, report.text)
        return _scan_bundle(conn, str(scan["id"]))


@app.get("/scans/{scan_id}/image")
def scan_image(scan_id: UUID):
    with db.connection() as conn:
        row = repo.get_scan_image(conn, str(scan_id))
        if row is None:
            _404("Image")
        return Response(
            content=bytes(row["image"]),
            media_type=row["image_type"],
            headers={"Cache-Control": "private, max-age=3600"},
        )


@app.get("/scans")
def list_scans(brand_id: UUID | None = None, status: str | None = None):
    with db.connection() as conn:
        return repo.list_scans(conn, str(brand_id) if brand_id else None, status)


@app.get("/scans/{scan_id}")
def get_scan(scan_id: UUID):
    with db.connection() as conn:
        return _scan_bundle(conn, str(scan_id))


@app.put("/scans/{scan_id}/content")
def replace_content(scan_id: UUID, body: ContentIn):
    """Creator rewrites the text: save a version and re-check it."""
    with db.connection() as conn:
        scan = repo.get_scan(conn, str(scan_id), lock=True)
        if scan is None:
            _404("Scan")
        if scan["status"] not in EDITABLE:
            raise HTTPException(409, "This content is locked while it is in review or approved")
        repo.set_scan_content(conn, str(scan_id), body.content)
        repo.add_version(conn, str(scan_id), body.content, body.author, "Edited by creator")
        repo.set_scan_status(conn, str(scan_id), "draft")
        _rescan(conn, scan, body.content)
        return _scan_bundle(conn, str(scan_id))


@app.patch("/issues/{issue_id}")
def decide_issue(issue_id: UUID, body: DecisionIn):
    with db.connection() as conn:
        issue = repo.get_issue(conn, str(issue_id))
        if issue is None:
            _404("Issue")
        scan_id = str(issue["scan_id"])
        scan = repo.get_scan(conn, scan_id, lock=True)
        if scan["status"] == "approved":
            raise HTTPException(409, "This content is approved and locked")

        if body.decision == "ignored":
            if not body.reason or len(body.reason.strip()) < 3:
                raise HTTPException(400, "Please give a reason for ignoring this issue")
            repo.set_issue_decision(conn, str(issue_id), "ignored", body.reason.strip())
            return _scan_bundle(conn, scan_id)

        if body.decision == "open":
            if issue["decision"] != "ignored":
                raise HTTPException(400, "Only an ignored issue can be reopened")
            repo.set_issue_decision(conn, str(issue_id), "open", None)
            return _scan_bundle(conn, scan_id)

        if issue["decision"] != "open":
            raise HTTPException(400, "This issue has already been resolved")
        if issue["span_start"] < 0:
            # Image issues are fixed in the design, not in the text.
            if body.decision != "edited":
                raise HTTPException(400, "Mark this image issue as fixed, or ignore it with a reason")
            repo.set_issue_decision(conn, str(issue_id), "edited", body.reason or "Fixed in the design")
            return _scan_bundle(conn, scan_id)
        if body.decision == "accepted":
            if issue["fix"] is None:
                raise HTTPException(400, "This issue has no automatic fix. Use Edit instead.")
            replacement = issue["fix"]
        else:
            if body.edited_text is None:
                raise HTTPException(400, "edited_text is required when editing")
            replacement = body.edited_text

        try:
            new_content = apply_fix(scan["content"], issue["excerpt"], replacement, issue["span_start"])
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

        repo.set_scan_content(conn, scan_id, new_content)
        repo.add_version(
            conn, scan_id, new_content, body.author,
            f"{'Accepted fix' if body.decision == 'accepted' else 'Edited'} for {issue['source_code']}",
        )
        repo.set_issue_decision(conn, str(issue_id), body.decision, body.reason)

        still_open = [
            i for i in repo.list_issues(conn, scan_id) if i["decision"] == "open" and i["span_start"] >= 0
        ]
        for oid, start, end in realign(new_content, still_open):
            if start < 0:
                repo.set_issue_decision(conn, oid, "edited", "Resolved by another fix")
            else:
                repo.move_issue(conn, oid, start, end)
        return _scan_bundle(conn, scan_id)


@app.post("/scans/{scan_id}/submit")
def submit_for_review(scan_id: UUID):
    with db.connection() as conn:
        scan = repo.get_scan(conn, str(scan_id), lock=True)
        if scan is None:
            _404("Scan")
        if scan["status"] not in EDITABLE:
            raise HTTPException(409, f"Cannot submit content that is {scan['status'].replace('_', ' ')}")
        blocking = [
            i for i in repo.list_issues(conn, str(scan_id))
            if i["decision"] == "open" and not i["needs_human"]
        ]
        if blocking:
            raise HTTPException(
                409, f"Resolve {len(blocking)} open issue(s) before submitting. "
                     "Issues marked 'needs human' can stay open for the reviewer."
            )
        repo.set_scan_status(conn, str(scan_id), "in_review")
        return _scan_bundle(conn, str(scan_id))


@app.post("/scans/{scan_id}/review")
def review(scan_id: UUID, body: ReviewIn):
    with db.connection() as conn:
        scan = repo.get_scan(conn, str(scan_id), lock=True)
        if scan is None:
            _404("Scan")
        if scan["status"] != "in_review":
            raise HTTPException(409, "Only content that is in review can be approved or sent back")
        if body.action == "send_back" and len(body.comment.strip()) < 3:
            raise HTTPException(400, "Tell the creator what to change")
        open_flags = [i for i in repo.list_issues(conn, str(scan_id)) if i["decision"] == "open"]
        if body.action == "approve" and open_flags:
            raise HTTPException(
                409, f"Decide the {len(open_flags)} flagged item(s) before approving: fix, edit or ignore with a reason."
            )
        repo.add_review(conn, str(scan_id), body.reviewer, body.action, body.comment.strip())
        repo.set_scan_status(conn, str(scan_id), "approved" if body.action == "approve" else "sent_back")
        return _scan_bundle(conn, str(scan_id))
