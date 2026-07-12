"""Provider-agnostic LLM client.

Default path is OpenRouter (works with the existing OPENROUTER_API_KEY). Setting
LAWLAB_LLM_PROVIDER=anthropic + ANTHROPIC_API_KEY switches to the native
Anthropic API (which unlocks strict structured outputs + prompt caching).

We request a JSON object and validate/parse in code (engine.py), which is robust
across providers and avoids depending on any one provider's json_schema support.
"""

from __future__ import annotations
import requests
import config


class LLMError(Exception):
    pass


def chat_json(system: str, user: str, temperature: float,
              max_tokens: int = 8000, model: str = None, timeout: int = 300) -> str:
    model = model or config.active_model()
    if config.LLM_PROVIDER == "anthropic":
        if not config.ANTHROPIC_API_KEY:
            raise LLMError("LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is unset")
        return _anthropic(system, user, temperature, max_tokens, model, timeout)
    if not config.OPENROUTER_API_KEY:
        raise LLMError("OPENROUTER_API_KEY is unset")
    return _openrouter(system, user, temperature, max_tokens, model, timeout)


def _openrouter(system, user, temperature, max_tokens, model, timeout) -> str:
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
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
    }
    r = requests.post("https://openrouter.ai/api/v1/chat/completions",
                      headers=headers, json=payload, timeout=timeout)
    if r.status_code != 200:
        raise LLMError(f"OpenRouter {r.status_code}: {r.text[:300]}")
    data = r.json()
    if "choices" not in data:
        raise LLMError(f"OpenRouter unexpected response: {str(data)[:300]}")
    return data["choices"][0]["message"]["content"]


def _anthropic(system, user, temperature, max_tokens, model, timeout) -> str:
    headers = {
        "x-api-key": config.ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    r = requests.post("https://api.anthropic.com/v1/messages",
                      headers=headers, json=payload, timeout=timeout)
    if r.status_code != 200:
        raise LLMError(f"Anthropic {r.status_code}: {r.text[:300]}")
    data = r.json()
    return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
