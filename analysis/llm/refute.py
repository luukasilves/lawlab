"""Skeptic review pass for sub-consensus interpretive findings."""

from __future__ import annotations

import json
import re
import time
from typing import List, Tuple

import requests

from ..models import Finding, SampleRecord
from ..prompts import refutation
from .client import LLMError, chat_json


def _snippet(content: str) -> str:
    return re.sub(r"\s+", " ", content.strip())[:200]


def _parse_verdict(content: str) -> Tuple[str, str]:
    text = content.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if fence:
        text = fence.group(1)
    data = None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            try:
                data = json.loads(m.group())
            except json.JSONDecodeError:
                data = None
    if not isinstance(data, dict):
        return "upheld", f"Skeptiku vastus ei olnud loetav JSON: {_snippet(content)}"
    verdict = (data.get("verdict") or "").strip().lower()
    if verdict not in ("upheld", "refuted"):
        return "upheld", (data.get("reasoning") or "Skeptiku otsus ei olnud üheselt loetav.").strip()
    return verdict, (data.get("reasoning") or "").strip()


def _finding_payload(finding: Finding) -> str:
    payload = {
        "title": finding.title,
        "category": finding.category,
        "location": finding.location,
        "evidence_quote": finding.evidence_quote,
        "reasoning": finding.reasoning,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def refute_findings(bill_text: str, candidates: List[Finding], model=None):
    records: List[SampleRecord] = []
    refuted = 0
    for idx, finding in enumerate(candidates):
        t0 = time.monotonic()
        raw_output = ""
        input_tokens = None
        output_tokens = None
        cost_usd = 0.0
        try:
            response = chat_json(
                refutation.SYSTEM_PROMPT,
                refutation.build_user_blocks(bill_text, _finding_payload(finding)),
                temperature=0.0,
                model=model,
            )
            raw_output = response.text if hasattr(response, "text") else response
            input_tokens = getattr(response, "input_tokens", None)
            output_tokens = getattr(response, "output_tokens", None)
            cost_usd = getattr(response, "cost_usd", 0.0)
            verdict, reasoning = _parse_verdict(raw_output)
        except (LLMError, requests.RequestException) as e:
            verdict, reasoning = "upheld", f"Skeptiku kontroll ebaõnnestus: {str(e)[:160]}"

        finding.skeptic_verdict = verdict
        finding.skeptic_reasoning = reasoning
        if verdict == "refuted":
            refuted += 1
        parsed = [{
            "target": {
                "title": finding.title,
                "category": finding.category,
                "provision": finding.provision_id,
            },
            "verdict": verdict,
            "reasoning": reasoning,
        }]
        records.append(SampleRecord(
            pass_id="refute",
            sample_idx=idx,
            temperature=0.0,
            raw_output=raw_output,
            parsed=parsed,
            returned_count=1,
            grounded_count=1,
            dropped_ungrounded=0,
            duration_ms=int((time.monotonic() - t0) * 1000),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
        ))
    return records, {"judged": len(candidates), "refuted": refuted}
