-- Lawlab schema (Supabase / Postgres). Idempotent: safe to re-run.
-- Transparency model: everything a paid analysis run produces is persisted and
-- publicly readable — per-sample raw LLM outputs (analysis_samples), run stats
-- incl. sub-threshold clusters (analyses.stats), token/cost usage, and skeptic
-- verdicts on findings. pipeline_runs is the freshness source of truth.
-- RLS: anon key is READ-ONLY (web app + public REST); workers write with the
-- service-role key. `feedback` is the one table anon may INSERT into.

-- ── bills ────────────────────────────────────────────────────────────────────
create table if not exists bills (
  id           uuid primary key default gen_random_uuid(),
  bill_number  text,
  title        text,
  api_data     jsonb,
  status       text,                    -- proceedingStatus (+ left_proceedings from sweep)
  last_seen_at timestamptz,             -- last time the listing sweep saw this bill
  created_at   timestamptz default now()
);

create table if not exists bill_documents (
  id                uuid primary key default gen_random_uuid(),
  bill_id           uuid references bills(id) on delete cascade,
  document_type     text,
  parsed_text       text,
  text_length       int,
  extraction_method text,
  content_hash      text,               -- sha256(parsed_text) = text_sha of the cache keys
  version           int default 1,
  fetched_at        timestamptz default now(),
  created_at        timestamptz default now()
);
create index if not exists bill_documents_hash_idx on bill_documents(content_hash);
-- retires the version-collision class: a duplicate bump now errors instead of inserting
create unique index if not exists bill_documents_bill_type_version_uq
  on bill_documents(bill_id, document_type, version);

-- ── analyses ─────────────────────────────────────────────────────────────────
-- One immutable row per (document text, engine fingerprint). History accrues as
-- prompts/checks/models evolve; cache_key UNIQUE is the idempotency backstop.
create table if not exists analyses (
  id                uuid primary key default gen_random_uuid(),
  bill_document_id  uuid references bill_documents(id) on delete cascade,
  cache_key         text unique not null,  -- sha256(text_sha | engine-manifest fp)[:32]
  llm_cache_key     text,                  -- sha256(text_sha | provider,model,n,temp,interpretive prompt_sha)[:32]
  model             text,
  provider          text,                  -- 'openrouter' | 'anthropic'
  prompt_version    text,                  -- human label, e.g. 'ic-v1'
  checker_version   text,                  -- derived label, e.g. 'section_numbering@1,eif_refs@1'
  engine            jsonb,                 -- full manifest: provider/model/params/checks/passes+prompt shas
  config            jsonb,                 -- {samples,k,temperature,used_llm}
  stats             jsonb,                 -- per-sample counts + clusters incl. kept:false sub-threshold
  duration_ms       int,
  input_tokens      int,
  output_tokens     int,
  cost_usd          numeric(10,4),
  status            text default 'complete',
  created_at        timestamptz default now()
);
create index if not exists analyses_doc_idx     on analyses(bill_document_id);
create index if not exists analyses_llm_key_idx on analyses(llm_cache_key);

-- ── analysis_samples ─────────────────────────────────────────────────────────
-- One row per LLM call: the raw material behind every published finding.
-- reused=true marks samples copied from a prior analysis via llm_cache_key.
create table if not exists analysis_samples (
  id                 uuid primary key default gen_random_uuid(),
  analysis_id        uuid not null references analyses(id) on delete cascade,
  pass_id            text not null,          -- 'interpretive' | 'refute' | future pass ids
  sample_idx         int  not null,          -- 0..N-1 for sampled passes; judged-finding ordinal for 'refute'
  temperature        numeric,
  raw_output         text,                   -- verbatim model output, untouched
  parsed             jsonb,                  -- grounded finding dicts / refute verdict object
  returned_count     int,
  grounded_count     int,
  dropped_ungrounded int,
  reused             boolean not null default false,
  duration_ms        int,
  input_tokens       int,
  output_tokens      int,
  cost_usd           numeric(10,4),
  created_at         timestamptz default now(),
  unique (analysis_id, pass_id, sample_idx)
);
create index if not exists analysis_samples_analysis_idx on analysis_samples(analysis_id);

-- ── findings ─────────────────────────────────────────────────────────────────
create table if not exists findings (
  id                uuid primary key default gen_random_uuid(),
  analysis_id       uuid references analyses(id) on delete cascade,
  source            text not null,                      -- 'deterministic' | 'llm'
  category          text not null,
  severity          text not null check (severity in ('HIGH','MEDIUM','LOW')),
  confidence        numeric not null default 1.0,       -- agreement rate (1.0 for deterministic)
  runs_found        int,
  runs_total        int,
  provision_id      text,
  location          text,
  evidence_quote    text,
  char_start        int,
  char_end          int,
  title             text,
  description       text,
  reasoning         text,
  suggestion        text,
  honte_rule        text,
  check_id          text,
  -- Refutation transparency: refuted findings stay as rows and are shown as
  -- "dropped by the skeptic pass"; the UI filters skeptic_verdict=neq.refuted.
  skeptic_verdict   text not null default 'not_checked'
                    check (skeptic_verdict in ('not_checked','upheld','refuted')),
  skeptic_reasoning text,
  created_at        timestamptz default now()
);
create index if not exists findings_analysis_idx on findings(analysis_id);

