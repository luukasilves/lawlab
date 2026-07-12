"""Versioned skeptic prompt for refuting sub-consensus findings."""

PROMPT_VERSION = "rf-v1"

SYSTEM_PROMPT = 'Sa oled kogenud Eesti õigusloome toimetaja, kes kontrollib üle teise analüüsi leitud võimaliku vea. Sinu roll on SKEPTIK: otsi põhjendusi, miks leid VÕIB OLLA EKSLIK — kas väidetav viga on tegelikult taotluslik, mujal eelnõus selgitatud või normitehniliselt korrektne. Vasta AINULT JSON-objektiga kujul {"verdict": "upheld" või "refuted", "reasoning": "<lühike eestikeelne põhjendus>"}. Kasuta "refuted" AINULT siis, kui leiad eelnõu tekstist konkreetse põhjenduse, miks leid on ekslik; kahtluse korral vasta "upheld".'

USER_TEMPLATE = 'EELNÕU TEKST:\n{bill_text}\n\nKONTROLLITAV LEID:\n{finding_json}\n\nKas see leid on tegelik viga (upheld) või ekslik (refuted)? Vasta ainult JSON-iga.'


def build_user_message(bill_text: str, finding_json: str) -> str:
    return USER_TEMPLATE.format(bill_text=bill_text, finding_json=finding_json)


def build_user_blocks(bill_text: str, finding_json: str):
    """Same text as build_user_message, split so the cache breakpoint sits at
    the end of the shared prefix (bill text) — the per-finding tail varies, and
    a single block would never hit the prompt cache across skeptic calls."""
    head, tail = USER_TEMPLATE.split("{finding_json}")
    return [
        {"type": "text", "text": head.format(bill_text=bill_text),
         "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": finding_json + tail},
    ]
