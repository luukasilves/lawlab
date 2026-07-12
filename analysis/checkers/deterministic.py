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

from dataclasses import dataclass
import re
from typing import Callable, List

from ..parser.structure import parse_bill, Bill, Section, percentages_in
from ..models import Finding, HONTE_RULE

_SUBPOINT_RE = re.compile(r"(?m)^\s*(\d+)\)\s")
_PCT_FIRST_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:protsenti|protsent|%)")


@dataclass(frozen=True)
class CheckSpec:
    id: str
    version: int
    category: str
    name_et: str
    name_en: str
    description_et: str
    description_en: str
    fn: Callable[[Bill], List[Finding]]
    enabled: bool = True


def _point_numbers(point: str) -> List[str]:
    out: List[str] = []
    for part in re.split(r"\s*,\s*", point):
        bounds = re.split(r"\s*[–—]\s*", part)
        if len(bounds) == 2 and all(b.isdigit() for b in bounds):
            lo, hi = int(bounds[0]), int(bounds[1])
            if lo <= hi:
                out.extend(str(n) for n in range(lo, hi + 1))
                continue
        if part.isdigit():
            out.append(part)
    return out or [point]


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
    out: List[Finding] = []

    raw_seen = {}
    for occ in getattr(bill, "raw_section_matches", []):
        if occ.number.isdigit():
            raw_seen.setdefault(int(occ.number), []).append(occ)
    for n, items in raw_seen.items():
        for occ in items[1:]:
            out.append(_finding(
                "structural_integrity", "MEDIUM",
                f"Korduv paragrahvi number § {n}",
                f"Paragrahvi number § {n} esineb eelnõus mitu korda.",
                f"§{n}", f"§ {n}", bill.raw_text, occ.start, min(occ.end, len(bill.raw_text)),
                reasoning="Korduv paragrahvinumber teeb sätete järjekorra ja viited ebaselgeks.",
                suggestion="Nummerda paragrahvid üheselt.",
                check_id="section_numbering",
            ))

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
        # Amendment-bill concept only: substantive sections legitimately restart
        # their 1) 2) 3) sub-lists under every lõige, which would read as
        # duplicates here (live FP on bill 652, a substantive law).
        if s.kind != "amendment":
            continue
        raw_seen = {}
        for occ in getattr(s, "raw_instruction_numbers", []):
            if occ.number.isdigit():
                raw_seen.setdefault(int(occ.number), []).append(occ)
        for n, items in raw_seen.items():
            for occ in items[1:]:
                out.append(_finding(
                    "structural_integrity", "MEDIUM",
                    f"Korduv muutmispunkti number {n}) {s.pid}",
                    f"Muutmiskäsu number {n}) esineb paragrahvis {s.pid} mitu korda.",
                    s.pid, f"{s.pid} p {n}", bill.raw_text, occ.start,
                    min(occ.start + 60, len(bill.raw_text)),
                    reasoning="Korduv punktinumber teeb muudatuste järjekorra ebaselgeks.",
                    suggestion="Nummerda muutmispunktid järjestikku.",
                    check_id="instruction_numbering",
                ))

        instr_nums = [int(i.number) for i in s.instructions if i.number.isdigit()]
        if len(instr_nums) < 2:
            continue
        seen = {}
        for i in s.instructions:
            if i.number.isdigit():
                seen.setdefault(int(i.number), []).append(i)
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
                    for point in _point_numbers(ref.point):
                        if point not in instr_nums:
                            out.append(_finding(
                                "reference_integrity", "HIGH",
                                f"Jõustumissäte viitab olematule punktile "
                                f"§ {ref.paragraph} p {point}",
                                f"Jõustumissäte viitab muutmispunktile {point}) "
                                f"paragrahvis § {ref.paragraph}, mida seal ei ole.",
                                s.pid, f"{s.pid} → § {ref.paragraph} p {point}",
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

    def scan_block(s: Section, block: str, anchor: int) -> None:
        # split into sibling sub-points "N) ..."
        subs = list(_SUBPOINT_RE.finditer(block))
        if len(subs) < 2:
            return
        vals = []
        for j, sm in enumerate(subs):
            seg_start = sm.end()
            seg_end = subs[j + 1].start() if j + 1 < len(subs) else len(block)
            pm = _PCT_FIRST_RE.search(block, seg_start, seg_end)
            if pm:
                vals.append(float(pm.group(1).replace(",", ".")))
        if len(vals) < 2:
            return
        total = round(sum(vals), 2)
        if 90.0 < total < 110.0 and abs(total - 100.0) > 0.05:
            out.append(_finding(
                "arithmetic", "MEDIUM",
                f"Protsendijaotus ei summeeru 100-le ({total}%)",
                f"Paralleelsete punktide protsendid summeeruvad {total}%, "
                f"mitte 100%: {vals}.",
                s.pid, s.pid, src, anchor, min(anchor + 200, len(src)),
                reasoning="Kui jaotus peaks olema ammendav, jääb osa vahenditest "
                          "jaotamata või on protsent valesti arvutatud.",
                suggestion="Kontrolli, kas protsendid peaksid kokku andma 100.",
                check_id="percentage_alloc",
            ))

    for s in bill.sections:
        quote_spans = [q for instr in s.instructions for q in instr.quote_spans]
        if quote_spans:
            for q in quote_spans:
                scan_block(s, src[q.start:q.end], q.start)
            continue

        body_start = src.find("\n", s.start, s.end)
        body_start = body_start + 1 if body_start != -1 else s.end
        scan_block(s, src[body_start:s.end], body_start)
    return out


CHECKS = [
    CheckSpec(
        "section_numbering", 1, "structural_integrity",
        "Paragrahvide numeratsioon", "Section numbering",
        "Tuvastab lüngad ja kordused paragrahvide numeratsioonis.",
        "Detects gaps and duplicate numbers in top-level section numbering.",
        check_section_numbering,
    ),
    CheckSpec(
        "instruction_numbering", 1, "structural_integrity",
        "Muutmispunktide numeratsioon", "Amendment instruction numbering",
        "Tuvastab lüngad ja kordused muutmiskäskude numeratsioonis.",
        "Detects gaps and duplicate numbers in amendment instruction lists.",
        check_instruction_numbering,
    ),
    CheckSpec(
        "eif_refs", 1, "reference_integrity",
        "Jõustumissätte viited", "Entry-into-force references",
        "Kontrollib, et jõustumissätte viited osutavad eelnõus olemasolevatele sätetele.",
        "Verifies that entry-into-force references resolve to provisions that exist in the bill.",
        check_entry_into_force_refs,
    ),
    CheckSpec(
        "percentage_alloc", 1, "arithmetic",
        "Protsendijaotuste aritmeetika", "Percentage allocation arithmetic",
        "Kontrollib, et paralleelsete punktide protsendid summeeruvad 100-le.",
        "Checks that sibling percentage allocations sum to 100.",
        check_percentage_allocations,
    ),
]


def enabled_checks() -> List[CheckSpec]:
    return [c for c in CHECKS if c.enabled]


def checker_version_label() -> str:
    return ",".join(f"{c.id}@{c.version}" for c in enabled_checks())


def run_deterministic(bill: Bill) -> List[Finding]:
    out: List[Finding] = []
    for spec in enabled_checks():
        findings = spec.fn(bill)
        for f in findings:
            f.check_id = spec.id
        out.extend(findings)
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
