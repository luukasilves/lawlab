"""Shared data model for analysis findings.

A Finding is produced by either a deterministic checker (confidence 1.0) or the
LLM interpretive pass (confidence = self-consistency agreement rate). Both carry
a verbatim evidence quote with character offsets so the UI can highlight it and
so we can verify the LLM didn't hallucinate a location.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Optional, List, Dict, Any


# Analysis categories (internal-consistency taxonomy, Estonian labels in UI).
CATEGORIES = {
    "reference_integrity":   "Viiteterviklus",
    "structural_integrity":  "Struktuuriterviklus",
    "arithmetic":            "Arvutuslik õigsus",
    "temporal":              "Ajaline loogika",
    "terminology":           "Terminoloogiline järjepidevus",
    "logical_contradiction": "Loogilised vastuolud",
    "completeness":          "Täielikkus",
    "linguistic_ambiguity":  "Keeleline ühemõttelisus",
}

CATEGORIES_EN = {
    "reference_integrity": "Reference integrity",
    "structural_integrity": "Structural integrity",
    "arithmetic": "Arithmetic accuracy",
    "temporal": "Temporal logic",
    "terminology": "Terminological consistency",
    "logical_contradiction": "Logical contradictions",
    "completeness": "Completeness",
    "linguistic_ambiguity": "Linguistic ambiguity",
}

# Mapping category -> HÕNTE rule citation. Verified §-numbers and titles live in
# reference/honte.py (single source of truth, extracted from the official
# regulation). Grounding each finding in a real drafting rule is what makes it
# defensible rather than vibes.
from reference.honte import HONTE_RULE  # noqa: E402

SEVERITIES = ("HIGH", "MEDIUM", "LOW")


@dataclass
class Finding:
    source: str                 # "deterministic" | "llm"
    category: str               # key in CATEGORIES
    severity: str               # HIGH | MEDIUM | LOW
    title: str
    description: str
    provision_id: str           # stable pid, e.g. "§5"
    location: str               # human-readable, e.g. "§ 5 lõige 2"
    evidence_quote: str         # verbatim span from the bill
    char_start: int
    char_end: int
    reasoning: str = ""
    suggestion: str = ""
    honte_rule: Optional[str] = None
    confidence: float = 1.0
    check_id: Optional[str] = None     # deterministic check name, or "llm"
    runs_found: Optional[int] = None   # for LLM findings: how many of N samples
    runs_total: Optional[int] = None
    skeptic_verdict: str = "not_checked"
    skeptic_reasoning: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AnalysisResult:
    bill_number: Optional[str]
    bill_title: str
    cache_key: str
    model: Optional[str]
    prompt_version: Optional[str]
    checker_version: str
    provider: Optional[str] = None
    engine: Dict[str, Any] = field(default_factory=dict)
    config: Dict[str, Any] = field(default_factory=dict)
    findings: List[Finding] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d

    def by_severity(self) -> Dict[str, int]:
        out = {s: 0 for s in SEVERITIES}
        for f in self.findings:
            if f.skeptic_verdict == "refuted":
                continue
            out[f.severity] = out.get(f.severity, 0) + 1
        return out


@dataclass
class SampleRecord:
    pass_id: str
    sample_idx: int
    temperature: float
    raw_output: str
    parsed: List[dict]
    returned_count: int
    grounded_count: int
    dropped_ungrounded: int
    reused: bool = False
    duration_ms: int = 0
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cost_usd: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def _legacy_stats(self) -> Dict[str, Any]:
        return {
            "returned": self.returned_count,
            "grounded": self.grounded_count,
            "dropped": self.dropped_ungrounded,
            "relabelled": getattr(self, "relabelled", 0),
        }

    def get(self, key: str, default: Any = None) -> Any:
        return self._legacy_stats().get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self._legacy_stats()[key]
