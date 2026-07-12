"""Adversarial regression suite for the analysis runner (Lane D).

Authored by the orchestrator BEFORE the fixes. RED on pre-fix code by design.

Contracts under test:
  * cache_key hashes the RAW text: whitespace-differing texts must NOT collide
    (offsets are the contract with the viewer's highlights; a collision serves
    one layout's offsets for another layout's text).
  * cache_key includes the LLM provider (same model id string across providers
    must not collide).
  * Engine bugs (TypeError & co) PROPAGATE out of analyze() — only transport
    errors (LLMError) may degrade to stats["llm_error"].
  * LLMError still degrades softly and never loses deterministic output (guard).

No network: run_self_consistency is monkeypatched. Run: python3 -m analysis.tests.test_run
"""

from __future__ import annotations

import config
from .. import run as runmod
from ..run import cache_key, analyze
from ..llm.client import LLMError

BILL = "Testseadus\n\n§ 1. Reegel\nSisu on lühike ja selge.\n"


def test_cache_key_raw_text():
    k1 = cache_key("a  b\n\nc", "test-model", 5, 3, 0.4)
    k2 = cache_key("a b c", "test-model", 5, 3, 0.4)
    assert k1 != k2, "whitespace-collapsed cache key: different raw texts collide (offset corruption)"
    print("✓ cache key distinguishes whitespace-differing raw texts")


def test_cache_key_includes_provider():
    saved = config.LLM_PROVIDER
    try:
        config.LLM_PROVIDER = "openrouter"
        k1 = cache_key(BILL, "same-model-id", 5, 3, 0.4)
        config.LLM_PROVIDER = "anthropic"
        k2 = cache_key(BILL, "same-model-id", 5, 3, 0.4)
    finally:
        config.LLM_PROVIDER = saved
    assert k1 != k2, "cache key must include the provider (cross-provider collision)"
    print("✓ cache key includes the LLM provider")


def test_engine_bug_propagates():
    saved = runmod.run_self_consistency

    def boom(*a, **k):
        raise TypeError("engine bug: not a transport error")

    runmod.run_self_consistency = boom
    try:
        try:
            analyze(BILL, use_llm=True, n=1, k=1, temp=0.4, use_cache=False)
        except TypeError:
            print("✓ engine bugs propagate instead of masquerading as llm_error")
        else:
            raise AssertionError("TypeError swallowed into stats['llm_error'] — engine bugs are invisible")
    finally:
        runmod.run_self_consistency = saved


def test_llm_transport_error_degrades_softly():
    saved = runmod.run_self_consistency

    def limited(*a, **k):
        raise LLMError("429 rate limited")

    runmod.run_self_consistency = limited
    try:
        out, cached = analyze(BILL, use_llm=True, n=1, k=1, temp=0.4, use_cache=False)
        assert "429" in out["stats"].get("llm_error", ""), f"llm_error missing: {out['stats']}"
        assert cached is False
        print("✓ transport errors still degrade softly (deterministic output kept)")
    finally:
        runmod.run_self_consistency = saved


if __name__ == "__main__":
    test_cache_key_raw_text()
    test_cache_key_includes_provider()
    test_engine_bug_propagates()
    test_llm_transport_error_degrades_softly()
    print("\nALL RUN TESTS PASSED")
