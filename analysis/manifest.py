"""Engine manifest and cache-key helpers."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict

from .checkers import deterministic
from . import passes


def text_sha(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_engine_manifest(provider: str, model: str, n: int, k: int, temp: float) -> Dict[str, Any]:
    return {
        "provider": provider,
        "model": model,
        "params": {"samples": n, "k": k, "temperature": temp},
        "checks": [[c.id, c.version] for c in deterministic.enabled_checks()],
        "passes": [[p.id, p.version, p.prompt_sha()] for p in passes.enabled_passes()],
    }


def _fp(manifest: Dict[str, Any]) -> str:
    blob = json.dumps(manifest, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _key(sha: str, manifest: Dict[str, Any]) -> str:
    return hashlib.sha256(f"{sha}|{_fp(manifest)}".encode("utf-8")).hexdigest()[:32]


def cache_key(sha: str, manifest: Dict[str, Any]) -> str:
    return _key(sha, manifest)


def llm_cache_key(sha: str, manifest: Dict[str, Any]) -> str:
    interpretive_prompt_sha = ""
    for pass_id, _version, prompt_sha in manifest.get("passes", []):
        if pass_id == "interpretive":
            interpretive_prompt_sha = prompt_sha
            break
    params = manifest.get("params", {})
    sub_manifest = {
        "provider": manifest.get("provider"),
        "model": manifest.get("model"),
        "samples": params.get("samples"),
        "temperature": params.get("temperature"),
        "interpretive_prompt_sha": interpretive_prompt_sha,
    }
    return _key(sha, sub_manifest)
