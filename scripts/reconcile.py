#!/usr/bin/env python3
"""
reconcile.py: an independent second parser, checked against measure_tokens.py
on live data.

WHY THIS EXISTS
---------------
docs/CLAIMS.md rows B3, B5, and B8 used to say their headline figures were
confirmed by "an independent second derivation (different code, same
transcripts)". No such code existed on disk (an audit found this twice, and
this script is the fix). It cannot replay those historical figures: the
transcript window churns by whole percents day to day (docs/CLAIMS.md records
a measured example, 85,021 tokens one day and 85,587 the next on the same
machine), so a second derivation run today can never reproduce a pinned
snapshot. Independence is checked meter versus meter, on whatever transcripts
are on disk right now, not against history.

This script parses the same ~/.claude/projects/*.jsonl transcripts as
measure_tokens.py, with its own code (stdlib only) and NOTHING imported from
measure_tokens.py, computes per session:
  - the first-request input total
  - whether the session's non-subagent messages carry more than one distinct
    model
then aggregates the median first-request total, the median first-request
share, and the count of multi-model sessions across the same day window, and
diffs those three numbers against a live run of measure_tokens.py.

POPULATION RULES MIRRORED FROM measure_tokens.py (must match measure_tokens.py
exactly, or the diff below measures definition drift instead of a code error;
line numbers below are measure_tokens.py at the time this script was written):
  - default root ~/.claude/projects, default 90 day window: measure_tokens.py:418-419
  - a session is one *.jsonl file, walked recursively, filtered by whole-file
    mtime against the window cutoff, not per-record time: measure_tokens.py:118-129
  - a line only counts if it contains the literal substring "usage" and
    parses as JSON: measure_tokens.py:174-181
  - usage lives at message.usage, falling back to the top-level record's
    usage: measure_tokens.py:182-185
  - input_tokens, cache_read_input_tokens read directly; cache_creation is
    read as the nested {ephemeral_5m_input_tokens, ephemeral_1h_input_tokens}
    object when either is nonzero, otherwise the flat
    cache_creation_input_tokens counter (unknown TTL class):
    measure_tokens.py:133-153, call site 189
  - a line with every counter at zero is not a call: measure_tokens.py:190-191
  - isSidechain marks a subagent call; subagent calls are excluded from the
    per-session model set and can never set first_request: measure_tokens.py:201-213
  - a parent (non-subagent) message's model is added to the session's model
    set unless it starts with "<" (an internal tag, not a real model id):
    measure_tokens.py:206-208
  - first_request is the FIRST non-subagent call's
    input + write_5m + write_1h + write_unsplit + cache_read: measure_tokens.py:211-213
  - a file with zero qualifying calls is not a session: measure_tokens.py:215-216
  - a "parent session" is one with first_request > 0 (had at least one
    non-subagent call); first_request_median is the median across parent
    sessions: measure_tokens.py:268, 286
  - first_request_share = first_request * calls / raw_input, computed only
    for parent sessions with calls >= 3; the reported figure is the median
    across those sessions: measure_tokens.py:236, 271-272, 290

EXIT CODES
  0  every compared field drifts under the tolerance (default 0.5 percent)
  1  a compared field drifted at or past the tolerance
  2  NO DATA: no session transcripts found under --root in the --days window

USAGE
  python3 reconcile.py --days 30
"""

import argparse
import json
import os
import pathlib
import re
import statistics
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
DEFAULT_MEASURE_TOKENS = HERE / "measure_tokens.py"
DRIFT_TOLERANCE = 0.005


def _split_writes(usage):
    """Independent reimplementation of measure_tokens.split_writes
    (measure_tokens.py:133-153): nested cache_creation TTL split wins when
    either class is nonzero, otherwise the flat counter with an unknown TTL
    class."""
    cc = usage.get("cache_creation")
    if isinstance(cc, dict):
        w5 = cc.get("ephemeral_5m_input_tokens") or 0
        w1 = cc.get("ephemeral_1h_input_tokens") or 0
        if w5 or w1:
            return w5, w1, 0
    return 0, 0, usage.get("cache_creation_input_tokens") or 0


