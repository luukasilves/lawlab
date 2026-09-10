"""Regression tests for parser handling of Estonian curly quote conventions.

The structure parser must mask section-like headings inside quoted replacement
text without letting Estonian ”...“ drafting quotes hide later top-level bill
sections or rewrite the verbatim source text.
"""

from __future__ import annotations

import os

from analysis.parser.structure import parse_bill


HERE = os.path.dirname(__file__)
ROOT = os.path.abspath(os.path.join(HERE, os.pardir, os.pardir))


def _pids(text):
    return [section.pid for section in parse_bill(text).sections]


def test_estonian_replacement_quotes_do_not_hide_later_sections():
    src = """EELNÕU

Näidisseaduse muutmise seadus

§ 1. Esimese seaduse muutmine

Seaduse paragrahv 4 muudetakse ja sõnastatakse järgmiselt:

”Asendustekst on siin.“

§ 2. Teise seaduse muutmine

Paragrahv 5 tunnistatakse kehtetuks.

§ 3. Seaduse jõustumine

Seadus jõustub järgmisel päeval pärast avaldamist.
"""
    original = src
    bill = parse_bill(src)

    assert bill.raw_text == original, "parse_bill must not rewrite source text containing ”...“ quotes"
    assert [section.pid for section in bill.sections] == ["§1", "§2", "§3"], (
        f"Estonian ”...“ quote must close before later sections, got "
        f"{[section.pid for section in bill.sections]}"
    )
    print("✓ Estonian replacement quotes do not hide later sections")


def test_unclosed_estonian_quote_does_not_swallow_later_sections():
    src = """EELNÕU

Näidisseaduse muutmise seadus

§ 1. Esimese seaduse muutmine

Tekstis on üksik avav jutumärk ” ilma sulgeva märgita.

§ 2. Teise seaduse muutmine

Paragrahv 5 tunnistatakse kehtetuks.

§ 3. Seaduse jõustumine

Seadus jõustub järgmisel päeval pärast avaldamist.
"""
    assert _pids(src) == ["§1", "§2", "§3"], (
        f"single unclosed ” must not swallow following sections, got {_pids(src)}"
    )
    print("✓ unclosed Estonian quote does not swallow later sections")


def test_existing_quote_conventions_still_mask_contents():
    cases = {
        "„...“": "„§ 12. Siseteksti pealkiri\nSisetekst.“",
        "„...”": "„§ 12. Siseteksti pealkiri\nSisetekst.”",
        "”...”": "”§ 12. Siseteksti pealkiri\nSisetekst.”",
    }
    for name, quoted in cases.items():
        src = f"""EELNÕU

Näidisseaduse muutmise seadus

§ 1. Esimese seaduse muutmine

Seaduse tekst asendatakse järgmise tekstiga:

{quoted}

§ 2. Seaduse jõustumine

Seadus jõustub järgmisel päeval pärast avaldamist.
"""
        assert _pids(src) == ["§1", "§2"], (
            f"{name} quote convention must mask inner § 12 heading, got {_pids(src)}"
        )
    print("✓ existing quote conventions still mask contents")


def test_quoted_replacement_section_heading_is_not_top_level():
    src = """EELNÕU

Näidisseaduse muutmise seadus

§ 1. Esimese seaduse muutmine

Seadust täiendatakse paragrahviga 12 järgmises sõnastuses:

”§ 12. Registri pidamine

Registripidaja peab andmeid korrektselt.“

§ 2. Seaduse jõustumine

Seadus jõustub järgmisel päeval pärast avaldamist.
"""
    assert _pids(src) == ["§1", "§2"], (
        f"quoted replacement § 12 must not become top-level bill section, got {_pids(src)}"
    )
    print("✓ quoted replacement heading is not top-level")


def test_bill_984_doc_fixture_stops_before_explanatory_memo():
    path = os.path.join(ROOT, "ingestion", "tests", "fixtures", "bill_984_doc.txt")
    lines = open(path, encoding="utf-8").read().splitlines(keepends=True)
    stop = next(
        i for i, line in enumerate(lines)
        if "seletuskiri" in line.lower()
    )
    bill = parse_bill("".join(lines[:stop]))

    assert [section.pid for section in bill.sections] == ["§1", "§2", "§3"], (
        f"bill_984_doc pre-memo text must parse exactly §1-§3, got "
        f"{[section.pid for section in bill.sections]}"
    )
    assert all("seletuskiri" not in section.title.lower() for section in bill.sections), (
        f"bill_984_doc section titles must exclude seletuskiri, got "
        f"{[section.title for section in bill.sections]}"
    )
    print("✓ bill_984_doc fixture parses exactly the bill sections")


if __name__ == "__main__":
    test_estonian_replacement_quotes_do_not_hide_later_sections()
    test_unclosed_estonian_quote_does_not_swallow_later_sections()
    test_existing_quote_conventions_still_mask_contents()
    test_quoted_replacement_section_heading_is_not_top_level()
    test_bill_984_doc_fixture_stops_before_explanatory_memo()
    print("\nALL PARSER QUOTE TESTS PASSED")
