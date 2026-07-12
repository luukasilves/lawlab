-- Lawlab schema (Supabase / Postgres). Idempotent: safe to re-run.
-- Reuses the existing `bills` and `bill_documents`; adds analysis tables.
-- RLS: anon key is READ-ONLY (used by the web app); workers write with the
-- service-role key. `feedback` is the one table anon may INSERT into.

-- ── existing tables (extend, don't clobber) ─────────────────────────────────
create table if not exists bills (
  id          uuid primary key default gen_random_uuid(),
  bill_number text,
  title       text,
  api_data    jsonb,
  status      text,
  created_at  timestamptz default now()
);

create table if not exists bill_documents (
  id                uuid primary key default gen_random_uuid(),
  bill_id           uuid references bills(id) on delete cascade,
  document_type     text,
  parsed_text       text,
  text_length       int,
  extraction_method text,
  created_at        timestamptz default now()
);
alter table bill_documents add column if not exists content_hash text;  -- dedup / version trigger
alter table bill_documents add column if not exists version      int default 1;
alter table bill_documents add column if not exists fetched_at    timestamptz default now();
create index if not exists bill_documents_hash_idx on bill_documents(content_hash);

-- ── analysis tables ─────────────────────────────────────────────────────────
create table if not exists analyses (
  id                uuid primary key default gen_random_uuid(),
  bill_document_id  uuid references bill_documents(id) on delete cascade,
  cache_key         text unique not null,           -- hash(text+prompt+model+checker+config)
  model             text,
  prompt_version    text,
  checker_version   text,
  config            jsonb,
  status            text default 'complete',
  created_at        timestamptz default now()
);
create index if not exists analyses_doc_idx on analyses(bill_document_id);

create table if not exists findings (
  id             uuid primary key default gen_random_uuid(),
  analysis_id    uuid references analyses(id) on delete cascade,
  source         text not null,                      -- 'deterministic' | 'llm'
  category       text not null,
  severity       text not null check (severity in ('HIGH','MEDIUM','LOW')),
  confidence     numeric not null default 1.0,       -- agreement rate (1.0 for deterministic)
  runs_found     int,
  runs_total     int,
  provision_id   text,
  location       text,
  evidence_quote text,
  char_start     int,
  char_end       int,
  title          text,
  description    text,
  reasoning      text,
  suggestion     text,
  honte_rule     text,
  check_id       text,
  created_at     timestamptz default now()
);
create index if not exists findings_analysis_idx on findings(analysis_id);

-- HÕNTE drafting rules (reference data for grounding findings)
create table if not exists honte_rules (
  id               uuid primary key default gen_random_uuid(),
  rule_id          text unique,                      -- e.g. 'HÕNTE §16'
  section          text,
  text             text,
  mapped_categories text[]
);

-- Gold-set labels for precision/recall evaluation
create table if not exists eval_labels (
  id            uuid primary key default gen_random_uuid(),
  bill_number   text,
  category      text,
  location      text,
  is_true_error boolean,
  note          text,
  created_at    timestamptz default now()
);

-- Human triage of findings (grows the gold set over time)
create table if not exists feedback (
  id          uuid primary key default gen_random_uuid(),
  finding_id  uuid references findings(id) on delete cascade,
  verdict     text check (verdict in ('confirm','dismiss')),
  note        text,
  created_at  timestamptz default now()
);

-- ── row-level security ──────────────────────────────────────────────────────
alter table bills          enable row level security;
alter table bill_documents enable row level security;
alter table analyses       enable row level security;
alter table findings       enable row level security;
alter table honte_rules    enable row level security;
alter table eval_labels    enable row level security;
alter table feedback       enable row level security;

-- public read (anon + authenticated)
do $$
declare t text;
begin
  foreach t in array array['bills','bill_documents','analyses','findings','honte_rules'] loop
    execute format($f$
      drop policy if exists %1$s_read on %1$s;
      create policy %1$s_read on %1$s for select using (true);
    $f$, t);
  end loop;
end $$;

-- anyone may submit feedback (confirm/dismiss), but not read others' notes
drop policy if exists feedback_insert on feedback;
create policy feedback_insert on feedback for insert with check (true);

-- NOTE: no INSERT/UPDATE/DELETE policies on the data tables => the anon key
-- cannot write them. Workers use the service-role key, which bypasses RLS.
