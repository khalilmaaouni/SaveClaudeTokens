#!/usr/bin/env python3
"""
measure_tokens.py: real token telemetry for Claude Code, read from the
session transcripts on disk.

WHY THIS IS EVIDENCE AND NOT AN ESTIMATE
----------------------------------------
Claude Code writes one JSONL file per session under ~/.claude/projects/.
Every assistant message in it carries the `usage` object the API returned:
input_tokens, cache_creation (5 minute and 1 hour write classes),
cache_read_input_tokens and output_tokens. Those are the counters billing is
computed from. This script reads them and does arithmetic. It does not model,
guess, or extrapolate.

Anything this script cannot measure is reported as NO DATA rather than filled
in with a plausible number. That rule is the whole point: a meter that
invents a number is worse than no meter.

THE METRICS, AND WHAT EACH ONE ANSWERS
--------------------------------------
1. FIRST REQUEST CONTEXT (the startup weight)
   The first assistant message of a session has read the always-loaded
   context (system prompt, CLAUDE.md, plugin and skill listings, MCP tool
   listings and instructions, session-start hook output) plus the user's
   opening message. So input + cache_creation + cache_read on that message
   measures the floor every later call in that session also pays.

   It is NOT a pure measurement of the always-loaded set alone, because the
   opening user message and any attachments ride along inside it. It is an
   upper bound on the always-loaded set and a direct measurement of what the
   session's first call actually cost. This is the number that moves when you
   prune plugins, prune MCP servers, quiet a hook, or diet CLAUDE.md.

2. FIRST REQUEST SHARE
   first_request * calls / total raw tokens. The share of everything the
   session read that was the startup floor being paid again on every call.
   High means pruning the always-loaded set beats every other lever.

3. CACHE HIT RATIO
   cache_read / (cache_read + cache_write + input), over the session. High is
   good: the prefix stayed stable and was re-read at the cheap rate.

4. NORMALIZED INPUT COST
   Cache writes bill at 1.25x base input for the 5 minute TTL and 2x for the
   1 hour TTL; cache reads bill at 0.1x (published Anthropic prompt caching
   multipliers). So:
       normalized = input + 1.25*write_5m + 2.0*write_1h + 0.1*read
   This is a relative input-cost measure in base-input units, not a dollar
   figure: it carries no model price table, because a hardcoded price goes
   stale and a stale price silently corrupts every later comparison.

   Transcripts that do not carry the split write classes get NO DATA here
   rather than an assumed 5 minute price.

5. WASTE SIGNALS, per session
   - rewrite_ratio: cache_write / cache_read. A SIGNAL, not proof. Ordinary
     conversation growth also writes cache, so a high ratio means "look
     here", not "the prefix was rebuilt". Measured causes worth checking:
     a model switch during the session (this script counts distinct models),
     a long idle gap past the cache TTL, or a change to the toolset or system
     prompt (settings, hooks, MCP config) mid-session.
   - output_to_input: output tokens over normalized input units. A ratio for
     comparing sessions, NOT a share of spend: output bills at its own
     per-model rate, which this script deliberately does not know.
   - subagent share: subagents run their own conversation with their own
     cache. Isolating exploration in a subagent can be cheaper than letting
     it flood the parent context, and can also be pure overhead for a task a
     script should have done. The number tells you which case you are in.

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
CACHE_WRITE_1H = 2.0
CACHE_READ = 0.1

# Files the walk could not open and lines that failed to decode as JSON (a
# truncated write, a corrupt record). Both were silently skipped before; now
# they are counted so a low session count can be told apart from a real
# absence of data. Reset at the start of each collect() call, so the counts
# summarize() reports describe that one walk, not a running total across calls.
SKIP_COUNTS = {"files": 0, "lines": 0}


def skip_counts():
    """A copy of the current skip counters, valid after the most recent collect()."""
    return dict(SKIP_COUNTS)


def net_saving(read, write_5m, write_1h):
    """Net caching saving in base-input units, for a bucket of counters.

    The canonical formula, defined once so every view (the dashboard, the
    per-model pricing walk) prices the same number. It is what caching earns on
    reads (0.9x each) minus the premium it pays to write the cache (0.25x extra
    at the 5 minute TTL, 1.0x extra at the 1 hour TTL): exactly uncached cost
    minus cached cost for the same token flow. token_shield.savings_breakdown
    computes the aggregate the same way; a test locks the two together.
    """
    gross = (1.0 - CACHE_READ) * read
    write_premium = (CACHE_WRITE_5M - 1.0) * write_5m + (CACHE_WRITE_1H - 1.0) * write_1h
    return gross - write_premium


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
                SKIP_COUNTS["files"] += 1
                continue
            yield fp


def split_writes(usage):
    """Return (write_5m, write_1h, write_unsplit).

    The nested cache_creation object carries the two TTL classes. Where it is
    absent the flat counter still gives a total, but the TTL split is unknown,
    so the tokens land in write_unsplit and normalized cost becomes NO DATA.

    Measured on one machine: the nested object was present on 11,760 of 11,760
    records, and on 8 of them the flat counter read 0 while the nested fields
    summed to 2,001. So the nested object is preferred where both exist.
    """
    cc = usage.get("cache_creation")
    if isinstance(cc, dict):
        w5 = cc.get("ephemeral_5m_input_tokens") or 0
        w1 = cc.get("ephemeral_1h_input_tokens") or 0
        if w5 or w1:
            return w5, w1, 0
    # No nested object, or a nested object accounting for nothing. The flat
    # counter is all there is: zero stays a measured zero, and anything else
    # has an unknown TTL class, so it must not be priced.
    return 0, 0, usage.get("cache_creation_input_tokens") or 0


def read_session(fp):
    """Return per-session totals, or None when the file carries no usage data."""
    first = None
    started = None
    tot = {"input": 0, "write_5m": 0, "write_1h": 0, "write_unsplit": 0,
           "read": 0, "output": 0}
    calls = 0
    sub_calls = 0
    sub_output = 0
    models = set()

    try:
        f = open(fp, "r", errors="ignore")
    except OSError:
        SKIP_COUNTS["files"] += 1
        return None

    with f:
        for line in f:
            if '"usage"' not in line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                SKIP_COUNTS["lines"] += 1
                continue
            msg = rec.get("message") or {}
            usage = msg.get("usage") or rec.get("usage")
            if not isinstance(usage, dict):
                continue
            inp = usage.get("input_tokens") or 0
            rd = usage.get("cache_read_input_tokens") or 0
            out = usage.get("output_tokens") or 0
            w5, w1, wu = split_writes(usage)
            if inp == 0 and rd == 0 and w5 == 0 and w1 == 0 and wu == 0:
                continue

            calls += 1
            tot["input"] += inp
            tot["write_5m"] += w5
            tot["write_1h"] += w1
            tot["write_unsplit"] += wu
            tot["read"] += rd
            tot["output"] += out

            is_sub = bool(rec.get("isSidechain"))
            if is_sub:
                sub_calls += 1
                sub_output += out
            else:
                model = msg.get("model")
                if model and not str(model).startswith("<"):
                    models.add(model)
                # The startup floor is the parent's first call. A subagent
                # starts its own context, so it never measures this session's.
                if first is None:
                    first = inp + w5 + w1 + wu + rd
                    started = rec.get("timestamp")

    if calls == 0:
        return None

    write_total = tot["write_5m"] + tot["write_1h"] + tot["write_unsplit"]
    raw_input = tot["input"] + write_total + tot["read"]

    # NO DATA rather than an assumed price when the TTL split is unavailable.
    if tot["write_unsplit"]:
        normalized = None
    else:
        normalized = (tot["input"]
                      + CACHE_WRITE_5M * tot["write_5m"]
                      + CACHE_WRITE_1H * tot["write_1h"]
                      + CACHE_READ * tot["read"])

    first = first or 0
    return {
        "file": fp,
        "calls": calls,
        "first_request": first,
        "started": started,
        "first_request_share": (first * calls / raw_input) if raw_input else None,
        "hit_ratio": (tot["read"] / raw_input) if raw_input else 0.0,
        "rewrite_ratio": (write_total / tot["read"]) if tot["read"] else None,
        "write_total": write_total,
        "raw_input": raw_input,
        "normalized_input": normalized,
        "output_to_input": (tot["output"] / normalized) if normalized else None,
        "models": len(models),
        "sub_calls": sub_calls,
        "sub_output": sub_output,
        **tot,
    }


def collect(root, days):
    cutoff = time.time() - days * 86400
    SKIP_COUNTS["files"] = 0
    SKIP_COUNTS["lines"] = 0
    out = []
    for fp in iter_session_files(root, cutoff):
        s = read_session(fp)
        if s:
            out.append(s)
    return out


def summarize(sessions):
    if not sessions:
        return None
    # A transcript with no parent-agent call is a subagent's own conversation,
    # not a session. Its tokens are real and stay in the totals, but it has no
    # startup floor of its own to measure, so it is excluded from those stats.
    parent = [s for s in sessions if s["first_request"] > 0]
    firsts = sorted(s["first_request"] for s in parent)
    hits = [s["hit_ratio"] for s in sessions if s["calls"] >= 3]
    shares = [s["first_request_share"] for s in parent
              if s["first_request_share"] is not None and s["calls"] >= 3]

    w5 = sum(s["write_5m"] for s in sessions)
    w1 = sum(s["write_1h"] for s in sessions)
    wu = sum(s["write_unsplit"] for s in sessions)
    out_total = sum(s["output"] for s in sessions)
    sub_out = sum(s["sub_output"] for s in sessions)

    priced = [s for s in sessions if s["normalized_input"] is not None]
    return {
        "sessions": len(sessions),
        "parent_sessions": len(parent),
        "subagent_transcripts": len(sessions) - len(parent),
        "total_calls": sum(s["calls"] for s in sessions),
        "first_request_median": statistics.median(firsts) if firsts else None,
        "first_request_mean": statistics.mean(firsts) if firsts else None,
        "first_request_p90": firsts[int(len(firsts) * 0.9)] if len(firsts) >= 10 else None,
        "first_request_n": len(firsts),
        "first_request_share_median": statistics.median(shares) if shares else None,
        "hit_ratio_median": statistics.median(hits) if hits else None,
        "input_total": sum(s["input"] for s in sessions),
        "read_total": sum(s["read"] for s in sessions),
        "write_5m_total": w5,
        "write_1h_total": w1,
        "write_unsplit_total": wu,
        "write_1h_share": (w1 / (w5 + w1)) if (w5 + w1) else None,
        "normalized_input_total": (sum(s["normalized_input"] for s in priced)
                                   if priced else None),
        "normalized_sessions": len(priced),
        "output_total": out_total,
        "subagent_output_total": sub_out,
        "subagent_output_share": (sub_out / out_total) if out_total else None,
        "subagent_calls": sum(s["sub_calls"] for s in sessions),
        "skipped_files": SKIP_COUNTS["files"],
        "skipped_lines": SKIP_COUNTS["lines"],
    }


def dominant_lever(sm):
    """Classify which lever the numbers support, as a key.

    One source for the thresholds so the dashboard and the exported note cannot
    disagree about what the same numbers mean. Each renderer maps the key to its
    own wording. Returns one of: nodata, shrink, cache, route, healthy.
    """
    share = sm.get("first_request_share_median")
    hit = sm.get("hit_ratio_median")
    sub = sm.get("subagent_output_share")
    if share is None and hit is None:
        return "nodata"
    if share is not None and share >= 0.30:
        return "shrink"
    if hit is not None and hit < 0.70:
        return "cache"
    if sub is not None and sub >= 0.40:
        return "route"
    return "healthy"


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
    print(f"transcripts measured       {fmt(sm['sessions'])} "
          f"({fmt(sm['parent_sessions'])} sessions, "
          f"{fmt(sm['subagent_transcripts'])} subagent transcripts)")
    print(f"assistant calls            {fmt(sm['total_calls'])}")
    print(f"first request median       {fmt(sm['first_request_median'])} tokens")
    print(f"first request mean         {fmt(sm['first_request_mean'])}")
    print(f"first request p90          {fmt(sm['first_request_p90'])}")
    print(f"first request share median {fmt(sm['first_request_share_median'])}")
    print(f"cache hit ratio median     {fmt(sm['hit_ratio_median'])}")
    print(f"cache read total           {fmt(sm['read_total'])}")
    print(f"cache write 5m total       {fmt(sm['write_5m_total'])}")
    print(f"cache write 1h total       {fmt(sm['write_1h_total'])}")
    print(f"cache write 1h share       {fmt(sm['write_1h_share'])}")
    if sm["write_unsplit_total"]:
        print(f"cache write unsplit        {fmt(sm['write_unsplit_total'])} "
              f"(TTL class absent, excluded from normalized cost)")
    if sm["normalized_input_total"] is None:
        print("normalized input total     NO DATA (no session carried the TTL split)")
    else:
        print(f"normalized input total     {fmt(sm['normalized_input_total'])} "
              f"base-input units, over {fmt(sm['normalized_sessions'])} transcripts")
    print(f"output total               {fmt(sm['output_total'])}")
    print(f"output from subagents      {fmt(sm['subagent_output_total'])} "
          f"({fmt(sm['subagent_output_share'])} share, "
          f"{fmt(sm['subagent_calls'])} calls)")
    print(f"skipped (unreadable)       {fmt(sm.get('skipped_files', 0))} files, "
          f"{fmt(sm.get('skipped_lines', 0))} lines")


# Baseline keys renamed in schema 2. Older snapshots stay readable, but the
# first_request family is NOT comparable across that boundary and the code
# refuses to print a delta for it rather than print a misleading one.
#
# Why: schema 1 took the first usage record of every transcript, including
# transcripts that are a subagent's own conversation. A subagent starts a
# smaller context, so those files dragged the median down. Measured on one
# machine over the same 90 day window: schema 1 saw 6,249 transcripts with a
# 41,898 token median, schema 2 saw the 229 actual sessions among them with an
# 85,021 token median. Same machine, same window, same counters. The metric
# changed, not the spend. Take a fresh baseline after upgrading.
SCHEMA = 2
LEGACY_KEYS = {
    "first_request_median": "preamble_median",
    "first_request_mean": "preamble_mean",
    "first_request_p90": "preamble_p90",
}
INCOMPARABLE_ACROSS_SCHEMA = set(LEGACY_KEYS)


def fmt_delta(a_v, b_v):
    """Format a change for the scale of the numbers being compared.

    Token counts and ratios share this table, and a ratio formatted as an
    integer prints every real move as +0. A percent against a zero baseline is
    undefined, so it prints NO DATA instead of a fabricated 0.0.
    """
    d = b_v - a_v
    small = abs(a_v) < 2 and abs(b_v) < 2
    ds = f"{d:+.3f}" if small else f"{d:+,.0f}"
    ps = "NO DATA" if a_v == 0 else f"{(d / a_v * 100):+.1f}%"
    return ds, ps


def baseline_get(old_summary, key):
    if key in old_summary:
        return old_summary[key], False
    legacy = LEGACY_KEYS.get(key)
    if legacy and legacy in old_summary:
        return old_summary[legacy], True
    return None, False


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
    # The window selects transcripts by file modification time, so a resumed
    # old session contributes its whole history. Say that rather than implying
    # every counted token was spent inside the window.
    print_summary(sm, f"MEASURED, transcripts touched in the last {a.days:g} days")

    if a.sessions and sessions:
        print("\n=== waste signals, highest first request first ===")
        print(f"{'first_req':>10} {'share':>6} {'calls':>6} {'hit':>6} "
              f"{'rewrite':>8} {'models':>7}  session")
        for s in sorted(sessions, key=lambda x: -x["first_request"])[: a.worst]:
            rw = "NO DATA" if s["rewrite_ratio"] is None else f"{s['rewrite_ratio']:.2f}"
            sh = "  n/a" if s["first_request_share"] is None else f"{s['first_request_share']:.3f}"
            print(
                f"{s['first_request']:>10,} {sh:>6} {s['calls']:>6} "
                f"{s['hit_ratio']:>6.3f} {rw:>8} {s['models']:>7}  "
                f"{os.path.basename(s['file'])[:24]}"
            )
        print("\nmodels above 1 means the session switched model mid-flight. "
              "Each model has its own cache, so that rebuilds from zero.")

    if a.baseline and sm:
        snap = {"measured_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "window_days": a.days, "schema": SCHEMA, "summary": sm}
        with open(a.baseline, "w") as f:
            json.dump(snap, f, indent=2)
        print(f"\nbaseline written: {a.baseline}")

    if a.compare:
        try:
            with open(a.compare) as f:
                old = json.load(f)
        except (OSError, ValueError) as e:
            print(f"NO DATA: cannot read baseline ({e})", file=sys.stderr)
            return 2
        if not isinstance(old, dict):
            print("NO DATA: baseline is not an object written by --baseline.",
                  file=sys.stderr)
            return 2
        o = old.get("summary")
        if not isinstance(o, dict):
            print("NO DATA: baseline carries no summary object.", file=sys.stderr)
            return 2
        print(f"\n=== CHANGE vs baseline taken {old.get('measured_at', 'NO DATA')} ===")
        try:
            old_days = float(old.get("window_days"))
        except (TypeError, ValueError):
            old_days = None
        if old_days is None:
            print("WARNING: baseline does not record its window length, so this "
                  "comparison may not be like-for-like.")
        elif old_days != float(a.days):
            print(f"WARNING: baseline covers {old_days:g} days, this run covers "
                  f"{a.days:g}. Different windows hold different sessions, so the "
                  f"deltas below are not a like-for-like comparison. Re-run with "
                  f"--days {old_days:g} to compare honestly.")
        old_schema = old.get("schema", 1)
        schema_mismatch = old_schema != SCHEMA
        if schema_mismatch:
            print(f"WARNING: baseline is schema {old_schema}, this script writes "
                  f"schema {SCHEMA}. The first_request family counted a different "
                  f"population before schema 2 (subagent transcripts were included), "
                  f"so those rows print NO DATA instead of a false delta. The cache "
                  f"and ratio rows below are unaffected. Take a fresh baseline.")
        used_legacy = False
        for k, unit in (("first_request_median", "tokens"),
                        ("first_request_mean", "tokens"),
                        ("first_request_share_median", "share"),
                        ("hit_ratio_median", "ratio"),
                        ("write_1h_share", "share")):
            if schema_mismatch and k in INCOMPARABLE_ACROSS_SCHEMA:
                print(f"{k:<28} NO DATA (not comparable across schema change)")
                continue
            a_v, legacy = baseline_get(o, k)
            used_legacy = used_legacy or legacy
            b_v = sm.get(k) if sm else None
            if not isinstance(a_v, (int, float)) or not isinstance(b_v, (int, float)):
                print(f"{k:<28} NO DATA")
                continue
            ds, ps = fmt_delta(a_v, b_v)
            print(f"{k:<28} {fmt(a_v)} -> {fmt(b_v)}  ({ds}, {ps}) {unit}")
        if used_legacy:
            print("\nnote: this baseline predates the first_request rename and was "
                  "read from its preamble_* keys. The two measure the same counters.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
