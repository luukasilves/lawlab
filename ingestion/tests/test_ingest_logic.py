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
import sys
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


def test_fetch_exhaustion_and_404():
    orig_get, orig_sleep = riigikogu.requests.get, time.sleep
    time.sleep = lambda *_: None
    try:
        log = []
        riigikogu.requests.get = _seq([FakeResp(503)], log)
        try:
            riigikogu.fetch_with_retry("http://x/503", max_retries=3)
            raise AssertionError("503 exhaustion must raise")
        except riigikogu.RiigikoguUnavailable as exc:
            assert exc.status == 503 and exc.reason == "HTTP 503"
            assert len(log) == 3

        log2 = []
        riigikogu.requests.get = _seq([_requests.Timeout("t")], log2)
        try:
            riigikogu.fetch_with_retry("http://x/timeout", max_retries=2)
            raise AssertionError("timeout exhaustion must raise")
        except riigikogu.RiigikoguUnavailable as exc:
            assert exc.status is None and exc.reason == "timeout"
            assert len(log2) == 2

        riigikogu.requests.get = _seq([FakeResp(404)], [])
        try:
            riigikogu.fetch_with_retry("http://x/404")
            raise AssertionError("404 must keep raising HTTPError")
        except _requests.HTTPError:
            pass
    finally:
        riigikogu.requests.get, time.sleep = orig_get, orig_sleep
    print("✓ fetch_with_retry raises typed failures after retries; 404 remains HTTPError")


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


def test_iterate_empty_page_vs_5xx():
    orig_get, orig_sleep = riigikogu.requests.get, time.sleep
    time.sleep = lambda *_: None
    try:
        page0 = {"_embedded": {"content": [_draft(1, "IN_PROCESS", "2026-06-01")]}}
        riigikogu.requests.get = _seq([FakeResp(200, page0),
                                       FakeResp(200, {"_embedded": {"content": []}})], [])
        got = [d["mark"] for d in riigikogu.iterate_corpus("2026-01-01", max_pages=2)]
        assert got == [1], f"genuine empty page should stop cleanly: {got}"

        log = []
        riigikogu.requests.get = _seq([FakeResp(200, page0), FakeResp(503)], log)
        it = riigikogu.iterate_corpus("2026-01-01", max_pages=2)
        assert next(it)["mark"] == 1
        try:
            next(it)
            raise AssertionError("5xx page must propagate RiigikoguUnavailable")
        except riigikogu.RiigikoguUnavailable as exc:
            assert exc.status == 503 and exc.reason == "HTTP 503"
    finally:
        riigikogu.requests.get, time.sleep = orig_get, orig_sleep
    print("✓ iterate_corpus separates empty pages from unavailable listing pages")


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
        assert "document_type=eq.eeln%C3%B5u" in log[0][0]
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
        assert "order=fetched_at.desc,id.asc" in url0, f"deterministic order missing: {url0}"
        assert log2[0][1].get("headers", {}).get("Range") is not None, "Range pagination expected"
    finally:
        store_mod.requests.get = orig_get
    print("✓ next_version max+1 w/ tiebreaker; doc listing paginates without parsed_text")


def test_bill_state_and_count_bills_urls():
    s = _mkstore()
    orig_get = store_mod.requests.get
    log = []
    store_mod.requests.get = _seq([
        FakeResp(206, [{"id": "b1"}], {"Content-Range": "0-0/212"}),
        FakeResp(200, [{"id": "b1", "stage": "2026-01-01", "bill_documents": []}]),
    ], log)
    try:
        assert s.count_bills() == 212
        assert log[0][1]["headers"]["Prefer"] == "count=exact"
        assert log[0][1]["headers"]["Range"] == "0-0"
        s.bill_state("9")
        assert "bill_documents.document_type=eq.eeln%C3%B5u" in log[1][0]
    finally:
        store_mod.requests.get = orig_get
    print("✓ count_bills parses Content-Range; bill_state counts only eelnõu docs")


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
        assert body["llm_cache_key"] == "lk"
        s.insert_samples("a1", [{"pass_id": "interpretive", "sample_idx": 0}])
        assert "/analysis_samples" in log[1][0] and log[1][1]["json"][0]["analysis_id"] == "a1"
        s.record_run("ingest", "2026-07-12T00:00:00Z", True, {"new": 1})
        assert "/pipeline_runs" in log[2][0]
    finally:
        store_mod.requests.post = orig_post
    print("✓ transparency columns written; insert_samples/record_run wired")


