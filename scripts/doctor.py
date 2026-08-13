#!/usr/bin/env python3
"""
doctor.py: read-only ecosystem doctor. Health, staleness, and shared-hook
facts across Token Shield's curated companion registry (data/companions.json)
and this machine's own plugin inventory (discover_companions.py).

This module writes nothing except, on demand, refreshing the local
companion state file via discover_companions.write_state() when it is
missing or older than STATE_FRESHNESS_SECONDS; that refresh always prints a
line saying it happened, never done silently. It never suppresses or
adjusts an advisor card, never writes to the experiment ledger, and never
installs, disables, or recommends anything: prescribed, never bundled.

Overlap is reported as a plain SHARED HOOK fact, never as CONFLICT: the
evidence run in docs/superpowers/plans/2026-08-13-v18-wave1-plan.md:99 shows
SessionStart shared by every curated companion on this machine, which is not
inherently a problem. Judging which shared hook matters is the hook
ownership table below, sourced from data/compatibility.json: for every
SHARED HOOK fact this module also prints who owns what behavior on that
hook and the compatibility.json verdict for the pair (known-safe,
needs-review, or NO DATA when the pair has no evidence on file). A pair
absent from compatibility.json is always NO DATA, never guessed at
known-safe.

USAGE
  python3 doctor.py
"""

import calendar
import datetime
import json
import os
import sys
import time

import discover_companions as dc
import profile as pf
import token_shield as ts

HERE = os.path.dirname(os.path.abspath(__file__))
COMPATIBILITY_PATH = os.path.join(HERE, "..", "data", "compatibility.json")

STATE_FRESHNESS_SECONDS = 24 * 60 * 60  # 1 day, plan Step 5's freshness window
STALENESS_DAYS = 180  # founder-reviewable threshold, plan ambiguity 3, 2026-08-13


def _load_state(path=None):
    path = path or dc.STATE_PATH
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _ensure_fresh_state():
    """Load the local companion state file, refreshing it with a live
    discover_companions run if missing or older than
    STATE_FRESHNESS_SECONDS. Always documents the refresh out loud."""
    state = _load_state()
    stale = state is None
    if not stale:
        try:
            checked = time.strptime(state["checked_at"], "%Y-%m-%dT%H:%M:%SZ")
            age = time.time() - calendar.timegm(checked)
            stale = age > STATE_FRESHNESS_SECONDS
        except (KeyError, ValueError):
            stale = True
    if stale:
        print("doctor: companion state is missing or older than a day, running discovery now.")
        discovered = dc.discover()
        if discovered is None:
            print("NO DATA: `claude plugin list --json` failed; continuing without discovery data.")
            return state
        state = dc.write_state(discovered)
    return state


def _health_lines(companions, state):
    discovered_by_name = {d["name"]: d for d in (state or {}).get("discovered", [])}
    lines = []
    for c in companions:
        row = discovered_by_name.get(c["name"])
        if row and row.get("enabled"):
            lines.append(f"  installed and active: {c['name']}")
        else:
            lines.append(f"  curated, not installed: {c['name']}")
    match = (state or {}).get("registry_match", {})
    for name, m in match.items():
        if m == "unknown" and discovered_by_name.get(name, {}).get("enabled"):
            lines.append(f"  installed but not in the curated registry (unvetted, "
                         f"never recommended): {name}")
    return lines


def _parse_date(s):
    try:
        return datetime.date(*(int(p) for p in s.split("-")))
    except (ValueError, TypeError, AttributeError):
        return None


def _staleness_lines(companions, today=None):
    today_date = _parse_date(today or time.strftime("%Y-%m-%d"))
    lines = []
    if today_date is None:
        return lines
    for c in companions:
        reviewed = c.get("last_reviewed")
        d = _parse_date(reviewed) if reviewed else None
        if d is None:
            continue
        age_days = (today_date - d).days
        if age_days > STALENESS_DAYS:
            lines.append(f"  NEEDS REVIEW: {c['name']} last reviewed {reviewed} "
                         f"({age_days} days ago, threshold {STALENESS_DAYS})")
    return lines


