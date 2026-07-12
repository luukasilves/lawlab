# Lawlab / Apsakaleidja — legislative error fact-finder (newbuild)

Reads Estonian draft bills (Riigikogu) and flags **internal drafting errors** —
contradictions, broken references, terminology scope drift, numbering and
arithmetic problems — each grounded in a verbatim text span and in Estonia's
drafting rules (HÕNTE), with an honest **confidence score**.

This is a ground-up rebuild of the early-2026 demo, fixing its two core flaws:
**non-determinism** (every run differed) and **no grounding** (ungrounded LLM
guesses). See `~/.claude/plans/early-in-the-year-nested-pebble.md` for the plan.

## How it's better

| Old demo | Newbuild |
|---|---|
| Single LLM pass, temp 0.2, no seed → results drifted | **Self-consistency**: N samples, keep only findings stable across ≥k runs, report agreement as confidence; cached so a bill version never silently changes |
| All errors judged by the LLM (incl. arithmetic it hallucinated) | **Hybrid**: deterministic code for mechanical checks (refs, numbering, %), LLM only for interpretive judgement |
| Locations like "§ 3" unverified | **Verbatim evidence** verified against parsed char offsets |
| Errors = LLM opinion | Each finding **cites a HÕNTE drafting rule** |
| Dead preview model id, hand-run pipeline | Current model (provider-agnostic), scheduled ingestion |

## Layout

```
analysis/         the engine
  parser/         § / lõige / punkt structure parser (offsets, stable IDs)
  checkers/       deterministic, high-precision checks (confidence 1.0)
  llm/            provider-agnostic interpretive pass (structured output)
  prompts/        versioned prompt (HÕNTE-anchored taxonomy)
  aggregate.py    self-consistency clustering + confidence
  models.py       Finding / AnalysisResult
  tests/          regression tests + fixtures (real bills + planted errors)
ingestion/        Riigikogu poll + document extract -> Supabase
reference/        HÕNTE rules + category↔rule mapping
db/               Supabase SQL migrations
web/              read-only SPA (bill list + inline-highlighted findings)
eval/             gold set + precision/recall
```

## Quick start

```bash
cp .env.example .env          # fill in keys (rotate the leaked ones!)
python3 -m analysis.tests.test_checkers          # offline, no keys needed
python3 -m analysis.run analysis/tests/fixtures/bill_728.txt   # full analysis
```

## Status — Phase 1 complete & verified

- **Parser + deterministic checkers** — 0 false positives on real bills; all planted errors caught.
- **LLM self-consistency engine** — verified live on Bill 728: the osavusmängu scope-drift
  caught at **100% confidence (5/5)**, grounded verbatim, cited to HÕNTE § 17; the old
  hallucinated "12%+80%" arithmetic error is **not** reproduced.
- **Eval** — 100% recall on the known error; arithmetic regression guard holds (0 false alarms).
- **HÕNTE grounding, Supabase schema + RLS, ingestion worker + daily scheduler, web viewer** — built.

Run the live analysis: `python3 -m analysis.run analysis/tests/fixtures/bill_728.txt`
View it: `python3 -m web.export_demo analysis/tests/fixtures/bill_728.txt 728 && (cd web && python3 -m http.server)`

### Before deploy
1. **Rotate the leaked keys** (old OpenRouter + Supabase keys are in the previous build's source).
2. Apply `db/schema.sql`; set `SUPABASE_SERVICE_KEY` + GitHub Actions secrets for the scheduler.

### Phase 2 (planned)
Riigi Teataja RAG (resolve cross-references against real consolidated law); refutation pass;
`.doc` + image-PDF (OCR) ingestion; expert-reviewed gold set; constitutional / EU-law checks.
