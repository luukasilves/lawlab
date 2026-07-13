"""Ingestion worker: poll Riigikogu for active draft bills, extract text, and
store a content-hash-versioned bill_documents row when the text is new/changed.

This is the fix for the outage's root cause: the old pipeline was run by hand and
went stale. Here it runs on a schedule (see .github/workflows/ingest.yml) and is
idempotent — an unchanged bill is a no-op; a changed bill gets a new version,
which triggers re-analysis.

Usage:
  python3 -m ingestion.run_ingest [--limit N] [--since YYYY-MM-DD]
                                  [--max-pages P] [--dry-run]
"""

from __future__ import annotations
import argparse
from datetime import datetime, timezone
import os
import time

from . import riigikogu
from .store import SupabaseStore


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ingest_corpus(store, cutoff: str, max_pages: int = 20,
                  dry_run: bool = False, limit: int = None):
    started_at = _now_iso()
    stats = {"seen": 0, "new": 0, "changed": 0, "unchanged": 0,
             "no_text": 0, "failed": 0}

    try:
        try:
            drafts = riigikogu.iterate_corpus(cutoff, max_pages=max_pages)
            for d in drafts:
                if limit is not None and stats["seen"] >= limit:
                    break
                stats["seen"] += 1

                try:
                    mark = d.get("mark")
                    uuid = d.get("uuid")
                    title = d.get("title", "")

                    if not dry_run:
                        # Cheap skip: same activeDraftStatusDate + a stored doc
                        # means no proceedings movement — no download needed
                        # (a full re-download crawl blew the 25-min cron cap).
                        state = store.bill_state(mark)
                        listing_stage = d.get("activeDraftStatusDate")
                        if state and state["has_doc"] and listing_stage \
                                and state["stage"] == listing_stage:
                            store.upsert_bill(mark, title, d)
                            stats["unchanged"] += 1
                            continue

                    bill_id = None
                    if not dry_run:
                        bill_id = store.upsert_bill(mark, title, d)

                    time.sleep(riigikogu.DELAY)
                    text, method = riigikogu.extract_bill_text(uuid)
                    if not text:
                        stats["no_text"] += 1
                        continue

                    h = riigikogu.content_hash(text)
                    if dry_run:
                        continue

                    prev = store.latest_doc_hash(bill_id)
                    if prev == h:
                        stats["unchanged"] += 1
                        continue

                    version = store.next_version(bill_id)
                    ok = store.insert_document(bill_id, text, method, h, version)
                    if ok:
                        stats["new" if prev is None else "changed"] += 1
                    else:
                        stats["failed"] += 1
                except Exception as exc:
                    print(f"  bill failed: {d.get('mark')} ({type(exc).__name__}: {exc})")
                    stats["failed"] += 1
                    continue
        except Exception as exc:
            print(f"  corpus iteration failed ({type(exc).__name__}: {exc})")
            stats["failed"] += 1
    finally:
        if not dry_run:
            try:
                store.record_run("ingest", started_at, stats["failed"] == 0, stats)
            except Exception as exc:  # bookkeeping is best-effort
                print(f"  record_run failed ({type(exc).__name__}) — documents already persisted")

    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="max drafts to process")
    ap.add_argument("--since", default=os.getenv("LAWLAB_CORPUS_SINCE", "2026-01-01"),
                    help="include bills with activity on or after this date")
    ap.add_argument("--max-pages", type=int, default=20, help="listing pages to scan")
    ap.add_argument("--pages", dest="max_pages", type=int, help=argparse.SUPPRESS)
    ap.add_argument("--dry-run", action="store_true", help="fetch+extract but don't write")
    a = ap.parse_args()

    store = None if a.dry_run else SupabaseStore()
    stats = ingest_corpus(store, cutoff=a.since, max_pages=a.max_pages,
                          dry_run=a.dry_run, limit=a.limit)
    print(stats)
    print("→ analysis worker will pick up new/changed documents (run: python3 -m ingestion.analyze_pending)")


if __name__ == "__main__":
    main()
