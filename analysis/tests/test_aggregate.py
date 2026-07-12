"""Offline tests for self-consistency clustering (no API needed).

Proves the core fix for non-determinism: a finding that recurs across samples is
kept with a confidence = agreement rate, while a one-off (flaky) finding is
dropped. Run: python3 -m analysis.tests.test_aggregate
"""

from __future__ import annotations
from analysis.models import Finding
from analysis.aggregate import cluster_llm_samples


def _f(category, severity, start, end, title):
    return Finding(source="llm", category=category, severity=severity, title=title,
                   description="", provision_id="§3", location="§ 3",
                   evidence_quote="x" * (end - start), char_start=start, char_end=end,
                   check_id="llm")


def test_stable_kept_flaky_dropped():
    # osavusmängu scope-drift finding recurs in 4 of 5 samples (spans overlap,
    # severities differ → majority vote). A flaky finding appears in only 1.
    samples = [
        [_f("terminology", "HIGH",   8200, 8260, "Termini ulatuse kõikumine")],
        [_f("terminology", "HIGH",   8205, 8255, "Erinev täpsusaste summa puhul")],
        [_f("terminology", "MEDIUM", 8200, 8260, "Termini ebakõla"),
         _f("completeness", "LOW",   5000, 5050, "Lünk loetelus")],          # flaky
        [_f("terminology", "HIGH",   8190, 8270, "Ulatuse täpsustuse kõikumine")],
        [],                                                                   # missed it
    ]
    stable = cluster_llm_samples(samples, n_runs=5, k=3)
    assert len(stable) == 1, f"expected 1 stable finding, got {len(stable)}"
    f = stable[0]
    assert f.category == "terminology"
    assert f.severity == "HIGH", f"majority vote should be HIGH, got {f.severity}"
    assert f.runs_found == 4 and f.runs_total == 5
    assert abs(f.confidence - 0.8) < 1e-6, f"confidence should be 0.8, got {f.confidence}"
    print(f"✓ stable finding kept (conf {f.confidence}, {f.runs_found}/{f.runs_total}); flaky dropped")


def test_different_categories_same_span_do_not_merge():
    samples = [
        [_f("terminology", "HIGH", 100, 200, "A")],
        [_f("logical_contradiction", "HIGH", 100, 200, "B")],
        [_f("terminology", "HIGH", 100, 200, "A")],
        [_f("logical_contradiction", "HIGH", 100, 200, "B")],
        [_f("terminology", "HIGH", 100, 200, "A")],
    ]
    stable = cluster_llm_samples(samples, n_runs=5, k=3)
    cats = sorted(f.category for f in stable)
    # terminology appears 3x (kept); logical_contradiction 2x (< k, dropped)
    assert cats == ["terminology"], f"unexpected: {cats}"
    print("✓ distinct categories at same span are not merged")


if __name__ == "__main__":
    test_stable_kept_flaky_dropped()
    test_different_categories_same_span_do_not_merge()
    print("\nALL AGGREGATION TESTS PASSED")
