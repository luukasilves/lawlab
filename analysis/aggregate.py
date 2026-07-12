"""Self-consistency aggregation — the fix for "every run is different".

We sample the interpretive pass N times, then keep only findings that recur in
at least k of the N samples. Confidence = (#samples found) / N. Severity is a
majority vote within the cluster. Deterministic findings bypass all of this at
confidence 1.0. The net effect: the UI shows only *stable* findings, each with
an honest confidence, instead of one volatile single-pass list.
"""

from __future__ import annotations
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from typing import List, Tuple, Dict, Any

from .models import Finding, SEVERITIES, SampleRecord

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


def _matches(f: Finding, cluster: List[Tuple[int, int, Finding]]) -> bool:
    """A finding joins a cluster if it matches every current member."""
    if not cluster:
        return False
    for _, _, member in cluster:
        if f.category != member.category:
            return False
        if not (
            _spans_overlap(f, member)
            or (f.provision_id and f.provision_id == member.provision_id and _title_similar(f, member))
        ):
            return False
    return True


def _build_clusters(samples: List[List[Finding]]) -> List[List[Tuple[int, int, Finding]]]:
    clusters: List[List[Tuple[int, int, Finding]]] = []
    for sample_idx, findings in enumerate(samples):
        for finding_idx, f in enumerate(findings):
            placed = False
            for cluster in clusters:
                if _matches(f, cluster):
                    cluster.append((sample_idx, finding_idx, f))
                    placed = True
                    break
            if not placed:
                clusters.append([(sample_idx, finding_idx, f)])
    return clusters


def _representative(cluster: List[Tuple[int, int, Finding]]) -> Tuple[Finding, str]:
    members = [f for _, _, f in cluster]
    # severity = majority vote, tie-break to the more severe
    sev = sorted(
        Counter(m.severity for m in members).items(),
        key=lambda kv: (kv[1], _SEV_RANK.get(kv[0], 0)), reverse=True,
    )[0][0]
    # representative: most severe, then longest reasoning (most informative)
    rep = sorted(members, key=lambda m: (_SEV_RANK.get(m.severity, 0), len(m.reasoning)),
                 reverse=True)[0]
    return rep, sev


def cluster_with_summaries(samples: List[List[Finding]], n_runs: int, k: int):
    clusters = _build_clusters(samples)

    stable: List[Finding] = []
    summaries = []
    for cluster in clusters:
        support = len({idx for idx, _, _ in cluster})        # distinct samples
        rep, sev = _representative(cluster)
        kept = support >= k
        summaries.append({
            "category": rep.category,
            "provision_id": rep.provision_id,
            "title": rep.title,
            "support": support,
            "n": n_runs,
            "kept": kept,
            "members": [[sample_idx, finding_idx] for sample_idx, finding_idx, _ in cluster],
        })
        if kept:
            rep.severity = sev
            rep.confidence = round(support / n_runs, 3)
            rep.runs_found = support
            rep.runs_total = n_runs
            stable.append(rep)

    stable.sort(key=lambda f: (_SEV_RANK.get(f.severity, 0), f.confidence), reverse=True)
    return stable, summaries


def cluster_llm_samples(samples: List[List[Finding]], n_runs: int, k: int) -> List[Finding]:
    """samples[i] = grounded findings from sample i. Returns stable findings."""
    stable, _summaries = cluster_with_summaries(samples, n_runs=n_runs, k=k)
    return stable


def run_self_consistency(bill_text: str, structure_hint: str, n: int, k: int,
                         temperature: float, model: str = None) -> Tuple[List[Finding], List[SampleRecord], Dict[str, Any]]:
    """Sample analyze_once N times concurrently and cluster stable findings."""
    from .llm import engine

    samples: List[List[Finding]] = [[] for _ in range(n)]
    records: List[SampleRecord] = [None] * n  # type: ignore[list-item]
    # Sample 0 runs alone so its request WRITES the prompt cache; the rest run
    # in parallel as cache READS (all-parallel means nobody can hit the cache).
    findings0, record0 = engine.analyze_once(bill_text, structure_hint,
                                             temperature=temperature, model=model)
    record0.sample_idx = 0
    samples[0] = findings0
    records[0] = record0
    if n > 1:
        with ThreadPoolExecutor(max_workers=min(n - 1, 5)) as pool:
            futures = [
                pool.submit(engine.analyze_once, bill_text, structure_hint,
                            temperature=temperature, model=model)
                for _ in range(n - 1)
            ]
            for sample_idx, future in enumerate(futures, start=1):
                findings, record = future.result()
                record.sample_idx = sample_idx
                samples[sample_idx] = findings
                records[sample_idx] = record
    stable, summaries = cluster_with_summaries(samples, n_runs=n, k=k)
    stats = {
        "samples": n, "min_agreement": k,
        "per_sample": [
            {
                "returned": r.returned_count,
                "grounded": r.grounded_count,
                "dropped": r.dropped_ungrounded,
            }
            for r in records
        ],
        "raw_findings": sum(len(s) for s in samples),
        "stable_findings": len(stable),
        "clusters": summaries,
    }
    return stable, records, stats
