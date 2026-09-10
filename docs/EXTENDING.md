# Extending the analysis — the owner's contract

The pipeline: **ingest → parse → deterministic checks → interpretive sampling
(N=5, keep ≥k=3) → complete-linkage clustering → dedup → skeptic review →
persist → static viewer**. Every stage's output is persisted and publicly
readable (see the Andmed/API section on /metoodika).

## Adding a deterministic check (the 3-touch recipe)

1. Write the check function in `analysis/checkers/deterministic.py`
   (`fn(Bill) -> List[Finding]`, use the `_finding` helper) and register it in
   the `CHECKS` list with a `CheckSpec` — id, `version=1`, category, bilingual
   name + description. The registry drives execution, the cache fingerprint,
   and the /metoodika page.
2. Add a fixture + failing-then-passing test in
   `analysis/tests/test_checkers_adversarial.py`. Real-bill zero-false-positive
   tests (`test_checkers.py`) must stay green.
3. Regenerate the methodology artifact:
   `python -m web.export_methodology --write` (CI's `--check` fails on drift).

**Bump `version` on any behavior change.** Cache economics: check changes
invalidate only `cache_key` (the analysis identity), never `llm_cache_key` —
the next `analyze_pending` run re-clusters from stored samples for ~$0
instead of re-buying the LLM sampling.

## Adding an LLM pass

1. Create `analysis/prompts/<pass>.py` exposing `PROMPT_VERSION`,
   `SYSTEM_PROMPT`, a literal `USER_TEMPLATE`, and builders.
2. Register a `PassSpec` in `analysis/passes.py` (bilingual metadata,
   `recorded_sha` = first 8 hex of `prompt_sha()` — the label-drift test in
   `test_manifest.py` forces this to move together with the prompt text).
3. Wire it explicitly in `analysis/run.py:analyze()` (orchestration is plain
   code by design — no plugin framework at n=2 passes).

## What invalidates what

| Change | `cache_key` (identity) | `llm_cache_key` (paid samples) |
|---|---|---|
| Prompt text (interpretive) | invalidated (auto, sha) | invalidated — re-buys sampling |
| Prompt text (refute/other) | invalidated | kept — samples reused |
| Check added/removed/version bump | invalidated | kept — samples reused |
| k (agreement threshold) | invalidated | kept — recluster free |
| n, temperature, model, provider | invalidated | invalidated — re-buys sampling |

## Persisted data contract (what the viewer reads)

`bill_index` and `analysis_history` views; `bills`; `bill_documents`;
`analyses` (engine manifest, stats incl. sub-threshold clusters, usage);
`analysis_samples` (verbatim raw outputs, per-call usage, `error` for failed
samples); `findings` (`skeptic_verdict` drives the refuted section);
`pipeline_runs` (freshness and worker health). Renaming any of these requires
touching `web/js/`.

`bills.text_status` is a closed vocabulary:
`ok`, `no_files`, `unsupported_format`, `image_only_pdf`, `empty_text`,
`download_failed`, `convert_failed`. `bills.text_formats` stores the
comma-joined file formats seen for the bill, for example `doc,pdf`.
`bills.text_checked_at` records when ingestion last evaluated text
availability.

`bill_index` exposes `text_status`, `text_formats`, `text_checked_at`,
`active_stage_date`, and `initiated_date` after `active_stage`. Because
Postgres `create or replace view` cannot reorder or drop existing output
columns, new `bill_index` columns must always be appended last.

`bill_documents.document_type` distinguishes the analysed bill text from other
documents. The analysed draft bill is `eelnõu`; explanatory memoranda split
from combined files are stored as `seletuskiri` rows and are never analysed.
Existing readers filter on `document_type='eelnõu'`.

`pipeline_runs.stats` for `ingest` carries `seen`, `new`, `changed`,
`unchanged`, `no_text`, `failed`, `text_status_counts`, `bills_total`,
`min_seen`, and, only on failure, `error`. For `analyze` it carries `analysed`,
`skipped`, `failed`, `reused`, `cost_usd`, `candidates`, `pending`, and
optionally `error`. Both workers set `ok=true` only when `failed` is zero and
there is no `error` key; otherwise they exit non-zero. A failed scheduled
pipeline run therefore turns the GitHub Actions job red and the existing
failure notification job files a GitHub issue.

Legacy `.doc` files are converted with headless LibreOffice to `.docx` and then
read with `python-docx`, matching the paragraph semantics of native `.docx`
inputs. `antiword` was considered as an alternative `.doc` converter, but it
produces different paragraph breaks; that would change text hashes and re-buy
paid analyses.

## Schema changes

1. Edit `db/schema.sql`.
2. Add new columns both to the `create table` block and to the deployed-schema
   compatibility section as idempotent `alter table ... add column if not
   exists` statements.
3. Append any new `bill_index` output columns last.
4. Run `python -m db.apply` with `SUPABASE_DB_POOLER_URL` set to the Supabase
   session-pooler DSN.

## Known caveat

`analysis/parser/structure.py` is not part of the analysis cache-key manifest:
`analysis/manifest.py` covers provider, model, sampling parameters, check
ids/versions, pass versions, and prompt hashes. A parser change can therefore
alter results without invalidating cached analyses. Bills affected by parser
fixes must be re-analysed deliberately.

## Backfill / cost playbook

After a check bump: `python -m ingestion.analyze_pending --max-bills-per-run 40`
— sample reuse makes this cents. After a prompt/model change: real re-sampling
(~$0.30–0.70/bill median, single monster bills up to ~$3); run chunked, watch
`pipeline_runs.stats.cost_usd`, keep the OpenRouter monthly cap sane.
