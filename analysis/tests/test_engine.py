"""Adversarial regression suite for the LLM engine (Lane C).

Authored by the orchestrator BEFORE the fixes. RED on pre-fix code by design.

Contracts under test:
  * _locate fallback end-offset: when only the first ~12 tokens match, the span
    must end at m2.end() (the matched prefix), not start+len(quote) arithmetic
    that bleeds arbitrary characters into the stored evidence.
  * Unparseable model output raises LLMParseError (defined in engine) instead
    of silently becoming {"issues": []} — which today gets CACHED as a clean
    empty result, permanently poisoning the bill.
  * _coerce_category relabels are counted in stats (stats["relabelled"]), not
    silent.
  * Grounding still drops ungrounded findings (guard).

No network: chat_json is monkeypatched. Run: python3 -m analysis.tests.test_engine
"""

from __future__ import annotations

from ..llm import engine
from ..llm.engine import _locate, analyze_once

BILL = (
    "Testseadus\n\n"
    "§ 1. Reegel\n"
    "See säte kehtib alates esimesest jaanuarist ja lõpeb detsembris.\n"
)


def test_locate_fallback_end_offset():
    toks = [f"sõna{i:02d}" for i in range(1, 21)]
    raw = " ".join(toks)
    quote = " ".join(toks[:12] + ["puudub", "siinkohal", "täiesti"])
    expected_end = len(" ".join(toks[:12]))
    loc = _locate(raw, quote)
    assert loc is not None, "fallback must still locate the 12-token prefix"
    start, end = loc
    assert start == 0, f"start wrong: {start}"
    assert end == expected_end, (
        f"fallback end must be the matched prefix end ({expected_end}), got {end} "
        f"(start+len(quote) arithmetic bleeds {end - expected_end} garbage chars)"
    )
    print("✓ _locate fallback ends at m2.end(), not start+len(quote)")


def test_unparseable_output_raises():
    assert hasattr(engine, "LLMParseError"), "engine must define LLMParseError"
    orig = engine.chat_json
    engine.chat_json = lambda *a, **k: "See ei ole JSON, vaid vaba tekst ilma sulgudeta."
    try:
        try:
            analyze_once(BILL)
        except engine.LLMParseError:
            print("✓ unparseable model output raises LLMParseError (no silent empty result)")
        else:
            raise AssertionError("unparseable output was silently swallowed (poisons the cache)")
    finally:
        engine.chat_json = orig


def test_relabel_is_counted():
    orig = engine.chat_json
    engine.chat_json = lambda *a, **k: (
        '{"issues": [{"category": "tundmatu_kategooria", "severity": "LOW",'
        ' "title": "t", "description": "d",'
        ' "evidence_quote": "See säte kehtib alates esimesest jaanuarist"}]}'
    )
    try:
        findings, stats = analyze_once(BILL)
        assert len(findings) == 1 and findings[0].category == "logical_contradiction"
        assert stats.get("relabelled") == 1, f"relabel not counted in stats: {stats}"
        print("✓ unknown-category relabel is counted in stats")
    finally:
        engine.chat_json = orig


def test_grounding_still_drops():
    orig = engine.chat_json
    engine.chat_json = lambda *a, **k: (
        '{"issues": [{"category": "terminology", "severity": "LOW",'
        ' "title": "t", "description": "d",'
        ' "evidence_quote": "seda lauset eelnõus kindlasti ei leidu"}]}'
    )
    try:
        findings, stats = analyze_once(BILL)
        assert findings == [] and stats["dropped"] == 1, f"grounding guard broken: {stats}"
        print("✓ ungrounded findings still dropped as hallucinations")
    finally:
        engine.chat_json = orig


if __name__ == "__main__":
    test_locate_fallback_end_offset()
    test_unparseable_output_raises()
    test_relabel_is_counted()
    test_grounding_still_drops()
    print("\nALL ENGINE TESTS PASSED")
