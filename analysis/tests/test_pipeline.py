"""Contract tests for the rebuilt analyze() pipeline (R2a). RED until built.

Pins:
  * models.SampleRecord dataclass (pass_id, sample_idx, temperature,
    raw_output, parsed, returned_count, grounded_count, dropped_ungrounded,
    reused, duration_ms, input_tokens, output_tokens, cost_usd, to_dict()).
  * run_self_consistency returns (stable, samples: List[SampleRecord], stats)
    and runs samples CONCURRENTLY (ThreadPoolExecutor); stats carries
    clusters incl. kept:false sub-threshold ones with members
    [[sample_idx, index_into_that_sample's_parsed], …].
  * aggregate.cluster_with_summaries(samples, n_runs, k) -> (stable,
    summaries); legacy cluster_llm_samples keeps its old signature.
  * analyze() output: {"result": {... provider, engine manifest ...},
    "stats": {...}, "samples": [record dicts], "usage": {input_tokens,
    output_tokens, cost_usd, duration_ms}}; refutation runs on stable llm
    findings with runs_found < runs_total; refuted findings REMAIN in
    result.findings with skeptic_verdict='refuted'.
  * analyze(reused_samples=[...]) rebuilds findings from stored parsed
    sample dicts WITHOUT calling the interpretive engine (the llm_cache_key
    reuse path that makes new checks ~free); reused records marked
    reused=True in the output.
  * AnalysisResult.by_severity() counts only non-refuted findings.

No network: engine.analyze_once / refute chat are monkeypatched.
Run: python3 -m analysis.tests.test_pipeline
"""

from __future__ import annotations

import threading
import time

from ..models import Finding, SampleRecord, AnalysisResult
from ..aggregate import run_self_consistency, cluster_with_summaries
from ..llm import engine as engine_mod
from ..llm import refute as refute_mod
from ..llm.client import LLMResponse
from .. import run as runmod
from ..run import analyze

BILL = "Testseadus\n\n§ 1. Reegel\nSee säte kehtib alates esimesest jaanuarist ja lõpeb detsembris.\n"


def _f(title="terminikasutus kõigub siin", start=13, end=35, cat="terminology"):
    return Finding(
        source="llm", category=cat, severity="MEDIUM", title=title,
        description="d", provision_id="§1", location="§ 1",
        evidence_quote=BILL[start:end], char_start=start, char_end=end,
        reasoning="r", confidence=1.0, check_id="llm",
    )


def _stub_analyze_once(track=None):
    lock = threading.Lock()
    state = {"live": 0, "peak": 0}

    def stub(bill_text, structure_hint="", temperature=0.4, model=None):
        with lock:
            state["live"] += 1
            state["peak"] = max(state["peak"], state["live"])
        time.sleep(0.15)
        with lock:
            state["live"] -= 1
        rec = SampleRecord(
            pass_id="interpretive", sample_idx=-1, temperature=temperature,
            raw_output='{"issues": [...]}', parsed=[_f().to_dict()],
            returned_count=1, grounded_count=1, dropped_ungrounded=0,
            duration_ms=150, input_tokens=1000, output_tokens=50, cost_usd=0.006,
        )
        return [_f()], rec

    if track is not None:
        track.update(state)
        return stub, state
    return stub


def test_parallel_sampling_and_records():
    orig = engine_mod.analyze_once
    stub, state = _stub_analyze_once(track={})
    engine_mod.analyze_once = stub
    try:
        t0 = time.monotonic()
        stable, samples, stats = run_self_consistency(BILL, "", n=4, k=3, temperature=0.4, model="m")
        elapsed = time.monotonic() - t0
        assert state["peak"] >= 2, f"samples must run concurrently (peak={state['peak']})"
        assert elapsed < 0.45, f"4 samples at 0.15s each took {elapsed:.2f}s — looks serial"
        assert len(samples) == 4 and sorted(r.sample_idx for r in samples) == [0, 1, 2, 3]
        assert all(r.pass_id == "interpretive" and not r.reused for r in samples)
        assert len(stable) == 1 and stable[0].runs_found == 4
        clusters = stats["clusters"]
        assert len(clusters) == 1 and clusters[0]["kept"] is True
        assert sorted(m[0] for m in clusters[0]["members"]) == [0, 1, 2, 3]
    finally:
        engine_mod.analyze_once = orig
    print("✓ parallel sampling with ordered SampleRecords + cluster membership map")


