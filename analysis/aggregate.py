"""Self-consistency aggregation — the fix for "every run is different".

We sample the interpretive pass N times, then keep only findings that recur in
at least k of the N samples. Confidence = (#samples found) / N. Severity is a
majority vote within the cluster. Deterministic findings bypass all of this at
confidence 1.0. The net effect: the UI shows only *stable* findings, each with
an honest confidence, instead of one volatile single-pass list.
"""

from __future__ import annotations
from collections import Counter
from typing import List, Tuple, Dict, Any

from .models import Finding, SEVERITIES

_SEV_RANK = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}


def _spans_overlap(a: Finding, b: Finding) -> bool:
    return max(a.char_start, b.char_start) < min(a.char_end, b.char_end)


def _title_tokens(s: str):
    return set(t for t in s.lower().split() if len(t) > 3)


def _title_similar(a: Finding, b: Finding) -> bool:
    ta, tb = _title_tokens(a.title), _title_tokens(b.title)
    if not ta or not tb:
        return False
    inter = len(ta & tb)
    return inter / min(len(ta), len(tb)) >= 0.5


def _matches(f: Finding, cluster: List[Tuple[int, Finding]]) -> bool:
    """A finding joins a cluster if it matches every current member."""
    if not cluster:
        return False
    for _, member in cluster:
        if f.category != member.category:
            return False
        if not (
            _spans_overlap(f, member)
            or (f.provision_id and f.provision_id == member.provision_id and _title_similar(f, member))
        ):
            return False
    return True


def cluster_llm_samples(samples: List[List[Finding]], n_runs: int, k: int) -> List[Finding]:
    """samples[i] = grounded findings from sample i. Returns stable findings."""
    clusters: List[List[Tuple[int, Finding]]] = []
    for sample_idx, findings in enumerate(samples):
        for f in findings:
            placed = False
            for cluster in clusters:
                if _matches(f, cluster):
                    cluster.append((sample_idx, f))
                    placed = True
                    break
            if not placed:
                clusters.append([(sample_idx, f)])

    stable: List[Finding] = []
    for cluster in clusters:
        support = len({idx for idx, _ in cluster})        # distinct samples
        if support < k:
            continue
        members = [f for _, f in cluster]
        # severity = majority vote, tie-break to the more severe
        sev = sorted(
            Counter(m.severity for m in members).items(),
            key=lambda kv: (kv[1], _SEV_RANK.get(kv[0], 0)), reverse=True,
        )[0][0]
        # representative: most severe, then longest reasoning (most informative)
        rep = sorted(members, key=lambda m: (_SEV_RANK.get(m.severity, 0), len(m.reasoning)),
                     reverse=True)[0]
        rep.severity = sev
        rep.confidence = round(support / n_runs, 3)
        rep.runs_found = support
        rep.runs_total = n_runs
        stable.append(rep)

    stable.sort(key=lambda f: (_SEV_RANK.get(f.severity, 0), f.confidence), reverse=True)
    return stable


def run_self_consistency(bill_text: str, structure_hint: str, n: int, k: int,
                         temperature: float, model: str = None) -> Tuple[List[Finding], Dict[str, Any]]:
    """Sample analyze_once N times and cluster. (Imports engine lazily so the
    aggregation logic stays unit-testable without any API access.)"""
    from .llm.engine import analyze_once
    samples: List[List[Finding]] = []
    per_sample_stats = []
    for i in range(n):
        findings, stats = analyze_once(bill_text, structure_hint, temperature=temperature, model=model)
        samples.append(findings)
        per_sample_stats.append(stats)
    stable = cluster_llm_samples(samples, n_runs=n, k=k)
    return stable, {
        "samples": n, "min_agreement": k,
        "per_sample": per_sample_stats,
        "raw_findings": sum(len(s) for s in samples),
        "stable_findings": len(stable),
    }
