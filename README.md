# Apsakaleidja / Lawlab — legislative error fact-finder

**Live: https://lawlab.luukas-ilves.workers.dev** · Estonian draft bills from
the Riigikogu API, checked for internal drafting errors — broken references,
numbering and arithmetic problems, terminology drift, contradictions — each
finding grounded in a verbatim text span and cited to Estonia's drafting
rules (HÕNTE), with an honest confidence score and a full public audit trail.

## How it works

```
Riigikogu API ──▶ ingest (daily cron) ──▶ Supabase (public REST reads)
                                              │
        parse → deterministic checks → LLM ×N self-consistency
              → complete-linkage clustering → skeptic review
                                              │
                    static viewer (no build step, Cloudflare Workers)
```

- **Hybrid engine** — mechanical error classes (references, numbering,
  percentages) are deterministic code at confidence 1.0; interpretive classes
  go to an LLM (Claude Opus 4.8 via OpenRouter).
- **Self-consistency** — N=5 independent samples; only findings stable in ≥3
  are published; agreement is the confidence score. A skeptic pass challenges
  sub-consensus findings; refuted ones stay visible, marked.
- **Verbatim grounding** — a finding whose evidence quote can't be located in
  the source text is dropped as a hallucination.
- **Radical inspectability** — every raw LLM sample, cluster decision (incl.
  below-threshold ones), token count and cost is persisted and publicly
  readable over REST; the /metoodika page publishes the full prompts and
  curl-ready examples. `web/data/methodology.json` is generated from the code
  registries, so the methodology page cannot drift from what actually runs.

## Layout

```
analysis/    engine: parser, checkers (CheckSpec registry), LLM passes
             (PassSpec registry), manifest.py (two-level cache keys)
ingestion/   Riigikogu client (retrying), Supabase REST store, workers
db/          schema (applied to Supabase; RLS: anon read, service writes)
web/         static viewer (vanilla ES modules) + methodology exporter
eval/        gold set + recall/false-alarm harness
scripts/     seed_reference.py, page_smoke.mjs (CDP live-page harness)
docs/        EXTENDING.md (add checks/passes), DEPLOY.md (routing, /en, DNS)
```

## Running

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env                    # Supabase + OpenRouter keys
.venv/bin/python -m analysis.tests.test_checkers        # offline suite (CI runs 11 modules)
.venv/bin/python -m analysis.run analysis/tests/fixtures/bill_728.txt   # one bill, live LLM
.venv/bin/python -m ingestion.run_ingest --dry-run --max-pages 2        # no keys needed
```

Daily pipeline: `.github/workflows/ingest.yml` (ingest + analyze, capped,
failure auto-files an issue). Deploy: `npx wrangler deploy` (Workers) and
`npx wrangler pages deploy web --project-name lawlab` (Pages, for the custom
domain). Routing, the `/en` language scheme, and the DNS cutover — including
the `run_worker_first` and Pages clean-URL gotchas — are in `docs/DEPLOY.md`.

## Cost & scale

Corpus: all SE bills with proceedings activity since 2026-01-01 (~212 at
launch). Steady state ≈ $5–10/month of LLM spend; adding a new deterministic
check re-analyzes the whole corpus for ~$0 thanks to sample reuse
(`docs/EXTENDING.md` → cache economics).

## License

MIT — see LICENSE. Findings are machine analysis, not legal advice
(masinanalüüs, mitte õiguslik hinnang).
