"""Provider-agnostic LLM client.

Default path is OpenRouter (works with the existing OPENROUTER_API_KEY). Setting
LAWLAB_LLM_PROVIDER=anthropic + ANTHROPIC_API_KEY switches to the native
Anthropic API (which unlocks strict structured outputs + prompt caching).

We request a JSON object and validate/parse in code (engine.py), which is robust
across providers and avoids depending on any one provider's json_schema support.
"""

from __future__ import annotations
from dataclasses import dataclass
import time

import requests
import config


class LLMError(Exception):
    pass


@dataclass
class LLMResponse:
    text: str
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float


def chat_json(system: str, user: str, temperature: float,
              max_tokens: int = 16000, model: str = None, timeout: int = 300) -> LLMResponse:
    model = model or config.active_model()
    if config.LLM_PROVIDER == "anthropic":
        if not config.ANTHROPIC_API_KEY:
            raise LLMError("LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is unset")
        return _anthropic(system, user, temperature, max_tokens, model, timeout)
    if not config.OPENROUTER_API_KEY:
        raise LLMError("OPENROUTER_API_KEY is unset")
    return _openrouter(system, user, temperature, max_tokens, model, timeout)


def _post_with_retry(url, *, headers, payload, timeout, provider):
    last_error = None
    for attempt in range(4):
        try:
            # (connect, read) tuple: requests' read timeout is per-received-chunk,
            # not wall-clock — callers add their own hard deadline on top.
            r = requests.post(url, headers=headers, json=payload, timeout=(20, timeout))
        except (requests.Timeout, requests.ConnectionError) as e:
            last_error = e
            if attempt == 3:
                raise LLMError(f"{provider} transport error after retries: {e}") from e
            time.sleep(2 ** attempt)
            continue

        if r.status_code == 200:
            return r
        if r.status_code == 429 or r.status_code >= 500:
            last_error = LLMError(f"{provider} {r.status_code}: {r.text[:300]}")
            if attempt == 3:
                raise last_error
            time.sleep(2 ** attempt)
            continue
        raise LLMError(f"{provider} {r.status_code}: {r.text[:300]}")
    raise LLMError(f"{provider} request failed: {last_error}")


def _system_block(system: str):
    return [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]


def _user_blocks(user):
    """Accept a plain string (one cached block) or pre-split content blocks —
    callers place the cache_control breakpoint at the end of the SHARED prefix
    (e.g. refutation: bill text cached, per-finding tail varies)."""
    if isinstance(user, list):
        return user
    return [{"type": "text", "text": user, "cache_control": {"type": "ephemeral"}}]


def _openrouter(system, user, temperature, max_tokens, model, timeout) -> LLMResponse:
    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "X-Title": "Lawlab",
    }
    payload = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": _system_block(system)},
            # cache_control must cover system + bill text to clear Opus's
            # 4096-token cache floor (the system prompt alone never does).
            {"role": "user", "content": _user_blocks(user)},
        ],
        "response_format": {"type": "json_object"},
        "usage": {"include": True},
    }
    r = _post_with_retry("https://openrouter.ai/api/v1/chat/completions",
                         headers=headers, payload=payload, timeout=timeout,
                         provider="OpenRouter")
    data = r.json()
    if "choices" not in data:
        raise LLMError(f"OpenRouter unexpected response: {str(data)[:300]}")
    finish = data["choices"][0].get("finish_reason")
    if finish == "length":
        raise LLMError("output truncated at max_tokens (finish_reason=length)")
    usage = data.get("usage") or {}
    return LLMResponse(
        text=data["choices"][0]["message"]["content"],
        input_tokens=usage.get("prompt_tokens"),
        output_tokens=usage.get("completion_tokens"),
        cost_usd=float(usage.get("cost") or 0.0),
    )


def _anthropic(system, user, temperature, max_tokens, model, timeout) -> LLMResponse:
    headers = {
        "x-api-key": config.ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": _system_block(system),
        "messages": [{"role": "user", "content": user}],
    }
    r = _post_with_retry("https://api.anthropic.com/v1/messages",
                         headers=headers, payload=payload, timeout=timeout,
                         provider="Anthropic")
    data = r.json()
    usage = data.get("usage") or {}
    return LLMResponse(
        text="".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"),
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
        cost_usd=0.0,
    )


def verify_model(model: str = None):
    model = model or config.active_model()
    if config.LLM_PROVIDER == "anthropic":
        headers = {
            "x-api-key": config.ANTHROPIC_API_KEY or "",
            "anthropic-version": "2023-06-01",
        }
        url = "https://api.anthropic.com/v1/models/"
        provider = "Anthropic"
    else:
        headers = {"Authorization": f"Bearer {config.OPENROUTER_API_KEY or ''}"}
        url = "https://openrouter.ai/api/v1/models/"
        provider = "OpenRouter"
    r = requests.get(url, headers=headers, params={"id": model}, timeout=30)
    if r.status_code != 200:
        raise LLMError(f"{provider} model verification failed for {model}: {r.status_code} {r.text[:300]}")
    return True
