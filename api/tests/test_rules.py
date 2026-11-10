import json
from pathlib import Path

import pytest

from app.privacy import mask_pii
from app.rules_engine import Rule, apply_fix, check_rules, validate_rule

KIT = json.loads((Path(__file__).parents[1] / "seed" / "brand_kit.json").read_text(encoding="utf-8"))
RULES = [Rule(**r) for r in KIT["rules"]]


def codes(text: str) -> set[str]:
    return {f.source_code for f in check_rules(text, RULES)}


def test_all_seed_rules_are_valid():
    for r in RULES:
        validate_rule(r)


def test_demo_post_flags_expected_issues():
    text = "Meet India's #1 protein bar — 100% sugar-free! Grab yours now, guys!!"
    found = {f.source_code: f for f in check_rules(text, RULES)}
    assert {"R-4.1", "R-4.5", "R-1.2a", "R-2.3a"} <= set(found)
    assert found["R-4.5"].fix == "no added sugar"
    assert found["R-4.1"].needs_human is True
    assert found["R-4.1"].fix is None


def test_every_finding_cites_a_source_and_exact_span():
    text = "OMG, Nutri Crunch is the BEST snack. Click here! #proteinforstudents"
    for f in check_rules(text, RULES):
        assert f.source_code
        assert text[f.span_start : f.span_end] == f.excerpt


def test_clean_post_has_no_findings():
    assert codes("NutriCrunch has 20 g of protein in every bar, with no added sugar.") == set()


def test_word_rules_respect_word_boundaries():
    assert "R-2.4b" not in codes("Try our new brownie flavour.")  # 'bro' inside 'brownie'
    assert "R-2.4b" in codes("Hey bro, try this.")


def test_term_rule_skips_correct_spelling_but_fixes_wrong_case():
    assert "R-3.1c" not in codes("NutriCrunch is here.")
    found = [f for f in check_rules("Nutricrunch is here.", RULES) if f.source_code == "R-3.1c"]
    assert found and found[0].fix == "NutriCrunch"


def test_caps_rule_allows_fssai():
    assert "R-2.3b" not in codes("Made in an FSSAI-licensed facility.")
    assert "R-2.3b" in codes("This is AMAZING.")


def test_apply_fix_replaces_and_tidies_spaces():
    text = "Grab yours now, guys!!"
    out = apply_fix(text, "!!", "!", text.index("!!"))
    assert out == "Grab yours now, guys!"
    assert apply_fix("a  great bar", "great", "", 3) == "a bar"


def test_apply_fix_raises_when_text_is_gone():
    with pytest.raises(ValueError):
        apply_fix("hello", "bye", "x")


@pytest.mark.parametrize(
    "rule",
    [
        Rule(code="X", kind="tone", pattern="(", message="m"),
        Rule(code="X", kind="tone", pattern="a*", message="m"),
        Rule(code="X", kind="term", pattern="foo", message="m"),
        Rule(code="X", kind="nope", pattern="foo", message="m"),
    ],
)
def test_invalid_rules_are_rejected(rule):
    with pytest.raises(ValueError):
        validate_rule(rule)


def test_mask_pii():
    out = mask_pii("Mail priya@example.com or call +91 98765 43210 today")
    assert "priya" not in out and "98765" not in out
    assert "[EMAIL]" in out and "[PHONE]" in out


def test_rules_ignore_emails_and_links():
    assert codes("Mail hello@nutricrunch.in or visit https://nutricrunch.in/best-deals") == set()
    assert "R-3.1c" in codes("Nutricrunch is great. Mail hello@nutricrunch.in")


def test_rules_match_the_labelled_test_set():
    import eval as evaluation

    r = evaluation.eval_rules()
    assert r["fp"] == 0 and r["fn"] == 0, r["mistakes"]
