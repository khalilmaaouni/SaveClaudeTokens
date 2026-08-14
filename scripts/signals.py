#!/usr/bin/env python3
"""
signals.py: Signals S1, the local, offline, opt-in usage summary.

Phase S1 only. This file writes ZERO network code (no sockets, no urllib,
no http.client, nothing that could ever leave the machine on its own). It
builds one small daily report from the local telemetry ledger, queues it in
a local outbox, and lets you preview the exact bytes a future send (S2)
would carry. Nothing is sent anywhere from this phase.

THE WHITELIST CONTRACT
-----------------------
data/signals.schema.json is the frozen, public, versioned whitelist: the
only fields a Signals report may ever carry off the machine. This script
never builds a report by taking a large internal object and deleting the
bad parts. Instead, build_report() assembles an internal candidate dict
(build_candidate), then walks the schema (_project) and copies out only the
keys the schema names, recursively. A field this file computes but the
schema does not name simply cannot reach the returned report, by
construction, not by discipline. test_signals.py calibrates this directly.

WHAT S1 POPULATES, AND WHY THE REST STAYS ABSENT
--------------------------------------------------
The schema itself documents which fields have no honest local basis yet
(error_classes, overspend_markers, environment.claude_code_minor_version,
environment.model_family_mix, treatment_outcomes, submission_id): S1 leaves
every one of those absent rather than report a fabricated zero or band,
because a fabricated "0" claims something was measured when it was not.
This script applies the same rule to waste_shares: the local ledger
(scripts/session_end_telemetry.py's DEFAULT_LEDGER) carries per-session
token counters, not a waste-class breakdown. Of the eight named waste
classes, exactly two have a direct, honest measurement in those counters:

  - startup_rent: the ledger already carries, per session, the tokens the
    session's first call cost (first_request) and how many calls repaid
    that floor (calls). Summed across a day and divided by the day's total
    raw tokens, this is exactly measure_tokens.py's own "first request
    share" concept (see its docstring, "FIRST REQUEST SHARE"), aggregated
    per day instead of per session.
  - cache_cold_rebuilds: the ledger carries cache_write_5m, cache_write_1h
    and cache_write_unsplit per session: tokens that had to be freshly
    written because they were not a cache hit. Summed across a day and
    divided by the day's total raw tokens, this is a direct share of
    tokens spent on cold cache writes.
  - unknown: whatever share of the day's tokens neither of the above
    accounts for. Per the schema's own description, waste_shares buckets
    need not sum to 100 (quantization is per-bucket), so startup_rent and
    cache_cold_rebuilds can overlap (a session's first call can itself be a
    cache write) without corrupting anything; unknown is clamped at 0
    rather than allowed to go negative, and it is never redistributed into
    the other buckets.

tool_output_noise, duplicate_reads, verbose_output, overbuild, and
routing_mismatch stay absent: the per-session ledger row has no field that
honestly measures any of them (that needs per-tool-call detail the ledger
does not carry). Reporting them as 0 would claim zero waste of a kind never
actually measured, which is the fabrication this whole design refuses.

THE LEDGER
----------
scripts/session_end_telemetry.py already defines the one telemetry ledger
this plugin writes: DEFAULT_LEDGER = ~/.claude/token-ledger.jsonl (see its
README.md and docs/TELEMETRY.md documentation, and its --ledger/TOKEN_LEDGER
override). This module imports that module and reuses its DEFAULT_LEDGER
constant directly rather than re-deriving the path string.

THE OUTBOX
----------
Reports queue locally as one file per report under
~/.token-shield/signals-outbox/ (created lazily on first write), capped at
OUTBOX_CAP entries; the oldest queued report is evicted first when the cap
is reached. Nothing here ever sends a queued report anywhere; S2 owns that.

USAGE
  python3 signals.py rollup [--day YYYY-MM-DD] [--ledger PATH] [--outbox DIR]
  python3 signals.py preview [--outbox DIR]
"""

import argparse
import glob
import json
import math
import os
import platform
import re
import sys
import time

import session_end_telemetry as telem

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(HERE, "..", "data", "signals.schema.json")
PLUGIN_MANIFEST_PATH = os.path.join(HERE, "..", ".claude-plugin", "plugin.json")

