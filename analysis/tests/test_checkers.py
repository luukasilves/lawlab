"""Regression tests for the structure parser + deterministic checkers.

Run from repo root:  python3 -m analysis.tests.test_checkers
(Plain asserts so it runs without pytest installed; exits non-zero on failure.)
"""

from __future__ import annotations
import os

from analysis.parser.structure import parse_bill
from analysis.checkers.deterministic import run_deterministic

HERE = os.path.dirname(__file__)
FIX = os.path.join(HERE, "fixtures")


def _load(name):
    return open(os.path.join(FIX, name), encoding="utf-8").read()


def test_no_false_positives_on_real_bills():
    """Real, well-drafted bills must yield ZERO deterministic findings — proving
    we do NOT reproduce the old hallucinated '12%+80%' arithmetic error
    (Bill 728's real allocation is 8+12+80=100 with `millest` sub-splits)."""
    for num in ("728", "657", "741"):
        bill = parse_bill(_load(f"bill_{num}.txt"))
        findings = run_deterministic(bill)
        assert findings == [], (
            f"bill {num} should have 0 deterministic findings, got "
            f"{[(f.check_id, f.title) for f in findings]}"
        )
    print("✓ no false positives on bills 728/657/741")


def test_catches_planted_errors():
    bill = parse_bill(_load("synthetic_errors.txt"))
    findings = run_deterministic(bill)
    by_check = {}
    for f in findings:
        by_check.setdefault(f.check_id, []).append(f)

    # 1) section gap: §3 missing (sections are §1, §2, §4)
    gaps = [f for f in by_check.get("section_numbering", []) if "§ 3" in f.title]
    assert gaps, "expected a section-numbering gap finding for § 3"

    # 2) entry-into-force ref to non-existent paragraph § 9 (HIGH)
    eif = by_check.get("eif_refs", [])
    assert any("§ 9" in f.title and f.severity == "HIGH" for f in eif), \
        "expected HIGH finding: jõustumine references non-existent § 9"

    # 3) entry-into-force ref to non-existent point § 2 p 9 (HIGH)
    assert any("§ 2 p 9" in f.title and f.severity == "HIGH" for f in eif), \
        "expected HIGH finding: jõustumine references non-existent § 2 punkt 9"

    # 4) arithmetic: 50+30+18 = 98 ≠ 100 (MEDIUM)
    arith = by_check.get("percentage_alloc", [])
    assert any("98" in f.title for f in arith), \
        f"expected arithmetic finding for 98% allocation, got {[f.title for f in arith]}"

    # every finding must carry a verbatim evidence span that exists in the text
    for f in findings:
        assert bill.raw_text[f.char_start:f.char_end], "evidence span must be non-empty"
        assert f.honte_rule, "every finding must cite a HÕNTE rule"

    print(f"✓ caught all planted errors ({len(findings)} findings)")
    for f in findings:
        print(f"    [{f.severity}] {f.check_id}: {f.title}")


if __name__ == "__main__":
    test_no_false_positives_on_real_bills()
    test_catches_planted_errors()
    print("\nALL CHECKER TESTS PASSED")