def parse_session(path):
    """One *.jsonl file in, the fields reconcile.py compares out, or None
    when the file has no qualifying call. Independent reimplementation of
    the walk in measure_tokens.read_session (measure_tokens.py:156-247);
    see the population rules block above for the exact mirrored behavior."""
    first_request = None
    calls = 0
    total_input = 0
    total_read = 0
    total_write = 0
    models = set()

    try:
        fh = open(path, "r", errors="ignore")
    except OSError:
        return None

    with fh:
        for line in fh:
            if "usage" not in line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            message = rec.get("message") or {}
            usage = message.get("usage") or rec.get("usage")
            if not isinstance(usage, dict):
                continue
            inp = usage.get("input_tokens") or 0
            read = usage.get("cache_read_input_tokens") or 0
            w5, w1, wu = _split_writes(usage)
            if inp == 0 and read == 0 and w5 == 0 and w1 == 0 and wu == 0:
                continue

            calls += 1
            total_input += inp
            total_read += read
            total_write += w5 + w1 + wu

            if not rec.get("isSidechain"):
                model = message.get("model")
                if model and not str(model).startswith("<"):
                    models.add(model)
                if first_request is None:
                    first_request = inp + w5 + w1 + wu + read

    if calls == 0:
        return None

    raw_input = total_input + total_write + total_read
    share = None
    if first_request and calls >= 3 and raw_input:
        share = first_request * calls / raw_input

    return {
        "first_request": first_request,  # None: file had no non-subagent call
        "calls": calls,
        "share": share,
        "multi_model": len(models) > 1,
    }


def collect_own(root, days):
    """Walk root for *.jsonl files touched inside the day window and parse
    each one. Returns the list of per-session dicts (parse_session results,
    unparseable files dropped)."""
    cutoff = time.time() - days * 86400
    root_path = pathlib.Path(root)
    sessions = []
    if not root_path.is_dir():
        return sessions
    for path in root_path.rglob("*.jsonl"):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime < cutoff:
            continue
        s = parse_session(path)
        if s:
            sessions.append(s)
    return sessions


def summarize_own(sessions):
    """The three comparable fields, computed the independent way."""
    parents = [s for s in sessions
               if s["first_request"] is not None and s["first_request"] > 0]
    firsts = sorted(s["first_request"] for s in parents)
    shares = [s["share"] for s in parents if s["share"] is not None]
    return {
        "session_count": len(sessions),
        "first_request_median": statistics.median(firsts) if firsts else None,
        "first_request_share_median": statistics.median(shares) if shares else None,
        "multi_model_count": sum(1 for s in sessions if s["multi_model"]),
    }


def run_measure_tokens(root, days, measure_tokens_path):
    """Shell out to measure_tokens.py over the same root and window. It has
    no --json flag (confirmed by reading the script before writing this
    one), so its stdout is parsed as text. --worst is set high enough to
    print every session's row, not just the top offenders, since the
    multi-model count needs the whole population."""
    args = [sys.executable, str(measure_tokens_path),
            "--root", str(root), "--days", str(days),
            "--sessions", "--worst", "100000000"]
    proc = subprocess.run(args, capture_output=True, text=True)
    return proc.returncode, proc.stdout