def test_insert_analysis_reads_llm_cache_key_from_config():
    s = _mkstore()
    orig_post = store_mod.requests.post
    log = []
    store_mod.requests.post = _seq([FakeResp(201, [{"id": "a2"}])], log)
    try:
        s.insert_analysis("d1", {
            "cache_key": "ck", "model": "m", "provider": "p",
            "config": {"llm_cache_key": "lk-from-config"}, "stats": {},
        })
        assert log[0][1]["json"]["llm_cache_key"] == "lk-from-config"
    finally:
        store_mod.requests.post = orig_post
    print("✓ insert_analysis reads llm_cache_key from result.config fallback")


class FakeStore:
    def __init__(self, docs, bill_count=0):
        self._docs = docs
        self.bill_count = bill_count
        self.analyses = []
        self.samples = []
        self.runs = []
        self.text_fetches = 0
        self.text_status = {}

    def count_bills(self):
        return self.bill_count

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

    def set_text_status(self, bill_id, status, formats):
        self.text_status[bill_id] = (status, formats)


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


def test_degraded_llm_analysis_not_persisted():
    """An analysis whose LLM stage soft-failed (stats.llm_error) must NOT be
    persisted: its cache_key would block the retry forever (live bug on bill
    652 — truncated JSON → llm_error → persisted as complete)."""
    fs = FakeStore([{"id": "d9", "bill_id": "b9", "content_hash": "h9"}])

    def degraded(text, **kw):
        return ({"result": {"cache_key": "ck9", "llm_cache_key": "lk9", "model": "m",
                            "provider": "p", "prompt_version": "v", "checker_version": "c",
                            "engine": {}, "config": {}, "findings": []},
                 "stats": {"deterministic": 3, "llm_error": "output truncated at max_tokens"},
                 "samples": [], "usage": {"input_tokens": 0, "output_tokens": 0,
                                          "cost_usd": 0.0, "duration_ms": 1}}, False)

    stats = analyze_pending.run_pending(fs, analyze_fn=degraded, max_bills=5)
    assert stats["failed"] == 1 and stats["analysed"] == 0, f"degraded run persisted: {stats}"
    assert fs.analyses == [], "degraded analysis row must not be written"
    print("✓ degraded (llm_error) analyses are not persisted — retry stays possible")


def test_ingest_skips_unmoved_bills_without_download():
    """Same activeDraftStatusDate + stored doc => no Riigikogu download (the
    full re-download crawl blew the 25-minute cron job cap)."""
    orig_iter, orig_extract, orig_sleep = riigikogu.iterate_corpus, riigikogu.extract_bill_text, time.sleep
    time.sleep = lambda *_: None
    riigikogu.iterate_corpus = lambda cutoff, **kw: iter([_draft(1, date="2026-06-01")])

    def must_not_download(uuid):
        raise AssertionError("unmoved bill was downloaded")
    riigikogu.extract_bill_text = must_not_download

    class S(FakeStore):
        def __init__(self):
            super().__init__([])
            self.states = {1: {"id": "b1", "stage": "2026-06-01", "has_doc": True}}

        def upsert_bill(self, mark, title, api_data):
            return "b1"

        def bill_state(self, mark):
            return self.states.get(mark)

    fs = S()
    try:
        stats = run_ingest.ingest_corpus(fs, cutoff="2026-01-01")
        assert stats["unchanged"] == 1 and stats["failed"] == 0, f"skip broken: {stats}"
    finally:
        riigikogu.iterate_corpus, riigikogu.extract_bill_text, time.sleep = orig_iter, orig_extract, orig_sleep
    print("✓ unmoved bills skip the download entirely")


