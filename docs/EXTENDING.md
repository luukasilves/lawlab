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

`bill_index` and `analysis_history` views; `analyses` (engine manifest, stats
incl. sub-threshold clusters, usage); `analysis_samples` (verbatim raw
outputs, per-call usage, `error` for failed samples); `findings`
(`skeptic_verdict` drives the refuted section); `pipeline_runs` (freshness).
Renaming any of these requires touching `web/js/`.

## Backfill / cost playbook

After a check bump: `python -m ingestion.analyze_pending --max-bills-per-run 40`
— sample reuse makes this cents. After a prompt/model change: real re-sampling
(~$0.30–0.70/bill median, single monster bills up to ~$3); run chunked, watch
`pipeline_runs.stats.cost_usd`, keep the OpenRouter monthly cap sane.