def parse_measure_tokens_output(text):
    """Pull the three comparable fields out of measure_tokens.py's stdout.

    The two summary lines are matched by their label text. The per-session
    table (printed by --sessions) is column-formatted with fixed widths
    (measure_tokens.py's --sessions block: first_req 10, share 6, calls 6,
    hit 6, rewrite 8, models 7, two spaces, then the session filename), so
    the models column is sliced by character position rather than split on
    whitespace: a "NO DATA" rewrite value contains an internal space that
    would otherwise misalign a plain .split() reader.
    """
    lines = text.splitlines()
    result = {"first_request_median": None, "first_request_share_median": None,
              "multi_model_count": None}

    for line in lines:
        m = re.match(r"^first request median\s+(NO DATA|[\d,]+)\s+tokens\s*$", line)
        if m:
            v = m.group(1)
            result["first_request_median"] = None if v == "NO DATA" else float(v.replace(",", ""))
            continue
        m = re.match(r"^first request share median\s+(NO DATA|[\d.]+)\s*$", line)
        if m:
            v = m.group(1)
            result["first_request_share_median"] = None if v == "NO DATA" else float(v)
            continue

    header_idx = None
    for i, l in enumerate(lines):
        stripped = l.strip()
        if stripped.startswith("first_req") and stripped.endswith("session"):
            header_idx = i
            break

    if header_idx is not None:
        multi = 0
        for line in lines[header_idx + 1:]:
            if not line.strip() or line.startswith("models above"):
                break
            models_field = line[41:48].strip()
            try:
                if int(models_field) > 1:
                    multi += 1
            except ValueError:
                continue
        result["multi_model_count"] = multi

    return result


def compare(own, mt, tol=DRIFT_TOLERANCE):
    """Field by field diff. Returns (all_ok, rows); each row is
    (name, own_value, mt_value, abs_drift_or_None, rel_drift_or_None, ok)."""
    fields = ["first_request_median", "first_request_share_median", "multi_model_count"]
    rows = []
    all_ok = True
    for name in fields:
        a = own.get(name)
        b = mt.get(name)
        if a is None and b is None:
            rows.append((name, a, b, 0.0, 0.0, True))
            continue
        if a is None or b is None:
            rows.append((name, a, b, None, None, False))
            all_ok = False
            continue
        abs_drift = abs(a - b)
        rel_drift = abs_drift / abs(b) if b else (0.0 if a == b else float("inf"))
        ok = rel_drift < tol
        all_ok = all_ok and ok
        rows.append((name, a, b, abs_drift, rel_drift, ok))
    return all_ok, rows


def _fmt(v):
    if v is None:
        return "NO DATA"
    if isinstance(v, float) and v < 2:
        return f"{v:.3f}"
    return f"{v:,.0f}"


def print_table(rows):
    print(f"{'field':<30} {'reconcile.py':>16} {'measure_tokens.py':>18} "
          f"{'abs drift':>12} {'rel drift':>10}  status")
    for name, a, b, abs_d, rel_d, ok in rows:
        abs_s = "NO DATA" if abs_d is None else f"{abs_d:,.3f}"
        rel_s = "NO DATA" if rel_d is None else f"{rel_d * 100:.3f}%"
        status = "OK" if ok else "DRIFT"
        print(f"{name:<30} {_fmt(a):>16} {_fmt(b):>18} {abs_s:>12} {rel_s:>10}  {status}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    ap.add_argument("--root", default=os.path.expanduser("~/.claude/projects"))
    ap.add_argument("--days", type=float, default=30)
    ap.add_argument("--measure-tokens", default=str(DEFAULT_MEASURE_TOKENS),
                     help="path to measure_tokens.py to reconcile against (test hook)")
    ap.add_argument("--tolerance", type=float, default=DRIFT_TOLERANCE)
    a = ap.parse_args()

    own_sessions = collect_own(a.root, a.days)
    if not own_sessions:
        print(f"NO DATA: no session transcripts under {a.root} in the last {a.days:g} days.",
              file=sys.stderr)
        return 2

    own = summarize_own(own_sessions)
    print(f"=== reconcile.py, independent parse of {a.root}, last {a.days:g} days ===")
    print(f"sessions parsed independently: {own['session_count']}")

    returncode, stdout = run_measure_tokens(a.root, a.days, a.measure_tokens)
    if returncode == 2:
        print("NO DATA: measure_tokens.py found no transcripts either.", file=sys.stderr)
        return 2
    mt = parse_measure_tokens_output(stdout)

    print()
    ok, rows = compare(own, mt, tol=a.tolerance)
    print_table(rows)
    print()
    if ok:
        print(f"RECONCILED: every compared field drifts under {a.tolerance * 100:.1f} percent.")
        return 0
    print(f"NOT RECONCILED: a compared field drifted {a.tolerance * 100:.1f} percent or more.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
