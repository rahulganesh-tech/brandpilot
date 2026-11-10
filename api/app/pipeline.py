"""The scan pipeline: turns content into cited findings.

1. Brand rules (exact, always on).
2. AI checks when GEMINI_API_KEY is set: claims vs approved facts, tone vs voice guide.
"""
from __future__ import annotations

from typing import Callable

from psycopg import Connection

from . import config, repo
from .ai import AIChecker, FactMatch
from .gemini import LLM, GeminiClient
from .rules_engine import Finding, Rule, check_rules

_client: GeminiClient | None = None


def default_llm() -> LLM | None:
    global _client
    if not config.GEMINI_API_KEY:
        return None
    if _client is None:
        _client = GeminiClient(config.GEMINI_API_KEY, config.GEMINI_MODEL, config.GEMINI_EMBED_MODEL)
    return _client


# Tests replace this to use a fake model.
llm_provider: Callable[[], LLM | None] = default_llm


class DbFactIndex:
    """Approved facts in Postgres, embedded lazily and searched with pgvector."""

    def __init__(self, conn: Connection, brand_id: str, llm: LLM):
        self.conn = conn
        self.brand_id = brand_id
        self.llm = llm

    def ensure_indexed(self) -> None:
        missing = repo.facts_without_embeddings(self.conn, self.brand_id)
        if missing:
            vectors = self.llm.embed([f"{f['code']}: {f['statement']}" for f in missing])
            repo.set_fact_embeddings(self.conn, [(str(f["id"]), v) for f, v in zip(missing, vectors)])

    def search(self, vector: list[float], k: int) -> list[FactMatch]:
        return [
            FactMatch(code=r["code"], statement=r["statement"], similarity=float(r["similarity"]))
            for r in repo.match_facts(self.conn, self.brand_id, vector, k)
        ]


def scan_text(text: str, rules: list[Rule]) -> list[Finding]:
    return check_rules(text, rules)


def run_checks(conn: Connection, brand: dict, text: str) -> tuple[list[Finding], str]:
    """All checks for one piece of content. Returns (findings, ai_status)."""
    brand_id = str(brand["id"])
    findings = scan_text(text, repo.rules_for_engine(conn, brand_id))
    llm = llm_provider()
    if llm is None:
        return findings, "off"
    checker = AIChecker(llm, DbFactIndex(conn, brand_id, llm), brand["voice_guide"])
    result = checker.check(text, findings)
    merged = sorted(findings + result.findings, key=lambda f: (f.span_start, f.source_code))
    return merged, result.status


def realign(text: str, issues: list[dict]) -> list[tuple[str, int, int]]:
    """After an edit, find where each open issue's excerpt now sits.

    Returns (issue_id, start, end) for issues whose span moved; issues whose
    text disappeared get start = end = -1.
    """
    moved = []
    for issue in issues:
        start, excerpt = issue["span_start"], issue["excerpt"]
        if text[start : start + len(excerpt)] == excerpt:
            continue
        candidates = []
        idx = text.find(excerpt)
        while idx >= 0:
            candidates.append(idx)
            idx = text.find(excerpt, idx + 1)
        if candidates:
            best = min(candidates, key=lambda c: abs(c - start))
            moved.append((str(issue["id"]), best, best + len(excerpt)))
        else:
            moved.append((str(issue["id"]), -1, -1))
    return moved
