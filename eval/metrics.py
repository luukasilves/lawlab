"""Evaluation metrics against a gold set.

The gold set is necessarily INCOMPLETE (we can't label every true error in every
bill), so naive precision would be misleading. We instead report:
  * recall on KNOWN true errors  — of the labelled true errors, how many found
  * false alarms on KNOWN non-errors — findings matching an is_true_error=false
    label (regression guards, e.g. the old hallucinated arithmetic case)
  * review queue — findings matching no label (candidate new errors for an
    expert to confirm; some become future gold labels via the feedback table)

A finding matches a label when categories agree AND the label's location/provision
is referenced by the finding.
"""

from __future__ import annotations
from typing import List, Dict, Any
from collections import defaultdict


def _matches(finding: Dict[str, Any], label: Dict[str, Any]) -> bool:
    if finding.get("category") != label.get("category"):
        return False
    loc = (finding.get("location") or "") + " " + (finding.get("provision_id") or "")
    return (label.get("provision_id", "") in loc) or (label.get("location", "") in loc)


def score(findings: List[Dict[str, Any]], labels: List[Dict[str, Any]]) -> Dict[str, Any]:
    true_labels = [l for l in labels if l.get("is_true_error") is True]
    false_labels = [l for l in labels if l.get("is_true_error") is False]

    recalled, missed = [], []
    for l in true_labels:
        if any(_matches(f, l) for f in findings):
            recalled.append(l)
        else:
            missed.append(l)

    false_alarms = [l for l in false_labels if any(_matches(f, l) for f in findings)]
    guards_held = [l for l in false_labels if l not in false_alarms]

    labelled = true_labels + false_labels
    review_queue = [f for f in findings if not any(_matches(f, l) for l in labelled)]

    recall = len(recalled) / len(true_labels) if true_labels else None
    return {
        "true_errors": len(true_labels),
        "recalled": len(recalled),
        "missed": [l["note"][:60] for l in missed],
        "recall": recall,
        "false_alarm_guards": len(false_labels),
        "false_alarms": len(false_alarms),
        "guards_held": len(guards_held),
        "review_queue": len(review_queue),
    }


def score_by_category(findings, labels) -> Dict[str, Dict[str, Any]]:
    cats = defaultdict(lambda: {"f": [], "l": []})
    for f in findings:
        cats[f.get("category")]["f"].append(f)
    for l in labels:
        cats[l.get("category")]["l"].append(l)
    return {c: score(d["f"], d["l"]) for c, d in cats.items()}
