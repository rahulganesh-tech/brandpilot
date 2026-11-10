"""Deterministic brand checks.

Rules are exact and repeatable, so they run before any AI step. Every finding
cites the rule code it came from ("no source, no flag").
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

KIND_TYPE = {
    "banned_word": "Banned word",
    "term": "Wrong term",
    "tone": "Off-tone",
    "claim_policy": "Unsupported claim",
    "accessibility": "Accessibility",
}
WORD_KINDS = {"banned_word", "term"}
MAX_FINDINGS_PER_RULE = 20


@dataclass
class Rule:
    code: str
    kind: str
    pattern: str
    message: str
    severity: str = "medium"
    replacement: str | None = None


@dataclass
class Finding:
    type: str
    severity: str
    span_start: int
    span_end: int
    excerpt: str
    why: str
    source_code: str
    fix: str | None
    confidence: float = 1.0
    needs_human: bool = False
    engine: str = "rules"

    def to_dict(self) -> dict:
        return asdict(self)


def compile_rule(rule: Rule) -> re.Pattern[str]:
    """Word rules match whole words, case-insensitively. Other kinds are regexes."""
    if rule.kind in WORD_KINDS:
        word = rule.pattern.strip()
        if not word:
            raise re.error("empty pattern")
        left = r"\b" if re.match(r"\w", word[0]) else ""
        right = r"\b" if re.match(r"\w", word[-1]) else ""
        return re.compile(left + re.escape(word) + right, re.IGNORECASE)
    return re.compile(rule.pattern)


def validate_rule(rule: Rule) -> None:
    """Raise ValueError with a readable message if the rule cannot be used."""
    if rule.kind not in KIND_TYPE:
        raise ValueError(f"Unknown rule kind '{rule.kind}'")
    if len(rule.pattern) > 300:
        raise ValueError(f"Rule {rule.code}: pattern is too long (max 300 characters)")
    try:
        rx = compile_rule(rule)
    except re.error as exc:
        raise ValueError(f"Rule {rule.code}: invalid pattern ({exc})") from exc
    if rx.search("") is not None:
        raise ValueError(f"Rule {rule.code}: pattern matches empty text")
    if rule.kind == "term" and rule.replacement is None:
        raise ValueError(f"Rule {rule.code}: a term rule needs the correct term as its replacement")


def _replacement_for(rx_match: re.Match[str], rule: Rule) -> str | None:
    if rule.replacement is None:
        return None
    if rule.kind in WORD_KINDS:
        return rule.replacement
    try:
        return rx_match.expand(rule.replacement)
    except (re.error, IndexError):
        return rule.replacement


_LINK = re.compile(r"@|://|^www\.", re.IGNORECASE)


def _inside_link(text: str, start: int, end: int) -> bool:
    """True if the match sits inside an email address or URL (e.g. hello@nutricrunch.in)."""
    left = max(text.rfind(c, 0, start) for c in " \n\t") + 1
    right_candidates = [i for i in (text.find(c, end) for c in " \n\t") if i >= 0]
    right = min(right_candidates) if right_candidates else len(text)
    return bool(_LINK.search(text[left:right]))


def check_rules(text: str, rules: list[Rule]) -> list[Finding]:
    findings: list[Finding] = []
    seen: set[tuple[str, int]] = set()
    for rule in rules:
        try:
            rx = compile_rule(rule)
        except re.error:
            continue
        for count, m in enumerate(rx.finditer(text)):
            if count >= MAX_FINDINGS_PER_RULE:
                break
            if m.end() == m.start() or (rule.code, m.start()) in seen:
                continue
            if _inside_link(text, m.start(), m.end()):
                continue
            fix = _replacement_for(m, rule)
            if fix is not None and fix == m.group(0):
                continue  # already written correctly (e.g. term rules that fix capitalisation)
            seen.add((rule.code, m.start()))
            findings.append(
                Finding(
                    type=KIND_TYPE[rule.kind],
                    severity=rule.severity,
                    span_start=m.start(),
                    span_end=m.end(),
                    excerpt=m.group(0),
                    why=rule.message,
                    source_code=rule.code,
                    fix=fix,
                    needs_human=rule.kind == "claim_policy" or rule.severity == "high",
                )
            )
    findings.sort(key=lambda f: (f.span_start, f.source_code))
    return findings


_SPACE_FIXES = [
    (re.compile(r"[ \t]{2,}"), " "),
    (re.compile(r" +([,.!?;:])"), r"\1"),
]


def apply_fix(text: str, excerpt: str, replacement: str, start: int | None = None) -> str:
    """Replace one occurrence of `excerpt` (preferring the one at `start`)."""
    if start is not None and text[start : start + len(excerpt)] == excerpt:
        idx = start
    else:
        idx = text.find(excerpt)
        if idx < 0:
            raise ValueError("The flagged text is no longer in the content")
    new_text = text[:idx] + replacement + text[idx + len(excerpt) :]
    for rx, sub in _SPACE_FIXES:
        new_text = rx.sub(sub, new_text)
    return new_text
