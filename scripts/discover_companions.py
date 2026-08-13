#!/usr/bin/env python3
"""
discover_companions.py: read-only native discovery of installed Claude Code
plugins, via `claude plugin list --json` and `claude plugin details <name>`.

Real CLI shape confirmed on this machine (not assumed), quoted in
docs/superpowers/plans/2026-08-13-v18-wave1-plan.md:44-101. `claude plugin
list --json` returns a JSON array with an `id` field shaped
"<name>@<marketplace>", a bool `enabled`, and other fields not used here.
`claude plugin details <name>` prints plain text with no `--json` flag; its
"Hooks (N)  a, b, c" line is what this module parses for a hook footprint.

Every row this module produces is labeled CLAUDE PROJECTED, the literal
label on the CLI's own "Projected token cost" section. CLAUDE PROJECTED
never carries a token count, a dollar figure, or any of the ledger's real
labels (MEASURED, ESTIMATED, VERIFIED, NATIVE); nothing here is ever written
to the experiment ledger or summed into OPPORTUNITY or VERIFIED.

Nothing in this module runs from a hook. It runs only when a human runs it
directly, or on demand from doctor.py.

USAGE
  python3 discover_companions.py       discover, write the local state file
"""

import json
import os
import subprocess
import sys
import time

import token_shield as ts

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.expanduser("~/.token-shield/companions_state.json")
SOURCE_LABEL = "CLAUDE PROJECTED"


def discover():
    """`claude plugin list --json`, parsed to one row per installed plugin:
    {"name": ..., "enabled": ..., "source_label": "CLAUDE PROJECTED"}.
    Never raises: any subprocess or JSON failure returns None (NO DATA)."""
    try:
        r = subprocess.run(["claude", "plugin", "list", "--json"],
                            capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            return None
        entries = json.loads(r.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return None
    rows = []
    for e in entries:
        name = e.get("id", "").split("@")[0]
        if not name:
            continue
        rows.append({"name": name, "enabled": bool(e.get("enabled")),
                     "version": e.get("version"), "source_label": SOURCE_LABEL})
    return rows


def hook_footprint_of(name):
    """`claude plugin details <name>`'s "Hooks (N)  a, b, c" line, parsed to
    a list of hook event names. Returns None (NO DATA) on a subprocess
    failure or on any line shape this does not recognize; never raises,
    never guesses at a future CLI reword."""
    try:
        r = subprocess.run(["claude", "plugin", "details", name],
                            capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            return None
    except (OSError, subprocess.SubprocessError):
        return None
    for line in r.stdout.splitlines():
        line = line.strip()
        if not line.startswith("Hooks ("):
            continue
        pieces = line.split(")", 1)
        if len(pieces) != 2:
            return None
        names_part = pieces[1].strip()
        paren = names_part.find("(")
        if paren != -1:
            names_part = names_part[:paren].strip()
        if not names_part:
            return []
        return [n.strip() for n in names_part.split(",") if n.strip()]
    return None


def _registry_match(names, companions_path):
    """name -> "curated" | "mention" | "unknown", cross-referenced against
    data/companions.json (reuses token_shield.load_companions rather than
    reimplementing the same defensive JSON read)."""
    data = ts.load_companions(companions_path)
    curated = {c["name"] for c in (data or {}).get("companions", [])}
    mentioned = {m["name"] for m in (data or {}).get("mentions", [])}
    match = {}
    for name in names:
        if name in curated:
            match[name] = "curated"
        elif name in mentioned:
            match[name] = "mention"
        else:
            match[name] = "unknown"
    return match


def version_drift(names, live, state):
    """Compare each of `names`' live version (from a discover() result,
    `live`) against the version last recorded for it in a previously loaded
    companions_state.json (`state`, or None when no state file exists yet).

    Returns {"no_data": True, "drifted": [], "missing": []} when `state` or
    `live` is None: absent state or a failed live discovery is NO DATA,
    never "no drift". Otherwise returns {"no_data": False, "drifted": [...],
    "missing": [...]}:
      - "drifted": one entry per name whose live version differs from the
        recorded one: {"name", "recorded_version", "live_version",
        "recorded_at"} (recorded_at is state["checked_at"], the only
        observation date the state file carries).
      - "missing": one entry per name the state never recorded a version
        for: {"name", "live_version"}. NO DATA for that row, never folded
        into "no drift".
    A name absent from `live` (not currently installed) is skipped: there
    is nothing live to compare it against. Never raises."""
    if state is None or live is None:
        return {"no_data": True, "drifted": [], "missing": []}
    live_by_name = {r["name"]: r for r in live}
    recorded_by_name = {d["name"]: d for d in (state.get("discovered") or [])}
    recorded_at = state.get("checked_at")
    drifted, missing = [], []
    for name in names:
        live_row = live_by_name.get(name)
        if live_row is None:
            continue
        live_version = live_row.get("version")
        recorded_row = recorded_by_name.get(name)
        recorded_version = recorded_row.get("version") if recorded_row else None
        if recorded_version is None:
            missing.append({"name": name, "live_version": live_version})
        elif live_version != recorded_version:
            drifted.append({"name": name, "recorded_version": recorded_version,
                            "live_version": live_version, "recorded_at": recorded_at})
    return {"no_data": False, "drifted": drifted, "missing": missing}


def write_state(discovered, path=STATE_PATH, companions_path=ts.COMPANIONS_PATH):
    """Writes the local companion state file. Called only on demand: a direct
    run of this module, or doctor.py when its cached state is missing or
    stale; never from a hook, matching the plugin's zero-hooks-by-default
    posture."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    discovered = discovered or []
    state = {
        "schema": 1,
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "discovered": discovered,
        "registry_match": _registry_match([d["name"] for d in discovered], companions_path),
    }
    with open(path, "w") as f:
        json.dump(state, f, indent=2)
    return state


def main(argv):
    discovered = discover()
    if discovered is None:
        print("NO DATA: `claude plugin list --json` failed or returned unreadable output.")
        return 0
    state = write_state(discovered)
    print(f"discovered {len(state['discovered'])} companion(s), wrote {STATE_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
