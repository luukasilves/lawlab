"""Export {title, text, findings} for a bill into web/demo_data.json so the
static viewer (web/index.html) can render the bill with inline-highlighted
findings. In production the SPA reads the same shape from Supabase REST.

Usage:
  python3 -m web.export_demo analysis/tests/fixtures/bill_728.txt 728
  python3 -m web.export_demo analysis/tests/fixtures/synthetic_errors.txt synthetic --no-llm
"""

from __future__ import annotations
import json
import os
import sys

from analysis.run import analyze

HERE = os.path.dirname(__file__)


def main():
    path = sys.argv[1]
    bill_number = sys.argv[2] if len(sys.argv) > 2 else None
    use_llm = "--no-llm" not in sys.argv
    text = open(path, encoding="utf-8").read()
    out, cached = analyze(text, use_llm=use_llm, n=5, k=3, temp=0.4, use_cache=True)
    r = out["result"]
    data = {
        "bill_number": bill_number,
        "title": r["bill_title"],
        "model": r["model"],
        "prompt_version": r["prompt_version"],
        "config": r["config"],
        "stats": out["stats"],
        "text": text,
        "findings": r["findings"],
    }
    dest = os.path.join(HERE, "demo_data.json")
    with open(dest, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    print(f"wrote {dest}  ({len(r['findings'])} findings, cached={cached})")
    if out["stats"].get("llm_error"):
        print("  note: LLM error -> deterministic findings only:", out["stats"]["llm_error"][:80])


if __name__ == "__main__":
    main()
