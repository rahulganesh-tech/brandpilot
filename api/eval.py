"""Measure BrandPilot against the labelled test set (tests/test_set.json).

    python eval.py            # brand rules only (no keys needed)
    python eval.py --ai       # also the AI claim checker (needs GEMINI_API_KEY)

Prints precision and recall as a Markdown report.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from app.rules_engine import KIND_TYPE, Rule, check_rules

ROOT = Path(__file__).parent
KIT = json.loads((ROOT / "seed" / "brand_kit.json").read_text(encoding="utf-8"))
POSTS = json.loads((ROOT / "tests" / "test_set.json").read_text(encoding="utf-8"))["posts"]
RULES = [Rule(**r) for r in KIT["rules"]]
RULE_TYPE = {r.code: KIND_TYPE[r.kind] for r in RULES}


def pct(n: int, d: int) -> str:
    return "–" if d == 0 else f"{100 * n / d:.0f}%"


def eval_rules() -> dict:
    per_type: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])  # tp, fp, fn
    mistakes = []
    for p in POSTS:
        got = {f.source_code for f in check_rules(p["text"], RULES)}
        want = set(p["rules"])
        for code in got | want:
            t = per_type[RULE_TYPE.get(code, "Unknown")]
            if code in got and code in want:
                t[0] += 1
            elif code in got:
                t[1] += 1
                mistakes.append(f"{p['id']}: unexpected {code}")
            else:
                t[2] += 1
                mistakes.append(f"{p['id']}: missed {code}")
    tp = sum(v[0] for v in per_type.values())
    fp = sum(v[1] for v in per_type.values())
    fn = sum(v[2] for v in per_type.values())
    return {"per_type": dict(per_type), "tp": tp, "fp": fp, "fn": fn, "mistakes": mistakes}


def eval_ai() -> dict:
    from app import config
    from app.ai import AIChecker, FactMatch
    from app.gemini import GeminiClient

    if not config.GEMINI_API_KEY:
        sys.exit("Set GEMINI_API_KEY to evaluate the AI checker.")
    llm = GeminiClient(config.GEMINI_API_KEY, config.GEMINI_MODEL, config.GEMINI_EMBED_MODEL)

    class MemoryFacts:
        def __init__(self):
            self.facts = KIT["facts"]
            self.vectors = llm.embed([f"{f['code']}: {f['statement']}" for f in self.facts])

        def ensure_indexed(self):
            pass

        def search(self, vector, k):
            scored = sorted(
                ((sum(a * b for a, b in zip(vector, v)), f) for f, v in zip(self.facts, self.vectors)),
                key=lambda x: -x[0],
            )
            return [FactMatch(code=f["code"], statement=f["statement"], similarity=s) for s, f in scored[:k]]

    index = MemoryFacts()
    checker = AIChecker(llm, index, KIT["brand"]["voice_guide"])
    tp = fp = fn = 0
    mistakes, other = [], []
    for p in POSTS:
        rule_findings = check_rules(p["text"], RULES)
        result = checker.check(p["text"], rule_findings)
        found = [f for f in result.findings if f.type == "Contradicts a fact"]
        want = [a for a in p["ai"] if a["type"] == "contradicts"]
        matched = set()
        for w in want:
            hit = next(
                (i for i, f in enumerate(found) if i not in matched and f.source_code == w["fact"]
                 and (w["quote"].lower() in f.excerpt.lower() or f.excerpt.lower() in w["quote"].lower())),
                None,
            )
            if hit is None:
                fn += 1
                mistakes.append(f"{p['id']}: missed contradiction of {w['fact']} (“{w['quote']}”)")
            else:
                matched.add(hit)
                tp += 1
        for i, f in enumerate(found):
            if i not in matched:
                fp += 1
                mistakes.append(f"{p['id']}: unexpected contradiction {f.source_code} on “{f.excerpt}”")
        for f in result.findings:
            if f.type != "Contradicts a fact":
                other.append(f"{p['id']}: {f.type} on “{f.excerpt}” ({f.source_code})")
        if result.status != "ok":
            mistakes.append(f"{p['id']}: AI status {result.status}")
    return {"tp": tp, "fp": fp, "fn": fn, "mistakes": mistakes, "other": other}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ai", action="store_true")
    args = parser.parse_args()

    r = eval_rules()
    print(f"# BrandPilot evaluation ({len(POSTS)} labelled posts)\n")
    print("## Brand rules\n")
    print("| Issue type | Correct | False alarms | Missed | Precision | Recall |")
    print("|---|---|---|---|---|---|")
    for t, (tp, fp, fn) in sorted(r["per_type"].items()):
        print(f"| {t} | {tp} | {fp} | {fn} | {pct(tp, tp + fp)} | {pct(tp, tp + fn)} |")
    print(f"| **All** | {r['tp']} | {r['fp']} | {r['fn']} | **{pct(r['tp'], r['tp'] + r['fp'])}** | **{pct(r['tp'], r['tp'] + r['fn'])}** |")
    if r["mistakes"]:
        print("\nMistakes:\n" + "\n".join(f"- {m}" for m in r["mistakes"]))

    if args.ai:
        a = eval_ai()
        print("\n## AI claim checker (contradictions of approved facts)\n")
        print("| Correct | False alarms | Missed | Precision | Recall |")
        print("|---|---|---|---|---|")
        print(f"| {a['tp']} | {a['fp']} | {a['fn']} | {pct(a['tp'], a['tp'] + a['fp'])} | {pct(a['tp'], a['tp'] + a['fn'])} |")
        if a["mistakes"]:
            print("\nMistakes:\n" + "\n".join(f"- {m}" for m in a["mistakes"]))
        if a["other"]:
            print("\nOther AI flags (review by hand):\n" + "\n".join(f"- {m}" for m in a["other"]))


if __name__ == "__main__":
    main()
