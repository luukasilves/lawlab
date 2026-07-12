"""Adversarial regression suite for self-consistency clustering (Lane B).

Authored by the orchestrator BEFORE the fix. RED on pre-fix code by design.

The bug: _matches() is single-linkage — a finding joins a cluster if it matches
ANY one member, so A~B and B~C chain-merge into one cluster even when A and C
are unrelated, inflating support/confidence (the "3 distinct issues published
as one 3/3=100% finding" failure).

The fix contract: a finding may join a cluster only if it matches ALL current
members (complete linkage), keeping distinct-sample support counting and the
category + (span-overlap OR same-provision+similar-title) match predicate.

Run: python3 -m analysis.tests.test_aggregate_adversarial
"""

from __future__ import annotations

from ..aggregate import cluster_llm_samples
from ..models import Finding


def mk(start, end, title, cat="terminology", sev="MEDIUM", pid="§1"):
    return Finding(
        source="llm", category=cat, severity=sev, title=title,
        description="", provision_id=pid, location=pid,
        evidence_quote="x" * (end - start), char_start=start, char_end=end,
        reasoning="r", confidence=1.0, check_id="llm",
    )


def test_chain_merge_killed():
    """A(0-10) ~ B(8-20) ~ C(18-30): a chain, not one issue. With complete
    linkage no cluster reaches k=3, so NOTHING is published — the pre-fix code
    published one bogus 3/3=100% finding."""
    samples = [
        [mk(0, 10, "esimene viga siin")],
        [mk(8, 20, "teine probleem tekstis")],
        [mk(18, 30, "kolmas küsimus lõigus")],
    ]
    stable = cluster_llm_samples(samples, n_runs=3, k=3)
    assert stable == [], (
        f"chain-merge inflation: published {[(f.title, f.runs_found, f.runs_total) for f in stable]}"
    )
    print("✓ chain A~B~C no longer merges into a fake 3/3 consensus")


def test_true_consensus_survives():
    """The same finding (same span) in 5/5 samples must still publish at 5/5."""
    samples = [[mk(5, 25, "osavusmängu mõiste nihkub definitsioonist")] for _ in range(5)]
    stable = cluster_llm_samples(samples, n_runs=5, k=3)
    assert len(stable) == 1, f"true consensus lost: {len(stable)} findings"
    f = stable[0]
    assert (f.runs_found, f.runs_total) == (5, 5) and f.confidence == 1.0, \
        f"support wrong: {f.runs_found}/{f.runs_total} conf={f.confidence}"
    print("✓ identical 5/5 consensus survives at confidence 1.0")


def test_all_pairs_overlap_still_merges():
    """Slightly shifted spans of the SAME issue (every pair overlaps) must merge:
    the fix must not require identical spans."""
    samples = [
        [mk(0, 20, "sama viga veidi nihkes")],
        [mk(5, 25, "sama viga veidi nihkes")],
        [mk(10, 22, "sama viga veidi nihkes")],
    ]
    stable = cluster_llm_samples(samples, n_runs=3, k=3)
    assert len(stable) == 1 and stable[0].runs_found == 3, (
        f"over-strict fix: shifted-span consensus lost "
        f"({[(f.title, f.runs_found) for f in stable]})"
    )
    print("✓ all-pairs-overlapping shifted spans still cluster (3/3)")


def test_order_invariance():
    """The published SET must not depend on sample order (complete linkage is
    order-stable for these inputs; single-linkage chains are not)."""
    a = mk(0, 10, "esimene viga siin")
    b = mk(8, 20, "teine probleem tekstis")
    c = mk(18, 30, "kolmas küsimus lõigus")
    for order in ([[a], [b], [c]], [[b], [c], [a]], [[c], [a], [b]]):
        # fresh copies each round: the aggregator mutates representatives
        fresh = [[mk(x[0].char_start, x[0].char_end, x[0].title)] for x in order]
        stable = cluster_llm_samples(fresh, n_runs=3, k=3)
        assert stable == [], f"order-dependent publication for order {[x[0].title for x in order]}"
    print("✓ chain suppression is order-invariant")


def test_provision_title_path_intact():
    """Disjoint spans, same provision + similar titles across samples must still
    cluster (the second arm of the match predicate)."""
    t = "terminite ebajärjekindel kasutamine osavusmängu määratluses"
    samples = [
        [mk(0, 12, t, pid="§2")],
        [mk(50, 62, t + " tekstis", pid="§2")],
        [mk(100, 112, t, pid="§2")],
    ]
    stable = cluster_llm_samples(samples, n_runs=3, k=3)
    assert len(stable) == 1 and stable[0].runs_found == 3, (
        f"provision+title clustering broken: {[(f.title, f.runs_found) for f in stable]}"
    )
    print("✓ same-provision + similar-title clustering intact")


if __name__ == "__main__":
    test_chain_merge_killed()
    test_true_consensus_survives()
    test_all_pairs_overlap_still_merges()
    test_order_invariance()
    test_provision_title_path_intact()
    print("\nALL ADVERSARIAL AGGREGATE TESTS PASSED")
