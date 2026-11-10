# BrandPilot — Project Brief for the AI agent (Antigravity)

Team Furious · CodeTitans India 2026 · Problem by Inkloom AI
Round 2 window: 8 Nov 2026 10:00 IST → 11 Nov 2026 10:00 IST

## What we are building
BrandPilot is a pre-publish brand-governance tool. A brand admin uploads guidelines,
approved facts, banned words and terms once. A creator pastes a post (or uploads an image).
BrandPilot flags issues, explains each one with the exact rule or fact it came from, and
suggests the smallest fix. A manager approves or sends back. AI suggests; humans decide.

Core flow that MUST work end to end (highest priority, 30% of score):
Brand Vault setup → New Scan → Issue cards (why + source + fix) → Accept / Edit / Ignore-with-reason → Manager approve → Saved version

## Stack
- Frontend: Next.js (App Router, TypeScript) + Tailwind CSS → Cloud Run service `brandpilot-web`
- Backend: FastAPI (Python 3.11) → Cloud Run service `brandpilot-api`
- Database + auth: Supabase (Postgres + pgvector + Supabase Auth)
- LLM: Gemini API (JSON mode, temperature 0)
- Embeddings: Gemini `text-embedding` model (keeps the container small); 768-dim vectors in pgvector
- Rules: plain Python (regex + term lists); spaCy only if needed
- Images (Day 3): Tesseract OCR + Pillow for colour/contrast
- Region: asia-south1 (Mumbai)

## Data model (Supabase)
- brands(id, name, voice_guide text, colors jsonb, created_at)
- facts(id, brand_id, code text e.g. 'F-07', statement text, source text, updated_at, embedding vector(768))
- rules(id, brand_id, code text e.g. 'R-2.3', kind enum[banned_word, term, tone, claim_policy, accessibility], pattern text, message text, severity enum[low, medium, high])
- scans(id, brand_id, author_id, channel text, content text, status enum[draft, in_review, approved, sent_back], created_at)
- issues(id, scan_id, type text, severity, span_start int, span_end int, excerpt text, why text, source_code text, fix text, confidence float, needs_human bool, decision enum[open, accepted, edited, ignored], decision_reason text)
- versions(id, scan_id, content text, created_by, created_at)
- reviews(id, scan_id, reviewer_id, action enum[approve, send_back], comment text, created_at)
- profiles(id, role enum[admin, creator, manager])

## API (FastAPI)
- POST /brands, GET /brands/{id}
- POST /brands/{id}/facts (bulk), POST /brands/{id}/rules (bulk)
- POST /scans  {brand_id, channel, content} → runs pipeline, returns scan + issues
- PATCH /issues/{id}  {decision, reason, edited_text?}
- POST /scans/{id}/review  {action, comment}
- GET /brands/{id}/insights  → most-overridden rules (Gap Radar), top issue types
- GET /health

## Scan pipeline (in this order)
1. Rule engine: banned words, wrong terms, "!!", ALL CAPS, etc. Deterministic. confidence = 1.0
2. Claim extraction: Gemini returns JSON list of factual claims with character spans.
3. Retrieval: embed each claim, top-3 facts from pgvector for that brand.
4. Judge: Gemini receives ONLY the claim + retrieved facts. Returns
   {verdict: supported|unsupported|outdated, fact_code, why, fix, confidence}.
   - If verdict is not "supported" and fact_code is missing or not in the retrieved set → DISCARD ("no source, no flag").
   - Unsupported claims with no matching fact → flag as "Unsupported claim", source = claims policy rule.
5. Tone: Gemini compares text to voice_guide; must quote the guide line it uses.
6. Gate: confidence < 0.7 OR type == claim → needs_human = true.
7. Mask emails/phone numbers before any Gemini call.

All Gemini calls: temperature 0, response_mime_type application/json, validated with Pydantic; one retry on invalid JSON.

## Screens
1. Vault — edit voice guide, facts table, rules table, upload JSON/CSV
2. New Scan — channel select + text box (+ image upload Day 3)
3. Results — text with highlighted spans; issue cards coloured by type; Accept / Edit / Ignore (reason required)
4. Review — manager view, version diff, Approve / Send back
5. Insights — Gap Radar (rules overridden most), issue counts

Issue card shows: TYPE · SEVERITY, Why, Source (code), Fix, buttons. Never show a flag without a source.

## Quality rules for the agent
- Small commits with clear messages; one feature per branch/PR is fine but not required.
- No secrets in code. Read from env: GEMINI_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_KEY, NEXT_PUBLIC_API_URL, NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY.
- Every endpoint has a basic pytest. Keep `tests/test_set.json` (30 labelled posts) and a script `eval.py` that prints precision/recall per issue type.
- Seed script loads the sample brand kit so the live demo is never empty.
- README: setup, architecture diagram, demo login, test results, AI-assistance disclosure (Antigravity + Gemini).

## Milestones
- Day 1 (8 Nov): DB + Vault APIs + rule engine + Next.js screens with mock data; both services live on Cloud Run.
- Day 2 (9 Nov): claim pipeline + tone check + real issue cards + accept/edit/ignore + login/roles + approve + versions.
- Day 3 (10 Nov): Gap Radar + basic image check (OCR → same scan, contrast check); run eval; fix bugs; README; updated PDF; SUBMIT by night.

Out of scope for Round 2: Docs add-on (Round 3), video/audio, auto-publishing.