def test_ingest_corpus_isolation_and_run_record():
    orig_iter, orig_extract, orig_sleep = riigikogu.iterate_corpus, riigikogu.extract_bill_text, time.sleep
    time.sleep = lambda *_: None
    riigikogu.iterate_corpus = lambda cutoff, **kw: iter([_draft(1), _draft(2)])
    riigikogu.extract_bill_text = lambda uuid: (
        riigikogu.Extraction(None, None, "no_files", "") if uuid == "u1"
        else riigikogu.Extraction(
            "Testseadus\n\n§ 1. Reegel\nSisu.\n" * 20, "docx", "ok", "docx"))

    class S(FakeStore):
        def __init__(self):
            super().__init__([])
            self.bills = {}

        def upsert_bill(self, mark, title, api_data):
            return f"b{mark}"

        def bill_state(self, mark):
            return self.states.get(mark) if hasattr(self, "states") else None

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


def test_ingest_listing_failure_records_not_ok():
    orig_iter = riigikogu.iterate_corpus

    def fail_listing(cutoff, **kw):
        raise riigikogu.RiigikoguUnavailable("http://x", 503, "HTTP 503")

    riigikogu.iterate_corpus = fail_listing
    fs = FakeStore([], bill_count=10)
    try:
        stats = run_ingest.ingest_corpus(fs, cutoff="2026-01-01")
        assert stats["failed"] == 1 and stats["error"].startswith("listing:"), stats
        assert fs.runs[-1][1] is False
    finally:
        riigikogu.iterate_corpus = orig_iter
    print("✓ listing failures record ok=False with a listing-prefixed error")


def test_ingest_seen_floor_and_disable():
    orig_iter, orig_extract, orig_sleep = riigikogu.iterate_corpus, riigikogu.extract_bill_text, time.sleep
    time.sleep = lambda *_: None
    riigikogu.iterate_corpus = lambda cutoff, **kw: iter([_draft(1), _draft(2), _draft(3)])
    riigikogu.extract_bill_text = lambda uuid: riigikogu.Extraction(None, None, "no_files", "")

    class S(FakeStore):
        def upsert_bill(self, mark, title, api_data):
            return f"b{mark}"

        def bill_state(self, mark):
            return None

    try:
        fs = S([], bill_count=200)
        stats = run_ingest.ingest_corpus(fs, cutoff="2026-01-01")
        assert stats["seen"] == 3 and stats["min_seen"] == 100, stats
        assert "listing may be truncated" in stats["error"]
        assert fs.runs[-1][1] is False

        fs2 = S([], bill_count=200)
        stats2 = run_ingest.ingest_corpus(fs2, cutoff="2026-01-01", min_seen=0)
        assert stats2["min_seen"] == 0 and "error" not in stats2, stats2
        assert fs2.runs[-1][1] is True
    finally:
        riigikogu.iterate_corpus, riigikogu.extract_bill_text, time.sleep = \
            orig_iter, orig_extract, orig_sleep
    print("✓ full runs enforce the seen floor; min_seen=0 disables it")


def test_ingest_records_text_statuses():
    orig_iter, orig_extract, orig_sleep = riigikogu.iterate_corpus, riigikogu.extract_bill_text, time.sleep
    time.sleep = lambda *_: None

    class S(FakeStore):
        def upsert_bill(self, mark, title, api_data):
            return f"b{mark}"

        def bill_state(self, mark):
            return None

        def latest_doc_hash(self, bill_id):
            return None

        def next_version(self, bill_id):
            return 1

        def insert_document(self, *a, **kw):
            return True

    try:
        riigikogu.iterate_corpus = lambda cutoff, **kw: iter([_draft(1)])
        riigikogu.extract_bill_text = lambda uuid: riigikogu.Extraction(
            None, None, "image_only_pdf", "pdf")
        fs = S([], bill_count=1)
        stats = run_ingest.ingest_corpus(fs, cutoff="2026-01-01", min_seen=0)
        assert stats["no_text"] == 1 and stats["failed"] == 0, stats
        assert fs.text_status["b1"] == ("image_only_pdf", "pdf")
        assert fs.runs[-1][1] is True

        riigikogu.extract_bill_text = lambda uuid: riigikogu.Extraction(
            None, None, "download_failed", "docx")
        fs2 = S([], bill_count=1)
        stats2 = run_ingest.ingest_corpus(fs2, cutoff="2026-01-01", min_seen=0)
        assert stats2["failed"] == 1 and fs2.runs[-1][1] is False, stats2
        assert fs2.text_status["b1"] == ("download_failed", "docx")

        text = "Testseadus\n\n§ 1. Reegel\n" + ("Sisu. " * 50)
        riigikogu.extract_bill_text = lambda uuid: riigikogu.Extraction(
            text, "docx", "ok", "doc,docx")
        fs3 = S([], bill_count=1)
        stats3 = run_ingest.ingest_corpus(fs3, cutoff="2026-01-01", min_seen=0)
        assert stats3["new"] == 1 and stats3["text_status_counts"]["ok"] == 1, stats3
        assert fs3.text_status["b1"] == ("ok", "doc,docx")
    finally:
        riigikogu.iterate_corpus, riigikogu.extract_bill_text, time.sleep = \
            orig_iter, orig_extract, orig_sleep
    print("✓ ingest records data/no-text, download failure, and success text statuses")


