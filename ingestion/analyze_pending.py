"""Analyse bill_documents that need a current analysis, then persist results.

Usage: python3 -m ingestion.analyze_pending [--max-bills-per-run N] [--no-llm]
"""

from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Callable, Dict, Optional

import config
from .store import SupabaseStore


MAX_BILLS_DEFAULT = 10


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fallback_manifest_keys(text_sha: str, provider: str, model: str,
                            n: int, k: int, temp: float):
    manifest = {"provider": provider, "model": model, "n": n, "k": k, "temp": temp}
    blob = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    cache = hashlib.sha256(f"analysis|{text_sha}|{blob}".encode("utf-8")).hexdigest()[:32]
    llm_cache = hashlib.sha256(f"llm|{text_sha}|{blob}".encode("utf-8")).hexdigest()[:32]
    return manifest, cache, llm_cache


def _manifest_keys(text_sha: str, n: int, k: int, temp: float):
    provider = config.LLM_PROVIDER
    model = config.active_model()
    try:
        from analysis.manifest import build_engine_manifest, cache_key, llm_cache_key
    except ModuleNotFoundError as exc:
        if exc.name != "analysis.manifest":
            raise
        return _fallback_manifest_keys(text_sha, provider, model, n, k, temp)

    engine = build_engine_manifest(provider=provider, model=model, n=n, k=k, temp=temp)
    return engine, cache_key(text_sha, engine), llm_cache_key(text_sha, engine)


def run_pending(store, analyze_fn: Optional[Callable[..., Any]] = None,
                max_bills: Optional[int] = None, use_llm: bool = True) -> Dict[str, Any]:
    started_at = _now_iso()
    stats = {"analysed": 0, "skipped": 0, "failed": 0,
             "reused": 0, "cost_usd": 0.0}
    n, k, temp = config.SC_SAMPLES, config.SC_MIN_AGREEMENT, config.SC_TEMPERATURE
    cap = MAX_BILLS_DEFAULT if max_bills is None else max_bills
    attempted = 0

    try:
        try:
            if analyze_fn is None:
                from analysis.run import analyze as analyze_fn
            docs = store.docs_needing_analysis()
            for doc in docs:
                try:
                    text_sha = doc["content_hash"]
                    _, analysis_key, llm_key = _manifest_keys(text_sha, n, k, temp)

                    if store.has_analysis(analysis_key):
                        stats["skipped"] += 1
                        continue

                    if cap is not None and attempted >= cap:
                        break
                    attempted += 1

                    samples = store.find_reusable_samples(llm_key)
                    if samples is not None:
                        stats["reused"] += 1

                    text = store.get_parsed_text(doc["id"])
                    if text is None:
                        raise RuntimeError("missing parsed_text")

                    out, _ = analyze_fn(text, use_llm=use_llm, n=n, k=k, temp=temp,
                                        use_cache=False, reused_samples=samples)
                    if use_llm and out["stats"].get("llm_error"):
                        # Never persist a degraded analysis: its cache_key would
                        # block the retry forever (has_analysis skip).
                        raise RuntimeError(f"llm degraded: {str(out['stats']['llm_error'])[:150]}")
                    usage = out["usage"]
                    aid = store.insert_analysis(doc["id"], {
                        **out["result"], "stats": out["stats"], **usage
                    })
                    store.insert_findings(aid, out["result"]["findings"])
                    store.insert_samples(aid, out["samples"])
                    stats["analysed"] += 1
                    stats["cost_usd"] += float(usage.get("cost_usd") or 0.0)
                except Exception as exc:
                    print(f"  doc failed: {doc.get('id')} ({type(exc).__name__}: {exc})")
                    stats["failed"] += 1
                    continue
        except Exception as exc:
            print(f"  analysis listing failed ({type(exc).__name__}: {exc})")
            stats["failed"] += 1
    finally:
        try:
            store.record_run("analyze", started_at, stats["failed"] == 0, stats)
        except Exception as exc:  # bookkeeping is best-effort: a flaky network
            print(f"  record_run failed ({type(exc).__name__}) — analyses already persisted")

    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-bills-per-run", "--limit", dest="max_bills_per_run",
                    type=int, default=MAX_BILLS_DEFAULT)
    ap.add_argument("--no-llm", action="store_true")
    a = ap.parse_args()

    store = SupabaseStore()
    stats = run_pending(store, max_bills=a.max_bills_per_run, use_llm=not a.no_llm)
    print(stats)


if __name__ == "__main__":
    main()
