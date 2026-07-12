"""End-to-end analysis runner.

  parse → deterministic checkers → LLM self-consistency → merge → cache

Caching is the second half of the non-determinism fix: a given (bill version,
prompt version, model, config) always yields the SAME stored result, so the UI
never silently changes. Locally we cache to analysis/.cache/<key>.json; in
production this is the `analyses`/`findings` tables keyed by the same hash.

Usage:
  python3 -m analysis.run <bill.txt> [--no-llm] [--samples N] [--k K] [--no-cache]
"""

from __future__ import annotations
import argparse
import json
import os
import sys
from typing import List

import config
import requests
from .parser.structure import parse_bill
from .checkers.deterministic import run_deterministic, checker_version_label
from .aggregate import run_self_consistency, cluster_with_summaries, _spans_overlap
from . import manifest as manifest_mod
from .llm import engine as llm_engine
from .llm import refute as refute_mod
from .llm.client import LLMError
from .models import Finding, AnalysisResult, CATEGORIES, SampleRecord
from .prompts import internal_consistency

CACHE_DIR = os.path.join(os.path.dirname(__file__), ".cache")


def cache_key(text: str, model: str, n: int, k: int, temp: float) -> str:
    engine_manifest = manifest_mod.build_engine_manifest(config.LLM_PROVIDER, model, n, k, temp)
    return manifest_mod.cache_key(manifest_mod.text_sha(text), engine_manifest)


def _dedup_llm_against_deterministic(det: List[Finding], llm: List[Finding]) -> List[Finding]:
    kept = []
    for f in llm:
        if any(d.category == f.category and _spans_overlap(d, f) for d in det):
            continue                      # deterministic finding is authoritative
        kept.append(f)
    return kept


def _sample_record_from_dict(data: dict, *, reused: bool = False) -> SampleRecord:
    allowed = SampleRecord.__dataclass_fields__.keys()
    kwargs = {key: data[key] for key in allowed if key in data}
    record = SampleRecord(**kwargs)
    record.reused = reused
    return record


def _cluster_reused_samples(reused_samples, n: int, k: int):
    records = []
    samples: List[List[Finding]] = [[] for _ in range(n)]
    for ordinal, item in enumerate(reused_samples or []):
        if item.get("pass_id", "interpretive") != "interpretive":
            continue
        record = _sample_record_from_dict(item, reused=True)
        if record.sample_idx < 0:
            record.sample_idx = ordinal
        records.append(record)
        if 0 <= record.sample_idx < n:
            samples[record.sample_idx] = [Finding(**d) for d in record.parsed]
    stable, summaries = cluster_with_summaries(samples, n_runs=n, k=k)
    stats = {
        "samples": n,
        "min_agreement": k,
        "per_sample": [
            {
                "returned": r.returned_count,
                "grounded": r.grounded_count,
                "dropped": r.dropped_ungrounded,
            }
            for r in sorted(records, key=lambda rec: rec.sample_idx)
        ],
        "raw_findings": sum(len(s) for s in samples),
        "stable_findings": len(stable),
        "clusters": summaries,
    }
    return stable, records, stats


def _usage(records: List[SampleRecord], wall_ms: int):
    return {
        "input_tokens": sum(r.input_tokens or 0 for r in records),
        "output_tokens": sum(r.output_tokens or 0 for r in records),
        "cost_usd": round(sum(r.cost_usd or 0.0 for r in records), 6),
        "duration_ms": wall_ms,
    }


