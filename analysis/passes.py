"""Registry of versioned analysis passes."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from types import ModuleType
from typing import List

from .prompts import internal_consistency, refutation


@dataclass(frozen=True)
class PassSpec:
    id: str
    version: str
    kind: str
    name_et: str
    name_en: str
    description_et: str
    description_en: str
    prompt: ModuleType
    enabled: bool = True
    recorded_sha: str = ""

    def prompt_sha(self) -> str:
        body = self.prompt.SYSTEM_PROMPT + "\x00" + self.prompt.USER_TEMPLATE
        return hashlib.sha256(body.encode("utf-8")).hexdigest()


PASSES = [
    PassSpec(
        "interpretive", internal_consistency.PROMPT_VERSION, "sampled",
        "Tõlgenduslik analüüs", "Interpretive analysis",
        "LLM otsib sisulisi vastuolusid N sõltumatu analüüsiga; avaldatakse ainult stabiilsed leiud.",
        "The LLM samples N independent analyses; only findings stable across runs are published.",
        internal_consistency,
        recorded_sha="d0aeefc4",
    ),
    PassSpec(
        "refute", refutation.PROMPT_VERSION, "per_finding",
        "Skeptiku kontroll", "Skeptic review",
        "Iga alla täisnõusoleku leidu kontrollib sõltumatu skeptik; ümberlükatud leiud jäävad nähtavale märgistatuna.",
        "Each sub-consensus finding is challenged by an independent skeptic; refuted findings remain visible, marked.",
        refutation,
        recorded_sha="c4e125ec",
    ),
]


def enabled_passes() -> List[PassSpec]:
    return [p for p in PASSES if p.enabled]
