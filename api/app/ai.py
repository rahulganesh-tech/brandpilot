"""AI checks: claims against approved facts, and tone against the voice guide.

Guardrails ("no source, no flag"):
- The model only sees masked text (emails and phone numbers removed).
- Every quote must be found word-for-word in the original content, or it is dropped.
- A contradiction must cite one of the facts we retrieved for that claim, or it is dropped.
- A tone issue must quote a line that really exists in the voice guide, or it is dropped.
- Every AI claim finding goes to a human reviewer.
"""
from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Protocol

from .gemini import LLM
from .privacy import mask_pii
from .rules_engine import Finding

log = logging.getLogger(__name__)

MAX_CLAIMS = 10
MAX_TONE_ISSUES = 5
FACTS_PER_CLAIM = 3
LOW_CONFIDENCE = 0.7

CLAIM_SYSTEM = """You find factual claims in marketing content.
A factual claim is a statement that can be true or false about the product, company, price, quantity,
ingredients, nutrition, ranking, availability, delivery, results or customers. Opinions, greetings and
calls to action are not claims.
Return JSON: {"claims": [{"quote": "<exact text copied character for character from the content>",
"claim": "<the claim as one short plain sentence>"}]}
Keep each quote to the smallest phrase that holds the claim. At most 10 claims.
Return {"claims": []} if there are none."""

JUDGE_SYSTEM = """You check marketing claims against a brand's approved facts.
Use ONLY the facts listed with each claim. Never use outside knowledge.
Verdicts:
- "supported": a listed fact says the same thing.
- "contradicted": a listed fact says something different (wrong number, old price, wrong detail).
- "unsupported": none of the listed facts covers the claim.
Return JSON: {"results": [{"id": <claim id>, "verdict": "supported" | "contradicted" | "unsupported",
"fact_code": "<code of the fact you relied on, or null>", "why": "<one plain sentence for the writer>",
"fix": "<replacement for the quote that is true according to the facts, or null>",
"confidence": <number from 0 to 1>}]}
For "supported" and "contradicted" you must give the fact_code you relied on."""

TONE_SYSTEM = """You are a brand editor. Compare the content with the brand's voice guide.
Flag only phrases that clearly break a specific written guideline. Do not flag factual claims, and do not
flag preferences the guide does not mention.
Return JSON: {"issues": [{"quote": "<exact text copied from the content>",
"guideline": "<the guideline line copied exactly from the voice guide>",
"section": "<its section number, e.g. 2.5>", "why": "<one plain sentence>",
"fix": "<replacement for the quote, or null>", "confidence": <number from 0 to 1>}]}
At most 5 issues. Return {"issues": []} if the content follows the guide."""


@dataclass
class FactMatch:
    code: str
    statement: str
    similarity: float


class FactIndex(Protocol):
    def ensure_indexed(self) -> None: ...
    def search(self, vector: list[float], k: int) -> list[FactMatch]: ...


@dataclass
class AIResult:
    findings: list[Finding]
    status: str  # "ok" or "error"


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def _confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _clean_fix(fix: Any, quote: str) -> str | None:
    if not isinstance(fix, str):
        return None
    fix = fix.strip()
    return fix if fix and fix != quote else None


def _overlaps(start: int, end: int, findings: list[Finding], types: set[str] | None = None) -> bool:
    return any(
        start < f.span_end and f.span_start < end and (types is None or f.type in types) for f in findings
    )


def locate(text: str, quote: str, taken: list[Finding]) -> tuple[int, int] | None:
    """Find the quote in the original text, preferring a spot no other finding covers."""
    if not isinstance(quote, str) or len(quote.strip()) < 2 or "[EMAIL]" in quote or "[PHONE]" in quote:
        return None
    quote = quote.strip()
    hay, needle = text, quote
    if text.find(quote) < 0:
        hay, needle = text.lower(), quote.lower()
    spots = []
    i = hay.find(needle)
    while i >= 0:
        spots.append((i, i + len(needle)))
        i = hay.find(needle, i + 1)
    if not spots:
        return None
    free = [s for s in spots if not _overlaps(s[0], s[1], taken)]
    return (free or spots)[0]


