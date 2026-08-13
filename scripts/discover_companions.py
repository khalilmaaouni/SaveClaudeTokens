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

I1 addition (docs/superpowers/specs/integration-contract-v1.md): this module
also reads token-shield.integration.json, an open declaration any
optimization plugin may ship in its own installed plugin root. Every field
read from a declaration is labeled DECLARED, never CURATED; a declaration
can never promote itself into data/companions.json's hand-verified
registry. The declaration file is UNTRUSTED THIRD-PARTY INPUT: any plugin
on the machine can write anything into it, so every field is treated as
hostile until validated. See read_declaration() and discover_declarations().

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

# I1: the open declaration contract, docs/superpowers/specs/
# integration-contract-v1.md. Any optimization plugin may ship this file in
# its own installed plugin root; discovery reads it as DECLARED data, never
# CURATED. See read_declaration() and discover_declarations() below.
INTEGRATION_FILENAME = "token-shield.integration.json"
DECLARED_LABEL = "DECLARED"
CURATED_LABEL = "CURATED"
# ponytail: named limit, not a magic number. A hostile declaration file
# (deeply nested JSON, or just huge) must be refused before it can cost
# meaningful parse time or memory. A real declaration is a few hundred
# bytes (see the field table in integration-contract-v1.md); 64 KiB leaves
# generous headroom for a verbose, legitimate file while still refusing
# anything shaped like an attack.
MAX_DECLARATION_BYTES = 65536


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


# I1: hand-written validation of a parsed declaration against data/
# integration.schema.json. No jsonschema dependency is available in this
# repo (standard library only), so this mirrors the schema by hand; keep
# the two in agreement whenever either changes.
_OPTIONAL_STRING_FIELDS = ("name", "status_command", "version_command",
                           "activation_command", "rollback_command")


def _validate_declaration(data):
    """Checks a parsed declaration dict against the contract. Returns None
    when it matches, or a string naming exactly the offending field
    otherwise. `data` is untrusted third-party JSON: every field is
    type-checked before anything downstream (name lookups, conflict
    checks) is allowed to touch it."""
    if "capabilities" not in data:
        return "missing required field 'capabilities'"
    caps = data["capabilities"]
    if not isinstance(caps, list) or not caps or not all(
            isinstance(c, str) and c for c in caps):
        return "'capabilities' must be a non-empty list of non-empty strings"
    modes = data.get("modes")
    if modes is not None and (not isinstance(modes, list) or not all(
            isinstance(m, str) and m for m in modes)):
        return "'modes' must be a list of strings"
    for field in _OPTIONAL_STRING_FIELDS:
        value = data.get(field)
        if value is not None and not isinstance(value, str):
            return f"'{field}' must be a string"
    return None


def _reject_duplicate_keys(pairs):
    """object_pairs_hook for json.loads: refuses (raises ValueError) a JSON
    object with a repeated top-level key, instead of the standard library's
    default silent last-value-wins. A duplicate key could otherwise smuggle
    a second, different value for a field like rollback_command past a
    reader that only looked at the first occurrence."""
    seen = set()
    dupes = set()
    for key, _ in pairs:
        if key in seen:
            dupes.add(key)
        seen.add(key)
    if dupes:
        raise ValueError(f"duplicate key(s): {', '.join(sorted(dupes))}")
    return dict(pairs)


def read_declaration(path):
    """Reads one token-shield.integration.json declaration file at `path`
    (the open contract, docs/superpowers/specs/integration-contract-v1.md).
    The file is UNTRUSTED THIRD-PARTY INPUT: any plugin on the machine can
    write anything into it, so every step here is a refusal, not a crash,
    for any shape that does not match the contract.

    Returns {"refused": False, "path": path, "name": <str or None>,
    "fields": {<key>: {"label": "DECLARED", "value": <value>, "source":
    path}, ...}} for every top-level key the file actually contains, or
    {"refused": True, "path": path, "reason": "..."} naming exactly what is
    wrong: an unreadable file, an oversized file, malformed JSON (including
    JSON too deeply nested to parse), a duplicate top-level key, a JSON
    value that is not an object, a missing required 'capabilities' field,
    or any field present with the wrong type. A refused declaration is
    never partially trusted: either every field loads as one DECLARED
    record, or none of it is used.

    Every field this function reports carries the DECLARED label. A
    declaration is the plugin's own claim about itself, never Token
    Shield's first-party verification (CURATED); there is no path through
    this function that can produce any other label. Never raises, for any
    input: unreadable files, malformed or duplicate-keyed or arbitrarily
    deeply nested JSON, and any other error are all caught and turned into
    a named refusal reason rather than an exception."""
    try:
        with open(path, encoding="utf-8") as f:
            raw = f.read(MAX_DECLARATION_BYTES + 1)
    except OSError as e:
        return {"refused": True, "path": path,
                "reason": f"NO DATA: could not read {path}: {e}"}
    if len(raw) > MAX_DECLARATION_BYTES:
        return {"refused": True, "path": path,
                "reason": f"NO DATA: {path} exceeds the "
                          f"{MAX_DECLARATION_BYTES}-byte declaration size limit"}
    try:
        data = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except json.JSONDecodeError as e:
        return {"refused": True, "path": path,
                "reason": f"NO DATA: malformed JSON in {path}: {e}"}
    except ValueError as e:
        # includes _reject_duplicate_keys's duplicate-key ValueError
        return {"refused": True, "path": path,
                "reason": f"NO DATA: {path}: {e}"}
    except RecursionError:
        return {"refused": True, "path": path,
                "reason": f"NO DATA: {path} is too deeply nested to parse"}
    except Exception as e:  # noqa: BLE001 - deliberately broad: a hostile
        # third-party file must never crash discovery, no matter what novel
        # way it finds to break the parser.
        return {"refused": True, "path": path,
                "reason": f"NO DATA: unexpected error parsing {path}: {e}"}
    if not isinstance(data, dict):
        return {"refused": True, "path": path,
                "reason": f"NO DATA: {path} is not a JSON object"}
    reason = _validate_declaration(data)
    if reason is not None:
        return {"refused": True, "path": path,
                "reason": f"NO DATA: {path} {reason}"}
    fields = {k: {"label": DECLARED_LABEL, "value": v, "source": path}
              for k, v in data.items()}
    return {"refused": False, "path": path, "name": data.get("name"), "fields": fields}


