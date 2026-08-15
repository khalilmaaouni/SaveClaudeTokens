#!/usr/bin/env python3
"""
pricing.py: turn a measured token saving into an honest USD figure.

WHY THIS IS SEPARATE FROM THE METER
The meter (measure_tokens.py) deliberately carries no price table: a hardcoded
price goes stale and silently corrupts every later comparison. This module adds
dollars back the only honest way:

- prices come from a VERSIONED, DATED snapshot (data/pricing.json), not code;
- each model's saving is priced at THAT model's own input rate, never a blended
  or substituted rate;
- a model absent from the snapshot goes into an explicit UNPRICED bucket, and its
  token saving still stands;
- if the snapshot is older than its own stale_after_days, the whole thing
  degrades to NO PRICE DATA while the token saving is still reported.

So a dollar figure here always names its snapshot, and the absence of a price is
a visible state, never a guess. The saving is measured either way.
"""

import argparse
import json
import os

from measure_tokens import iter_session_files, split_writes, net_saving

DEFAULT_PRICING = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "..", "data", "pricing.json")


def load_pricing(path=DEFAULT_PRICING):
    with open(path) as f:
        p = json.load(f)
    if "snapshot" not in p or "models" not in p:
        raise ValueError("pricing.json missing snapshot or models")
    return p


def normalize_model(mid):
    """Map a raw record model id to a pricing-table key.

    Exact match wins; otherwise strip a trailing -YYYYMMDD date snapshot
    (claude-haiku-4-5-20251001 -> claude-haiku-4-5). Anything else is returned
    unchanged and will land in the unpriced bucket rather than be mispriced.
    """
    if not mid:
        return "<none>"
    parts = mid.rsplit("-", 1)
    if len(parts) == 2 and len(parts[1]) == 8 and parts[1].isdigit():
        return parts[0]
    return mid


def days_between(a_iso, b_iso):
    """Whole days from a_iso to b_iso, both YYYY-MM-DD. No clock, no Date.now:
    the caller supplies today at the CLI edge, so this stays a pure function."""
    import datetime
    a = datetime.date.fromisoformat(a_iso)
    b = datetime.date.fromisoformat(b_iso)
    return (b - a).days


def saving_by_model(root, days):
    """Walk the transcripts and return net-saving units bucketed by model.

    Uses the meter's own file walk, write split, and canonical net_saving
    formula, so this is a per-model VIEW of the same number, not a second
    implementation of it.
    """
    import time
    cutoff = time.time() - days * 86400
    read = {}
    w5 = {}
    w1 = {}
    for fp in iter_session_files(root, cutoff):
        with open(fp, "r", errors="ignore") as f:
            for line in f:
                if '"usage"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = rec.get("message") or {}
                usage = msg.get("usage") or rec.get("usage")
                if not isinstance(usage, dict):
                    continue
                m = normalize_model(msg.get("model"))
                rd = usage.get("cache_read_input_tokens") or 0
                a, b, _ = split_writes(usage)
                if rd or a or b:
                    read[m] = read.get(m, 0) + rd
                    w5[m] = w5.get(m, 0) + a
                    w1[m] = w1.get(m, 0) + b
    out = {}
    for m in read:
        out[m] = net_saving(read[m], w5.get(m, 0), w1.get(m, 0))
    return out


def price_saving(by_model, pricing, today):
    """Price a per-model saving. today is 'YYYY-MM-DD', supplied by the caller.

    Returns a dict that always carries the token total; usd is None (a NO PRICE
    DATA state) when the snapshot is stale, and unpriced_units holds every unit
    whose model is not in the snapshot.
    """
    total_units = sum(by_model.values())
    age = days_between(pricing["snapshot"], today)
    stale_after = pricing.get("stale_after_days")
    stale = stale_after is not None and age > stale_after
    if stale:
        return {"status": "NO_PRICE_DATA", "reason": f"pricing snapshot is {age} days old "
                f"(stale after {stale_after}); refresh data/pricing.json",
                "snapshot": pricing["snapshot"], "saved_units": total_units, "usd": None,
                "unpriced_units": total_units, "rows": []}
    models = pricing["models"]
    usd = 0.0
    priced_units = 0.0
    unpriced_units = 0.0
    rows = []
    for m, units in sorted(by_model.items(), key=lambda kv: -kv[1]):
        rate = models.get(m, {}).get("input")
        if rate is None:
            unpriced_units += units
            rows.append({"model": m, "units": units, "usd": None})
        else:
            row_usd = units / 1e6 * rate
            usd += row_usd
            priced_units += units
            rows.append({"model": m, "units": units, "usd": row_usd, "rate": rate})
    return {"status": "OK", "snapshot": pricing["snapshot"], "age_days": age,
            "usd": usd, "saved_units": total_units, "priced_units": priced_units,
            "unpriced_units": unpriced_units, "rows": rows}


def main():
    ap = argparse.ArgumentParser(description="Honest per-model USD for a measured saving.")
    ap.add_argument("--root", default=os.path.expanduser("~/.claude/projects"))
    ap.add_argument("--days", type=float, default=90)
    ap.add_argument("--pricing", default=DEFAULT_PRICING)
    ap.add_argument("--today", default=None, help="YYYY-MM-DD; default is the OS date")
    a = ap.parse_args()
    if not os.path.isdir(a.root):
        print(f"NO DATA: {a.root} does not exist.")
        return 2
    today = a.today
    if today is None:
        import time
        today = time.strftime("%Y-%m-%d")
    pricing = load_pricing(a.pricing)
    res = price_saving(saving_by_model(a.root, a.days), pricing, today)
    # Same order as cli.prices, and for the same reason: this module is the
    # OTHER door onto the same figures, and it used to open with a heading
    # and a six-figure "priced total" whose caveat sat five lines below it.
    # A reader takes the number and leaves the caveat behind, so the caveat
    # goes first and the summed headline goes away. The per-model rows stay:
    # those are genuinely useful when choosing a model.
    print("This is not money you saved.")
    print("Claude Code's caching (Anthropic's own mechanism, not Token Shield) "
          "kept these tokens off the wire for you. No bill went down: on a "
          "subscription you pay the same either way.")
    print(f"=== USD-equivalent of the native caching saving, last {a.days:g} days ===")
    print(f"pricing snapshot   {res['snapshot']}")
    if res["status"] == "NO_PRICE_DATA":
        print(f"NO PRICE DATA      {res['reason']}")
        print(f"saving still measured  {res['saved_units']/1e9:.2f}B base-input units")
        return 0
    for r in res["rows"]:
        u = f"${r['usd']:,.2f}" if r["usd"] is not None else "UNPRICED"
        print(f"  {r['model']:<28} {r['units']/1e9:7.3f}B units   {u}")
    print(f"priced             {res['priced_units']/1e9:.2f}B units, API-equivalent, "
          f"per model above")
    if res["unpriced_units"]:
        print(f"unpriced           {res['unpriced_units']/1e9:.3f}B units at models not in "
              f"the snapshot (saving measured, not priced)")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
