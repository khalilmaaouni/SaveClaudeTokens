#!/usr/bin/env python3
"""
session_end_telemetry.py: append one line of measured token usage per session.

OPT IN. This plugin does not register this hook for you. Nothing here runs
unless you add it to your own settings, because a plugin that silently runs
code on every session of every machine that installs it has stopped being a
one-line skill listing. Wiring instructions are in the README.

WHAT IT DOES
Claude Code sends hook input as JSON on stdin, including transcript_path.
This reads that transcript, computes the same measured counters the audit
uses, and appends one JSON object to a local ledger. Then you have a history
without paying a model anything to produce it: measuring token spend by asking
a language model to measure it is the joke this script refuses to be.

WHAT IT DOES NOT DO
- It never writes conversation text, file contents, prompts, or tool output to
  the ledger. Only counters, a model list, and the transcript's own path.
- It never sends anything anywhere. The ledger is a local file.
- It never prints to stdout, so it cannot inject anything into a session.
- It never fails your session: any error exits 0 silently, because a telemetry
  script that breaks the tool it measures is worse than no telemetry.

USAGE (as a hook, reading stdin)
  python3 session_end_telemetry.py
USAGE (by hand, for a transcript you name)
  python3 session_end_telemetry.py --transcript PATH [--ledger PATH]
"""

import argparse
import importlib.util
import json
import os
import sys
import time

DEFAULT_LEDGER = os.path.expanduser("~/.claude/token-ledger.jsonl")


def load_measure():
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location(
        "measure_tokens", os.path.join(here, "measure_tokens.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def record(mt, transcript, session_id):
    s = mt.read_session(transcript)
    if not s:
        return None
    # Only counters leave this function. Nothing derived from message content.
    return {
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "session_id": session_id,
        "transcript": os.path.basename(transcript),
        "schema": mt.SCHEMA,
        "calls": s["calls"],
        "first_request": s["first_request"],
        "first_request_share": s["first_request_share"],
        "input": s["input"],
        "cache_read": s["read"],
        "cache_write_5m": s["write_5m"],
        "cache_write_1h": s["write_1h"],
        "cache_write_unsplit": s["write_unsplit"],
        "normalized_input": s["normalized_input"],
        "output": s["output"],
        "hit_ratio": s["hit_ratio"],
        "rewrite_ratio": s["rewrite_ratio"],
        "models": s["models"],
        "subagent_calls": s["sub_calls"],
        "subagent_output": s["sub_output"],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--transcript", help="transcript path (default: read hook JSON on stdin)")
    ap.add_argument("--ledger", default=os.environ.get("TOKEN_LEDGER", DEFAULT_LEDGER))
    a = ap.parse_args()

    transcript = a.transcript
    session_id = None
    if not transcript:
        if sys.stdin.isatty():
            print("NO DATA: no --transcript given and no hook JSON on stdin.",
                  file=sys.stderr)
            return 0
        payload = json.load(sys.stdin)
        transcript = payload.get("transcript_path")
        session_id = payload.get("session_id")
    if not transcript or not os.path.isfile(transcript):
        print(f"NO DATA: transcript not found: {transcript}", file=sys.stderr)
        return 0

    mt = load_measure()
    row = record(mt, transcript, session_id)
    if row is None:
        print("NO DATA: transcript carried no usage counters.", file=sys.stderr)
        return 0

    os.makedirs(os.path.dirname(os.path.abspath(a.ledger)) or ".", exist_ok=True)
    with open(a.ledger, "a") as f:
        f.write(json.dumps(row) + "\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # never break the session this is measuring
        print(f"NO DATA: telemetry failed ({e})", file=sys.stderr)
        sys.exit(0)
