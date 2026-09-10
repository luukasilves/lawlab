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
import sys
import time
from typing import Iterable

from . import riigikogu
from .store import SupabaseStore


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_ok(stats: dict) -> bool:
    return stats.get("failed", 0) == 0 and "error" not in stats


def ingest_corpus(store, cutoff: str, max_pages: int = 20,
                  dry_run: bool = False, limit: int = None,
                  min_seen: int = None, recheck: Iterable[str] = ()):
    started_at = _now_iso()
    stats = {"seen": 0, "new": 0, "changed": 0, "unchanged": 0,
             "no_text": 0, "failed": 0, "text_status_counts": {}}
    bills_before = 0
    recheck_set = {str(x).strip() for x in recheck if str(x).strip()}

    try:
        try:
            if not dry_run:
                bills_before = store.count_bills()
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
                        if str(mark) not in recheck_set and state and state["has_doc"] and listing_stage \
                                and state["stage"] == listing_stage:
                            store.upsert_bill(mark, title, d)
                            stats["unchanged"] += 1
                            continue

                    bill_id = None
                    if not dry_run:
                        bill_id = store.upsert_bill(mark, title, d)

                    time.sleep(riigikogu.DELAY)
                    ex = riigikogu.extract_bill_text(uuid)
                    if ex.status != "ok":
                        stats["text_status_counts"][ex.status] = \
                            stats["text_status_counts"].get(ex.status, 0) + 1
                        if not dry_run:
                            store.set_text_status(bill_id, ex.status, ex.formats)
                        if ex.status in ("download_failed", "convert_failed"):
                            stats["failed"] += 1
                        else:
                            stats["no_text"] += 1
                        continue

                    h = riigikogu.content_hash(ex.text)
                    if dry_run:
                        continue

                    prev = store.latest_doc_hash(bill_id)
                    if prev == h:
                        store.set_text_status(bill_id, "ok", ex.formats)
                        stats["text_status_counts"]["ok"] = \
                            stats["text_status_counts"].get("ok", 0) + 1
                        stats["unchanged"] += 1
                        continue

                    version = store.next_version(bill_id)
                    ok = store.insert_document(bill_id, ex.text, ex.method, h, version)
                    if ok:
                        if ex.memo:
                            memo_hash = riigikogu.content_hash(ex.memo)
                            memo_ok = store.insert_document(
                                bill_id, ex.memo, ex.method, memo_hash, version,
                                document_type="seletuskiri")
                            if not memo_ok:
                                stats["failed"] += 1
                        store.set_text_status(bill_id, "ok", ex.formats)
                        stats["text_status_counts"]["ok"] = \
                            stats["text_status_counts"].get("ok", 0) + 1
                        stats["new" if prev is None else "changed"] += 1
                    else:
                        stats["failed"] += 1
                except Exception as exc:
                    print(f"  bill failed: {d.get('mark')} ({type(exc).__name__}: {exc})")
                    stats["failed"] += 1
                    continue
            if not dry_run and limit is None:
                floor = min_seen if min_seen is not None else bills_before // 2
                stats["min_seen"] = floor
                if stats["seen"] < floor:
                    stats["error"] = (
                        f"seen {stats['seen']} below minimum {floor}; listing may be truncated"
                    )
        except Exception as exc:
            print(f"  corpus iteration failed ({type(exc).__name__}: {exc})")
            stats["failed"] += 1
            stats["error"] = f"listing: {type(exc).__name__}: {str(exc)[:170]}"
    finally:
        if not dry_run:
            try:
                stats["bills_total"] = store.count_bills()
            except Exception as exc:
                print(f"  count_bills failed ({type(exc).__name__})")
            try:
                store.record_run("ingest", started_at, run_ok(stats), stats)
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
    ap.add_argument("--min-seen", type=int,
                    default=(int(os.getenv("LAWLAB_MIN_SEEN"))
                             if os.getenv("LAWLAB_MIN_SEEN") else None),
                    help="minimum drafts expected in a full run")
    ap.add_argument("--recheck", default=os.getenv("LAWLAB_RECHECK_BILLS", ""),
                    help="comma-separated bill numbers to force re-download")
    a = ap.parse_args()

    store = None if a.dry_run else SupabaseStore()
    recheck = [x.strip() for x in a.recheck.split(",") if x.strip()]
    stats = ingest_corpus(store, cutoff=a.since, max_pages=a.max_pages,
                          dry_run=a.dry_run, limit=a.limit,
                          min_seen=a.min_seen, recheck=recheck)
    print(stats)
    print("→ analysis worker will pick up new/changed documents (run: python3 -m ingestion.analyze_pending)")
    if not run_ok(stats):
        sys.exit(1)


if __name__ == "__main__":
    main()
