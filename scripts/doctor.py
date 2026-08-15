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

It also reports fact staleness from data/facts.json: a registry of dated,
sourced platform facts (see docs/CLAIMS.md for their provenance). A fact
past its own review_interval_days is printed as NEEDS REVIEW with its age;
a fact missing a source or a verified date is refused at load and named in
the report. This module never re-verifies a fact itself, never fetches a
page: it only ages the date already on file.

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
import experiment as ex
import measure_tokens as mt
import profile as pf
import config as cfg

HERE = os.path.dirname(os.path.abspath(__file__))
COMPATIBILITY_PATH = os.path.join(HERE, "..", "data", "compatibility.json")
FACTS_PATH = os.path.join(HERE, "..", "data", "facts.json")

STATE_FRESHNESS_SECONDS = 24 * 60 * 60  # 1 day, plan Step 5's freshness window
STALENESS_DAYS = 180  # founder-reviewable threshold, plan ambiguity 3, 2026-08-13
# 30 days, not a quarter. A platform fact (a documented default, a cache rule,
# a price) can change in any given week, and this tool's whole claim is that it
# does not hand out stale advice. 30 also matches the monthly report rhythm, so
# a fact that went stale surfaces within one reporting cycle rather than three.
# Fallback only; every fact in data/facts.json states its own.
DEFAULT_FACT_REVIEW_DAYS = 30

TRANSCRIPT_ROOT = os.path.expanduser("~/.claude/projects")
CANARY_DAYS = 90  # matches measure_tokens.py's own --days default


def _load_state(path=None):
    path = path or dc.STATE_PATH
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None  # sbe: allow-silent an unreadable JSON file becomes NO DATA in doctor's own report, which is what doctor exists to print honestly


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
        return None  # sbe: allow-silent an unparseable date is NO DATA; the caller skips the staleness comparison rather than guessing a date and calling something stale


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


def _load_facts(path=None):
    """data/facts.json: (facts, refused, error). facts is the list of valid
    entries, each carrying at least a source and a verified date. refused is
    a list of (id, reason) pairs for entries that fail that requirement, the
    reason naming the offending field so the caller can report it by name. A
    fact with no source or no date is not a fact: it never reaches the
    facts list. error is a human-readable string when the file is missing or
    the JSON is malformed; both a missing file and a parse failure read as
    NO DATA to the caller, same posture as _load_compatibility. Never
    raises."""
    path = path or FACTS_PATH
    if not os.path.exists(path):
        return [], [], "data/facts.json not found"
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        return [], [], str(e)
    raw = data.get("facts", []) if isinstance(data, dict) else []
    facts = []
    refused = []
    for i, fact in enumerate(raw):
        if not isinstance(fact, dict):
            refused.append((f"#{i}", "not an object"))
            continue
        fid = fact.get("id") or f"#{i}"
        if not fact.get("source"):
            refused.append((fid, "missing source"))
            continue
        if not fact.get("verified"):
            refused.append((fid, "missing verified date"))
            continue
        facts.append(fact)
    return facts, refused, None


def _is_fact_stale(fact, today=None):
    """True when a single fact's verified date is older than its own
    review_interval_days (falling back to DEFAULT_FACT_REVIEW_DAYS when the
    fact omits the field). The one staleness rule this repo uses, so a
    caller elsewhere (advisor.py's stale-fact card line) reuses this instead
    of re-deriving the same age/interval math. An unparseable date reads as
    not stale: NO DATA beats a guess."""
    today_date = _parse_date(today or time.strftime("%Y-%m-%d"))
    d = _parse_date(fact.get("verified"))
    if today_date is None or d is None:
        return False
    try:
        interval = int(fact.get("review_interval_days", DEFAULT_FACT_REVIEW_DAYS))
    except (TypeError, ValueError):
        interval = DEFAULT_FACT_REVIEW_DAYS
    return (today_date - d).days > interval


