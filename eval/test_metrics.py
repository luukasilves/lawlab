"""Offline tests for eval metrics (no API). python3 -m eval.test_metrics"""

from __future__ import annotations
from eval.metrics import score


def _find(category, location, provision="§3"):
    return {"category": category, "location": location, "provision_id": provision}


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


if __name__ == "__main__":
    test_recall_false_alarm_and_review_queue()
    test_false_alarm_detected()
    print("\nALL METRICS TESTS PASSED")
