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
inherently a problem. Judging which shared hook matters is wave 2 (a hook
ownership table), not built here.

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


def _overlap_lines(companions, state):
    """Facts, not verdicts: every pair of currently-active curated companions
    that shares a hook_footprint entry gets one SHARED HOOK line. Never the
    word CONFLICT; wave 2 owns judging which overlap matters."""
    enabled_names = {d["name"] for d in (state or {}).get("discovered", []) if d.get("enabled")}
    active = [c for c in companions if c["name"] in enabled_names and c.get("hook_footprint")]
    lines = []
    for i, a in enumerate(active):
        for b in active[i + 1:]:
            shared = sorted(set(a["hook_footprint"]) & set(b["hook_footprint"]))
            for hook in shared:
                lines.append(f"  SHARED HOOK: {a['name']} and {b['name']} both register {hook}")
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
    print("  Judging which shared hook actually matters is a wave 2 feature "
          "(data/compatibility.json, hook ownership table), not available yet.")
    return 0


def main(argv):
    return report()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
