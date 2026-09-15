"""Contract tests for splitting appended explanatory memos from bill text.

Run: python3 -m ingestion.tests.test_memo_split
"""

from __future__ import annotations

import os

from analysis.parser.structure import parse_bill
from ..riigikogu import MIN_TEXT_CHARS, split_off_memo


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _read(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return f.read()


def test_bill_984_memo_split_and_parses():
    text = _read("ingestion/tests/fixtures/bill_984_doc.txt")
    bill, memo = split_off_memo(text)
    assert memo is not None
    assert memo.lower().startswith(
        "hasartmängumaksu seaduse ja teiste seaduste muutmise seadus eelnõu seletuskiri"
    )
    assert "§ 3. Seaduse jõustumine" in bill
    assert "seletuskiri" not in bill.lower()

    parsed = parse_bill(bill)
    assert len(parsed.sections) == 3, parsed.summary()
    assert all("seletuskiri" not in s.title.lower() for s in parsed.sections)
    print("✓ bill 984 memo is split and the bill part parses as exactly 3 sections")


def test_bill_728_unchanged_same_object():
    text = _read("analysis/tests/fixtures/bill_728.txt")
    bill, memo = split_off_memo(text)
    assert bill is text
    assert memo is None
    print("✓ bill 728 is unchanged and returned as the same object")


def test_long_initiator_tail_unchanged_same_object():
    original = _read("analysis/tests/fixtures/bill_728.txt")
    tail = "\n" + ("Algatavad Sotsiaaldemokraatliku Erakonna fraktsioon, Jaak Aab\n" * 12)
    text = original + tail
    bill, memo = split_off_memo(text)
    assert len(tail) > 600
    assert bill is text
    assert memo is None
    print("✓ long initiator signature tails without a memo heading are untouched")


def test_seletuskiri_before_last_section_does_not_split():
    text = (
        "EELNÕU\n\n"
        "Seadus\n\n"
        "Seletuskiri\n\n"
        "§ 1. Esimene\n" + ("Sisu. " * 25) + "\n\n"
        "§ 2. Teine\n" + ("Sisu. " * 25)
    )
    bill, memo = split_off_memo(text)
    assert bill is text
    assert memo is None
    print("✓ seletuskiri before the last section heading does not split")


def test_split_guards():
    no_sections = "Seletuskiri\n" + ("Memo. " * 60)
    bill, memo = split_off_memo(no_sections)
    assert bill is no_sections
    assert memo is None

    short_bill = (
        "EELNÕU\n\n§ 1. Liiga lühike\nSisu.\n\n"
        "Riigikogu esimees\n\n"
        "Seletuskiri\n" + ("Memo. " * 60)
    )
    assert len(short_bill.split("Seletuskiri", 1)[0].rstrip()) < MIN_TEXT_CHARS
    bill2, memo2 = split_off_memo(short_bill)
    assert bill2 is short_bill
    assert memo2 is None
    print("✓ split guards keep no-section and under-200-character bill text untouched")


def test_idempotency_after_split():
    text = _read("ingestion/tests/fixtures/bill_984_doc.txt")
    bill, memo = split_off_memo(text)
    assert memo is not None
    bill2, memo2 = split_off_memo(bill)
    assert bill2 is bill
    assert memo2 is None
    print("✓ splitting an already-split bill part is idempotent")


if __name__ == "__main__":
    test_bill_984_memo_split_and_parses()
    test_bill_728_unchanged_same_object()
    test_long_initiator_tail_unchanged_same_object()
    test_seletuskiri_before_last_section_does_not_split()
    test_split_guards()
    test_idempotency_after_split()
    print("\nALL MEMO SPLIT TESTS PASSED")