def _fact_staleness_lines(facts, today=None):
    """One NEEDS REVIEW line per fact whose verified date is older than its
    own review_interval_days (falling back to DEFAULT_FACT_REVIEW_DAYS when
    a fact omits the field). Read only: never re-verifies, never fetches,
    just ages the date already on file."""
    today_date = _parse_date(today or time.strftime("%Y-%m-%d"))
    lines = []
    if today_date is None:
        return lines
    for fact in facts:
        d = _parse_date(fact.get("verified"))
        if d is None:
            continue
        if not _is_fact_stale(fact, today):
            continue
        try:
            interval = int(fact.get("review_interval_days", DEFAULT_FACT_REVIEW_DAYS))
        except (TypeError, ValueError):
            interval = DEFAULT_FACT_REVIEW_DAYS
        age_days = (today_date - d).days
        lines.append(f"  NEEDS REVIEW: {fact.get('id', '?')}: verified {fact.get('verified')} "
                     f"({age_days} days ago, review interval {interval} days)")
    return lines


def _canary_result(root=None):
    """Wraps measure_tokens.format_canary so a test can override it without
    ever touching real transcripts, the same seam every other _xxx() in this
    module already uses for real state (_ensure_fresh_state, dc.discover,
    _open_experiments, _load_facts)."""
    return mt.format_canary(root or TRANSCRIPT_ROOT, days=CANARY_DAYS)


def _canary_lines(canary):
    """One line, NEEDS REVIEW styled when the canary is the alarm, matching
    the wording convention _staleness_lines and _fact_staleness_lines use
    elsewhere in this module. FORMAT UNRECOGNISED is the section 2a hole:
    the transcript parsers stopped recognising the format, so every counter
    fed from usage may now silently read as zero rather than absent."""
    if canary.get("parse_health") == "UNRECOGNISED":
        return [f"  NEEDS REVIEW: {canary['reason']}"]
    return [f"  {canary['reason']}"]


def _version_drift_lines(drift):
    """Render a dc.version_drift() result (drift["no_data"] is False) to
    print-ready lines: one DRIFT line per companion whose version moved,
    one NO DATA line per companion the state never recorded a version for.
    An empty return means neither happened; report() supplies the "no
    drift" clean line for that case, not this function, so a caller can
    never mistake "not yet checked" for "checked, found nothing"."""
    lines = []
    for d in drift["drifted"]:
        observed = f" (observed {d['recorded_at']})" if d.get("recorded_at") else ""
        lines.append(f"  DRIFT: {d['name']}: recorded {d['recorded_version']}"
                     f"{observed} -> live {d['live_version']}")
    for m in drift["missing"]:
        lines.append(f"  NO DATA: {m['name']}: no recorded version to compare "
                     f"(live {m['live_version']})")
    return lines


def _open_experiments(exp_dir=None):
    """Every experiment baseline pinned by `experiment.py start`, read from
    ex.EXP_DIR (the same directory cmd_start writes to and cmd_end reads
    from): one dict per label, {"label", "started"}. Read only, never
    writes.

    ponytail: experiment.py never deletes or flags a baseline file once
    `experiment.py end` has closed it (confirmed by reading cmd_end: no
    os.remove, no "ended" key written back), so this cannot yet tell a
    still-running experiment from an already-closed one; it reports every
    pinned baseline as open. Upgrade path if that starts producing false
    positives: cross-check ex.LEDGER for a later record with the same
    label and drop it from this list."""
    exp_dir = exp_dir or ex.EXP_DIR
    if not os.path.isdir(exp_dir):
        return []
    open_experiments = []
    for fname in sorted(os.listdir(exp_dir)):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(exp_dir, fname)) as f:
                baseline = json.load(f)
        except (OSError, ValueError):
            continue  # sbe: allow-silent one unreadable baseline file is skipped so a single corrupt experiment cannot empty doctor's whole view of open experiments
        label = baseline.get("label")
        started = baseline.get("started")
        if label and started:
            open_experiments.append({"label": label, "started": started})
    return open_experiments


