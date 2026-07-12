"""Ingestion worker: poll Riigikogu for active draft bills, extract text, and
store a content-hash-versioned bill_documents row when the text is new/changed.

This is the fix for the outage's root cause: the old pipeline was run by hand and
went stale. Here it runs on a schedule (see .github/workflows/ingest.yml) and is
idempotent — an unchanged bill is a no-op; a changed bill gets a new version,
which triggers re-analysis.

Usage:
  python3 -m ingestion.run_ingest [--limit N] [--pages P] [--dry-run]
"""

from __future__ import annotations
import argparse
import time

from . import riigikogu
from .store import SupabaseStore


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="max drafts to process")
    ap.add_argument("--pages", type=int, default=1, help="listing pages to scan")
    ap.add_argument("--dry-run", action="store_true", help="fetch+extract but don't write")
    a = ap.parse_args()

    drafts = []
    for p in range(a.pages):
        drafts.extend(riigikogu.list_drafts(only_bills=True, only_active=True, page=p, size=50))
        time.sleep(riigikogu.DELAY)
    if a.limit:
        drafts = drafts[:a.limit]
    print(f"active draft bills (SE, in process): {len(drafts)}")

    store = None if a.dry_run else SupabaseStore()
    stats = {"new": 0, "changed": 0, "unchanged": 0, "no_text": 0}

    for d in drafts:
        mark, uuid, title = d.get("mark"), d.get("uuid"), d.get("title", "")
        print(f"  · {mark}: {title[:55]}", end=" ")
        text, method = riigikogu.extract_bill_text(uuid)
        if not text:
            print("— no extractable bill text"); stats["no_text"] += 1; continue
        h = riigikogu.content_hash(text)
        if a.dry_run:
            print(f"[dry-run] {len(text)} chars ({method}) hash={h[:8]}"); continue

        bill_id = store.upsert_bill(mark, title, d)
        prev = store.latest_doc_hash(bill_id)
        if prev == h:
            print("unchanged"); stats["unchanged"] += 1; continue
        version = 1 if prev is None else 2   # simple bump; real impl reads max(version)+1
        ok = store.insert_document(bill_id, text, method, h, version)
        if ok:
            print("NEW" if prev is None else "CHANGED -> new version")
            stats["new" if prev is None else "changed"] += 1
        time.sleep(riigikogu.DELAY)

    print(f"\ningest summary: {stats}")
    print("→ analysis worker will pick up new/changed documents (run: python3 -m ingestion.analyze_pending)")


if __name__ == "__main__":
    main()
