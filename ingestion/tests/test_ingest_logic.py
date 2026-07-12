"""Contract tests for the hardened ingestion layer (R2b). RED until built.

Pins (recon facts: listing is recency-ordered; draftTypeCode=SE filters
server-side; ~212-bill corpus = activity >= LAWLAB_CORPUS_SINCE union
IN_PROCESS; the previous build died on unretried API timeouts):

  * riigikogu.fetch_with_retry retries timeouts/connection errors/5xx too.
  * riigikogu.list_drafts sends draftTypeCode=SE server-side.
  * riigikogu.iterate_corpus(cutoff) walks pages, keeps SE drafts with
    activeDraftStatusDate >= cutoff OR proceedingStatus == IN_PROCESS, and
    stops after the first page wholly older than the cutoff.
  * store.upsert_bill UPDATES existing rows (title/status/api_data/
    last_seen_at) — today it returns early and status rots forever.
  * store.next_version = max(version)+1 with fetched_at tiebreaker.
  * store.docs_needing_analysis() (no params) selects id,bill_id,content_hash
    — never parsed_text — and paginates with Range headers.
  * store.insert_analysis writes the transparency columns; insert_samples,
    record_run, find_reusable_samples exist and hit the right tables.
  * analyze_pending.run_pending(store, analyze_fn, max_bills=10): computes
    cache keys FROM content_hash (no text download on skip), enforces the
    cap, isolates per-doc failures, records a pipeline run.
  * run_ingest.ingest_corpus(store, cutoff, ...): isolates per-bill
    failures and records a pipeline run even on partial success.

Run: python3 -m ingestion.tests.test_ingest_logic
"""

from __future__ import annotations

import json
import time

import requests as _requests

import config
from .. import riigikogu, store as store_mod, analyze_pending, run_ingest
from ..store import SupabaseStore


class FakeResp:
    def __init__(self, status=200, payload=None, headers=None):
        self.status_code = status
        self._payload = payload if payload is not None else []
        self.text = json.dumps(self._payload)
        self.headers = headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise _requests.HTTPError(f"HTTP {self.status_code}")


def _seq(responses, log):
    def fake(url, **kw):
        log.append((url, kw))
        r = responses[min(len(log) - 1, len(responses) - 1)]
        if isinstance(r, Exception):
            raise r
        return r
    return fake


def test_fetch_retries_timeouts_and_5xx():
    orig_get, orig_sleep = riigikogu.requests.get, time.sleep
    time.sleep = lambda *_: None
    try:
        log = []
        riigikogu.requests.get = _seq([_requests.Timeout("t"), FakeResp(200, {"ok": 1})], log)
        assert riigikogu.fetch_with_retry("http://x").json() == {"ok": 1} and len(log) == 2

        log2 = []
        riigikogu.requests.get = _seq([FakeResp(503), FakeResp(200, {"ok": 2})], log2)
        assert riigikogu.fetch_with_retry("http://x").json() == {"ok": 2} and len(log2) == 2
    finally:
        riigikogu.requests.get, time.sleep = orig_get, orig_sleep
    print("✓ fetch_with_retry survives timeouts and 5xx (not just 429)")


def _draft(mark, status="IN_PROCESS", date="2026-05-01", code="SE"):
    return {"uuid": f"u{mark}", "mark": mark, "title": f"t{mark}",
            "draftTypeCode": code, "proceedingStatus": status,
            "activeDraftStatusDate": date}


def test_list_drafts_server_side_se_filter():
    orig_get = riigikogu.requests.get
    log = []
    riigikogu.requests.get = _seq([FakeResp(200, {"_embedded": {"content": [_draft(1)]}})], log)
    try:
        riigikogu.list_drafts(only_bills=True, only_active=False, page=0, size=50)
        assert "draftTypeCode=SE" in log[0][0], f"server-side SE filter missing: {log[0][0]}"
    finally:
        riigikogu.requests.get = orig_get
    print("✓ list_drafts filters SE server-side")