def _shared_hook_pairs(companions, state):
    """Every (a_name, b_name, hook) triple among currently-active curated
    companions that share a hook_footprint entry. Raw data shared by the
    Overlap section and the Hook ownership section below it."""
    enabled_names = {d["name"] for d in (state or {}).get("discovered", []) if d.get("enabled")}
    active = [c for c in companions if c["name"] in enabled_names and c.get("hook_footprint")]
    pairs = []
    for i, a in enumerate(active):
        for b in active[i + 1:]:
            shared = sorted(set(a["hook_footprint"]) & set(b["hook_footprint"]))
            for hook in shared:
                pairs.append((a["name"], b["name"], hook))
    return pairs


def _overlap_lines(companions, state):
    """Facts, not verdicts: every pair of currently-active curated companions
    that shares a hook_footprint entry gets one SHARED HOOK line. Never the
    word CONFLICT; the Hook ownership section owns judging which overlap
    matters."""
    return [f"  SHARED HOOK: {a} and {b} both register {hook}"
            for a, b, hook in _shared_hook_pairs(companions, state)]


def _load_compatibility(path=None):
    """data/compatibility.json: (data, error). data is None and error is
    None when the file is simply missing (no compatibility evidence exists
    yet, same posture as a missing companions.json). error carries the
    parse failure reason on malformed JSON so the caller can print it;
    never raises."""
    path = path or COMPATIBILITY_PATH
    if not os.path.exists(path):
        return None, None
    try:
        with open(path) as f:
            return json.load(f), None
    except (OSError, ValueError) as e:
        return None, str(e)


def _find_compat_entry(compat_data, a, b, hook):
    for entry in (compat_data or {}).get("pairs", []):
        if set(entry.get("companions") or []) == {a, b} and entry.get("hook_event") == hook:
            return entry
    return None


def _ownership_lines(companions, state, compat_data):
    """For each SHARED HOOK fact, who owns what behavior on that hook and
    compatibility.json's verdict for the pair. A pair with no entry in
    compatibility.json is always reported NO DATA, never defaulted to
    known-safe."""
    lines = []
    for a, b, hook in _shared_hook_pairs(companions, state):
        entry = _find_compat_entry(compat_data, a, b, hook)
        if entry is None:
            lines.append(f"  {hook}: {a} + {b}: verdict NO DATA "
                         f"(no data/compatibility.json entry for this pair)")
            continue
        verdict = entry.get("verdict", "NO DATA")
        evidence_date = entry.get("evidence_date", "unknown")
        lines.append(f"  {hook}: {a} + {b}: verdict {verdict} (evidence {evidence_date})")
        ownership = entry.get("ownership", {})
        for name in (a, b):
            behavior = ownership.get(name)
            if behavior:
                lines.append(f"    {name} owns: {behavior}")
    return lines


def report():
    companions_data = ts.load_companions(ts.COMPANIONS_PATH)
    if not companions_data:
        print("NO DATA: data/companions.json not found or unreadable.")
        return 0
    companions = companions_data.get("companions", [])

    state = _ensure_fresh_state()

    plugin_cache_root = os.path.expanduser("~/.claude/plugins/cache")
    plugin_count = pf._plugin_count(plugin_cache_root)

    print("Token Shield ecosystem doctor")
    print(f"  plugin cache: "
          f"{plugin_count if plugin_count is not None else 'NO DATA'} entries under "
          f"{plugin_cache_root}")
    print()

    print("Health")
    health = _health_lines(companions, state)
    for line in (health or ["  NO DATA: no companion state available."]):
        print(line)
    print()

    print("Staleness")
    stale = _staleness_lines(companions)
    for line in (stale or [f"  none past the {STALENESS_DAYS}-day review window."]):
        print(line)
    print()

    print("Overlap (facts, not verdicts)")
    overlap = _overlap_lines(companions, state)
    for line in (overlap or ["  no shared hooks among currently active curated companions."]):
        print(line)
    print()

    print("Hook ownership (verdicts from data/compatibility.json)")
    compat_data, compat_error = _load_compatibility()
    if compat_error:
        print(f"  NO DATA: data/compatibility.json is malformed ({compat_error}); "
              f"continuing without hook ownership data.")
    elif not overlap:
        print("  no shared hooks to judge.")
    else:
        for line in _ownership_lines(companions, state, compat_data):
            print(line)
    return 0


def main(argv):
    return report()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
