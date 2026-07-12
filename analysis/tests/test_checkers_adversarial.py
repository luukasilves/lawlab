"""Adversarial regression suite for parser + deterministic checkers (Lane A).

Authored by the orchestrator BEFORE the fixes: every case below encodes the
expected behavior of the R1 Lane A work. This module is RED on the pre-fix
code by design (failing-then-passing discipline). Do not weaken assertions to
make it pass — fix the parser/checkers.

Covers:
  * _REF_RE multi-digit truncation («§ 41» read as «§ 4…1», «punkt 27» as «7»)
  * instruction-list tail dropped after a numbering gap (1,2,4,5 → 1,2)
  * duplicate top-level § headings (currently structurally undetectable)
  * quoted «”§ N. …”» replacement text adopted as a real section (latent bug:
    corrupts section boundaries; quote mask must apply to section matches)
  * duplicate instruction numbers (needs raw candidate numbers + registration
    of check_instruction_numbering)
  * superscript digits ¹²³ normalized length-preservingly at parse entry
  * percentage-sum check blind outside quoted blocks

Run: python3 -m analysis.tests.test_checkers_adversarial
"""

from __future__ import annotations

import os

from ..parser import structure
from ..parser.structure import parse_bill
from ..checkers.deterministic import run_deterministic

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _load(name: str) -> str:
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as fh:
        return fh.read()


def _by_check(findings, check_id):
    return [f for f in findings if f.check_id == check_id]


def test_multidigit_refs():
    """§ 41 (dangling) and § 11 p 27 (dangling) must be flagged; § 11 p 12 (valid) must not."""
    bill = parse_bill(_load("synthetic_multidigit.txt"))
    assert [s.pid for s in bill.sections] == [f"§{i}" for i in range(1, 13)], \
        f"section tree wrong: {[s.pid for s in bill.sections]}"

    findings = run_deterministic(bill)
    eif = _by_check(findings, "eif_refs")
    locs = sorted(f.location for f in eif)
    assert len(eif) == 2, f"expected 2 dangling-ref findings, got {len(eif)}: {locs}"
    assert all(f.severity == "HIGH" for f in eif)
    assert any("§ 41" in f.location for f in eif), f"missed dangling § 41: {locs}"
    assert any("§ 11 p 27" in f.location for f in eif), f"missed dangling § 11 p 27: {locs}"
    assert not any("p 12" in f.location for f in eif), f"valid § 11 p 12 false-flagged: {locs}"
    print("✓ multi-digit refs: dangling § 41 and § 11 p 27 caught; valid § 11 p 12 untouched")


def test_gap_duplicates_and_quoted_decoy():
    """Gap 3) survives the tail-drop; duplicate 3) and duplicate § 3 are flagged;
    the quoted ”§ 4. Vastutus” replacement text is NOT adopted as a section."""
    bill = parse_bill(_load("synthetic_gap_dup.txt"))
    pids = [s.pid for s in bill.sections]
    assert pids == ["§1", "§2", "§3", "§4"], f"section tree wrong (quoted decoy adopted?): {pids}"
    kinds = {s.pid: s.kind for s in bill.sections}
    assert kinds["§4"] == "entry_into_force", f"§4 must be the real jõustumine section, got {kinds['§4']}"

    s1 = bill.sections[0]
    assert [i.number for i in s1.instructions] == ["1", "2", "4", "5"], \
        f"§1 instruction tail dropped after gap: {[i.number for i in s1.instructions]}"

    findings = run_deterministic(bill)
    instr = _by_check(findings, "instruction_numbering")
    gaps = [f for f in instr if "Vahelejääv" in f.title]
    dups = [f for f in instr if "Korduv" in f.title]
    assert any(f.provision_id == "§1" and "3" in f.title for f in gaps), \
        f"missing instruction-gap finding for §1 p 3: {[f.title for f in instr]}"
    assert any(f.provision_id == "§2" and "3" in f.title and f.severity == "MEDIUM" for f in dups), \
        f"missing duplicate-instruction finding for §2 p 3: {[f.title for f in instr]}"

    sect = _by_check(findings, "section_numbering")
    dup_sections = [f for f in sect if "Korduv" in f.title and "§ 3" in f.title]
    assert dup_sections and dup_sections[0].severity == "MEDIUM", \
        f"missing duplicate-§ finding for § 3: {[f.title for f in sect]}"

    assert not _by_check(findings, "eif_refs"), "no eif findings expected in this fixture"
    assert not _by_check(findings, "percentage_alloc"), "no percentage findings expected"
    print("✓ gap/duplicates: instruction gap + duplicate 3) + duplicate § 3 flagged; quoted decoy excluded")


def test_superscript_normalization():
    """Superscript digits normalize 1:1 at parse entry; raw_text is untouched."""
    assert hasattr(structure, "normalize_superscripts"), \
        "parser must expose normalize_superscripts(text) (length-preserving)"
    norm = structure.normalize_superscripts("§ 10¹ ja lõike 5² punkt 3⁴")
    assert norm == "§ 101 ja lõike 52 punkt 34", f"bad normalization: {norm!r}"
    assert len(norm) == len("§ 10¹ ja lõike 5² punkt 3⁴"), "normalization must be length-preserving"

    src = _load("synthetic_superscript.txt")
    bill = parse_bill(src)
    assert bill.raw_text == src, "raw_text must remain the ORIGINAL text (offsets contract)"
    assert [s.pid for s in bill.sections] == ["§1", "§2"], \
        f"superscript fixture parsed wrong: {[s.pid for s in bill.sections]}"
    findings = run_deterministic(bill)
    assert findings == [], f"valid bill must yield zero findings, got {[f.title for f in findings]}"
    print("✓ superscripts: normalize_superscripts length-preserving; fixture parses clean, zero findings")


def test_percentage_outside_quotes():
    """Sibling percentage instructions OUTSIDE quoted blocks must be summed (45+30+23=98)."""
    bill = parse_bill(_load("synthetic_pct_unquoted.txt"))
    findings = run_deterministic(bill)
    pct = _by_check(findings, "percentage_alloc")
    assert len(pct) == 1, f"expected exactly 1 percentage finding, got {len(pct)}: {[f.title for f in findings]}"
    f = pct[0]
    assert f.severity == "MEDIUM" and "98" in f.title and f.provision_id == "§1", \
        f"wrong percentage finding: {f.severity} {f.title} {f.provision_id}"
    print("✓ percentages: unquoted sibling list 45+30+23=98% flagged")


def test_quoted_percentage_regression():
    """The original quoted-98% planted error must STILL be caught after the refactor."""
    bill = parse_bill(_load("synthetic_errors.txt"))
    findings = run_deterministic(bill)
    pct = _by_check(findings, "percentage_alloc")
    assert any("98" in f.title for f in pct), \
        f"quoted percentage regression: {[f.title for f in findings]}"
    print("✓ percentages: original quoted 98% case still caught")


if __name__ == "__main__":
    test_multidigit_refs()
    test_gap_duplicates_and_quoted_decoy()
    test_superscript_normalization()
    test_percentage_outside_quotes()
    test_quoted_percentage_regression()
    print("\nALL ADVERSARIAL CHECKER TESTS PASSED")
