"""Central configuration. All secrets come from the environment / .env — never
hardcode keys in source (the previous build leaked its OpenRouter + Supabase
keys in plaintext; those must be rotated)."""

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


def _get(name, default=None):
    v = os.getenv(name)
    return v if v not in (None, "") else default


# ── LLM provider ────────────────────────────────────────────────────────────
# "openrouter" works today with the existing OPENROUTER_API_KEY; switch to
# "anthropic" once ANTHROPIC_API_KEY is set (unlocks native structured outputs
# + prompt caching). The model id is verified against the provider at runtime.
LLM_PROVIDER       = _get("LAWLAB_LLM_PROVIDER", "openrouter")
OPENROUTER_API_KEY = _get("OPENROUTER_API_KEY")
ANTHROPIC_API_KEY  = _get("ANTHROPIC_API_KEY")
OPENROUTER_MODEL   = _get("LAWLAB_OR_MODEL", "anthropic/claude-opus-4.8")
ANTHROPIC_MODEL    = _get("LAWLAB_ANTHROPIC_MODEL", "claude-opus-4-8")

# ── self-consistency (the non-determinism fix) ───────────────────────────────
SC_SAMPLES       = int(_get("LAWLAB_SC_SAMPLES", "5"))    # N samples
SC_MIN_AGREEMENT = int(_get("LAWLAB_SC_K", "3"))          # keep clusters in >= k
SC_TEMPERATURE   = float(_get("LAWLAB_SC_TEMP", "0.4"))   # diversity for sampling

# ── data store ────────────────────────────────────────────────────────────────
SUPABASE_URL         = _get("SUPABASE_URL")
SUPABASE_ANON_KEY    = _get("SUPABASE_ANON_KEY") or _get("SUPABASE_KEY")
SUPABASE_SERVICE_KEY = _get("SUPABASE_SERVICE_KEY")   # writes (ingestion/analysis)

# ── external APIs ─────────────────────────────────────────────────────────────
RIIGIKOGU_API = _get("RIIGIKOGU_API", "https://api.riigikogu.ee/api")
RIIGIKOGU_API_DELAY = float(_get("RIIGIKOGU_API_DELAY", "8"))


def active_model():
    return ANTHROPIC_MODEL if LLM_PROVIDER == "anthropic" else OPENROUTER_MODEL
