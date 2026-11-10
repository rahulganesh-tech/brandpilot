"""All SQL lives here."""
from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from .rules_engine import Finding, Rule

# ---------- brands ----------


def list_brands(conn: Connection) -> list[dict]:
    return conn.execute("select id, name, created_at from brands order by created_at").fetchall()


def create_brand(conn: Connection, name: str, voice_guide: str, colors: list[str]) -> dict:
    return conn.execute(
        "insert into brands (name, voice_guide, colors) values (%s, %s, %s) returning *",
        (name, voice_guide, Jsonb(colors)),
    ).fetchone()


def get_brand(conn: Connection, brand_id: str) -> dict | None:
    return conn.execute("select * from brands where id = %s", (brand_id,)).fetchone()


def update_brand(conn: Connection, brand_id: str, fields: dict) -> dict | None:
    if not fields:
        return get_brand(conn, brand_id)
    if "colors" in fields:
        fields["colors"] = Jsonb(fields["colors"])
    sets = ", ".join(f"{k} = %({k})s" for k in fields)
    return conn.execute(
        f"update brands set {sets} where id = %(id)s returning *", {**fields, "id": brand_id}
    ).fetchone()


# ---------- facts & rules ----------


def list_facts(conn: Connection, brand_id: str) -> list[dict]:
    return conn.execute(
        "select id, code, statement, source, updated_at, embedding is not null as indexed "
        "from facts where brand_id = %s order by code",
        (brand_id,),
    ).fetchall()


def upsert_facts(conn: Connection, brand_id: str, facts: list[dict]) -> int:
    with conn.cursor() as cur:
        cur.executemany(
            """insert into facts (brand_id, code, statement, source) values (%s, %s, %s, %s)
               on conflict (brand_id, code) do update
               set statement = excluded.statement, source = excluded.source,
                   updated_at = now(), embedding = null""",
            [(brand_id, f["code"], f["statement"], f["source"]) for f in facts],
        )
    return len(facts)


def delete_fact(conn: Connection, fact_id: str) -> bool:
    return conn.execute("delete from facts where id = %s", (fact_id,)).rowcount > 0


def list_rules(conn: Connection, brand_id: str) -> list[dict]:
    return conn.execute(
        "select id, code, kind, pattern, replacement, message, severity from rules "
        "where brand_id = %s order by code",
        (brand_id,),
    ).fetchall()


def rules_for_engine(conn: Connection, brand_id: str) -> list[Rule]:
    return [
        Rule(
            code=r["code"],
            kind=r["kind"],
            pattern=r["pattern"],
            message=r["message"],
            severity=r["severity"],
            replacement=r["replacement"],
        )
        for r in list_rules(conn, brand_id)
    ]


def upsert_rules(conn: Connection, brand_id: str, rules: list[dict]) -> int:
    with conn.cursor() as cur:
        cur.executemany(
            """insert into rules (brand_id, code, kind, pattern, replacement, message, severity)
               values (%s, %s, %s, %s, %s, %s, %s)
               on conflict (brand_id, code) do update
               set kind = excluded.kind, pattern = excluded.pattern,
                   replacement = excluded.replacement, message = excluded.message,
                   severity = excluded.severity""",
            [
                (brand_id, r["code"], r["kind"], r["pattern"], r["replacement"], r["message"], r["severity"])
                for r in rules
            ],
        )
    return len(rules)


def delete_rule(conn: Connection, rule_id: str) -> bool:
    return conn.execute("delete from rules where id = %s", (rule_id,)).rowcount > 0


# ---------- scans ----------


def create_scan(conn: Connection, brand_id: str, author: str, channel: str, content: str) -> dict:
    return conn.execute(
        "insert into scans (brand_id, author, channel, content) values (%s, %s, %s, %s) returning id, brand_id",
        (brand_id, author, channel, content),
    ).fetchone()


SCAN_COLUMNS = (
    "id, brand_id, author, channel, content, status, ai_status, created_at, updated_at, "
    "image is not null as has_image"
)


def get_scan(conn: Connection, scan_id: str, lock: bool = False) -> dict | None:
    sql = f"select {SCAN_COLUMNS} from scans where id = %s" + (" for update" if lock else "")
    return conn.execute(sql, (scan_id,)).fetchone()


def create_image_scan(
    conn: Connection, brand_id: str, author: str, channel: str, content: str, image: bytes, image_type: str
) -> dict:
    return conn.execute(
        f"""insert into scans (brand_id, author, channel, content, image, image_type)
            values (%s, %s, %s, %s, %s, %s) returning {SCAN_COLUMNS}""",
        (brand_id, author, channel, content, image, image_type),
    ).fetchone()


def get_scan_image(conn: Connection, scan_id: str) -> dict | None:
    return conn.execute(
        "select image, image_type from scans where id = %s and image is not null", (scan_id,)
    ).fetchone()


def list_scans(conn: Connection, brand_id: str | None, status: str | None) -> list[dict]:
    return conn.execute(
        """select s.id, s.brand_id, s.author, s.channel, s.status, s.created_at, s.updated_at,
                  left(s.content, 140) as preview, s.image is not null as has_image,
                  count(i.id) filter (where i.decision = 'open') as open_issues,
                  count(i.id) as total_issues
           from scans s left join issues i on i.scan_id = s.id
           where (%(brand)s::uuid is null or s.brand_id = %(brand)s::uuid)
             and (%(status)s::text is null or s.status = %(status)s::text)
           group by s.id order by s.updated_at desc limit 100""",
        {"brand": brand_id, "status": status},
    ).fetchall()