def test_iterate_corpus_window_and_stop():
    orig_get, orig_sleep = riigikogu.requests.get, time.sleep
    time.sleep = lambda *_: None
    page0 = {"_embedded": {"content": [
        _draft(1, "IN_PROCESS", "2026-06-01"),
        _draft(2, "PROCESSED", "2026-03-01"),
        _draft(3, "PROCESSED", "2025-11-01"),          # pre-cutoff, not in process -> excluded
        _draft(4, "IN_PROCESS", "2025-10-01"),          # dormant but active -> kept (union rule)
        _draft(5, "IN_PROCESS", "2026-04-01", "OE"),    # not SE -> excluded
    ]}}
    page1 = {"_embedded": {"content": [_draft(6, "PROCESSED", "2025-09-01"),
                                       _draft(7, "PROCESSED", "2025-08-01")]}}
    log = []
    riigikogu.requests.get = _seq([FakeResp(200, page0), FakeResp(200, page1),
                                   FakeResp(500)], log)
    try:
        got = [d["mark"] for d in riigikogu.iterate_corpus("2026-01-01")]
        assert got == [1, 2, 4], f"window union rule wrong: {got}"
        assert len(log) == 2, f"must stop after the first wholly-pre-cutoff page, made {len(log)} calls"
    finally:
        riigikogu.requests.get, time.sleep = orig_get, orig_sleep
    print("✓ iterate_corpus: activity-window ∪ IN_PROCESS, SE-only, early stop")


def _mkstore():
    saved = (config.SUPABASE_URL, config.SUPABASE_ANON_KEY, config.SUPABASE_SERVICE_KEY)
    config.SUPABASE_URL, config.SUPABASE_ANON_KEY, config.SUPABASE_SERVICE_KEY = \
        "http://fake", "anon", "svc"
    s = SupabaseStore()
    config.SUPABASE_URL, config.SUPABASE_ANON_KEY, config.SUPABASE_SERVICE_KEY = saved
    return s


def test_upsert_updates_existing():
    s = _mkstore()
    orig_get, orig_patch = store_mod.requests.get, getattr(store_mod.requests, "patch", None)
    log = {"patch": []}
    store_mod.requests.get = _seq([FakeResp(200, [{"id": "b1", "bill_number": "9", "title": "old"}])], [])
    store_mod.requests.patch = lambda url, **kw: (log["patch"].append((url, kw)), FakeResp(204))[1]
    try:
        bid = s.upsert_bill("9", "uus pealkiri", {"proceedingStatus": "PROCESSED"})
        assert bid == "b1"
        assert log["patch"], "existing bill must be UPDATED (status/title/api_data/last_seen_at)"
        body = log["patch"][0][1]["json"]
        assert body.get("status") == "PROCESSED" and body.get("title") == "uus pealkiri"
        assert "last_seen_at" in body and "api_data" in body
    finally:
        store_mod.requests.get = orig_get
        if orig_patch is not None:
            store_mod.requests.patch = orig_patch
    print("✓ upsert_bill refreshes existing rows (status can no longer rot)")


def test_next_version_and_doc_listing():
    s = _mkstore()
    orig_get = store_mod.requests.get
    log = []
    store_mod.requests.get = _seq([FakeResp(200, [{"version": 2, "content_hash": "h"}])], log)
    try:
        assert s.next_version("b1") == 3
        assert "order=version.desc" in log[0][0] and "fetched_at.desc" in log[0][0]
    finally:
        store_mod.requests.get = orig_get

    log2 = []
    full = [{"id": f"d{i}", "bill_id": f"b{i}", "content_hash": f"h{i}"} for i in range(1000)]
    orig_get = store_mod.requests.get
    store_mod.requests.get = _seq([FakeResp(200, full), FakeResp(200, full[:3])], log2)
    try:
        docs = s.docs_needing_analysis()
        assert len(docs) == 1003, f"pagination broken: {len(docs)}"
        url0 = log2[0][0]
        assert "parsed_text" not in url0 and "content_hash" in url0, \
            f"listing must never pull parsed_text: {url0}"
        assert log2[0][1].get("headers", {}).get("Range") is not None, "Range pagination expected"
    finally:
        store_mod.requests.get = orig_get
    print("✓ next_version max+1 w/ tiebreaker; doc listing paginates without parsed_text")


def test_insert_analysis_and_new_writers():
    s = _mkstore()
    orig_post = store_mod.requests.post
    log = []
    store_mod.requests.post = _seq([FakeResp(201, [{"id": "a1"}]), FakeResp(201), FakeResp(201)], log)
    try:
        aid = s.insert_analysis("d1", {
            "cache_key": "ck", "llm_cache_key": "lk", "model": "m", "provider": "openrouter",
            "prompt_version": "ic-v1", "checker_version": "x@1", "engine": {"e": 1},
            "config": {}, "stats": {}, "duration_ms": 5,
            "input_tokens": 10, "output_tokens": 2, "cost_usd": 0.01,
        })
        assert aid == "a1"
        body = log[0][1]["json"]
        for col in ("llm_cache_key", "provider", "engine", "stats", "duration_ms",
                    "input_tokens", "output_tokens", "cost_usd"):
            assert col in body, f"insert_analysis must write {col}"
        s.insert_samples("a1", [{"pass_id": "interpretive", "sample_idx": 0}])
        assert "/analysis_samples" in log[1][0] and log[1][1]["json"][0]["analysis_id"] == "a1"
        s.record_run("ingest", "2026-07-12T00:00:00Z", True, {"new": 1})
        assert "/pipeline_runs" in log[2][0]
    finally:
        store_mod.requests.post = orig_post
    print("✓ transparency columns written; insert_samples/record_run wired")


