-- BrandPilot database schema (PostgreSQL / Supabase)
-- Run once in the Supabase SQL editor, or: psql "$DATABASE_URL" -f sql/schema.sql

create extension if not exists vector;
create extension if not exists pgcrypto;

create table if not exists brands (
  id          uuid primary key default gen_random_uuid(),
  name        text not null,
  voice_guide text not null default '',
  colors      jsonb not null default '[]'::jsonb,
  created_at  timestamptz not null default now()
);

-- Approved facts: the only evidence a claim can be checked against.
create table if not exists facts (
  id         uuid primary key default gen_random_uuid(),
  brand_id   uuid not null references brands(id) on delete cascade,
  code       text not null,                 -- e.g. F-07
  statement  text not null,
  source     text not null default '',
  updated_at timestamptz not null default now(),
  embedding  vector(768),
  unique (brand_id, code)
);

-- Deterministic brand rules.
create table if not exists rules (
  id          uuid primary key default gen_random_uuid(),
  brand_id    uuid not null references brands(id) on delete cascade,
  code        text not null,                -- e.g. R-2.3
  kind        text not null check (kind in ('banned_word','term','tone','claim_policy','accessibility')),
  pattern     text not null,
  replacement text,                         -- null = no automatic fix
  message     text not null,
  severity    text not null default 'medium' check (severity in ('low','medium','high')),
  unique (brand_id, code)
);

create table if not exists scans (
  id         uuid primary key default gen_random_uuid(),
  brand_id   uuid not null references brands(id) on delete cascade,
  author     text not null default 'creator',
  channel    text not null default 'social',
  content    text not null,
  status     text not null default 'draft' check (status in ('draft','in_review','approved','sent_back')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists versions (
  id         uuid primary key default gen_random_uuid(),
  scan_id    uuid not null references scans(id) on delete cascade,
  number     int  not null,
  content    text not null,
  created_by text not null,
  note       text not null default '',
  created_at timestamptz not null default now(),
  unique (scan_id, number)
);

create table if not exists issues (
  id              uuid primary key default gen_random_uuid(),
  scan_id         uuid not null references scans(id) on delete cascade,
  type            text not null,
  severity        text not null check (severity in ('low','medium','high')),
  span_start      int  not null,
  span_end        int  not null,
  excerpt         text not null,
  why             text not null,
  source_code     text not null,            -- every issue cites a rule or fact
  fix             text,                     -- replacement text; null = needs a human edit
  confidence      real not null default 1.0,
  needs_human     boolean not null default false,
  engine          text not null default 'rules',
  decision        text not null default 'open' check (decision in ('open','accepted','edited','ignored')),
  decision_reason text,
  created_at      timestamptz not null default now()
);
create index if not exists issues_scan_idx on issues(scan_id);

create table if not exists reviews (
  id         uuid primary key default gen_random_uuid(),
  scan_id    uuid not null references scans(id) on delete cascade,
  reviewer   text not null,
  action     text not null check (action in ('approve','send_back')),
  comment    text not null default '',
  created_at timestamptz not null default now()
);

-- Nearest approved facts for a claim embedding (used by the claim checker).
create or replace function match_facts(p_brand uuid, p_embedding vector(768), p_count int default 3)
returns table (id uuid, code text, statement text, source text, similarity float)
language sql stable as $$
  select f.id, f.code, f.statement, f.source, 1 - (f.embedding <=> p_embedding) as similarity
  from facts f
  where f.brand_id = p_brand and f.embedding is not null
  order by f.embedding <=> p_embedding
  limit p_count;
$$;

-- Day 2: record whether the AI checks ran for each scan ('off', 'ok', 'partial', 'error').
alter table scans add column if not exists ai_status text not null default 'off';

-- Day 3: image checks. The uploaded image is kept with its scan.
alter table scans add column if not exists image bytea;
alter table scans add column if not exists image_type text;
