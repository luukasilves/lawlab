"""Offline tests for eval metrics (no API). python3 -m eval.test_metrics"""

from __future__ import annotations
from eval.metrics import score, score_by_category


def _find(category, location, provision="§3", **extra):
    finding = {"category": category, "location": location, "provision_id": provision}
    finding.update(extra)
    return finding


def test_recall_false_alarm_and_review_queue():
    labels = [
        {"category": "terminology", "provision_id": "§3", "location": "§ 3", "is_true_error": True},
        {"category": "arithmetic", "provision_id": "§2", "location": "§ 2", "is_true_error": False},  # guard
    ]
    findings = [
        _find("terminology", "§ 3 p 7"),            # recalls the true label
        _find("completeness", "§ 1 p 2", "§1"),     # unlabelled -> review queue
    ]
    s = score(findings, labels)
    assert s["recalled"] == 1 and s["true_errors"] == 1 and s["recall"] == 1.0
    assert s["false_alarms"] == 0 and s["guards_held"] == 1
    assert s["review_queue"] == 1
    print("✓ recall, guard-held, and review-queue accounting correct")


def test_false_alarm_detected():
    labels = [{"category": "arithmetic", "provision_id": "§2", "location": "§ 2", "is_true_error": False}]
    findings = [_find("arithmetic", "§ 2 lõige 10", "§2")]   # flags the guard => false alarm
    s = score(findings, labels)
    assert s["false_alarms"] == 1 and s["guards_held"] == 0
    print("✓ false alarm against a regression guard is detected")


def test_refuted_findings_are_excluded():
    labels = [
        {
            "category": "terminology",
            "provision_id": "§3",
            "location": "§ 3",
            "is_true_error": True,
            "note": "known terminology error",
        },
        {"category": "arithmetic", "provision_id": "§2", "location": "§ 2", "is_true_error": False},
    ]
    findings = [
        _find("terminology", "§ 3 p 7", skeptic_verdict="refuted"),
        _find("arithmetic", "§ 2 lõige 10", "§2", skeptic_verdict="refuted"),
        _find("completeness", "§ 9 p 1", "§9", skeptic_verdict="refuted"),
    ]
    s = score(findings, labels)
    assert s["recalled"] == 0 and s["true_errors"] == 1 and s["recall"] == 0.0
    assert s["false_alarms"] == 0 and s["guards_held"] == 1
    assert s["review_queue"] == 0

    by_category = score_by_category(findings, labels)
    assert by_category["terminology"]["recalled"] == 0
    assert by_category["arithmetic"]["false_alarms"] == 0
    assert "completeness" not in by_category
    print("✓ refuted findings are excluded from recall, guards, and review queue")


if __name__ == "__main__":
    test_recall_false_alarm_and_review_queue()
    test_false_alarm_detected()
    test_refuted_findings_are_excluded()
    print("\nALL METRICS TESTS PASSED")