class FakeStore:
    def __init__(self, docs):
        self._docs = docs
        self.analyses = []
        self.samples = []
        self.runs = []
        self.text_fetches = 0

    def docs_needing_analysis(self):
        return self._docs

    def has_analysis(self, key):
        return False

    def find_reusable_samples(self, llm_key):
        return None

    def get_parsed_text(self, doc_id):
        self.text_fetches += 1
        return f"Testseadus\n\n§ 1. Reegel\nSisu {doc_id}.\n"

    def insert_analysis(self, doc_id, payload):
        self.analyses.append(doc_id)
        return f"a-{doc_id}"

    def insert_findings(self, aid, findings):
        return True

    def insert_samples(self, aid, samples):
        self.samples.append(aid)
        return True

    def record_run(self, kind, started_at, ok, stats):
        self.runs.append((kind, ok, stats))


def test_run_pending_cap_and_isolation():
    docs = [{"id": f"d{i}", "bill_id": f"b{i}", "content_hash": f"h{i}"} for i in range(5)]
    fs = FakeStore(docs)

    def fake_analyze(text, **kw):
        if "d1" in text:
            raise RuntimeError("boom on d1")
        return ({"result": {"cache_key": "ck", "llm_cache_key": "lk", "model": "m",
                            "provider": "p", "prompt_version": "v", "checker_version": "c",
                            "engine": {}, "config": {}, "findings": []},
                 "stats": {}, "samples": [], "usage": {"input_tokens": 1, "output_tokens": 1,
                                                       "cost_usd": 0.0, "duration_ms": 1}}, False)

    stats = analyze_pending.run_pending(fs, analyze_fn=fake_analyze, max_bills=3)
    assert stats["analysed"] == 2 and stats["failed"] == 1, f"cap/isolation wrong: {stats}"
    assert len(fs.analyses) == 2, "d1 failure must not abort the run"
    assert fs.runs and fs.runs[-1][0] == "analyze", "pipeline run must be recorded"
    assert analyze_pending.MAX_BILLS_DEFAULT == 10
    print("✓ run_pending: cap enforced, per-doc isolation, pipeline run recorded")


def test_ingest_corpus_isolation_and_run_record():
    orig_iter, orig_extract, orig_sleep = riigikogu.iterate_corpus, riigikogu.extract_bill_text, time.sleep
    time.sleep = lambda *_: None
    riigikogu.iterate_corpus = lambda cutoff, **kw: iter([_draft(1), _draft(2)])
    riigikogu.extract_bill_text = lambda uuid: ((None, None) if uuid == "u1"
                                                else ("Testseadus\n\n§ 1. Reegel\nSisu.\n", "docx"))

    class S(FakeStore):
        def __init__(self):
            super().__init__([])
            self.bills = {}

        def upsert_bill(self, mark, title, api_data):
            return f"b{mark}"

        def latest_doc_hash(self, bill_id):
            return None

        def next_version(self, bill_id):
            return 1

        def insert_document(self, *a, **kw):
            return True

    fs = S()
    try:
        stats = run_ingest.ingest_corpus(fs, cutoff="2026-01-01")
        assert stats["no_text"] == 1 and stats["new"] == 1, f"stats wrong: {stats}"
        assert fs.runs and fs.runs[-1][0] == "ingest"
    finally:
        riigikogu.iterate_corpus, riigikogu.extract_bill_text, time.sleep = \
            orig_iter, orig_extract, orig_sleep
    print("✓ ingest_corpus: no-text isolated + counted, pipeline run recorded")


if __name__ == "__main__":
    test_fetch_retries_timeouts_and_5xx()
    test_list_drafts_server_side_se_filter()
    test_iterate_corpus_window_and_stop()
    test_upsert_updates_existing()
    test_next_version_and_doc_listing()
    test_insert_analysis_and_new_writers()
    test_run_pending_cap_and_isolation()
    test_ingest_corpus_isolation_and_run_record()
    print("\nALL INGESTION CONTRACT TESTS PASSED")