class AIChecker:
    def __init__(self, llm: LLM, facts: FactIndex, voice_guide: str):
        self.llm = llm
        self.facts = facts
        self.voice_guide = voice_guide

    def check(self, text: str, existing: list[Finding]) -> AIResult:
        masked = mask_pii(text)
        failures = 0
        claims: list[Finding] = []
        tone_raw: list[dict] = []
        # An AI failure must never break the scan: rule findings are still saved.
        with ThreadPoolExecutor(max_workers=1) as pool:
            tone_future = pool.submit(self._tone, masked) if self.voice_guide.strip() else None
            try:
                claims = self._claims(text, masked, existing)
            except Exception as exc:
                log.warning("AI claim check failed: %s", exc)
                failures += 1
            if tone_future is not None:
                try:
                    tone_raw = tone_future.result()
                except Exception as exc:
                    log.warning("AI tone check failed: %s", exc)
                    failures += 1

        findings = list(claims)
        for item in tone_raw:
            f = self._tone_finding(text, item, existing + findings)
            if f:
                findings.append(f)
        branches = 2 if tone_future is not None else 1
        status = "ok" if failures == 0 else ("error" if failures == branches else "partial")
        return AIResult(findings, status)

    # ---------- claims ----------

    def _claims(self, text: str, masked: str, existing: list[Finding]) -> list[Finding]:
        data = self.llm.generate_json(CLAIM_SYSTEM, f"Content:\n<<<\n{masked}\n>>>")
        raw = data.get("claims", []) if isinstance(data, dict) else []
        claims = []
        for c in raw[:MAX_CLAIMS]:
            if not isinstance(c, dict) or not isinstance(c.get("claim"), str):
                continue
            spot = locate(text, c.get("quote", ""), existing)
            if spot is None:
                continue
            if _overlaps(spot[0], spot[1], existing, {"Unsupported claim", "Contradicts a fact"}):
                continue  # a brand rule already flags this claim
            claims.append({"quote": text[spot[0] : spot[1]], "claim": c["claim"].strip(), "span": spot})
        if not claims:
            return []

        self.facts.ensure_indexed()
        vectors = self.llm.embed([c["claim"] for c in claims])
        for c, v in zip(claims, vectors):
            c["facts"] = self.facts.search(v, FACTS_PER_CLAIM)

        payload = [
            {
                "id": n,
                "quote": c["quote"],
                "claim": c["claim"],
                "facts": [{"code": f.code, "statement": f.statement} for f in c["facts"]],
            }
            for n, c in enumerate(claims)
        ]
        verdicts = self.llm.generate_json(JUDGE_SYSTEM, json.dumps({"claims": payload}, ensure_ascii=False))
        results = verdicts.get("results", []) if isinstance(verdicts, dict) else []

        findings: list[Finding] = []
        for r in results:
            if not isinstance(r, dict) or not isinstance(r.get("id"), int) or not 0 <= r["id"] < len(claims):
                continue
            c = claims[r["id"]]
            verdict = r.get("verdict")
            codes = {f.code: f for f in c["facts"]}
            why = r.get("why") if isinstance(r.get("why"), str) and r.get("why").strip() else None
            if verdict == "contradicted":
                fact = codes.get(r.get("fact_code"))
                if fact is None:
                    continue  # no source, no flag
                findings.append(
                    Finding(
                        type="Contradicts a fact",
                        severity="high",
                        span_start=c["span"][0],
                        span_end=c["span"][1],
                        excerpt=c["quote"],
                        why=f"{why or 'This does not match the approved fact.'} Approved: “{fact.statement}”",
                        source_code=fact.code,
                        fix=_clean_fix(r.get("fix"), c["quote"]),
                        confidence=_confidence(r.get("confidence")),
                        needs_human=True,
                        engine="ai",
                    )
                )
            elif verdict == "unsupported":
                findings.append(
                    Finding(
                        type="Unsupported claim",
                        severity="medium",
                        span_start=c["span"][0],
                        span_end=c["span"][1],
                        excerpt=c["quote"],
                        why=f"No approved fact backs this claim. {why or ''}".strip(),
                        source_code="Fact Vault",
                        fix=_clean_fix(r.get("fix"), c["quote"]),
                        confidence=_confidence(r.get("confidence")),
                        needs_human=True,
                        engine="ai",
                    )
                )
        return findings

    # ---------- tone ----------

    def _tone(self, masked: str) -> list[dict]:
        prompt = f"Voice guide:\n<<<\n{self.voice_guide}\n>>>\n\nContent:\n<<<\n{masked}\n>>>"
        data = self.llm.generate_json(TONE_SYSTEM, prompt)
        raw = data.get("issues", []) if isinstance(data, dict) else []
        return [i for i in raw[:MAX_TONE_ISSUES] if isinstance(i, dict)]

    def _tone_finding(self, text: str, item: dict, taken: list[Finding]) -> Finding | None:
        guideline = item.get("guideline")
        if not isinstance(guideline, str) or len(guideline.strip()) < 12:
            return None
        if _norm(guideline) not in _norm(self.voice_guide):
            return None  # the model must quote a real guideline
        spot = locate(text, item.get("quote", ""), taken)
        if spot is None or _overlaps(spot[0], spot[1], taken):
            return None
        section = str(item.get("section") or "").strip().lstrip("§")
        source = f"Voice §{section}" if re.fullmatch(r"\d+(\.\d+)*", section) else "Voice guide"
        confidence = _confidence(item.get("confidence"))
        why = item.get("why") if isinstance(item.get("why"), str) else ""
        quote = text[spot[0] : spot[1]]
        return Finding(
            type="Off-tone",
            severity="low",
            span_start=spot[0],
            span_end=spot[1],
            excerpt=quote,
            why=f"{why.strip()} Guide: “{guideline.strip()}”".strip(),
            source_code=source,
            fix=_clean_fix(item.get("fix"), quote),
            confidence=confidence,
            needs_human=confidence < LOW_CONFIDENCE,
            engine="ai",
        )
