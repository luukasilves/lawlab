"""Deterministic, fully-reproducible checks (confidence = 1.0).

These cover the *mechanical* error classes that need no judgement: structural
numbering, internal reference resolution in the entry-into-force section, and
arithmetic of percentage allocations. They are written to be HIGH PRECISION —
they stay silent unless an error is genuinely present. In particular the
percentage check is deliberately conservative so it does NOT reproduce the old
system's hallucinated "12% + 80% ≠ 100%" finding (the real text is 8+12+80=100,
with `millest` sub-splits that legitimately do not sum to 100).

Interpretive classes (terminology drift, logical contradiction, ambiguity,
completeness) are intentionally left to the LLM pass.
"""

from __future__ import annotations

import re
from typing import List

from ..parser.structure import parse_bill, Bill, Section, percentages_in
from ..models import Finding, HONTE_RULE

CHECKER_VERSION = "det-v1"

_SUBPOINT_RE = re.compile(r"(?m)^\s*(\d+)\)\s")
_PCT_FIRST_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:protsenti|protsent|%)")


def _quote(src: str, start: int, end: int, cap: int = 220) -> str:
    s = src[start:end].strip()
    s = re.sub(r"\s+", " ", s)
    return s[:cap] + ("…" if len(s) > cap else "")


def _finding(category, severity, title, description, pid, location,
             src, start, end, reasoning="", suggestion="", check_id=""):
    return Finding(
        source="deterministic", category=category, severity=severity,
        title=title, description=description, provision_id=pid, location=location,
        evidence_quote=_quote(src, start, end), char_start=start, char_end=end,
        reasoning=reasoning, suggestion=suggestion,
        honte_rule=HONTE_RULE.get(category), confidence=1.0, check_id=check_id,
    )


def check_section_numbering(bill: Bill) -> List[Finding]:
    # Only gap detection: the parser's monotonic section selector already drops
    # non-increasing duplicates, so a duplicate-§ branch would be unreachable.
    out: List[Finding] = []
    nums = [int(s.number) for s in bill.sections]
    seen = {int(s.number): s for s in bill.sections}
    if nums:
        for expected in range(min(nums), max(nums) + 1):
            if expected not in seen:
                anchor = bill.sections[0]
                out.append(_finding(
                    "structural_integrity", "LOW",
                    f"Vahelejääv paragrahvi number § {expected}",
                    f"Paragrahvide numeratsioonis puudub § {expected} "
                    f"(järjestus {min(nums)}–{max(nums)}).",
                    anchor.pid, f"§ {expected}", bill.raw_text, anchor.start, anchor.start + 40,
                    reasoning="Numeratsiooni lünk võib viidata kustunud või unustatud sättele.",
                    suggestion="Kontrolli, kas vahelejääv paragrahv on tahtlik.",
                    check_id="section_numbering",
                ))
    return out


def check_instruction_numbering(bill: Bill) -> List[Finding]:
    out: List[Finding] = []
    for s in bill.sections:
        instr_nums = [int(i.number) for i in s.instructions if i.number.isdigit()]
        if len(instr_nums) < 2:
            continue
        seen = {}
        for i in s.instructions:
            if i.number.isdigit():
                seen.setdefault(int(i.number), []).append(i)
        for n, items in seen.items():
            if len(items) > 1:
                it = items[1]
                out.append(_finding(
                    "structural_integrity", "MEDIUM",
                    f"Korduv muutmispunkti number {n}) {s.pid}",
                    f"Muutmiskäsu number {n}) esineb paragrahvis {s.pid} mitu korda.",
                    s.pid, f"{s.pid} p {n}", bill.raw_text, it.start, it.start + 60,
                    reasoning="Korduv punktinumber teeb muudatuste järjekorra ebaselgeks.",
                    suggestion="Nummerda muutmispunktid järjestikku.",
                    check_id="instruction_numbering",
                ))
        lo, hi = min(instr_nums), max(instr_nums)
        for expected in range(lo, hi + 1):
            if expected not in seen:
                out.append(_finding(
                    "structural_integrity", "LOW",
                    f"Vahelejääv muutmispunkt {expected}) {s.pid}",
                    f"Paragrahvis {s.pid} puudub muutmispunkt {expected}) "
                    f"(järjestus {lo}–{hi}).",
                    s.pid, f"{s.pid} p {expected}", bill.raw_text, s.start, s.start + 40,
                    reasoning="Punktinumbri lünk võib viidata väljajäänud muudatusele.",
                    suggestion="Kontrolli muutmispunktide täielikkust.",
                    check_id="instruction_numbering",
                ))
    return out