# The design doc (docs/superpowers/specs/2026-08-14-token-shield-signals-design.md)
# names ~/.token-shield/signals/outbox/; the S1 build brief that scoped this
# file names this exact path instead. The brief is the standing instruction
# for this phase, so this is the one Signals S1 uses.
OUTBOX_DIR = os.path.expanduser("~/.token-shield/signals-outbox/")
OUTBOX_CAP = 90

SCHEMA_VERSION = 1

_PLATFORM_NAMES = {"Darwin": "mac", "Linux": "linux", "Windows": "windows"}


def _load_schema():
    with open(SCHEMA_PATH) as f:
        return json.load(f)


def _project(node, data):
    """The whitelist serializer: copy from `data` only the keys `node` (a
    JSON-schema object node) names, recursively into nested object
    properties. Anything `data` carries that the schema does not name is
    dropped here, silently and by construction. This is the only place a
    report's fields are chosen; nothing else in this file trims a payload.
    """
    if not isinstance(data, dict):
        return data
    props = node.get("properties", {}) or {}
    pattern_props = node.get("patternProperties", {}) or {}
    compiled = [(re.compile(pat), sub) for pat, sub in pattern_props.items()]
    result = {}
    for key, value in data.items():
        sub_schema = props.get(key)
        if sub_schema is not None:
            if sub_schema.get("type") == "object" and isinstance(value, dict):
                result[key] = _project(sub_schema, value)
            else:
                result[key] = value
            continue
        for pat, sub in compiled:
            if pat.match(key):
                result[key] = value
                break
    return result


def quantize_5(frac):
    """A fraction (0.0 to 1.0, or beyond) to an int in [0, 100], the nearest
    multiple of 5, rounding a .5 boundary up. Clamped to the schema's
    [0, 100] range before rounding, so an out-of-range input never produces
    an out-of-range bucket."""
    pct = max(0.0, min(100.0, frac * 100.0))
    bucket = int(math.floor(pct / 5.0 + 0.5)) * 5
    return max(0, min(100, bucket))


def _platform_name():
    return _PLATFORM_NAMES.get(platform.system(), "unknown")


def _plugin_version():
    try:
        with open(PLUGIN_MANIFEST_PATH) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    v = data.get("version")
    return v if isinstance(v, str) and v else None


