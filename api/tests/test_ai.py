import json
from pathlib import Path

from app.ai import AIChecker, FactMatch
from app.rules_engine import Rule, check_rules

from .fake_llm import FakeLLM, bag_of_words

KIT = json.loads((Path(__file__).parents[1] / "seed" / "brand_kit.json").read_text(encoding="utf-8"))
GUIDE = KIT["brand"]["voice_guide"]
RULES = [Rule(**r) for r in KIT["rules"]]


class MemoryFacts:
    def __init__(self):
        self.facts = [(f["code"], f["statement"], bag_of_words(f"{f['code']}: {f['statement']}")) for f in KIT["facts"]]
        self.indexed = False

    def ensure_indexed(self):
        self.indexed = True

    def search(self, vector, k):
        scored = [(sum(a * b for a, b in zip(vector, v)), c, s) for c, s, v in self.facts]
        scored.sort(reverse=True)
        return [FactMatch(code=c, statement=s, similarity=sim) for sim, c, s in scored[:k]]


def run(text, llm, guide=GUIDE):
    existing = check_rules(text, RULES)
    return AIChecker(llm, MemoryFacts(), guide).check(text, existing), existing


def judge_all(verdict, fact_code=None, fix=None):
    def judge(payload):
        out = []
        for c in payload["claims"]:
            code = fact_code(c) if callable(fact_code) else fact_code
            out.append({"id": c["id"], "verdict": verdict, "fact_code": code, "why": "Checked.", "fix": fix, "confidence": 0.9})
        return out

    return judge


TEXT = "Each NutriCrunch bar packs 25 g of protein."
CLAIM = [{"quote": "25 g of protein", "claim": "Each bar has 25 g of protein."}]


def test_contradiction_cites_a_retrieved_fact():
    llm = FakeLLM(claims=CLAIM, judge=judge_all("contradicted", lambda c: c["facts"][0]["code"], "20 g of protein"))
    result, _ = run(TEXT, llm)
    assert result.status == "ok"
    [f] = result.findings
    assert f.type == "Contradicts a fact" and f.source_code == "F-01"
    assert f.excerpt == "25 g of protein" and TEXT[f.span_start : f.span_end] == f.excerpt
    assert f.fix == "20 g of protein" and f.needs_human and f.engine == "ai"
    assert "20 g of protein" in f.why  # shows the approved fact


def test_contradiction_with_made_up_source_is_dropped():
    llm = FakeLLM(claims=CLAIM, judge=judge_all("contradicted", "F-99"))
    result, _ = run(TEXT, llm)
    assert result.findings == []


def test_contradiction_citing_a_fact_that_was_not_retrieved_is_dropped():
    llm = FakeLLM(claims=CLAIM, judge=judge_all("contradicted", "F-13"))  # founding year: not a top match
    result, _ = run(TEXT, llm)
    assert result.findings == []


def test_unsupported_claim_is_flagged_for_a_human():
    llm = FakeLLM(
        claims=[{"quote": "used by 500 gyms", "claim": "NutriCrunch is used by 500 gyms."}],
        judge=judge_all("unsupported"),
    )
    result, _ = run("NutriCrunch is used by 500 gyms across India.", llm)
    [f] = result.findings
    assert f.type == "Unsupported claim" and f.source_code == "Fact Vault" and f.needs_human


def test_supported_claim_is_not_flagged():
    llm = FakeLLM(claims=CLAIM, judge=judge_all("supported", "F-01"))
    result, _ = run(TEXT, llm)
    assert result.findings == []


def test_quote_not_in_content_is_dropped():
    llm = FakeLLM(claims=[{"quote": "30 g of protein", "claim": "x"}], judge=judge_all("unsupported"))
    result, _ = run(TEXT, llm)
    assert result.findings == []


def test_claim_already_flagged_by_a_rule_is_skipped():
    text = "Meet India's #1 protein bar."
    llm = FakeLLM(claims=[{"quote": "India's #1 protein bar", "claim": "It is India's top bar."}], judge=judge_all("unsupported"))
    result, existing = run(text, llm)
    assert any(f.source_code == "R-4.1" for f in existing)
    assert result.findings == []


def test_personal_data_never_reaches_the_model():
    llm = FakeLLM()
    run("Write to priya@example.com or call 98765 43210 for bulk orders.", llm)
    assert llm.prompts and all("priya" not in p and "98765" not in p for p in llm.prompts)


def test_tone_issue_must_quote_a_real_guideline():
    tone = [
        {"quote": "lazy people", "guideline": "We don't shame food choices.", "section": "2.5", "why": "Shaming.", "fix": "busy people", "confidence": 0.9},
        {"quote": "snack", "guideline": "Never say snack.", "section": "9.9", "why": "Invented rule.", "fix": None, "confidence": 0.9},
    ]
    result, _ = run("A snack for lazy people.", FakeLLM(tone=tone))
    [f] = result.findings
    assert f.type == "Off-tone" and f.source_code == "Voice §2.5" and f.fix == "busy people"
    assert "We don't shame food choices." in f.why


def test_low_confidence_tone_goes_to_a_human():
    tone = [{"quote": "lazy people", "guideline": "We don't shame food choices.", "section": "2.5", "why": "x", "fix": None, "confidence": 0.4}]
    result, _ = run("A snack for lazy people.", FakeLLM(tone=tone))
    assert result.findings[0].needs_human


def test_ai_failure_keeps_scan_alive():
    result, _ = run(TEXT, FakeLLM(fail={"claims", "tone"}))
    assert result.status == "error" and result.findings == []
    tone = [{"quote": "lazy people", "guideline": "We don't shame food choices.", "section": "2.5", "why": "x", "fix": None, "confidence": 0.9}]
    result, _ = run("A snack for lazy people.", FakeLLM(fail={"claims"}, tone=tone))
    assert result.status == "partial" and len(result.findings) == 1
