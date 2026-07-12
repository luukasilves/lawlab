"""LLM interpretive pass — one sample.

Calls the model, parses its JSON, and GROUNDS every finding: the model's
evidence_quote must actually occur in the bill text (whitespace/quote/case
tolerant). Findings whose evidence can't be located are dropped as
hallucinations. This is what lets the UI highlight a real span and what stops
the model inventing "§ 3" locations that don't exist.
"""

from __future__ import annotations
import json
import re
from typing import List, Optional, Tuple

from ..models import Finding, CATEGORIES, SEVERITIES, HONTE_RULE
from ..prompts.internal_consistency import SYSTEM_PROMPT, PROMPT_VERSION, build_user_message
from .client import chat_json

# Normalise the many quote/apostrophe variants to a single char, 1:1 in length
# so character offsets are preserved.
_QUOTE_MAP = {ord(c): '"' for c in "”“„‟”“'’‘`´"}


def _norm(s: str) -> str:
    return s.translate(_QUOTE_MAP)


def _locate(raw: str, quote: str) -> Optional[Tuple[int, int]]:
    """Whitespace/quote/case-tolerant search; returns (start, end) in raw or None.

    Tokenises on whitespace and joins with \\s+ — this is robust to the bill's
    \\n\\n paragraph breaks and narrow no-break spaces (U+202F), and avoids the
    re.escape-escapes-the-space pitfall that previously dropped every finding."""
    q = _norm(quote).strip()
    if len(q) < 10:
        return None
    R = _norm(raw)
    toks = q.split()
    if not toks:
        return None
    pat = r"\s+".join(re.escape(t) for t in toks)
    m = re.search(pat, R, re.IGNORECASE)
    if m:
        return m.start(), m.end()
    # fallback: match on the first ~12 tokens (tolerates an edited/truncated tail)
    if len(toks) > 12:
        pat2 = r"\s+".join(re.escape(t) for t in toks[:12])
        m2 = re.search(pat2, R, re.IGNORECASE)
        if m2:
            return m2.start(), min(len(raw), m2.start() + len(q))
    return None


def _parse_json(content: str) -> dict:
    content = content.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
    if fence:
        content = fence.group(1)
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        m = re.search(r'\{[\s\S]*"issues"[\s\S]*\}', content)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
    return {"issues": []}


def _coerce_category(c: str) -> str:
    c = (c or "").strip().lower().replace(" ", "_")
    if c in CATEGORIES:
        return c
    aliases = {
        "viiteterviklus": "reference_integrity",
        "struktuuriterviklus": "structural_integrity",
        "arvutuslik_õigsus": "arithmetic",
        "ajaline_loogika": "temporal",
        "terminoloogiline_järjepidevus": "terminology",
        "loogilised_vastuolud": "logical_contradiction",
        "loogiline_vastuolu": "logical_contradiction",
        "täielikkus": "completeness",
        "keeleline_ühemõttelisus": "linguistic_ambiguity",
    }
    return aliases.get(c, "logical_contradiction")


def analyze_once(bill_text: str, structure_hint: str = "",
                 temperature: float = 0.4, model: str = None) -> Tuple[List[Finding], dict]:
    """Returns (grounded findings, stats). Stats records hallucinated/dropped count."""
    content = chat_json(SYSTEM_PROMPT, build_user_message(bill_text, structure_hint),
                        temperature=temperature, model=model)
    data = _parse_json(content)
    issues = data.get("issues", []) if isinstance(data, dict) else []

    findings: List[Finding] = []
    dropped = 0
    for it in issues:
        if not isinstance(it, dict):
            continue
        quote = it.get("evidence_quote") or ""
        loc = _locate(bill_text, quote)
        if loc is None:
            dropped += 1            # ungrounded → treat as hallucination
            continue
        start, end = loc
        category = _coerce_category(it.get("category"))
        severity = (it.get("severity") or "MEDIUM").upper()
        if severity not in SEVERITIES:
            severity = "MEDIUM"
        findings.append(Finding(
            source="llm", category=category, severity=severity,
            title=(it.get("title") or "").strip(),
            description=(it.get("description") or "").strip(),
            provision_id=(it.get("provision_id") or "").strip(),
            location=(it.get("location") or "").strip(),
            evidence_quote=bill_text[start:end],   # canonical, verified span
            char_start=start, char_end=end,
            reasoning=(it.get("reasoning") or "").strip(),
            suggestion=(it.get("suggestion") or "").strip(),
            # use our verified citation, not the model's (avoids hallucinated §)
            honte_rule=HONTE_RULE.get(category),
            confidence=1.0, check_id="llm",
        ))
    return findings, {"returned": len(issues), "grounded": len(findings), "dropped": dropped}
