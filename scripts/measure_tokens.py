#!/usr/bin/env python3
"""
measure_tokens.py: real token telemetry for Claude Code, read from the
session transcripts on disk.

WHY THIS IS EVIDENCE AND NOT AN ESTIMATE
----------------------------------------
Claude Code writes one JSONL file per session under ~/.claude/projects/.
Every assistant message in it carries the `usage` object the API returned:
input_tokens, cache_creation_input_tokens, cache_read_input_tokens and
output_tokens. Those are the counters billing is computed from. This script
reads them and does arithmetic. It does not model, guess, or extrapolate.

Anything this script cannot measure is reported as NO DATA rather than
filled in with a plausible number.

THE METRICS, AND WHAT EACH ONE ANSWERS
--------------------------------------
1. PREAMBLE COST (the startup weight)
   The first assistant message of a session has read exactly one thing: the
   always-loaded context (system prompt, CLAUDE.md, plugin and MCP listings,
   session-start hook output) plus the user's opening message. So
   input + cache_creation + cache_read on that first message is a direct
   measurement of what every later call in that session also pays for.
   This is the number that moves when you prune plugins or diet CLAUDE.md.

2. CACHE HIT RATIO
   cache_read / (cache_read + cache_creation + input), over the session.
   High is good: it means the prefix stayed stable and was re-read cheaply.
   A low ratio on a long session means something kept busting the prefix.

3. EFFECTIVE INPUT COST
   Cache reads bill at 0.1x base input and 5-minute cache writes at 1.25x
   (published Anthropic prompt-caching multipliers). Weighting the raw
   counters by those multipliers gives a single comparable number:
       effective = input + 1.25*cache_creation + 0.1*cache_read
   Use it to compare two sessions honestly, since raw token totals flatter
   a session that happened to re-read a lot of cache.

4. WASTE SIGNALS
   Reported per session, each one a ratio a human can act on:
   - rewrite_ratio: cache_creation / cache_read. Above ~0.5 on a long
     session means the prefix was being rebuilt repeatedly. Usual causes:
     config edited mid-session, model switched, or long idle gaps past the
     cache TTL.
   - output_share: output tokens as a share of effective cost. High means
     verbosity is the problem, not context size.
   - preamble_share: preamble cost times number of calls, over total.
     High means the always-loaded context dominates and pruning pays more
     than any other lever.

USAGE
  python3 measure_tokens.py                  # summary across all sessions
  python3 measure_tokens.py --days 30        # window it
  python3 measure_tokens.py --baseline FILE  # write a baseline snapshot
  python3 measure_tokens.py --compare FILE   # compare now against baseline
  python3 measure_tokens.py --sessions       # per session, worst first
"""

import argparse
import json
import os
import statistics
import sys
import time

# Published Anthropic prompt caching multipliers, relative to base input price.
CACHE_WRITE_5M = 1.25
CACHE_READ = 0.1


def iter_session_files(root, cutoff):
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            if not fn.endswith(".jsonl"):
                continue
            fp = os.path.join(dirpath, fn)
            try:
                if os.path.getmtime(fp) < cutoff:
                    continue
            except OSError:
                continue
            yield fp


def read_session(fp):
    """Return per-session totals, or None when the file carries no usage data."""
    first = None
    tot = {"input": 0, "write": 0, "read": 0, "output": 0}
    calls = 0
    started = None
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
            inp = usage.get("input_tokens") or 0
            wr = usage.get("cache_creation_input_tokens") or 0
            rd = usage.get("cache_read_input_tokens") or 0
            out = usage.get("output_tokens") or 0
            if inp == 0 and wr == 0 and rd == 0:
                continue
            calls += 1
            tot["input"] += inp
            tot["write"] += wr
            tot["read"] += rd
            tot["output"] += out
            if first is None:
                first = inp + wr + rd
                started = rec.get("timestamp")
    if calls == 0:
        return None
    eff = tot["input"] + CACHE_WRITE_5M * tot["write"] + CACHE_READ * tot["read"]
    denom = tot["read"] + tot["write"] + tot["input"]
    return {
        "file": fp,
        "calls": calls,
        "preamble": first or 0,
        "started": started,
        "hit_ratio": (tot["read"] / denom) if denom else 0.0,
        "rewrite_ratio": (tot["write"] / tot["read"]) if tot["read"] else None,
        "effective_input": eff,
        "output": tot["output"],
        "output_share": (tot["output"] / eff) if eff else None,
        **tot,
    }


