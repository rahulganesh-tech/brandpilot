"""Load the sample brand kit (and optionally demo scans).

Usage (from the api/ folder):
    python -m seed.seed            # brand, facts, rules
    python -m seed.seed --demo     # also create demo scans
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app import db, repo
from app.pipeline import scan_text
from app.rules_engine import Rule, validate_rule

KIT = Path(__file__).with_name("brand_kit.json")


def seed(demo: bool = False) -> str:
    kit = json.loads(KIT.read_text(encoding="utf-8"))
    for r in kit["rules"]:
        validate_rule(Rule(**r))

    with db.connection() as conn:
        b = kit["brand"]
        existing = conn.execute("select id from brands where name = %s", (b["name"],)).fetchone()
        if existing:
            brand_id = str(existing["id"])
            repo.update_brand(conn, brand_id, {"voice_guide": b["voice_guide"], "colors": b["colors"]})
        else:
            brand_id = str(repo.create_brand(conn, b["name"], b["voice_guide"], b["colors"])["id"])

        repo.upsert_facts(conn, brand_id, kit["facts"])
        repo.upsert_rules(conn, brand_id, kit["rules"])
        print(f"Brand {b['name']} ({brand_id}): {len(kit['facts'])} facts, {len(kit['rules'])} rules")

        if demo:
            rules = repo.rules_for_engine(conn, brand_id)
            for d in kit["demo_scans"]:
                scan = repo.create_scan(conn, brand_id, "Creator", d["channel"], d["content"])
                repo.add_version(conn, str(scan["id"]), d["content"], "Creator", "First draft")
                repo.replace_open_issues(conn, str(scan["id"]), scan_text(d["content"], rules))
            print(f"Created {len(kit['demo_scans'])} demo scans")
    return brand_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true", help="also create demo scans")
    seed(parser.parse_args().demo)
    db.close_pool()
