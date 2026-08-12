#!/usr/bin/env python3
"""
experiment.py: the only honest way Token Shield produces a VERIFIED saving.

A prevented event is a counterfactual, so it is at best ESTIMATED, never
verified. The only thing that earns VERIFIED is a real before/after: measure,
change one thing, measure again over the SAME window, and refuse the comparison
if anything that would invalidate it changed.

  python3 experiment.py start "shrink-claude-md"   # pins a baseline now
  ...do the one change, work normally for a while...
  python3 experiment.py end "shrink-claude-md"     # compares, writes one record

Each ended experiment appends ONE record to ~/.claude/token-shield/savings.jsonl,
the append-only proof ledger the dashboard reads for its VERIFIED column. The
comparison reuses the meter's own guards: it refuses across a schema change and
downgrades to NOT_PROVEN on a window mismatch or thin data, rather than print a
confident number that means nothing.
"""

import argparse
import json
import os

import measure_tokens as mt

HOME = os.path.expanduser("~")
STORE = os.path.join(HOME, ".claude", "token-shield")
EXP_DIR = os.path.join(STORE, "experiments")
LEDGER = os.path.join(STORE, "savings.jsonl")

MIN_SESSIONS = 3  # below this, coverage is too thin to call a comparison verified


def build_record(baseline, after_sm, ended_iso):
    """Pure verdict function: baseline (the start snapshot) + the after summary
    -> one ledger record with a confidence class. No I/O, so it is testable.

    Guards, each of which downgrades to NOT_PROVEN with a stated reason:
      - schema changed since the baseline (the meter's own refusal);
      - window length differs (different windows hold different sessions);
      - too few sessions after the change to measure a floor honestly.
    """
    reasons = []
    b = baseline.get("summary") or {}
    if baseline.get("schema") != mt.SCHEMA:
        reasons.append(f"baseline is schema {baseline.get('schema')}, meter is {mt.SCHEMA}")
    if baseline.get("window_days") != after_sm.get("_window_days"):
        reasons.append(f"window changed ({baseline.get('window_days')} vs "
                       f"{after_sm.get('_window_days')} days)")
    if (after_sm.get("parent_sessions") or 0) < MIN_SESSIONS:
        reasons.append(f"only {after_sm.get('parent_sessions')} sessions after the change, "
                       f"need {MIN_SESSIONS}")

    fr_before = b.get("first_request_median")
    fr_after = after_sm.get("first_request_median")
    if fr_before is None or fr_after is None:
        reasons.append("no first-request median on one side")

    verified = not reasons
    floor_reduction = None
    if fr_before is not None and fr_after is not None:
        floor_reduction = fr_before - fr_after

    return {
        "timestamp": ended_iso,
        "label": baseline.get("label"),
        "confidence": "VERIFIED" if verified else "NOT_PROVEN",
        "reasons": reasons,
        "window_days": baseline.get("window_days"),
        "first_request_before": fr_before,
        "first_request_after": fr_after,
        "floor_reduction_tokens": floor_reduction,
        "normalized_input_before": b.get("normalized_input_total"),
        "normalized_input_after": after_sm.get("normalized_input_total"),
        "models_before": b.get("_models"),
        "models_after": after_sm.get("_models"),
        "evidence": "API usage counters, before/after over the same window",
    }


def _measure(root, days):
    sm = mt.summarize(mt.collect(root, days)) or {}
    sm = dict(sm)
    sm["_window_days"] = days
    return sm


def cmd_start(label, root, days, now_iso):
    os.makedirs(EXP_DIR, exist_ok=True)
    sm = _measure(root, days)
    snap = {"label": label, "started": now_iso, "window_days": days,
            "schema": mt.SCHEMA, "summary": sm}
    path = os.path.join(EXP_DIR, label.replace("/", "_") + ".json")
    with open(path, "w") as f:
        json.dump(snap, f, indent=2)
    fr = sm.get("first_request_median")
    print(f"baseline pinned for '{label}': first-request median "
          f"{mt.fmt(fr)} tokens over {days:g} days.")
    print("Make ONE change now (for example diet CLAUDE.md), work normally, then run: "
          f"python3 experiment.py end \"{label}\"")
    return 0


def cmd_end(label, root, days, now_iso):
    path = os.path.join(EXP_DIR, label.replace("/", "_") + ".json")
    if not os.path.exists(path):
        print(f"NO DATA: no baseline named '{label}'. Run start first.")
        return 2
    with open(path) as f:
        baseline = json.load(f)
    after = _measure(root, days)
    rec = build_record(baseline, after, now_iso)
    os.makedirs(STORE, exist_ok=True)
    with open(LEDGER, "a") as f:
        f.write(json.dumps(rec) + "\n")
    print(f"=== experiment '{label}': {rec['confidence']} ===")
    if rec["confidence"] != "VERIFIED":
        print("NOT PROVEN, so nothing is claimed as verified. Reasons:")
        for r in rec["reasons"]:
            print(f"  - {r}")
    fr_b, fr_a = rec["first_request_before"], rec["first_request_after"]
    if fr_b is not None and fr_a is not None:
        print(f"first-request median  {mt.fmt(fr_b)} -> {mt.fmt(fr_a)} tokens "
              f"({rec['floor_reduction_tokens']:+,} per call)")
    print(f"one record appended to {LEDGER}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("action", choices=["start", "end"])
    ap.add_argument("label")
    ap.add_argument("--root", default=os.path.expanduser("~/.claude/projects"))
    ap.add_argument("--days", type=float, default=30)
    a = ap.parse_args()
    if not os.path.isdir(a.root):
        print(f"NO DATA: {a.root} does not exist.")
        return 2
    import time
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%S%z") or time.strftime("%Y-%m-%dT%H:%M:%S")
    if a.action == "start":
        return cmd_start(a.label, a.root, a.days, now_iso)
    return cmd_end(a.label, a.root, a.days, now_iso)


if __name__ == "__main__":
    import sys
    sys.exit(main())
