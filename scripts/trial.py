#!/usr/bin/env python3
"""
trial.py: the zero install look at your own token usage.

WHY THIS EXISTS
----------------
A stranger who has never heard of Token Shield should be able to run one
command, install nothing, and see an honest read of their own Claude Code
usage. This script is that command: `python3 scripts/trial.py`, run straight
out of a git checkout. It reads only the local session transcripts under
~/.claude/projects, the same files measure_tokens.py and token_shield.py
already read, and it writes nothing anywhere.

It reuses measure_tokens.py (the measurement core) and token_shield.py (the
savings math and lever classification) for every number shown here. This
script adds no formula of its own: a second copy of the token math is the
exact failure this script exists to prevent.

LABELS, KEPT SEPARATE (see CLAUDE.md's Invariants section)
  MEASURED   counted from this machine's own transcripts, right now.
  ESTIMATED  a projection built from MEASURED numbers (the opportunity line).
  NATIVE     Anthropic's own prompt-caching saving. Attributed to Anthropic,
             never claimed by this tool, never shown in dollars.
No price table ships here, so nothing in this output is ever a dollar figure.

NO DATA BEATS A GUESS
No transcripts, unreadable transcripts, or too little data print a plain
NO DATA line naming what was missing and what to do about it. A malformed
transcript is a named skip, never a crash; the rest still measures.

USAGE
  python3 trial.py
  python3 trial.py --root PATH --days N
"""

import argparse
import os
import sys

import measure_tokens as mt
import token_shield as ts

DEFAULT_ROOT = os.path.expanduser("~/.claude/projects")
DEFAULT_DAYS = 30


def run(root, days, out=None):
    """Print the trial read to `out` (defaults to sys.stdout). Read only:
    this function never opens a file for writing and never deletes anything.
    Returns an exit code; never raises on bad input, a malformed transcript
    just becomes a named skip."""
    out = out or sys.stdout

    if not os.path.isdir(root):
        print(f"NO DATA: no Claude Code transcripts found at {root}.", file=out)
        print("Use Claude Code for a session or two, then run this again.", file=out)
        return 0

    # Measured at 21 seconds of total silence on a real machine, reported at
    # 36 on a longer history. This is the FIRST thing a stranger runs, before
    # they have any reason to trust the project, and a blank terminal reads as
    # a hang. cli.py summary already prints a line like this before its own
    # scan; the trial needed it more and did not have it. stderr, not stdout,
    # so anything piping the reading stays clean.
    print(f"Reading your Claude Code transcripts under {root} (last {days:g} "
          f"days). On a long history this takes up to a minute.", file=sys.stderr)
    sessions = mt.collect(root, days)
    sm = mt.summarize(sessions)
    skip = mt.skip_counts()

    if not sm:
        print(f"NO DATA: {root} exists but carried no usage counters in the "
              f"last {days:g} days.", file=out)
        print("Use Claude Code for a session or two, then run this again.", file=out)
        if skip["files"] or skip["lines"]:
            print(f"(along the way, skipped {skip['files']} unreadable file(s) "
                  f"and {skip['lines']} unreadable line(s))", file=out)
        return 0

    print("Token Shield trial run: zero install, reads only, nothing sent anywhere", file=out)
    # The labels carry the whole honesty claim of this product, and they used
    # to appear with no legend anywhere on screen. The module docstring
    # defines them, which nobody reading a terminal has open.
    print("MEASURED = counted from your own machine. NATIVE = Anthropic's own "
          "caching, not this tool. ESTIMATED = a projection.", file=out)
    # Sessions first: a person has sessions, and transcripts are only the
    # files those sessions happen to be stored in. This led with transcripts,
    # which is the number that means least to the reader.
    print(f"MEASURED  {mt.fmt(sm['parent_sessions'])} sessions "
          f"({mt.fmt(sm['sessions'])} transcript files), "
          f"{mt.fmt(sm['total_calls'])} calls, last {days:g} days", file=out)
    if skip["files"] or skip["lines"]:
        print(f"          skipped {skip['files']} unreadable file(s) and "
              f"{skip['lines']} unreadable line(s); the rest still measured", file=out)

    # One quantity, one format. This printed "0.365 share of everything read"
    # here and "36% of everything a session reads" seven lines below, and a
    # reader has no way to tell those are the same fact. The percentage is the
    # readable one, so both places use it.
    share = sm.get("first_request_share_median")
    share_txt = (f"{share * 100:.0f}% of everything read"
                 if isinstance(share, (int, float)) and not isinstance(share, bool)
                 else "NO DATA on its share of everything read")
    print(f"MEASURED  startup floor, paid again on every call: "
          f"{mt.fmt(sm['first_request_median'])} tokens median, "
          f"{share_txt}", file=out)
    print(f"MEASURED  cache hit ratio median: {mt.fmt(sm['hit_ratio_median'])}", file=out)
    print(f"MEASURED  output tokens: {mt.fmt(sm['output_total'])} total, "
          f"{mt.fmt(sm['subagent_output_share'])} of it from subagents", file=out)

    sv = ts.savings_breakdown(sm)
    print(f"NATIVE    {ts.human(sv['saved'])} base-input token-units saved by Claude "
          f"Code's own prompt caching (Anthropic's mechanism, not this tool; "
          f"never shown in dollars){ts.native_note(sv)}", file=out)

    rx = ts.prescriptions(sm, sessions)
    if rx:
        top = max(rx, key=lambda r: r["saving"])
        print(f"ESTIMATED {ts.human(top['saving'])} base-input token-units you could "
              f"still cut, projected from your own sessions", file=out)

    title, detail = ts.lever(sm, mt)
    print(f"\nBiggest lever: {title}", file=out)
    print(f"  {detail}", file=out)

    # The follow-on command is built from where this file actually sits, not
    # from a hardcoded "scripts/cli.py". A stranger who ran the README's clone
    # command is standing one directory above the checkout, so a bare relative
    # path would print a command that fails from the only place they could be.
    cli = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cli.py")
    try:
        rel = os.path.relpath(cli)
        if len(rel) < len(cli):
            cli = rel
    except ValueError:
        pass  # sbe: allow-silent relpath raises when no relative path exists (a different drive on Windows); the absolute path already printed is correct, just longer
    print(f"\nFull plugin, more views, and a way to prove a fix worked: "
          f"python3 {cli} summary "
          f"(github.com/khalilmaaouni/token-shield)", file=out)
    return 0


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--root", default=DEFAULT_ROOT)
    ap.add_argument("--days", type=float, default=DEFAULT_DAYS)
    a = ap.parse_args(argv)
    return run(a.root, a.days)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
