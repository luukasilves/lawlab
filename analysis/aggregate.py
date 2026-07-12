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
                         temperature: float, model: str = None,
                         sample_timeout: float = 900.0) -> Tuple[List[Finding], List[SampleRecord], Dict[str, Any]]:
    """Sample analyze_once N times concurrently and cluster stable findings."""
    from concurrent.futures import TimeoutError as FutureTimeout
    from .llm import engine

    from .llm.engine import LLMParseError
    from .llm.client import LLMError

    samples: List[List[Finding]] = [[] for _ in range(n)]
    records: List[SampleRecord] = [None] * n  # type: ignore[list-item]

    def _failed_record(idx: int, message: str, raw: str = "") -> SampleRecord:
        # A bad sample is recorded (raw output preserved for the transparency
        # panel) but must not nuke the batch — absorbing sample noise is the
        # entire point of self-consistency.
        return SampleRecord(
            pass_id="interpretive", sample_idx=idx, temperature=temperature,
            raw_output=raw, parsed=[],
            returned_count=0, grounded_count=0, dropped_ungrounded=0,
            error=message[:300],
        )

    def _one(idx: int):
        try:
            findings, record = engine.analyze_once(bill_text, structure_hint,
                                                   temperature=temperature, model=model)
            record.sample_idx = idx
            return findings, record
        except LLMParseError as exc:
            return None, _failed_record(idx, str(exc), getattr(exc, "raw", "") or "")

    # Every sample gets a hard wall-clock cap: requests' timeout is per-chunk
    # (reset on each received byte), so a slow-drip response can hang a socket
    # forever — observed live wedging 4 threads for 2+ hours. A timed-out
    # sample becomes a failed record; the usable<k floor still applies.
    # Sample 0 runs alone so its request WRITES the prompt cache; the rest run
    # in parallel as cache READS (all-parallel means nobody can hit the cache).
    pool = ThreadPoolExecutor(max_workers=min(n, 5))
    try:
        def _collect(idx, future):
            try:
                return future.result(timeout=sample_timeout)
            except FutureTimeout:
                return None, _failed_record(idx, f"sample timed out after {int(sample_timeout)}s")

        findings0, record0 = _collect(0, pool.submit(_one, 0))
        samples[0] = findings0 or []
        records[0] = record0
        futures = [(idx, pool.submit(_one, idx)) for idx in range(1, n)]
        for idx, future in futures:
            findings, record = _collect(idx, future)
            record.sample_idx = record.sample_idx if record.sample_idx >= 0 else idx
            samples[idx] = findings or []
            records[idx] = record
    finally:
        # wait=False: a timed-out thread on a wedged socket must not re-block
        # the batch here; the abandoned thread dies with its connection.
        pool.shutdown(wait=False, cancel_futures=True)

    usable_idx = [i for i, r in enumerate(records) if r.error is None]
    if len(usable_idx) < k:
        raise LLMError(
            f"only {len(usable_idx)}/{n} samples parseable — below agreement floor k={k}")
    usable_samples = [samples[i] for i in usable_idx]
    stable, summaries = cluster_with_summaries(usable_samples, n_runs=len(usable_idx), k=k)
    # cluster membership indices refer to positions within usable_samples —
    # map them back to the original sample_idx for the transparency panel.
    for c in summaries:
        c["members"] = [[usable_idx[p], f_idx] for p, f_idx in c["members"]]
    stats = {
        "samples": n, "min_agreement": k,
        "usable_samples": len(usable_idx),
        "failed_samples": n - len(usable_idx),
        "per_sample": [
            {
                "returned": r.returned_count,
                "grounded": r.grounded_count,
                "dropped": r.dropped_ungrounded,
                **({"error": r.error} if r.error else {}),
            }
            for r in records
        ],
        "raw_findings": sum(len(s) for s in usable_samples),
        "stable_findings": len(stable),
        "clusters": summaries,
    }
    return stable, records, stats