def discover_declarations(cache_root=None, companions_path=None, live=None):
    """Walks the installed-plugin cache tree for a token-shield.integration.json
    in each plugin root, and reads every one found via read_declaration().

    The tree shape (cache_root/<marketplace>/<plugin>/<version>/) is the
    real layout confirmed in docs/research/2026-08-13-companion-first-party.md.
    Never raises: a missing cache_root returns []; an unreadable directory
    at any level is skipped, never fatal to the rest of the walk. A
    malformed, oversized, hostile-shaped, or otherwise invalid declaration
    file is refused (see read_declaration) rather than crashing discovery,
    and one plugin's refused declaration never stops discovery of any
    other plugin's. A declaration path that turns out to be a directory or
    a broken symlink is also reported as an explicit refusal row rather
    than silently skipped, so a silent drop and a clean pass never look
    identical.

    Every row (refused or not) carries "version": the cache directory name
    it was read from. `live`, when given a discover()-shaped list of
    currently-installed plugins, resolves whether that cached version is
    actually installed: a non-refused row then also carries "installed"
    (True/False), or None with an "installed_note" naming why it could not
    be determined (no `live` given, or the declaration has no usable
    'name'). A cached, no-longer-installed version's self-claims are never
    reported as though they were current.

    Each non-refused row also carries "curated_conflict": True/False,
    cross-referenced by name against data/companions.json's curated
    "companions" list, and, when True, a "note" spelling out the rule this
    unit exists to enforce: a plugin that is BOTH curated and shipping a
    declaration keeps its curated evidence as the evidence of record. The
    declaration is reported here, never merged into or allowed to override
    the curated entry."""
    cache_root = cache_root or os.path.expanduser("~/.claude/plugins/cache")
    companions_path = companions_path or ts.COMPANIONS_PATH
    curated_names = {c["name"] for c in
                      (ts.load_companions(companions_path) or {}).get("companions", [])}
    live_by_name = {r["name"]: r.get("version") for r in live} if live is not None else None
    if not os.path.isdir(cache_root):
        return []
    try:
        marketplaces = sorted(os.listdir(cache_root))
    except OSError:
        return []
    results = []
    for marketplace in marketplaces:
        mpath = os.path.join(cache_root, marketplace)
        if not os.path.isdir(mpath):
            continue
        try:
            plugins = sorted(os.listdir(mpath))
        except OSError:
            continue
        for plugin in plugins:
            ppath = os.path.join(mpath, plugin)
            if not os.path.isdir(ppath):
                continue
            try:
                versions = sorted(os.listdir(ppath))
            except OSError:
                continue
            for version in versions:
                decl_path = os.path.join(ppath, version, INTEGRATION_FILENAME)
                if os.path.isfile(decl_path):
                    row = read_declaration(decl_path)
                elif os.path.islink(decl_path) or os.path.exists(decl_path):
                    # a directory, a broken symlink, or some other
                    # non-regular entry sitting at the expected path
                    # (Minor 7): refuse explicitly rather than silently
                    # skipping it.
                    row = {"refused": True, "path": decl_path,
                           "reason": f"NO DATA: {decl_path} exists but is "
                                     f"not a readable regular file"}
                else:
                    continue
                row["version"] = version
                if not row["refused"]:
                    name = row.get("name")
                    conflict = isinstance(name, str) and name in curated_names
                    row["curated_conflict"] = conflict
                    if conflict:
                        row["note"] = (
                            f"'{name}' is a curated companion in data/companions.json; "
                            f"curated evidence ({CURATED_LABEL}) wins over this "
                            f"declaration for any overlapping field. This declaration "
                            f"is reported here, never merged into the curated entry.")
                    if live_by_name is None:
                        row["installed"] = None
                        row["installed_note"] = ("NO DATA: no live `claude plugin "
                                                  "list` result was supplied")
                    elif not isinstance(name, str) or not name:
                        row["installed"] = None
                        row["installed_note"] = ("NO DATA: declaration has no usable "
                                                  "'name' field to resolve against "
                                                  "the installed version")
                    elif name not in live_by_name:
                        row["installed"] = False
                        row["installed_note"] = f"'{name}' is not currently installed"
                    else:
                        row["installed"] = (live_by_name[name] == version)
                results.append(row)
    return results


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
    declarations = discover_declarations(live=discovered)
    refused = [d for d in declarations if d["refused"]]
    accepted = [d for d in declarations if not d["refused"]]
    if declarations:
        print(f"found {len(accepted)} declaration(s) (DECLARED), "
              f"{len(refused)} refused")
        for d in refused:
            print(f"  refused: {d['reason']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