def analyze(text: str, use_llm: bool, n: int, k: int, temp: float, use_cache: bool,
            reused_samples=None):
    import time

    t0 = time.monotonic()
    model = config.active_model()
    text_hash = manifest_mod.text_sha(text)
    engine_manifest = manifest_mod.build_engine_manifest(config.LLM_PROVIDER, model, n, k, temp)
    key = manifest_mod.cache_key(text_hash, engine_manifest)
    llm_key = manifest_mod.llm_cache_key(text_hash, engine_manifest)
    cache_path = os.path.join(CACHE_DIR, key + ".json")
    if use_cache and os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as fh:
            return json.load(fh), True

    bill = parse_bill(text)
    findings: List[Finding] = run_deterministic(bill)
    stats = {"deterministic": len(findings)}
    records: List[SampleRecord] = []

    if use_llm:
        hint = " ".join(f"{s.pid}({s.kind})" for s in bill.sections)
        try:
            if reused_samples is not None:
                stable, llm_records, llm_stats = _cluster_reused_samples(reused_samples, n, k)
            else:
                stable, llm_records, llm_stats = run_self_consistency(
                    text, hint, n=n, k=k, temperature=temp, model=model
                )
            stable = _dedup_llm_against_deterministic(findings, stable)
            candidates = [
                f for f in stable
                if f.runs_found and f.runs_total and f.runs_found < f.runs_total
            ]
            refute_records, refute_stats = refute_mod.refute_findings(text, candidates, model=model)
            findings.extend(stable)
            records.extend(llm_records)
            records.extend(refute_records)
            stats["llm"] = llm_stats
            stats["refute"] = refute_stats
        except (
            LLMError,
            requests.RequestException,
            llm_engine.LLMParseError,
        ) as e:
            # API/limit errors must not lose deterministic output.
            stats["llm_error"] = str(e)[:200]

    result = AnalysisResult(
        bill_number=None, bill_title=bill.title, cache_key=key, model=model,
        prompt_version=internal_consistency.PROMPT_VERSION,
        checker_version=checker_version_label(),
        provider=config.LLM_PROVIDER,
        engine=engine_manifest,
        config={
            "samples": n, "k": k, "temperature": temp, "used_llm": use_llm,
            "llm_cache_key": llm_key,
        },
        findings=findings,
    )
    wall_ms = int((time.monotonic() - t0) * 1000)
    out = {
        "result": result.to_dict(),
        "stats": stats,
        "samples": [r.to_dict() for r in records],
        "usage": _usage(records, wall_ms),
    }
    # Never cache a run whose LLM pass errored (e.g. transient/limit) — it would
    # freeze an incomplete result; let it retry once the API is reachable.
    if use_cache and "llm_error" not in stats:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=2)
    return out, False


def _print(out, cached):
    r = out["result"]
    print(f"\n{'═'*70}\n{r['bill_title']}\n{'═'*70}")
    print(f"cache_key={r['cache_key']}  model={r['model']}  prompt={r['prompt_version']}"
          f"  {'(CACHED)' if cached else ''}")
    print(f"stats: {json.dumps(out['stats'], ensure_ascii=False)[:300]}")
    sev = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for f in r["findings"]:
        sev[f["severity"]] = sev.get(f["severity"], 0) + 1
    print(f"findings: {len(r['findings'])}  (HIGH {sev['HIGH']} / MED {sev['MEDIUM']} / LOW {sev['LOW']})\n")
    for f in r["findings"]:
        conf = f"{f['confidence']:.0%}"
        runs = f" {f['runs_found']}/{f['runs_total']}" if f.get("runs_total") else ""
        print(f"  [{f['severity']}] ({f['source']} {conf}{runs}) {CATEGORIES.get(f['category'], f['category'])}")
        print(f"      {f['title']}")
        print(f"      {f['location']}  ·  {f['honte_rule']}")
        print(f"      “{f['evidence_quote'][:120].strip()}”")
        print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bill")
    ap.add_argument("--no-llm", action="store_true", help="deterministic checks only")
    ap.add_argument("--samples", type=int, default=config.SC_SAMPLES)
    ap.add_argument("--k", type=int, default=config.SC_MIN_AGREEMENT)
    ap.add_argument("--temp", type=float, default=config.SC_TEMPERATURE)
    ap.add_argument("--no-cache", action="store_true")
    a = ap.parse_args()
    text = open(a.bill, encoding="utf-8").read()
    out, cached = analyze(text, use_llm=not a.no_llm, n=a.samples, k=a.k,
                          temp=a.temp, use_cache=not a.no_cache)
    _print(out, cached)


if __name__ == "__main__":
    main()