def test_ingest_stores_memo_as_second_document():
    orig_iter, orig_extract, orig_sleep = riigikogu.iterate_corpus, riigikogu.extract_bill_text, time.sleep
    time.sleep = lambda *_: None
    text = "Testseadus\n\n§ 1. Reegel\n" + ("Sisu. " * 50)
    memo = "Seletuskiri\n" + ("Memo. " * 50)
    riigikogu.iterate_corpus = lambda cutoff, **kw: iter([_draft(1)])
    riigikogu.extract_bill_text = lambda uuid: riigikogu.Extraction(
        text, "doc_via_libreoffice", "ok", "doc,pdf", memo=memo)

    class S(FakeStore):
        def __init__(self):
            super().__init__([], bill_count=1)
            self.documents = []

        def upsert_bill(self, mark, title, api_data):
            return "b1"

        def bill_state(self, mark):
            return None

        def latest_doc_hash(self, bill_id):
            return None

        def next_version(self, bill_id):
            return 7

        def insert_document(self, *a, **kw):
            self.documents.append((a, kw))
            return True

    fs = S()
    try:
        stats = run_ingest.ingest_corpus(fs, cutoff="2026-01-01", min_seen=0)
        assert stats["new"] == 1 and len(fs.documents) == 2, stats
        assert fs.documents[0][0][4] == 7 and fs.documents[0][1].get("document_type") is None
        assert fs.documents[1][0][4] == 7
        assert fs.documents[1][1]["document_type"] == "seletuskiri"
    finally:
        riigikogu.iterate_corpus, riigikogu.extract_bill_text, time.sleep = \
            orig_iter, orig_extract, orig_sleep
    print("✓ appended memo is stored as a separate seletuskiri document at the same version")


def test_recheck_bypasses_cheap_skip():
    orig_iter, orig_extract, orig_sleep = riigikogu.iterate_corpus, riigikogu.extract_bill_text, time.sleep
    time.sleep = lambda *_: None
    text = "Testseadus\n\n§ 1. Reegel\n" + ("Sisu. " * 50)
    calls = []
    riigikogu.iterate_corpus = lambda cutoff, **kw: iter([_draft(1, date="2026-06-01")])

    def extract(uuid):
        calls.append(uuid)
        return riigikogu.Extraction(text, "docx", "ok", "docx")

    riigikogu.extract_bill_text = extract

    class S(FakeStore):
        def __init__(self):
            super().__init__([], bill_count=1)

        def bill_state(self, mark):
            return {"id": "b1", "stage": "2026-06-01", "has_doc": True}

        def upsert_bill(self, mark, title, api_data):
            return "b1"

        def latest_doc_hash(self, bill_id):
            return riigikogu.content_hash(text)

    fs = S()
    try:
        stats = run_ingest.ingest_corpus(fs, cutoff="2026-01-01", min_seen=0, recheck=["1"])
        assert calls == ["u1"], calls
        assert stats["unchanged"] == 1 and fs.text_status["b1"] == ("ok", "docx")
    finally:
        riigikogu.iterate_corpus, riigikogu.extract_bill_text, time.sleep = \
            orig_iter, orig_extract, orig_sleep
    print("✓ recheck bill numbers bypass the cheap skip and refresh text_status")


