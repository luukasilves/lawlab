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
import hashlib
import json
import os
import re
import sys
from typing import List

import config
from .parser.structure import parse_bill
from .checkers.deterministic import run_deterministic, CHECKER_VERSION
from .aggregate import run_self_consistency, _spans_overlap
from .models import Finding, AnalysisResult, CATEGORIES
from .prompts.internal_consistency import PROMPT_VERSION

CACHE_DIR = os.path.join(os.path.dirname(__file__), ".cache")


def cache_key(text: str, model: str, n: int, k: int, temp: float) -> str:
    norm = re.sub(r"\s+", " ", text).strip()
    blob = f"{norm}|{PROMPT_VERSION}|{model}|{CHECKER_VERSION}|n={n}|k={k}|t={temp}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def _dedup_llm_against_deterministic(det: List[Finding], llm: List[Finding]) -> List[Finding]:
    kept = []
    for f in llm:
        if any(d.category == f.category and _spans_overlap(d, f) for d in det):
            continue                      # deterministic finding is authoritative
        kept.append(f)
    return kept


def analyze(text: str, use_llm: bool, n: int, k: int, temp: float, use_cache: bool):
    model = config.active_model()
    key = cache_key(text, model, n, k, temp)
    cache_path = os.path.join(CACHE_DIR, key + ".json")
    if use_cache and os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as fh:
            return json.load(fh), True

    bill = parse_bill(text)
    findings: List[Finding] = run_deterministic(bill)
    stats = {"deterministic": len(findings)}

    if use_llm:
        hint = " ".join(f"{s.pid}({s.kind})" for s in bill.sections)
        try:
            stable, llm_stats = run_self_consistency(text, hint, n=n, k=k, temperature=temp, model=model)
            stable = _dedup_llm_against_deterministic(findings, stable)
            findings.extend(stable)
            stats["llm"] = llm_stats
        except Exception as e:          # API/limit errors must not lose deterministic output
            stats["llm_error"] = str(e)[:200]

    result = AnalysisResult(
        bill_number=None, bill_title=bill.title, cache_key=key, model=model,
        prompt_version=PROMPT_VERSION, checker_version=CHECKER_VERSION,
        config={"samples": n, "k": k, "temperature": temp, "used_llm": use_llm},
        findings=findings,
    )
    out = {"result": result.to_dict(), "stats": stats}
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
