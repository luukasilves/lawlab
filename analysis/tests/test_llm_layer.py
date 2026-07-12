"""Contract tests for the LLM client resilience + refutation pass (R2a). RED until built.

Pins:
  * client.chat_json returns LLMResponse(text, input_tokens, output_tokens,
    cost_usd) — usage is captured, not discarded.
  * Bounded retry with backoff on 429/5xx AND requests timeouts/connection
    errors (the previous build died on unretried Riigikogu/LLM timeouts);
    non-429 4xx raises immediately.
  * verify_model() pings the provider for the configured model id at startup
    and raises LLMError on an unknown id (the v1-killing failure class).
  * The OpenRouter payload requests usage accounting and marks the system
    block with cache_control (prompt caching: sample 1 writes, samples 2..N
    + refute read).
  * refute.refute_findings judges sub-consensus findings with the skeptic
    prompt, sets skeptic_verdict/skeptic_reasoning on the finding IN PLACE
    (refuted findings are kept, never deleted), and returns SampleRecords
    with pass_id='refute'.

No network: requests.post/get and time.sleep are monkeypatched.
Run: python3 -m analysis.tests.test_llm_layer
"""

from __future__ import annotations

import json
import os
import time

# Hermetic: the client's key guard runs before the (monkeypatched) HTTP call,
# so a keyless CI runner must still pass this suite.
os.environ.setdefault("OPENROUTER_API_KEY", "test-key-hermetic")

import requests as _requests

from ..llm import client
from ..llm.client import chat_json, verify_model, LLMError, LLMResponse
from ..llm import refute
from ..models import Finding


class FakeResp:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload or {}
        self.text = json.dumps(self._payload)

    def json(self):
        return self._payload


def _ok_payload(text='{"issues": []}'):
    return {
        "choices": [{"message": {"content": text}}],
        "usage": {"prompt_tokens": 1200, "completion_tokens": 80, "cost": 0.0081},
    }


def _patch(posts):
    calls = {"n": 0, "payloads": []}

    def fake_post(url, **kw):
        calls["payloads"].append(kw.get("json"))
        resp = posts[min(calls["n"], len(posts) - 1)]
        calls["n"] += 1
        if isinstance(resp, Exception):
            raise resp
        return resp

    return fake_post, calls


def test_retry_on_429_then_success():
    orig_post, orig_sleep = client.requests.post, time.sleep
    fake, calls = _patch([FakeResp(429), FakeResp(200, _ok_payload())])
    client.requests.post = fake
    time.sleep = lambda *_: None
    try:
        r = chat_json("s", "u", temperature=0.4)
        assert isinstance(r, LLMResponse) and r.text == '{"issues": []}'
        assert calls["n"] == 2, f"expected one retry, got {calls['n']} calls"
        assert (r.input_tokens, r.output_tokens, r.cost_usd) == (1200, 80, 0.0081), \
            "usage must be captured from the response"
    finally:
        client.requests.post, time.sleep = orig_post, orig_sleep
    print("✓ 429 retried once then succeeds; usage captured into LLMResponse")


def test_retry_on_timeout_then_success():
    orig_post, orig_sleep = client.requests.post, time.sleep
    fake, calls = _patch([_requests.Timeout("read timeout"), FakeResp(200, _ok_payload())])
    client.requests.post = fake
    time.sleep = lambda *_: None
    try:
        r = chat_json("s", "u", temperature=0.4)
        assert r.text == '{"issues": []}' and calls["n"] == 2
    finally:
        client.requests.post, time.sleep = orig_post, orig_sleep
    print("✓ transport timeout retried (the previous build's killer)")


def test_client_error_fails_fast():
    orig_post, orig_sleep = client.requests.post, time.sleep
    fake, calls = _patch([FakeResp(401, {"error": "bad key"})])
    client.requests.post = fake
    time.sleep = lambda *_: None
    try:
        try:
            chat_json("s", "u", temperature=0.4)
        except LLMError:
            assert calls["n"] == 1, "4xx (non-429) must not be retried"
        else:
            raise AssertionError("401 did not raise LLMError")
    finally:
        client.requests.post, time.sleep = orig_post, orig_sleep
    print("✓ non-retryable 4xx raises immediately")