def _day_rows(ledger_path, day):
    """Yield parsed ledger rows whose recorded_at falls on `day`
    (YYYY-MM-DD). Tolerant of a missing ledger and of corrupt lines: both
    are silently skipped rather than raised, because a rollup that crashes
    on one bad line is worse than a rollup that reports NO DATA."""
    if not ledger_path or not os.path.isfile(ledger_path):
        return
    with open(ledger_path, errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            recorded = row.get("recorded_at")
            if isinstance(recorded, str) and recorded[:10] == day:
                yield row


def build_candidate(ledger_path, day):
    """Aggregate one day's ledger rows into the internal report candidate.

    NOT a whitelisted report yet: build_report() below is the only path that
    turns this into something that may be queued, and it always passes this
    dict through the schema-driven _project() first. Returns None (NO DATA)
    when the ledger is absent, unparseable, or carries no row for `day` with
    a nonzero token count: this function never fabricates a report to fill
    the gap.
    """
    total_raw = 0.0
    total_startup_paid = 0.0
    total_write = 0.0
    seen = False

    for row in _day_rows(ledger_path, day):
        try:
            inp = float(row.get("input") or 0)
            rd = float(row.get("cache_read") or 0)
            w5 = float(row.get("cache_write_5m") or 0)
            w1 = float(row.get("cache_write_1h") or 0)
            wu = float(row.get("cache_write_unsplit") or 0)
            first = float(row.get("first_request") or 0)
            calls = float(row.get("calls") or 0)
        except (TypeError, ValueError):
            continue
        raw_input = inp + rd + w5 + w1 + wu
        if raw_input <= 0:
            continue
        seen = True
        total_raw += raw_input
        total_startup_paid += first * calls
        total_write += (w5 + w1 + wu)

    if not seen or total_raw <= 0:
        return None

    startup_frac = total_startup_paid / total_raw
    write_frac = total_write / total_raw
    unknown_frac = max(0.0, 1.0 - startup_frac - write_frac)

    candidate = {
        "schema_version": SCHEMA_VERSION,
        "report_date": day,
        "waste_shares": {
            "startup_rent": quantize_5(startup_frac),
            "cache_cold_rebuilds": quantize_5(write_frac),
            "unknown": quantize_5(unknown_frac),
        },
    }

    env = {"platform": _platform_name()}
    version = _plugin_version()
    if version:
        env["token_shield_version"] = version
    candidate["environment"] = env

    return candidate


def build_report(ledger_path, day):
    """Build one whitelisted Signals report for `day` from `ledger_path`, or
    None (NO DATA) when the day has nothing to report. Every value that
    reaches the return has been through _project() against the frozen
    schema; nothing bypasses it."""
    candidate = build_candidate(ledger_path, day)
    if candidate is None:
        return None
    return _project(_load_schema(), candidate)


def serialize(report):
    """Deterministic bytes for one report: sorted keys, stable indentation,
    a trailing newline. This is the exact byte sequence queue_report writes
    and preview prints; the two must never diverge."""
    return (json.dumps(report, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _seq_of(path):
    name = os.path.basename(path)
    head = name.split("-", 1)[0]
    try:
        return int(head)
    except ValueError:
        return -1


def _outbox_files(outbox_dir):
    return sorted(glob.glob(os.path.join(outbox_dir, "*.json")), key=_seq_of)


def queue_report(report, outbox_dir=None):
    """Append `report` to the local outbox, oldest-first eviction once the
    outbox holds OUTBOX_CAP entries. Filenames embed a monotonic sequence
    number so ordering survives eviction without relying on filesystem
    mtimes or a separate counter file: a new report's sequence number is
    always one past the highest sequence number ever seen in the directory,
    evicted files included. Returns the path written."""
    outbox_dir = os.path.expanduser(outbox_dir or OUTBOX_DIR)
    os.makedirs(outbox_dir, exist_ok=True)
    existing = _outbox_files(outbox_dir)
    next_seq = max((_seq_of(p) for p in existing), default=-1) + 1
    if len(existing) >= OUTBOX_CAP:
        overflow = len(existing) - OUTBOX_CAP + 1
        for stale in existing[:overflow]:
            os.remove(stale)
    fname = f"{next_seq:08d}-{report.get('report_date', 'unknown')}.json"
    path = os.path.join(outbox_dir, fname)
    with open(path, "wb") as f:
        f.write(serialize(report))
    return path


def cmd_rollup(day, ledger_path, outbox_dir):
    day = day or time.strftime("%Y-%m-%d")
    ledger_path = ledger_path or telem.DEFAULT_LEDGER
    report = build_report(ledger_path, day)
    if report is None:
        print(f"NO DATA: no usage in {ledger_path} for {day}.", file=sys.stderr)
        return 2
    path = queue_report(report, outbox_dir)
    print(f"queued: {path}")
    return 0


def cmd_preview(outbox_dir):
    """Print the newest queued report's exact payload bytes: precisely what
    a future send (S2) would transmit, and nothing else. NO DATA (exit 2) on
    an empty or absent outbox, never an empty-but-valid report."""
    outbox_dir = os.path.expanduser(outbox_dir or OUTBOX_DIR)
    files = _outbox_files(outbox_dir)
    if not files:
        print("NO DATA: signals outbox is empty or absent.", file=sys.stderr)
        return 2
    with open(files[-1], "rb") as f:
        data = f.read()
    sys.stdout.buffer.write(data)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    sub = ap.add_subparsers(dest="action", required=True)

    p_roll = sub.add_parser("rollup", help="build and queue one day's report from the local ledger")
    p_roll.add_argument("--day", default=None, help="YYYY-MM-DD, default today")
    p_roll.add_argument("--ledger", default=None, help="ledger path, default session_end_telemetry.DEFAULT_LEDGER")
    p_roll.add_argument("--outbox", default=None, help="outbox dir, default ~/.token-shield/signals-outbox/")

    p_prev = sub.add_parser("preview", help="print the newest queued report's exact payload bytes")
    p_prev.add_argument("--outbox", default=None, help="outbox dir, default ~/.token-shield/signals-outbox/")

    a = ap.parse_args()
    if a.action == "rollup":
        return cmd_rollup(a.day, a.ledger, a.outbox)
    return cmd_preview(a.outbox)


if __name__ == "__main__":
    sys.exit(main())
