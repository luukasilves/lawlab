"""
Structure parser for Estonian draft bills (seaduseelnõu).

Turns flat extracted text into a provision tree with stable IDs and character
offsets, so that (a) deterministic checkers can reason over structure and
(b) every finding can be grounded to a verbatim span in the source text.

Estonian bills come in two broad shapes:
  * amendment bills (muutmise seadus) — each top-level § amends a *different*
    law via a numbered list of amendment instructions ("1) paragrahvi 2 ...").
    Most references point into the *target* law, not the bill.
  * substantive bills — the §s are the actual new law.

Design notes / known limits (v1, internal-only):
  * DOCX extraction flattens superscripts, so "§ 101" is really "§ 10¹" and
    "lõikega 51" is "lõige 5¹". We therefore treat reference *numbers* as opaque
    tokens and never do arithmetic on them. Full target-law resolution is a
    Phase-2 concern (Riigi Teataja RAG).
  * Estonian uses the same character (”, U+201D) to open and close quotes, and
    nests them, so we do not try to balance quotes. Top-level §s are detected by
    a near-sequential numbering heuristic instead, which is robust to inserted
    paragraphs whose numbers (10¹→"101") fall outside the sequence.

Python 3.9 compatible (no match statements, no PEP 604 unions at runtime).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any


# ── data model ────────────────────────────────────────────────────────────

@dataclass
class Span:
    start: int
    end: int

    def text(self, src: str) -> str:
        return src[self.start:self.end]


@dataclass
class NumberedMatch:
    number: str
    start: int
    end: int


@dataclass
class Reference:
    """A reference like 'paragrahvi 2 lõike 5 punktis 31' or '§ 1 lõike 1 punktis 5'."""
    raw: str
    paragraph: Optional[str]
    subsection: Optional[str]   # lõige
    point: Optional[str]        # punkt
    scope: str                  # "self" | "external" | "unknown"
    start: int
    end: int


@dataclass
class Instruction:
    """A numbered amendment instruction inside a § ('1) paragrahvi 2 ... ')."""
    number: str
    start: int
    end: int
    references: List[Reference] = field(default_factory=list)
    quote_spans: List[Span] = field(default_factory=list)


@dataclass
class Section:
    """A top-level bill provision (§ N)."""
    number: str                 # as printed, e.g. "1"
    pid: str                    # stable id, e.g. "§1"
    title: str
    kind: str                   # "amendment" | "entry_into_force" | "substantive"
    target_law: Optional[str]   # inferred name of the amended law, if any
    start: int
    end: int
    instructions: List[Instruction] = field(default_factory=list)
    raw_instruction_numbers: List[NumberedMatch] = field(default_factory=list)


@dataclass
class Bill:
    title: str
    raw_text: str
    sections: List[Section] = field(default_factory=list)
    raw_section_matches: List[NumberedMatch] = field(default_factory=list)

    def summary(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "chars": len(self.raw_text),
            "sections": [
                {
                    "pid": s.pid,
                    "kind": s.kind,
                    "title": s.title,
                    "target_law": s.target_law,
                    "instructions": len(s.instructions),
                    "references": sum(len(i.references) for i in s.instructions),
                }
                for s in self.sections
            ],
        }


# ── regexes ───────────────────────────────────────────────────────────────

# Top-level section heading: "§ 1. Hasartmänguseaduse muutmine"
_SECTION_RE = re.compile(r"(?m)^§\s*(\d+)\.\s+(.+?)\s*$")

# Amendment instruction at line start: "1) paragrahvi 2 ..."  /  "12) ..."
_INSTR_RE = re.compile(r"(?m)^(\d+)\)\s")

# Reference forms. We capture the leading paragraph token, then optionally a
# lõige and a punkt with their (opaque) numbers. Handles both "paragrahvi N"
# and "§ N" / "§-ga N" / "§-s N" lead-ins, in any Estonian case ending.
_PARA_LEAD = r"(?:§\s*(?:-?\s*[a-zõäöüšž]+)?\s*|paragrahv\w*\s+)(\d+)"
_LOIGE = r"(?:\s+lõi\w+\s+(\d+))?"
_PUNKT = r"(?:\s+punkt\w*\s+(\d+(?:\s*[–—,]\s*\d+)*))?"
_REF_RE = re.compile(_PARA_LEAD + _LOIGE + _PUNKT)

# A percentage token: "12 protsenti", "4,5 protsenti", "60,6 protsenti"
_PCT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:protsenti|protsent|%)")

# Quoted normative block (best effort; non-greedy between curly double quotes)
_QUOTE_RE = re.compile(r"(?:”.*?”|„.*?[“”])", re.DOTALL)

_SUPERSCRIPT_TRANSLATION = str.maketrans({
    "⁰": "0",
    "¹": "1",
    "²": "2",
    "³": "3",
    "⁴": "4",
    "⁵": "5",
    "⁶": "6",
    "⁷": "7",
    "⁸": "8",
    "⁹": "9",
})


def normalize_superscripts(text: str) -> str:
    """Normalize Unicode superscript digits without changing text length."""
    return text.translate(_SUPERSCRIPT_TRANSLATION)


def _classify(title: str) -> str:
    t = title.lower()
    if "jõustumine" in t or "jõustub" in t:
        return "entry_into_force"
    if "muutmine" in t or "muutmise" in t:
        return "amendment"
    return "substantive"


def _target_law(title: str) -> Optional[str]:
    """'Hasartmänguseaduse muutmine' -> 'Hasartmänguseadus' (best effort)."""
    m = re.match(r"(.+?)\s+muutmin", title.strip(), re.IGNORECASE)
    if not m:
        return None
    name = m.group(1).strip()
    # crude genitive→nominative: 'seaduse' -> 'seadus'
    name = re.sub(r"seaduse$", "seadus", name)
    return name


# ── reference extraction ────────────────────────────────────────────────────

def _extract_references(src: str, start: int, end: int, self_law: Optional[str]) -> List[Reference]:
    """Pull references out of [start,end). Scope is 'self' when the reference is
    explicitly to 'käesoleva seaduse/paragrahvi' (this act), else 'external'/'unknown'."""
    refs: List[Reference] = []
    window = src[start:end]
    for m in _REF_RE.finditer(window):
        gstart = start + m.start()
        gend = start + m.end()
        # look back a few chars to detect 'käesoleva' (this act/section) markers
        prefix = src[max(0, gstart - 40):gstart].lower()
        if "käesoleva seaduse" in prefix or "käesoleva seaduse" in prefix:
            scope = "self"
        elif "käesoleva paragrahvi" in prefix:
            scope = "self"
        else:
            scope = "external"
        refs.append(Reference(
            raw=m.group(0).strip(),
            paragraph=m.group(1),
            subsection=m.group(2),
            point=(m.group(3).strip() if m.group(3) else None),
            scope=scope,
            start=gstart, end=gend,
        ))
    return refs


# ── main parse ──────────────────────────────────────────────────────────────

def _quote_mask(s: str) -> List[bool]:
    """Mark chars inside curly-quoted text while preserving one char per input."""
    mask = [False] * len(s)
    inside = False
    opener = ""
    for i, ch in enumerate(s):
        if ch == "„" and not inside:
            inside = True
            opener = ch
            mask[i] = True
        elif ch in ("“", "”") and inside and opener == "„":
            inside = False
            opener = ""
            mask[i] = True
        elif ch == "”":
            inside = not inside
            opener = ch if inside else ""
            mask[i] = True
        else:
            mask[i] = inside
    return mask


_META_KEYWORDS = ("juhtivkomisjon", "eelnõu", "lugemine", "esitab", "riigikogu")
_AMENDMENT_VERBS = (
    "muudetakse", "täiendatakse", "asendatakse", "tunnistatakse",
    "jäetakse", "loetakse", "sõnastatakse",
)


def _looks_like_amendment_command(src: str, start: int, end: int) -> bool:
    line_end = src.find("\n", start, end)
    if line_end == -1:
        line_end = end
    line = src[start:line_end].lower()
    return any(verb in line for verb in _AMENDMENT_VERBS)


def parse_bill(text: str) -> Bill:
    src = normalize_superscripts(text)

    # Title: first non-empty line that looks like a law title, skipping the
    # metadata header (committee, reading, date, "NNN SE", "EELNÕU").
    title = ""
    fallback = ""
    for line in src.splitlines():
        s = line.strip()
        if not s:
            continue
        low = s.lower()
        if any(k in low for k in _META_KEYWORDS) or re.match(r"^\d+\s+SE\b", s) \
           or re.match(r"^\d{1,2}\.\d{1,2}\.\d{4}", s) or s.startswith("§"):
            continue
        if not fallback:
            fallback = s
        if "seadus" in low:           # law titles end in "...seadus"
            title = s
            break
    title = title or fallback

    full_mask = _quote_mask(src)
    matches = [m for m in _SECTION_RE.finditer(src) if not full_mask[m.start()]]
    raw_section_matches = [NumberedMatch(m.group(1), m.start(), m.end()) for m in matches]

    # Keep only near-sequential top-level §s (drop inserted "§ 10¹"→"101" etc.).
    kept = []
    current_max = 0
    for m in matches:
        num = int(m.group(1))
        if not kept:
            if num == 1 or num <= 3:        # first real section is usually § 1
                kept.append(m); current_max = num
            continue
        if current_max < num <= current_max + 5:
            kept.append(m); current_max = num
        # else: out-of-sequence (quoted/inserted paragraph) → ignore

    sections: List[Section] = []
    for idx, m in enumerate(kept):
        sec_start = m.start()
        sec_end = kept[idx + 1].start() if idx + 1 < len(kept) else len(src)
        number = m.group(1)
        sec_title = m.group(2).strip()
        kind = _classify(sec_title)
        law = _target_law(sec_title) if kind == "amendment" else None

        sec = Section(
            number=number, pid="§" + number, title=sec_title, kind=kind,
            target_law=law, start=sec_start, end=sec_end,
        )

        # amendment instructions inside the section body. Two filters, because
        # quoted replacement text contains the target law's own "N)" lists:
        #   1) drop "N)" inside curly quotes (best-effort mask), then
        #   2) start at 1) and keep forward jumps; nested lists restart at lower
        #      numbers and are thereby excluded.
        body_start = m.end()
        candidates = []
        for im in _INSTR_RE.finditer(src, body_start, sec_end):
            if not full_mask[im.start()]:
                candidates.append(im)
                continue
            if candidates:
                prev = int(candidates[-1].group(1))
                n = int(im.group(1))
                # Real drafts sometimes leave a replacement block quote unclosed;
                # recover only the next amendment-command heading.
                if n == prev + 1 and _looks_like_amendment_command(src, im.start(), sec_end):
                    candidates.append(im)
        sec.raw_instruction_numbers = [
            NumberedMatch(im.group(1), im.start(), im.end()) for im in candidates
        ]
        instr_iter = []
        last = 0
        for im in candidates:
            n = int(im.group(1))
            if not instr_iter:
                if n == 1:
                    instr_iter.append(im); last = n
                continue
            if n > last:
                instr_iter.append(im); last = n
        for j, im in enumerate(instr_iter):
            i_start = im.start()
            i_end = instr_iter[j + 1].start() if j + 1 < len(instr_iter) else sec_end
            instr = Instruction(number=im.group(1), start=i_start, end=i_end)
            instr.references = _extract_references(src, i_start, i_end, law)
            instr.quote_spans = [Span(i_start + q.start(), i_start + q.end())
                                 for q in _QUOTE_RE.finditer(src[i_start:i_end])]
            sec.instructions.append(instr)

        # For entry-into-force / substantive sections with no "N)" instructions,
        # still capture references at the section level under a synthetic instr.
        if not sec.instructions:
            synth = Instruction(number="", start=body_start, end=sec_end)
            synth.references = _extract_references(src, body_start, sec_end, law)
            sec.instructions.append(synth)

        sections.append(sec)

    return Bill(title=title, raw_text=text, sections=sections,
                raw_section_matches=raw_section_matches)


def percentages_in(src: str, start: int, end: int) -> List[float]:
    """All percentage values in a span, as floats (handles Estonian decimal comma)."""
    out = []
    for m in _PCT_RE.finditer(src[start:end]):
        out.append(float(m.group(1).replace(",", ".")))
    return out


if __name__ == "__main__":
    import sys, json
    txt = open(sys.argv[1], encoding="utf-8").read()
    bill = parse_bill(txt)
    print(json.dumps(bill.summary(), ensure_ascii=False, indent=2))
