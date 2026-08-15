"""
companions package: one read-only adapter contract, shared by ponytail.py,
caveman.py and token_saver.py (unit H1, docs/superpowers/plans/
2026-08-13-finish-program-plan.md).

Every fact an adapter reports is READ from data/companions.json plus the
local discovery state written by discover_companions.py
(~/.token-shield/companions_state.json); nothing is computed from belief.
An adapter answers exactly five questions about one curated companion:
status, version, available modes, activation command, rollback command.

Central rule: describe() REFUSES a registry entry missing any evidence
field it needs, naming the missing field in the refusal reason, instead of
falling back to a default or guessing. A command this module returns is
always the verbatim string from data/companions.json's "install" or
"uninstall" field: never rebuilt, never templated.

Adapters here are READ ONLY: describe() and report() below only open files
for reading, never for writing, and never shell out to any command,
mutating or not.
"""

import json
import os

import discover_companions as dc
import token_shield as ts

REQUIRED_FIELDS = ("install", "uninstall", "tested_version_range")
REQUIRED_VERSION_SUBFIELDS = ("min", "max", "tested_on")


def _find(companions_data, name):
    """The curated registry entry named `name`, or None. Only the curated
    "companions" list is searched: "mentions" entries are NO DATA by
    design (data/companions.json's own "reason": "NO DATA: not yet
    verified first-party" on every mention)."""
    for c in (companions_data or {}).get("companions", []):
        if c.get("name") == name:
            return c
    return None


def _status(state, name):
    """"active" (installed and enabled), "installed" (present but not
    enabled), or "neither" (absent from the discovery state), mirroring
    discover_companions.py's own installed/enabled vocabulary."""
    discovered_by_name = {d["name"]: d for d in (state or {}).get("discovered", [])}
    row = discovered_by_name.get(name)
    if row is None:
        return "neither"
    return "active" if row.get("enabled") else "installed"


def describe(companions_data, state, name):
    """The read-only report for one companion: {"refused": False, "name",
    "status", "version", "modes", "activation_command", "rollback_command"}
    or, when the registry entry is absent or missing an evidence field,
    {"refused": True, "name", "reason"} naming the exact missing field.
    Pure function: takes already-loaded data, never touches disk itself,
    so it runs identically against a fixture or the live registry.
    """
    entry = _find(companions_data, name)
    if entry is None:
        return {"refused": True, "name": name,
                "reason": f"NO DATA: '{name}' has no entry in data/companions.json"}
    for field in REQUIRED_FIELDS:
        if not entry.get(field):
            return {"refused": True, "name": name,
                    "reason": f"NO DATA: '{name}' registry entry is missing "
                              f"required field '{field}'"}
    vr = entry["tested_version_range"]
    for sub in REQUIRED_VERSION_SUBFIELDS:
        if not vr.get(sub):
            return {"refused": True, "name": name,
                    "reason": f"NO DATA: '{name}' tested_version_range is "
                              f"missing '{sub}'"}
    version_value = vr["min"] if vr["min"] == vr["max"] else f"{vr['min']} to {vr['max']}"
    modes = entry.get("modes")
    if modes:
        modes_field = {"label": "MEASURED", "value": modes, "source": "data/companions.json"}
    else:
        modes_field = {"label": "NO DATA",
                       "reason": f"'{name}' registry entry has no 'modes' field",
                       "source": "data/companions.json"}
    return {
        "refused": False,
        "name": name,
        "status": _status(state, name),
        "version": {"label": "MEASURED", "value": version_value,
                    "tested_on": vr["tested_on"], "source": "data/companions.json"},
        "modes": modes_field,
        "activation_command": {"label": "MEASURED", "value": entry["install"],
                               "source": "data/companions.json"},
        "rollback_command": {"label": "MEASURED", "value": entry["uninstall"],
                             "source": "data/companions.json"},
    }


def load_registry(path=None):
    """data/companions.json, with every CURATED entry's install and
    uninstall commands validated eagerly, the moment the whole file loads,
    the same way advisor.load_strategies() refuses a strategy naming an
    unknown problem_class before ranking ever runs (unit CF1). Raises
    ValueError naming the exact companion and the missing field.

    Standing policy: we never prescribe a companion we cannot tell a user
    how to undo. Before this function existed that policy lived only in a
    document (docs/research/2026-08-15-companion-fabric-facts.md), which
    means the next person to add a curated entry could quietly break it
    with nobody noticing until a user asked for the wrong recipe. This is
    the mechanical version of that same rule.

    Mentions are never checked here: NO DATA on rollback is their whole
    point, not a defect.

    Returns the raw doc (dict), or None if the file is missing or not
    valid JSON, the same tolerance token_shield.load_companions already
    has. Pure read: never writes, mirrors load_state below.
    """
    data = ts.load_companions(path or ts.COMPANIONS_PATH)
    if data is None:
        return None
    for entry in data.get("companions", []):
        name = entry.get("name", "<unnamed>")
        for field in ("install", "uninstall"):
            if not entry.get(field):
                raise ValueError(
                    f"companion {name!r}: refused at load, missing required "
                    f"field {field!r} (a companion without a documented "
                    f"{field} command is never prescribed)")
    return data


def load_state(path=None):
    """The on-disk discovery state (dc.STATE_PATH by default), or None if
    missing or corrupt. Read only; mirrors doctor.py's own _load_state.
    Never raises."""
    path = path or dc.STATE_PATH
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None  # sbe: allow-silent an unreadable registry means describe() refuses every companion by name, which is the documented contract, rather than answering from a default


def report(name, companions_path=None, state=None):
    """describe(), wired to real files: data/companions.json by default,
    and the live discovery state unless `state` is passed (tests pass a
    fixture state so nothing here ever depends on the live machine).
    Prints the refusal reason when refused, same as discover_companions.py
    prints its own NO DATA lines."""
    data = ts.load_companions(companions_path or ts.COMPANIONS_PATH)
    if state is None:
        state = load_state()
    result = describe(data, state, name)
    if result["refused"]:
        print(result["reason"])
    return result