def collect(root, days):
    cutoff = time.time() - days * 86400
    out = []
    for fp in iter_session_files(root, cutoff):
        s = read_session(fp)
        if s:
            out.append(s)
    return out


def summarize(sessions):
    if not sessions:
        return None
    pre = sorted(s["preamble"] for s in sessions if s["preamble"] > 0)
    hits = [s["hit_ratio"] for s in sessions if s["calls"] >= 3]
    return {
        "sessions": len(sessions),
        "total_calls": sum(s["calls"] for s in sessions),
        "preamble_median": statistics.median(pre) if pre else None,
        "preamble_mean": statistics.mean(pre) if pre else None,
        "preamble_p90": pre[int(len(pre) * 0.9)] if len(pre) >= 10 else None,
        "preamble_n": len(pre),
        "hit_ratio_median": statistics.median(hits) if hits else None,
        "effective_input_total": sum(s["effective_input"] for s in sessions),
        "output_total": sum(s["output"] for s in sessions),
    }


def fmt(n):
    if n is None:
        return "NO DATA"
    if isinstance(n, float) and n < 2:
        return f"{n:.3f}"
    return f"{int(round(n)):,}"


def print_summary(sm, label):
    print(f"=== {label} ===")
    if not sm:
        print("NO DATA: no session transcripts carried usage counters.")
        return
    print(f"sessions measured        {fmt(sm['sessions'])}")
    print(f"assistant calls          {fmt(sm['total_calls'])}")
    print(f"preamble median          {fmt(sm['preamble_median'])} tokens per call")
    print(f"preamble mean            {fmt(sm['preamble_mean'])}")
    print(f"preamble p90             {fmt(sm['preamble_p90'])}")
    print(f"cache hit ratio median   {fmt(sm['hit_ratio_median'])}")
    print(f"effective input total    {fmt(sm['effective_input_total'])}")
    print(f"output total             {fmt(sm['output_total'])}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--root", default=os.path.expanduser("~/.claude/projects"))
    ap.add_argument("--days", type=float, default=90)
    ap.add_argument("--baseline", help="write a baseline snapshot to this path")
    ap.add_argument("--compare", help="compare current window against this baseline")
    ap.add_argument("--sessions", action="store_true", help="per-session detail")
    ap.add_argument("--worst", type=int, default=10)
    a = ap.parse_args()

    if not os.path.isdir(a.root):
        print(f"NO DATA: {a.root} does not exist.", file=sys.stderr)
        return 2

    sessions = collect(a.root, a.days)
    sm = summarize(sessions)
    print_summary(sm, f"MEASURED, last {a.days:g} days")

    if a.sessions and sessions:
        print("\n=== waste signals, highest preamble first ===")
        print(f"{'preamble':>10} {'calls':>6} {'hit':>6} {'rewrite':>8}  session")
        for s in sorted(sessions, key=lambda x: -x["preamble"])[: a.worst]:
            rw = "NO DATA" if s["rewrite_ratio"] is None else f"{s['rewrite_ratio']:.2f}"
            print(
                f"{s['preamble']:>10,} {s['calls']:>6} "
                f"{s['hit_ratio']:>6.3f} {rw:>8}  {os.path.basename(s['file'])[:28]}"
            )

    if a.baseline and sm:
        snap = {"measured_at": time.strftime("%Y-%m-%d %H:%M:%S"), "window_days": a.days,
                "summary": sm}
        with open(a.baseline, "w") as f:
            json.dump(snap, f, indent=2)
        print(f"\nbaseline written: {a.baseline}")

    if a.compare:
        try:
            with open(a.compare) as f:
                old = json.load(f)
        except OSError as e:
            print(f"NO DATA: cannot read baseline ({e})", file=sys.stderr)
            return 2
        o = old["summary"]
        print(f"\n=== CHANGE vs baseline taken {old['measured_at']} ===")
        for k, unit in (("preamble_median", "tokens per call"),
                        ("preamble_mean", "tokens per call"),
                        ("hit_ratio_median", "ratio")):
            a_v, b_v = o.get(k), sm.get(k)
            if a_v is None or b_v is None:
                print(f"{k:<22} NO DATA")
                continue
            d = b_v - a_v
            pct = (d / a_v * 100) if a_v else 0
            print(f"{k:<22} {fmt(a_v)} -> {fmt(b_v)}  ({d:+,.0f}, {pct:+.1f}%) {unit}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