def test_mains_exit_nonzero_when_not_ok():
    orig_argv = sys.argv[:]
    orig_ingest = run_ingest.ingest_corpus
    orig_pending = analyze_pending.run_pending
    orig_store = analyze_pending.SupabaseStore
    try:
        run_ingest.ingest_corpus = lambda *a, **kw: {"failed": 1}
        sys.argv = ["run_ingest", "--dry-run"]
        try:
            run_ingest.main()
            raise AssertionError("ingest main must exit 1")
        except SystemExit as exc:
            assert exc.code == 1

        analyze_pending.SupabaseStore = lambda: FakeStore([])
        analyze_pending.run_pending = lambda *a, **kw: {"error": "bad", "failed": 0}
        sys.argv = ["analyze_pending"]
        try:
            analyze_pending.main()
            raise AssertionError("analyze main must exit 1")
        except SystemExit as exc:
            assert exc.code == 1
    finally:
        sys.argv = orig_argv
        run_ingest.ingest_corpus = orig_ingest
        analyze_pending.run_pending = orig_pending
        analyze_pending.SupabaseStore = orig_store
    print("✓ worker mains exit SystemExit(1) when run_ok is false")


def test_run_pending_empty_candidates_and_pending_count():
    fs = FakeStore([], bill_count=5)
    stats = analyze_pending.run_pending(fs, analyze_fn=lambda text, **kw: None)
    assert stats["candidates"] == 0 and stats["error"] == "no candidate documents while bills exist"
    assert fs.runs[-1][1] is False

    empty = FakeStore([], bill_count=0)
    stats_empty = analyze_pending.run_pending(empty, analyze_fn=lambda text, **kw: None)
    assert stats_empty["candidates"] == 0 and "error" not in stats_empty
    assert empty.runs[-1][1] is True

    docs = [{"id": f"d{i}", "bill_id": f"b{i}", "content_hash": f"h{i}"} for i in range(4)]
    capped = FakeStore(docs, bill_count=4)

    def ok_analyze(text, **kw):
        return ({"result": {"cache_key": "ck", "llm_cache_key": "lk", "model": "m",
                            "provider": "p", "prompt_version": "v", "checker_version": "c",
                            "engine": {}, "config": {}, "findings": []},
                 "stats": {}, "samples": [], "usage": {"input_tokens": 1, "output_tokens": 1,
                                                       "cost_usd": 0.0, "duration_ms": 1}}, False)

    stats_cap = analyze_pending.run_pending(capped, analyze_fn=ok_analyze, max_bills=2)
    assert stats_cap["analysed"] == 2 and stats_cap["pending"] == 2, stats_cap
    assert capped.runs[-1][1] is True
    print("✓ run_pending flags empty candidate gaps and reports capped backlog")


def test_find_best_document_preference_and_formats():
    texts = [
        {"file": {"fileTitle": "Eelnõu tekst", "fileExtension": "pdf",
                  "_links": {"download": {"href": "pdf-url"}}}},
        {"file": {"fileTitle": "Algtekst", "fileExtension": "doc",
                  "_links": {"download": {"href": "doc-url"}}}},
        {"file": {"fileTitle": "Seletuskiri", "fileExtension": "docx",
                  "_links": {"download": {"href": "memo-url"}}}},
        {"file": {"fileTitle": "Eelnõu", "fileExtension": "asice",
                  "_links": {"download": {"href": "asice-url"}}}},
    ]
    ext, url, formats = riigikogu.find_best_document(texts)
    assert (ext, url) == ("doc", "doc-url")
    assert formats == ["asice", "doc", "pdf"]

    texts.append({"file": {"fileTitle": "Eelnõu", "fileExtension": "docx",
                           "_links": {"download": {"href": "docx-url"}}}})
    ext2, url2, formats2 = riigikogu.find_best_document(texts)
    assert (ext2, url2) == ("docx", "docx-url")
    assert formats2 == ["asice", "doc", "docx", "pdf"]
    print("✓ find_best_document prefers docx/doc/pdf and reports all seen formats")


