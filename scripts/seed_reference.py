"""Seed the honte_rules reference table (idempotent upsert on rule_id).

Run: python -m scripts.seed_reference   (needs SUPABASE_SERVICE_KEY)
"""

from __future__ import annotations

import requests

import config
from reference.honte import load_honte_rules


def main() -> None:
    rows = load_honte_rules()
    h = {
        "apikey": config.SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {config.SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    r = requests.post(
        f"{config.SUPABASE_URL}/rest/v1/honte_rules?on_conflict=rule_id",
        headers=h, json=rows, timeout=30,
    )
    r.raise_for_status()
    print(f"seeded {len(rows)} HÕNTE rules (HTTP {r.status_code})")


if __name__ == "__main__":
    main()