def test_payload_has_cache_control_and_usage():
    orig_post = client.requests.post
    fake, calls = _patch([FakeResp(200, _ok_payload())])
    client.requests.post = fake
    try:
        chat_json("SÜSTEEMIPROMPT", "kasutaja sisu", temperature=0.4)
        payload = calls["payloads"][0]
        assert payload.get("usage", {}).get("include") is True, "usage accounting must be requested"
        blob = json.dumps(payload.get("messages", []))
        assert "cache_control" in blob and "ephemeral" in blob, \
            "system/bill block must carry cache_control for prompt caching"
    finally:
        client.requests.post = orig_post
    print("✓ OpenRouter payload requests usage + marks cache_control")


def test_verify_model():
    orig_get = client.requests.get
    client.requests.get = lambda url, **kw: FakeResp(404, {"error": "not found"})
    try:
        try:
            verify_model("anthropic/claude-does-not-exist")
        except LLMError:
            pass
        else:
            raise AssertionError("unknown model id did not raise")
    finally:
        client.requests.get = orig_get

    client.requests.get = lambda url, **kw: FakeResp(200, {"data": {"id": "anthropic/claude-opus-4.8"}})
    try:
        verify_model("anthropic/claude-opus-4.8")
    finally:
        client.requests.get = orig_get
    print("✓ verify_model pings the provider and fails fast on a dead model id")


BILL = "Testseadus\n\n§ 1. Reegel\nSee säte kehtib alates esimesest jaanuarist.\n"


def _finding(runs_found=3, runs_total=5):
    return Finding(
        source="llm", category="terminology", severity="MEDIUM",
        title="terminikasutus kõigub", description="d", provision_id="§1",
        location="§ 1", evidence_quote="See säte kehtib alates",
        char_start=13, char_end=35, reasoning="r", confidence=runs_found / runs_total,
        check_id="llm", runs_found=runs_found, runs_total=runs_total,
    )


def test_refute_marks_in_place():
    orig = refute.chat_json
    refute.chat_json = lambda *a, **k: LLMResponse(
        text='{"verdict": "refuted", "reasoning": "Säte on kooskõlas: mõiste on defineeritud § 1 alguses."}',
        input_tokens=900, output_tokens=40, cost_usd=0.002)
    try:
        f = _finding(3, 5)
        records, stats = refute.refute_findings(BILL, [f])
        assert f.skeptic_verdict == "refuted" and "kooskõlas" in f.skeptic_reasoning
        assert stats == {"judged": 1, "refuted": 1}
        assert len(records) == 1 and records[0].pass_id == "refute"
        assert records[0].input_tokens == 900
    finally:
        refute.chat_json = orig
    print("✓ refuted finding stays, marked in place; SampleRecord carries usage")


def test_refute_blocks_match_template():
    """The split blocks must concatenate to EXACTLY build_user_message's text
    (the published prompt), with the cache breakpoint on the shared bill prefix."""
    from ..prompts import refutation
    blocks = refutation.build_user_blocks("SEADUSTEKST siin", '{"title": "x"}')
    joined = "".join(b["text"] for b in blocks)
    assert joined == refutation.build_user_message("SEADUSTEKST siin", '{"title": "x"}')
    assert "cache_control" in blocks[0] and "cache_control" not in blocks[1]
    print("✓ refute blocks == published template text; breakpoint on shared prefix")


def test_refute_upholds():
    orig = refute.chat_json
    refute.chat_json = lambda *a, **k: LLMResponse(
        text='{"verdict": "upheld", "reasoning": "Vastuolu on tegelik."}',
        input_tokens=900, output_tokens=30, cost_usd=0.002)
    try:
        f = _finding(4, 5)
        records, stats = refute.refute_findings(BILL, [f])
        assert f.skeptic_verdict == "upheld" and stats == {"judged": 1, "refuted": 0}
    finally:
        refute.chat_json = orig
    print("✓ upheld verdict recorded")


if __name__ == "__main__":
    test_retry_on_429_then_success()
    test_retry_on_timeout_then_success()
    test_client_error_fails_fast()
    test_payload_has_cache_control_and_usage()
    test_verify_model()
    test_refute_marks_in_place()
    test_refute_blocks_match_template()
    test_refute_upholds()
    print("\nALL LLM-LAYER TESTS PASSED")
