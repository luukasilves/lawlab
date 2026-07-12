"""Run the analyzer against the gold set and report recall / false alarms.

Usage:
  python3 -m eval.run_eval                 # all labelled bills
  python3 -m eval.run_eval synthetic       # one bill (offline, deterministic)

'synthetic' runs deterministic-only (no API). '728' runs the full LLM pipeline,
so it needs API access; results are cached, so re-runs are free.
"""

from __future__ import annotations
import json
import os
import sys
from collections import defaultdict

from analysis.run import analyze
from .metrics import score, score_by_category

HERE = os.path.dirname(__file__)
ROOT = os.path.dirname(HERE)
GOLD = os.path.join(HERE, "gold_set.json")

FIXTURES = {
    "728":       (os.path.join(ROOT, "analysis/tests/fixtures/bill_728.txt"), True),
    "657":       (os.path.join(ROOT, "analysis/tests/fixtures/bill_657.txt"), False),
    "741":       (os.path.join(ROOT, "analysis/tests/fixtures/bill_741.txt"), False),
    "synthetic": (os.path.join(ROOT, "analysis/tests/fixtures/synthetic_errors.txt"), False),
}


def main():
    labels = json.load(open(GOLD, encoding="utf-8"))
    by_bill = defaultdict(list)
    for l in labels:
        by_bill[l["bill_number"]].append(l)

    only = sys.argv[1] if len(sys.argv) > 1 else None
    print(f"{'='*64}\nLAWLAB EVAL — gold set: {len(labels)} labels across {len(by_bill)} bills\n{'='*64}")

    for bill, blabels in by_bill.items():
        if only and bill != only:
            continue
        path, use_llm = FIXTURES.get(bill, (None, False))
        if not path or not os.path.exists(path):
            print(f"\n[{bill}] no fixture — skipped")
            continue
        text = open(path, encoding="utf-8").read()
        out, cached = analyze(text, use_llm=use_llm, n=5, k=3, temp=0.4, use_cache=True)
        findings = out["result"]["findings"]
        if out["stats"].get("llm_error"):
            print(f"\n[{bill}] LLM error: {out['stats']['llm_error'][:80]} — deterministic only")
        s = score(findings, blabels)
        refuted_count = len([f for f in findings if f.get("skeptic_verdict") == "refuted"])
        rc = f"{s['recall']:.0%}" if s["recall"] is not None else "n/a"
        print(f"\n[{bill}] {'(cached)' if cached else ''} findings={len(findings)} refuted={refuted_count}")
        print(f"   recall on known errors: {s['recalled']}/{s['true_errors']} ({rc})")
        print(f"   false-alarm guards held: {s['guards_held']}/{s['false_alarm_guards']}"
              f"  (false alarms: {s['false_alarms']})")
        print(f"   review queue (unlabelled findings): {s['review_queue']}")
        if s["missed"]:
            print(f"   MISSED: {s['missed']}")


if __name__ == "__main__":
    main()