def _parse_iso_utc(s):
    """Epoch seconds for the naive "YYYY-MM-DDTHH:MM:SS" prefix shared by
    both ISO-UTC formats this codebase writes: discover_companions'
    "...SSZ" and experiment.py's _iso()'s "...SS+0000". Both name UTC, so
    the shared 19-character prefix alone is enough to compare them
    chronologically. Returns None on anything that does not match, never
    raises."""
    if not isinstance(s, str) or len(s) < 19:
        return None
    try:
        return calendar.timegm(time.strptime(s[:19], "%Y-%m-%dT%H:%M:%S"))
    except ValueError:
        return None  # sbe: allow-silent an unparseable timestamp becomes NO DATA at the caller, which is what doctor prints, rather than a guessed date


def _spanning_warning_lines(open_experiments, drifted):
    """One line per (open experiment, drifted companion) pair where the
    companion's recorded_at (the last time its now-stale recorded version
    was itself confirmed current) falls at or after the experiment's own
    "started" timestamp. The actual version bump happened strictly after
    recorded_at, so recorded_at >= started guarantees the bump also falls
    after started, inside the experiment's still-open window: a confound
    for that experiment's attribution. A drift whose recorded_at predates
    the experiment start is ambiguous (the bump could equally have
    happened before the experiment opened) and is never warned about,
    matching NO DATA beats a guess."""
    lines = []
    for exp in open_experiments:
        started_epoch = _parse_iso_utc(exp.get("started"))
        if started_epoch is None:
            continue
        for d in drifted:
            recorded_epoch = _parse_iso_utc(d.get("recorded_at"))
            if recorded_epoch is None or recorded_epoch < started_epoch:
                continue
            lines.append(
                f"  SPANNING EXPERIMENT WARNING: experiment '{exp['label']}' now spans "
                f"a companion change: {d['name']} moved {d['recorded_version']} -> "
                f"{d['live_version']} during its window (started {exp['started']}); "
                f"attribution for this experiment can no longer be trusted.")
    return lines


def report():
    companions_data = cfg.load_companions(cfg.COMPANIONS_PATH)
    if not companions_data:
        print("NO DATA: data/companions.json not found or unreadable.")
        print()
        # The canary is unrelated to the companion registry and must run and
        # be honoured regardless: an optional section failing earlier must
        # never silently disable the layer 0 parser-health alarm (found in
        # review: a missing companions.json returned 0 before the canary
        # ever ran).
        print("Transcript format canary (layer 0 parser health, STATE-MODEL section 2a)")
        canary = _canary_result()
        for line in _canary_lines(canary):
            print(line)
        return canary.get("exit_code", 0)
    companions = companions_data.get("companions", [])

    # Loaded before _ensure_fresh_state() below, which may overwrite the
    # state file when it is stale: this is the "recorded" snapshot version
    # drift compares the live check against, and it must be read before
    # any refresh could clobber it with the live values.
    old_state = _load_state()

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
    print()

    print("Version drift")
    live = dc.discover()
    drift = dc.version_drift([c["name"] for c in companions], live, old_state)
    if drift["no_data"]:
        if old_state is None and live is None:
            print("  NO DATA: no companion state file, and live discovery failed.")
        elif old_state is None:
            print("  NO DATA: no companion state file yet (run discover_companions.py "
                  "once to establish a baseline).")
        else:
            print("  NO DATA: live discovery failed (`claude plugin list --json`).")
    else:
        lines = _version_drift_lines(drift)
        for line in (lines or ["  no version drift among curated companions."]):
            print(line)
        if drift["drifted"]:
            for line in _spanning_warning_lines(_open_experiments(), drift["drifted"]):
                print(line)
    print()

    print("Facts (staleness of dated, sourced platform claims)")
    facts, refused, facts_error = _load_facts()
    if facts_error:
        print(f"  NO DATA: {facts_error}; continuing without fact staleness data.")
    else:
        for fid, reason in refused:
            print(f"  REFUSED: {fid}: {reason}")
        stale_facts = _fact_staleness_lines(facts)
        for line in (stale_facts or ["  no facts past their review interval."]):
            print(line)
    print()

    print("Transcript format canary (layer 0 parser health, STATE-MODEL section 2a)")
    canary = _canary_result()
    for line in _canary_lines(canary):
        print(line)

    return canary.get("exit_code", 0)


def main(argv):
    return report()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