-- ── pipeline_runs ────────────────────────────────────────────────────────────
-- One row per worker run; freshness = max(finished_at) where kind='ingest' and ok.
-- A crashed run writes nothing -> the site's staleness banner fires. Intentional.
create table if not exists pipeline_runs (
  id          uuid primary key default gen_random_uuid(),
  kind        text not null check (kind in ('ingest','analyze')),
  started_at  timestamptz not null default now(),
  finished_at timestamptz,
  ok          boolean,
  stats       jsonb        -- ingest: {new,changed,unchanged,no_text}; analyze: {analysed,skipped,cost_usd}
);

-- HÕNTE drafting rules (reference data for grounding findings)
create table if not exists honte_rules (
  id                uuid primary key default gen_random_uuid(),
  rule_id           text unique,                      -- e.g. 'HÕNTE §16'
  section           text,
  text              text,
  mapped_categories text[]
);

-- Gold-set labels for precision/recall evaluation (public: they concern public bills)
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

-- ── dashboard views (PostgREST exposes these; the index page reads ONE call) ─
-- security_invoker: views respect the underlying RLS instead of running as owner.
-- bill_index never touches parsed_text — index payload stays small.
create or replace view bill_index with (security_invoker = on) as
select
  b.id                    as bill_id,
  b.bill_number,
  b.title,
  b.status,
  b.last_seen_at,
  d.id                    as document_id,
  d.version               as doc_version,
  d.fetched_at            as doc_fetched_at,       -- "Muudetud"
  d.text_length,
  d.extraction_method,
  a.id                    as analysis_id,
  a.created_at            as analyzed_at,
  a.prompt_version,
  a.model,
  coalesce(fc.high, 0)    as high_count,
  coalesce(fc.medium, 0)  as medium_count,
  coalesce(fc.low, 0)     as low_count,
  coalesce(fc.refuted, 0) as refuted_count
from bills b
left join lateral (
  select id, version, fetched_at, text_length, extraction_method
  from bill_documents
  where bill_id = b.id and document_type = 'eelnõu'
  order by version desc, fetched_at desc
  limit 1
) d on true
left join lateral (
  select id, created_at, prompt_version, model
  from analyses
  where bill_document_id = d.id and status = 'complete'
  order by created_at desc
  limit 1
) a on true
left join lateral (
  select
    count(*) filter (where severity = 'HIGH'   and skeptic_verdict <> 'refuted') as high,
    count(*) filter (where severity = 'MEDIUM' and skeptic_verdict <> 'refuted') as medium,
    count(*) filter (where severity = 'LOW'    and skeptic_verdict <> 'refuted') as low,
    count(*) filter (where skeptic_verdict = 'refuted')                          as refuted
  from findings
  where analysis_id = a.id
) fc on true;

create or replace view analysis_history with (security_invoker = on) as
select
  a.id               as analysis_id,
  d.bill_id,
  a.bill_document_id as document_id,
  d.version          as doc_version,
  a.created_at,
  a.prompt_version,
  a.checker_version,
  a.model,
  a.provider,
  a.status,
  a.duration_ms,
  a.cost_usd,
  (select count(*) from findings f
     where f.analysis_id = a.id and f.skeptic_verdict <> 'refuted') as finding_count,
  (select count(*) from findings f
     where f.analysis_id = a.id and f.skeptic_verdict = 'refuted')  as refuted_count
from analyses a
join bill_documents d on d.id = a.bill_document_id;

grant select on bill_index, analysis_history to anon, authenticated;

-- ── row-level security ───────────────────────────────────────────────────────
alter table bills            enable row level security;
alter table bill_documents   enable row level security;
alter table analyses         enable row level security;
alter table analysis_samples enable row level security;
alter table findings         enable row level security;
alter table pipeline_runs    enable row level security;
alter table honte_rules      enable row level security;
alter table eval_labels      enable row level security;
alter table feedback         enable row level security;

-- public read (anon + authenticated) — the "all data inspectable" surface
do $$
declare t text;
begin
  foreach t in array array['bills','bill_documents','analyses','analysis_samples',
                           'findings','pipeline_runs','honte_rules','eval_labels'] loop
    execute format($f$
      drop policy if exists %1$s_read on %1$s;
      create policy %1$s_read on %1$s for select using (true);
    $f$, t);
  end loop;
end $$;

-- anyone may submit feedback (confirm/dismiss), but not read others' notes.
-- Client note: INSERT with `Prefer: return=minimal` — anon has no SELECT here.
drop policy if exists feedback_insert on feedback;
create policy feedback_insert on feedback for insert with check (true);

-- NOTE: no INSERT/UPDATE/DELETE policies on the data tables => the anon key
-- cannot write them. Workers use the service-role key, which bypasses RLS.