def set_scan_content(conn: Connection, scan_id: str, content: str) -> None:
    conn.execute("update scans set content = %s, updated_at = now() where id = %s", (content, scan_id))


def set_scan_status(conn: Connection, scan_id: str, status: str) -> None:
    conn.execute("update scans set status = %s, updated_at = now() where id = %s", (status, scan_id))


def add_version(conn: Connection, scan_id: str, content: str, created_by: str, note: str) -> dict:
    return conn.execute(
        """insert into versions (scan_id, number, content, created_by, note)
           values (%s, coalesce((select max(number) from versions where scan_id = %s), 0) + 1, %s, %s, %s)
           returning *""",
        (scan_id, scan_id, content, created_by, note),
    ).fetchone()


def list_versions(conn: Connection, scan_id: str) -> list[dict]:
    return conn.execute(
        "select * from versions where scan_id = %s order by number", (scan_id,)
    ).fetchall()


# ---------- issues ----------


def add_issues(conn: Connection, scan_id: str, findings: list[Finding]) -> None:
    if not findings:
        return
    with conn.cursor() as cur:
        cur.executemany(
            """insert into issues (scan_id, type, severity, span_start, span_end, excerpt, why,
                                   source_code, fix, confidence, needs_human, engine)
               values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            [
                (scan_id, f.type, f.severity, f.span_start, f.span_end, f.excerpt, f.why,
                 f.source_code, f.fix, f.confidence, f.needs_human, f.engine)
                for f in findings
            ],
        )


def replace_open_issues(conn: Connection, scan_id: str, findings: list[Finding]) -> None:
    # Image findings (colours, contrast) belong to the picture, not the text, so a text re-check keeps them.
    conn.execute(
        "delete from issues where scan_id = %s and decision = 'open' and engine <> 'vision'", (scan_id,)
    )
    add_issues(conn, scan_id, findings)


def list_issues(conn: Connection, scan_id: str) -> list[dict]:
    return conn.execute(
        "select * from issues where scan_id = %s order by decision != 'open', span_start, source_code",
        (scan_id,),
    ).fetchall()


def get_issue(conn: Connection, issue_id: str) -> dict | None:
    return conn.execute("select * from issues where id = %s", (issue_id,)).fetchone()


def set_issue_decision(conn: Connection, issue_id: str, decision: str, reason: str | None) -> None:
    conn.execute(
        "update issues set decision = %s, decision_reason = %s where id = %s",
        (decision, reason, issue_id),
    )


def move_issue(conn: Connection, issue_id: str, start: int, end: int) -> None:
    conn.execute(
        "update issues set span_start = %s, span_end = %s where id = %s", (start, end, issue_id)
    )


# ---------- reviews & insights ----------


def add_review(conn: Connection, scan_id: str, reviewer: str, action: str, comment: str) -> dict:
    return conn.execute(
        "insert into reviews (scan_id, reviewer, action, comment) values (%s, %s, %s, %s) returning *",
        (scan_id, reviewer, action, comment),
    ).fetchone()


def list_reviews(conn: Connection, scan_id: str) -> list[dict]:
    return conn.execute(
        "select * from reviews where scan_id = %s order by created_at", (scan_id,)
    ).fetchall()


def rule_stats(conn: Connection, brand_id: str) -> list[dict]:
    return conn.execute(
        """select i.source_code, min(i.type) as type,
                  count(*) as total,
                  count(*) filter (where i.decision = 'ignored') as ignored,
                  count(*) filter (where i.decision in ('accepted', 'edited')) as fixed,
                  (array_agg(i.decision_reason order by i.created_at desc)
                     filter (where i.decision = 'ignored'))[1:3] as sample_reasons
           from issues i join scans s on s.id = i.scan_id
           where s.brand_id = %s
           group by i.source_code
           order by ignored desc, total desc""",
        (brand_id,),
    ).fetchall()


def scan_status_counts(conn: Connection, brand_id: str) -> dict:
    rows = conn.execute(
        "select status, count(*) as n from scans where brand_id = %s group by status", (brand_id,)
    ).fetchall()
    return {r["status"]: r["n"] for r in rows}


# ---------- fact embeddings ----------


def _vec(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.7f}" for x in v) + "]"


def facts_without_embeddings(conn: Connection, brand_id: str) -> list[dict]:
    return conn.execute(
        "select id, code, statement from facts where brand_id = %s and embedding is null order by code",
        (brand_id,),
    ).fetchall()


def set_fact_embeddings(conn: Connection, rows: list[tuple[str, list[float]]]) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            "update facts set embedding = %s::vector where id = %s",
            [(_vec(v), fid) for fid, v in rows],
        )


def match_facts(conn: Connection, brand_id: str, vector: list[float], k: int) -> list[dict]:
    return conn.execute(
        "select code, statement, similarity from match_facts(%s, %s::vector, %s)",
        (brand_id, _vec(vector), k),
    ).fetchall()


def set_ai_status(conn: Connection, scan_id: str, status: str) -> None:
    conn.execute("update scans set ai_status = %s where id = %s", (status, scan_id))
