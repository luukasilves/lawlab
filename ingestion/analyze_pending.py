"""Analyse bill_documents that don't yet have an analysis at the current prompt
version, and persist analyses + findings. Idempotent via the analyses.cache_key
unique constraint. Requires SUPABASE_SERVICE_KEY (writes) + LLM access.

Usage: python3 -m ingestion.analyze_pending [--limit N] [--no-llm]
"""

from __future__ import annotations
import argparse

import config
from analysis.run import analyze, cache_key
from analysis.prompts.internal_consistency import PROMPT_VERSION
from .store import SupabaseStore


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--no-llm", action="store_true")
    a = ap.parse_args()

    store = SupabaseStore()
    docs = store.docs_needing_analysis(PROMPT_VERSION)
    if a.limit:
        docs = docs[:a.limit]
    print(f"candidate documents: {len(docs)}")

    n, k, t = config.SC_SAMPLES, config.SC_MIN_AGREEMENT, config.SC_TEMPERATURE
    model = config.active_model()
    done = skipped = 0
    for doc in docs:
        text = doc.get("parsed_text") or ""
        if len(text) < 200:
            continue
        key = cache_key(text, model, n, k, t)
        if store.has_analysis(key):          # already analysed at this version/config
            skipped += 1
            continue
        out, _ = analyze(text, use_llm=not a.no_llm, n=n, k=k, temp=t, use_cache=True)
        if out["stats"].get("llm_error"):
            print(f"  doc {doc['id'][:8]}: LLM error, skipping persist")
            continue
        analysis_id = store.insert_analysis(doc["id"], out["result"])
        store.insert_findings(analysis_id, out["result"]["findings"])
        done += 1
        print(f"  doc {doc['id'][:8]}: {len(out['result']['findings'])} findings persisted")

    print(f"\nanalysed {done}, already-current {skipped}")


if __name__ == "__main__":
    main()
