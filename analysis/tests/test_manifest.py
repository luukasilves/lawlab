"""Contract tests for the two-level cache keys + registries (R2a). RED until built.

The design (see docs/EXTENDING.md once written):
  * analysis/manifest.py — text_sha(raw)->sha256 hex; build_engine_manifest(
    provider, model, n, k, temp)->dict; cache_key(sha, manifest)->32 hex chars
    (identity of an analyses row); llm_cache_key(sha, manifest)->32 hex chars
    (keys ONLY what the expensive interpretive samples depend on: provider,
    model, n, temperature, interpretive prompt sha — NOT k, NOT checks, NOT
    other passes).
  * deterministic.CHECKS — list of CheckSpec(id, version:int, category,
    name_et, name_en, description_et, description_en, fn, enabled);
    enabled_checks(); checker_version_label() -> 'id@v,id@v,…'.
  * analysis/passes.py — PASSES list of PassSpec(id, version, kind, name_et,
    name_en, description_et, description_en, prompt(module), enabled,
    recorded_sha); PassSpec.prompt_sha() = sha256(SYSTEM_PROMPT + '\\x00' +
    USER_TEMPLATE) hexdigest. Label drift: prompt_sha()[:8] must equal
    recorded_sha — editing a prompt without bumping version+recorded_sha
    fails CI.

Run: python3 -m analysis.tests.test_manifest
"""

from __future__ import annotations

import hashlib

from ..manifest import text_sha, build_engine_manifest, cache_key, llm_cache_key
from ..checkers import deterministic as det
from .. import passes


def _m(**kw):
    base = dict(provider="openrouter", model="anthropic/claude-opus-4.8", n=5, k=3, temp=0.4)
    base.update(kw)
    return build_engine_manifest(**base)


def test_text_sha_is_raw_sha256():
    assert text_sha("a  b") == hashlib.sha256("a  b".encode("utf-8")).hexdigest()
    assert text_sha("a  b") != text_sha("a b"), "raw bytes, no whitespace collapsing"
    print("✓ text_sha is plain sha256 over raw bytes (equals bill_documents.content_hash)")


def test_manifest_shape():
    m = _m()
    assert m["provider"] == "openrouter" and m["model"] == "anthropic/claude-opus-4.8"
    assert m["params"] == {"samples": 5, "k": 3, "temperature": 0.4}
    assert m["checks"] == [[c.id, c.version] for c in det.enabled_checks()]
    assert m["passes"] == [[p.id, p.version, p.prompt_sha()] for p in passes.enabled_passes()]
    print("✓ engine manifest carries params + check versions + pass shas")


def test_key_sensitivity():
    sha = text_sha("Testseadus\n\n§ 1. Reegel\nSisu.")
    base = _m()
    k0, l0 = cache_key(sha, base), llm_cache_key(sha, base)
    assert len(k0) == 32 and len(l0) == 32 and k0 != l0

    m = _m()
    m["checks"] = [[cid, v + 1] for cid, v in m["checks"]]
    assert cache_key(sha, m) != k0, "check version bump must invalidate the analysis identity"
    assert llm_cache_key(sha, m) == l0, "check version bump must NOT re-buy the samples"

    m = _m(k=4)
    assert cache_key(sha, m) != k0 and llm_cache_key(sha, m) == l0, "k retunes recluster for free"

    m = _m(n=7)
    assert cache_key(sha, m) != k0 and llm_cache_key(sha, m) != l0, "n changes the sample set"

    m = _m(temp=0.2)
    assert cache_key(sha, m) != k0 and llm_cache_key(sha, m) != l0

    m = _m(provider="anthropic")
    assert cache_key(sha, m) != k0 and llm_cache_key(sha, m) != l0

    m = _m()
    m["passes"] = [[pid, ver, ("f" * 64 if pid == "interpretive" else psha)]
                   for pid, ver, psha in m["passes"]]
    assert cache_key(sha, m) != k0 and llm_cache_key(sha, m) != l0, \
        "interpretive prompt text change must invalidate BOTH keys (auto-invalidation)"

    m = _m()
    m["passes"] = [[pid, ver, ("f" * 64 if pid == "refute" else psha)]
                   for pid, ver, psha in m["passes"]]
    assert cache_key(sha, m) != k0, "refute prompt change invalidates the analysis identity"
    assert llm_cache_key(sha, m) == l0, "refute prompt change must NOT re-buy interpretive samples"

    assert cache_key(sha, _m()) == k0 and llm_cache_key(sha, _m()) == l0, "determinism"
    print("✓ two-level key sensitivity: checks/k/refute are free; prompt/model/provider/n/temp re-buy")


def test_check_registry():
    ids = [c.id for c in det.CHECKS]
    assert ids == ["section_numbering", "instruction_numbering", "eif_refs", "percentage_alloc"], ids
    for c in det.CHECKS:
        assert isinstance(c.version, int) and c.version >= 1
        assert c.category and c.name_et and c.name_en and c.description_et and c.description_en
        assert c.enabled is True, f"{c.id} must be enabled (instruction_numbering is active post-R1)"
    label = det.checker_version_label()
    assert label == ",".join(f"{c.id}@{c.version}" for c in det.enabled_checks())
    assert not hasattr(det, "CHECKER_VERSION"), "global CHECKER_VERSION constant must be deleted"
    print("✓ CheckSpec registry: 4 enabled checks, bilingual metadata, derived version label")


def test_pass_registry_and_label_drift():
    ids = [p.id for p in passes.PASSES]
    assert ids == ["interpretive", "refute"], ids
    for p in passes.PASSES:
        assert p.kind in ("sampled", "per_finding")
        assert p.name_et and p.name_en and p.description_et and p.description_en
        assert p.prompt.SYSTEM_PROMPT and p.prompt.USER_TEMPLATE and p.prompt.PROMPT_VERSION
        expected = hashlib.sha256(
            (p.prompt.SYSTEM_PROMPT + "\x00" + p.prompt.USER_TEMPLATE).encode("utf-8")
        ).hexdigest()
        assert p.prompt_sha() == expected
        assert p.recorded_sha == expected[:8], (
            f"label drift on pass '{p.id}': prompt text changed without bumping "
            f"version+recorded_sha (recorded {p.recorded_sha}, actual {expected[:8]})"
        )
    interp = passes.PASSES[0]
    assert interp.version == interp.prompt.PROMPT_VERSION
    assert "{bill_text}" in interp.prompt.USER_TEMPLATE, "USER_TEMPLATE must be a format template"
    print("✓ PassSpec registry: interpretive+refute, sha-pinned prompts, drift guard armed")


if __name__ == "__main__":
    test_text_sha_is_raw_sha256()
    test_manifest_shape()
    test_key_sensitivity()
    test_check_registry()
    test_pass_registry_and_label_drift()
    print("\nALL MANIFEST/REGISTRY TESTS PASSED")