def test_subthreshold_cluster_reported():
    samples = [[_f("ainulaadne leid siin", 40, 55, "completeness")], [], []]
    stable, summaries = cluster_with_summaries(samples, n_runs=3, k=2)
    assert stable == []
    assert len(summaries) == 1 and summaries[0]["kept"] is False and summaries[0]["support"] == 1
    print("✓ sub-threshold clusters surface in summaries with kept:false")


def test_analyze_output_shape_and_refute_wiring():
    orig_once, orig_chat = engine_mod.analyze_once, refute_mod.chat_json

    def two_of_three(bill_text, structure_hint="", temperature=0.4, model=None):
        idx = getattr(two_of_three, "i", 0)
        two_of_three.i = idx + 1
        finds = [_f()] if idx < 2 else []
        rec = SampleRecord(
            pass_id="interpretive", sample_idx=-1, temperature=temperature,
            raw_output="{}", parsed=[f.to_dict() for f in finds],
            returned_count=len(finds), grounded_count=len(finds), dropped_ungrounded=0,
            duration_ms=10, input_tokens=1000, output_tokens=40, cost_usd=0.005,
        )
        return finds, rec

    engine_mod.analyze_once = two_of_three
    refute_mod.chat_json = lambda *a, **k: LLMResponse(
        text='{"verdict": "refuted", "reasoning": "Termin on järjepidev."}',
        input_tokens=800, output_tokens=30, cost_usd=0.002)
    try:
        out, cached = analyze(BILL, use_llm=True, n=3, k=2, temp=0.4, use_cache=False)
        res = out["result"]
        assert res["provider"] and isinstance(res["engine"], dict) and res["engine"]["checks"]
        llm_f = [f for f in res["findings"] if f["source"] == "llm"]
        assert len(llm_f) == 1 and llm_f[0]["skeptic_verdict"] == "refuted", \
            "sub-consensus finding must be judged and KEPT with verdict"
        assert llm_f[0]["skeptic_reasoning"]
        recs = out["samples"]
        assert len(recs) == 4, f"3 interpretive + 1 refute records expected, got {len(recs)}"
        assert [r["pass_id"] for r in recs].count("refute") == 1
        u = out["usage"]
        assert u["input_tokens"] == 3800 and u["output_tokens"] == 150
        assert abs(u["cost_usd"] - 0.017) < 1e-9 and u["duration_ms"] >= 0
        ar = AnalysisResult(**{**{k: v for k, v in res.items() if k != "findings"},
                               "findings": [Finding(**f) for f in res["findings"]]})
        sev = ar.by_severity()
        assert sev["MEDIUM"] == 0, "refuted findings must not count in by_severity"
    finally:
        engine_mod.analyze_once = orig_once
        refute_mod.chat_json = orig_chat
        if hasattr(two_of_three, "i"):
            del two_of_three.i
    print("✓ analyze(): engine manifest + samples + usage totals; refuted kept but not counted")


def test_reuse_path_skips_sampling():
    orig_once = engine_mod.analyze_once
    orig_refute = refute_mod.refute_findings

    def must_not_sample(*a, **k):
        raise AssertionError("interpretive engine called despite reused_samples")

    engine_mod.analyze_once = must_not_sample
    refute_mod.refute_findings = lambda bill_text, cands, model=None: ([], {"judged": 0, "refuted": 0})
    try:
        reused = [SampleRecord(
            pass_id="interpretive", sample_idx=i, temperature=0.4,
            raw_output="{}", parsed=[_f().to_dict()],
            returned_count=1, grounded_count=1, dropped_ungrounded=0,
            duration_ms=5, input_tokens=0, output_tokens=0, cost_usd=0.0,
        ).to_dict() for i in range(3)]
        out, _ = analyze(BILL, use_llm=True, n=3, k=2, temp=0.4, use_cache=False,
                         reused_samples=reused)
        llm_f = [f for f in out["result"]["findings"] if f["source"] == "llm"]
        assert len(llm_f) == 1 and llm_f[0]["runs_found"] == 3
        assert all(r["reused"] for r in out["samples"] if r["pass_id"] == "interpretive"), \
            "reused provenance must be honest in the stored samples"
    finally:
        engine_mod.analyze_once = orig_once
        refute_mod.refute_findings = orig_refute
    print("✓ reuse path: findings rebuilt from stored samples, zero interpretive calls")


if __name__ == "__main__":
    test_parallel_sampling_and_records()
    test_subthreshold_cluster_reported()
    test_analyze_output_shape_and_refute_wiring()
    test_reuse_path_skips_sampling()
    print("\nALL PIPELINE TESTS PASSED")