def check_entry_into_force_refs(bill: Bill) -> List[Finding]:
    """In the jõustumine section, 'käesoleva seaduse § N punkt M' must resolve to
    a provision that actually exists in THIS bill (internal, high precision)."""
    out: List[Finding] = []
    by_num = {s.number: s for s in bill.sections}
    for s in bill.sections:
        if s.kind != "entry_into_force":
            continue
        for instr in s.instructions:
            for ref in instr.references:
                if ref.scope != "self" or not ref.paragraph:
                    continue
                target = by_num.get(ref.paragraph)
                if target is None:
                    out.append(_finding(
                        "reference_integrity", "HIGH",
                        f"Jõustumissäte viitab olematule paragrahvile § {ref.paragraph}",
                        f"Jõustumissäte viitab paragrahvile § {ref.paragraph}, "
                        f"mida eelnõus ei ole.",
                        s.pid, f"{s.pid} → § {ref.paragraph}",
                        bill.raw_text, ref.start, ref.end,
                        reasoning="Jõustumine seotakse olematu sättega — säte ei jõustu õigesti.",
                        suggestion="Paranda viide kehtivale paragrahvile.",
                        check_id="eif_refs",
                    ))
                    continue
                if ref.point and target.kind == "amendment":
                    instr_nums = {i.number for i in target.instructions if i.number.isdigit()}
                    if ref.point not in instr_nums:
                        out.append(_finding(
                            "reference_integrity", "HIGH",
                            f"Jõustumissäte viitab olematule punktile "
                            f"§ {ref.paragraph} p {ref.point}",
                            f"Jõustumissäte viitab muutmispunktile {ref.point}) "
                            f"paragrahvis § {ref.paragraph}, mida seal ei ole.",
                            s.pid, f"{s.pid} → § {ref.paragraph} p {ref.point}",
                            bill.raw_text, ref.start, ref.end,
                            reasoning="Vale punktiviide jätab osa muudatusi jõustumistähtajata.",
                            suggestion="Kontrolli ja paranda punkti number.",
                            check_id="eif_refs",
                        ))
    return out


def check_percentage_allocations(bill: Bill) -> List[Finding]:
    """Flag a sibling list of percentage allocations that ALMOST sums to 100 but
    doesn't (likely a rounding/omission error). Conservative band (90,110)\\{100}
    so genuine partial splits (`millest …`) and rate lists are not false-flagged."""
    out: List[Finding] = []
    src = bill.raw_text
    for s in bill.sections:
        for instr in s.instructions:
            for q in instr.quote_spans:
                block = src[q.start:q.end]
                # split into sibling sub-points "N) ..."
                subs = list(_SUBPOINT_RE.finditer(block))
                if len(subs) < 2:
                    continue
                vals = []
                for j, sm in enumerate(subs):
                    seg_start = sm.end()
                    seg_end = subs[j + 1].start() if j + 1 < len(subs) else len(block)
                    pm = _PCT_FIRST_RE.search(block, seg_start, seg_end)
                    if pm:
                        vals.append(float(pm.group(1).replace(",", ".")))
                if len(vals) < 2:
                    continue
                total = round(sum(vals), 2)
                if 90.0 < total < 110.0 and abs(total - 100.0) > 0.05:
                    out.append(_finding(
                        "arithmetic", "MEDIUM",
                        f"Protsendijaotus ei summeeru 100-le ({total}%)",
                        f"Paralleelsete punktide protsendid summeeruvad {total}%, "
                        f"mitte 100%: {vals}.",
                        s.pid, s.pid, src, q.start, q.start + 200,
                        reasoning="Kui jaotus peaks olema ammendav, jääb osa vahenditest "
                                  "jaotamata või on protsent valesti arvutatud.",
                        suggestion="Kontrolli, kas protsendid peaksid kokku andma 100.",
                        check_id="percentage_alloc",
                    ))
    return out


# NOTE: check_instruction_numbering is intentionally NOT in the active set.
# The parser now keeps only the strictly-increasing top-level instruction run,
# so apparent "duplicate"/"gap" instruction numbers were nested quoted lists —
# false positives. Kept as a function for possible future use on structured XML.
_ALL = [
    check_section_numbering,
    check_entry_into_force_refs,
    check_percentage_allocations,
]


def run_deterministic(bill: Bill) -> List[Finding]:
    out: List[Finding] = []
    for fn in _ALL:
        out.extend(fn(bill))
    return out


if __name__ == "__main__":
    import sys, json
    txt = open(sys.argv[1], encoding="utf-8").read()
    bill = parse_bill(txt)
    findings = run_deterministic(bill)
    print(f"{len(findings)} deterministic finding(s):\n")
    for f in findings:
        print(f"  [{f.severity}] {f.category} — {f.title}")
        print(f"     loc: {f.location} | {f.honte_rule}")
        print(f"     evidence: {f.evidence_quote[:100]}")
    print(json.dumps([f.to_dict() for f in findings], ensure_ascii=False, indent=2))