def test_extract_bill_text_status_classification():
    orig_texts = riigikogu.get_draft_texts
    orig_doc = riigikogu.extract_doc
    orig_docx = riigikogu.extract_docx
    orig_pdf = riigikogu.extract_pdf
    orig_sleep = time.sleep
    time.sleep = lambda *_: None
    try:
        riigikogu.get_draft_texts = lambda uuid: []
        ex = riigikogu.extract_bill_text("u")
        assert ex.status == "no_files" and ex.formats == ""

        riigikogu.get_draft_texts = lambda uuid: [
            {"file": {"fileTitle": "Eelnõu", "fileExtension": "asice",
                      "_links": {"download": {"href": "asice-url"}}}}]
        ex = riigikogu.extract_bill_text("u")
        assert ex.status == "unsupported_format" and ex.formats == "asice"

        riigikogu.get_draft_texts = lambda uuid: [
            {"file": {"fileTitle": "Eelnõu", "fileExtension": "doc",
                      "_links": {"download": {"href": "doc-url"}}}},
            {"file": {"fileTitle": "Eelnõu", "fileExtension": "pdf",
                      "_links": {"download": {"href": "pdf-url"}}}},
        ]
        riigikogu.extract_doc = lambda url: (_ for _ in ()).throw(
            riigikogu.DocConvertError("no soffice"))
        ex = riigikogu.extract_bill_text("u")
        assert ex.status == "convert_failed" and ex.formats == "doc,pdf"

        riigikogu.get_draft_texts = lambda uuid: [
            {"file": {"fileTitle": "Eelnõu", "fileExtension": "pdf",
                      "_links": {"download": {"href": "pdf-url"}}}}]
        riigikogu.extract_pdf = lambda url: "too short"
        ex = riigikogu.extract_bill_text("u")
        assert ex.status == "image_only_pdf" and ex.method == "pdf_text"

        riigikogu.get_draft_texts = lambda uuid: [
            {"file": {"fileTitle": "Eelnõu", "fileExtension": "docx",
                      "_links": {"download": {"href": "docx-url"}}}}]
        riigikogu.extract_docx = lambda url: (_ for _ in ()).throw(
            riigikogu.RiigikoguUnavailable(url, 503, "HTTP 503"))
        ex = riigikogu.extract_bill_text("u")
        assert ex.status == "download_failed" and ex.formats == "docx"
    finally:
        riigikogu.get_draft_texts = orig_texts
        riigikogu.extract_doc = orig_doc
        riigikogu.extract_docx = orig_docx
        riigikogu.extract_pdf = orig_pdf
        time.sleep = orig_sleep
    print("✓ extract_bill_text classifies no_files/unsupported/convert/pdf/download statuses")


if __name__ == "__main__":
    test_fetch_retries_timeouts_and_5xx()
    test_fetch_exhaustion_and_404()
    test_list_drafts_server_side_se_filter()
    test_iterate_corpus_window_and_stop()
    test_iterate_empty_page_vs_5xx()
    test_upsert_updates_existing()
    test_next_version_and_doc_listing()
    test_bill_state_and_count_bills_urls()
    test_insert_analysis_and_new_writers()
    test_insert_analysis_reads_llm_cache_key_from_config()
    test_run_pending_cap_and_isolation()
    test_degraded_llm_analysis_not_persisted()
    test_ingest_skips_unmoved_bills_without_download()
    test_ingest_corpus_isolation_and_run_record()
    test_ingest_listing_failure_records_not_ok()
    test_ingest_seen_floor_and_disable()
    test_ingest_records_text_statuses()
    test_ingest_stores_memo_as_second_document()
    test_recheck_bypasses_cheap_skip()
    test_mains_exit_nonzero_when_not_ok()
    test_run_pending_empty_candidates_and_pending_count()
    test_find_best_document_preference_and_formats()
    test_extract_bill_text_status_classification()
    print("\nALL INGESTION CONTRACT TESTS PASSED")
