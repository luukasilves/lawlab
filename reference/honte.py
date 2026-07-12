"""HÕNTE grounding — maps each analysis category to the real drafting rule it
implicates, with verified § numbers and titles from the official regulation
(Hea õigusloome ja normitehnika eeskiri, VV määrus nr 180).

Rule texts were extracted from the official handbook into honte_rules.json and
are committed so the mapping is reproducible without re-downloading. Citing a
real, named rule is what turns a finding from "the LLM thinks so" into "this
violates HÕNTE § N", which a legal reviewer can check.
"""

from __future__ import annotations
import json
import os
from typing import List, Dict, Any

HONTE_AKT_URL = "https://www.riigiteataja.ee/akt/129122011228"

# category -> (HÕNTE § number, short label). Verified against the regulation.
CATEGORY_TO_RULE = {
    "terminology":           ("17", "terminite ühtne kasutamine"),
    "reference_integrity":   ("28", "viitamine"),
    "structural_integrity":  ("23", "paragrahvide numeratsioon ja pealkirjastamine"),
    "temporal":              ("14", "jõustumisnorm"),
    "linguistic_ambiguity":  ("15", "keele- ja stiilinõuded"),
    "logical_contradiction": ("16", "sätte selge ja täpne sõnastamine"),
    "completeness":          ("16", "sätte terviklik sõnastamine"),
    "arithmetic":            ("16", "sätte täpne sõnastamine"),
}

# Secondary rule that also applies (shown as context), if any.
CATEGORY_SECONDARY = {
    "terminology":          "18",   # termini määratlemine
    "reference_integrity":  "29",   # viite vormistamine
    "structural_integrity": "37",   # muudetava seaduse numeratsiooni säilitamine
}

_HERE = os.path.dirname(__file__)
_RULES_PATH = os.path.join(_HERE, "honte_rules.json")


def _rules() -> Dict[str, Any]:
    with open(_RULES_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def citation(category: str) -> str:
    """Human-readable citation, e.g. 'HÕNTE § 17 (terminite ühtne kasutamine)'."""
    rule = CATEGORY_TO_RULE.get(category)
    if not rule:
        return "HÕNTE"
    num, label = rule
    return f"HÕNTE § {num} ({label})"


def rule_text(category: str) -> str:
    """The normative text of the primary rule for a category (for LLM grounding)."""
    rule = CATEGORY_TO_RULE.get(category)
    if not rule:
        return ""
    return _rules().get(rule[0], {}).get("text", "")


# Single source of truth for models.HONTE_RULE
HONTE_RULE = {cat: citation(cat) for cat in CATEGORY_TO_RULE}


def load_honte_rules() -> List[Dict[str, Any]]:
    """Rows for the honte_rules table (rule_id, section, text, mapped_categories)."""
    rules = _rules()
    by_num: Dict[str, List[str]] = {}
    for cat, (num, _) in CATEGORY_TO_RULE.items():
        by_num.setdefault(num, []).append(cat)
    for cat, num in CATEGORY_SECONDARY.items():
        by_num.setdefault(num, []).append(cat)
    out = []
    for num, data in rules.items():
        out.append({
            "rule_id": f"HÕNTE § {num}",
            "section": data.get("title", ""),
            "text": data.get("text", ""),
            "mapped_categories": by_num.get(num, []),
        })
    return out


if __name__ == "__main__":
    for cat in CATEGORY_TO_RULE:
        print(f"{cat:24} -> {citation(cat)}")
    print(f"\n{len(load_honte_rules())} rules ready for honte_rules table")
