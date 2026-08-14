#!/usr/bin/env python3
"""
fleet.py: Fleet F1, the per-machine per-day record and the git store adapter.

Phase F1 only (docs/superpowers/specs/2026-08-14-token-shield-fleet-design.md,
docs/superpowers/plans/2026-08-14-token-shield-fleet-plan.md). This file
builds one fleet record per machine per day from data that already exists
locally (the telemetry ledger session_end_telemetry.py writes, and the proof
ledger experiment.py writes), and pushes it into an org-owned git store. No
`fleet init`, `fleet join`, `fleet dashboard`, org profile, or budgets: those
are F2 through F5.

THE WHITELIST CONTRACT
-----------------------
data/fleet.schema.json is the frozen, versioned whitelist for this record,
the same discipline signals.py applies to Signals reports: build_candidate()
assembles an internal candidate dict, and build_record() is the only path
that turns a candidate into something that may be queued or pushed, always
by walking the schema and copying out only the keys it names (reusing
signals._project, a generic whitelist walker, rather than re-implementing
it: it takes any schema node and any dict, nothing about it is
Signals-specific). A field this file computes but the schema does not name
cannot reach a pushed record, by construction.

The one exception is the "experiments" array: signals._project's whitelist
walk recurses into nested OBJECT properties but never validates the shape
of items inside a JSON array (a "type": "array" node is just a leaf-type
check). So each experiment record is whitelisted at CONSTRUCTION time
instead, by _day_experiments() below, which names every field it copies out
of the proof ledger one at a time. Nothing about the schema's own
"experiments.items" node is enforced by the walk; it documents the contract,
it does not police it. test_fleet.py calibrates the object-field path (via
_project) and documents this array exception directly.

WHAT F1 DELIBERATELY LEAVES ABSENT
------------------------------------
Per the design doc: no prompts, no file contents, no repo names, no session
transcripts, no user names. Concretely: the telemetry ledger
(session_end_telemetry.py) never wrote any of those to begin with, and the
proof ledger's own richer fields (cohort timestamps, "evidence" prose,
per-session file paths) are simply never named by _day_experiments' explicit
field list, so they never reach a candidate in the first place.

WHAT "PER MODEL" ACTUALLY MEANS HERE
---------------------------------------
The spec asks for counters "per model, per day". The local telemetry ledger
this file reads (session_end_telemetry.record()) carries a distinct MODEL
COUNT per session ("models": len(models)), never model identity: no session
row names which model it ran. So a true per-model split has no honest local
basis in this data source today, and this file does not fabricate one.
Every day's counters are aggregated under the single bucket key "unknown"
(the same "no honest attribution, no guess" name signals.py's own
waste_shares uses for an unattributed remainder). A future phase that wants
real per-model counters needs a ledger change first, not a fleet.py guess.

THE FIELD NAMES
----------------
Inside each model bucket, the four counter fields are named verbatim from
the transcript usage schema measure_tokens.py parses directly off the API
response (input_tokens, output_tokens, cache_read_input_tokens,
cache_creation_input_tokens: see measure_tokens.read_session), never the
ledger's own renamed fields (input, output, cache_read, cache_write_5m,
cache_write_1h, cache_write_unsplit). cache_creation_input_tokens is
reconstructed as cache_write_5m + cache_write_1h + cache_write_unsplit: the
ledger only ever split cache_creation_input_tokens into those two TTL
classes (see measure_tokens.split_writes), it never lost any of it, so the
sum round-trips exactly back to the original counter.

THE GIT STORE ADAPTER
-----------------------
push_record() clones the org's store, writes the record at
fleet/<org>/<machine-id>/<date>.json, commits, and pushes. Every git
subprocess call's exit code is checked explicitly (_run_git, and the
dedicated diff --cached --quiet check in _has_staged_changes, which treats
its two meaningful exit codes, 0 and 1, differently on purpose, and any
other exit code as an error rather than silently picking one meaning). A
store that cannot be reached, or a push that fails for any other reason,
never raises and never blocks the caller: the record is queued locally
instead (LOCAL_QUEUE_DIR), one plain warning is printed, and push_record()
returns False. This matches the design doc's "availability never gates a
developer" rule.

THE READER'S SCHEMA REFUSAL
------------------------------
load_record() refuses (raises FleetSchemaError) a record whose "schema" int
is newer than SCHEMA_VERSION, stating so, rather than guessing at fields it
has never seen. This is the same refusal discipline measure_tokens.py and
experiment.py already apply to their own schema fields.

USAGE
  python3 fleet.py build [--day YYYY-MM-DD] [--config PATH] [--telemetry-ledger PATH] [--experiment-ledger PATH] [--config-fingerprint STR] [--token-shield-version STR]
  python3 fleet.py push --store URL [--day YYYY-MM-DD] [--config PATH] [--telemetry-ledger PATH] [--experiment-ledger PATH] [--config-fingerprint STR] [--token-shield-version STR] [--queue-dir PATH]
"""

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
import time

import experiment as exp
import session_end_telemetry as telem
import signals as sig

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(HERE, "..", "data", "fleet.schema.json")
PLUGIN_MANIFEST_PATH = os.path.join(HERE, "..", ".claude-plugin", "plugin.json")

SCHEMA_VERSION = 1

DEFAULT_FLEET_CONFIG = os.path.expanduser("~/.token-shield/fleet-config.json")
LOCAL_QUEUE_DIR = os.path.expanduser("~/.token-shield/fleet-queue/")


class FleetSchemaError(ValueError):
    """Raised by load_record() when a record's schema is newer than this
    reader understands. The message names the reason; nothing about this
    reader guesses at a field from a schema it has never seen."""


def _load_schema():
    with open(SCHEMA_PATH) as f:
        return json.load(f)


def _display_path(path):
    """`path` with the user's home directory prefix shortened to "~", so a
    printed warning never carries the account name. Mirrors
    signals._display_path exactly; kept local because it is one line and
    fleet.py should not reach into signals.py for something this small."""
    home = os.path.expanduser("~")
    if path.startswith(home):
        return "~" + path[len(home):]
    return path


def _plugin_version():
    try:
        with open(PLUGIN_MANIFEST_PATH) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    v = data.get("version")
    return v if isinstance(v, str) and v else None


def compute_machine_id(hostname, salt):
    """Stable anonymous machine id: sha256 hex digest of "hostname:salt".
    Never the raw hostname: the org's salt is what makes the id unlinkable
    without the org's cooperation, and what lets the org choose whether ids
    are readable (a memorable salt) or pseudonymous (a random one), per the
    design doc's "team, environment: free tags... machine_id: stable
    anonymous id (hash of hostname plus a salt the org sets)"."""
    return hashlib.sha256(f"{hostname}:{salt}".encode("utf-8")).hexdigest()


def _read_local_config(path):
    """Load the local fleet config (org, team, environment, salt, hostname)
    that `fleet join` (F2) will write. Returns None if absent or
    unparseable: F1 ships no `fleet join`, so "no config file yet" is the
    normal state for a machine that has not joined a fleet, not an error."""
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _day_counters(ledger_path, day):
    """Aggregate one day's telemetry ledger rows (session_end_telemetry.py's
    DEFAULT_LEDGER shape) into raw usage-schema counters, bucketed under
    "unknown" (see the module docstring: the ledger carries no model
    identity). Reuses signals._day_rows for the same tolerant per-day
    filtering signals.py already relies on (malformed lines and a missing
    ledger both yield nothing, never a crash). Returns {} when the day has
    no rows with a token count, never a fabricated all-zero bucket."""
    totals = {"input_tokens": 0.0, "output_tokens": 0.0,
              "cache_read_input_tokens": 0.0, "cache_creation_input_tokens": 0.0}
    seen = False
    for row in sig._day_rows(ledger_path, day):
        try:
            inp = float(row.get("input") or 0)
            out = float(row.get("output") or 0)
            rd = float(row.get("cache_read") or 0)
            w5 = float(row.get("cache_write_5m") or 0)
            w1 = float(row.get("cache_write_1h") or 0)
            wu = float(row.get("cache_write_unsplit") or 0)
        except (TypeError, ValueError):
            continue
        if inp == 0 and out == 0 and rd == 0 and w5 == 0 and w1 == 0 and wu == 0:
            continue
        seen = True
        totals["input_tokens"] += inp
        totals["output_tokens"] += out
        totals["cache_read_input_tokens"] += rd
        totals["cache_creation_input_tokens"] += w5 + w1 + wu

    if not seen:
        return {}
    return {"unknown": {k: int(round(v)) for k, v in totals.items()}}


def _day_experiments(exp_ledger_path, day):
    """Read experiment.py's proof ledger (JSON lines, EXP_SCHEMA-shaped
    records) and return the records whose timestamp falls on `day`
    (YYYY-MM-DD), each reduced to an explicit field-by-field whitelist:
    label, confidence, timestamp, target_metric, metric_delta, direction,
    fingerprint_start, fingerprint_end. Built by naming fields one at a
    time, the same "never copy a candidate through unfiltered" rule
    signals.py's _project applies, because the proof ledger's own records
    also carry cohort timestamps and free-text "evidence" that must stay
    off a fleet record by construction, not by discipline. Tolerant of a
    missing or malformed ledger, same as _day_counters."""
    out = []
    if not exp_ledger_path or not os.path.isfile(exp_ledger_path):
        return out
    with open(exp_ledger_path, errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line, parse_constant=sig._reject_non_finite_constant)
            except (json.JSONDecodeError, ValueError):
                continue
            if not isinstance(rec, dict):
                continue
            ts = rec.get("timestamp")
            if not isinstance(ts, str) or ts[:10] != day:
                continue
            confidence = rec.get("confidence")
            if confidence not in ("VERIFIED", "NOT_PROVEN"):
                continue
            label = rec.get("label")
            item = {
                "label": label if isinstance(label, str) and label else "(unlabeled)",
                "confidence": confidence,
                "timestamp": ts,
            }
            metric = rec.get("target_metric")
            if isinstance(metric, str) and metric:
                item["target_metric"] = metric
            delta = rec.get("metric_delta")
            if isinstance(delta, (int, float)) and not isinstance(delta, bool):
                item["metric_delta"] = delta
            direction = rec.get("direction")
            if direction in ("saving", "regression", "flat"):
                item["direction"] = direction
            fp_start = rec.get("fingerprint_start")
            if isinstance(fp_start, str) and fp_start:
                item["fingerprint_start"] = fp_start
            fp_end = rec.get("fingerprint_end")
            if isinstance(fp_end, str) and fp_end:
                item["fingerprint_end"] = fp_end
            out.append(item)
    return out


def build_candidate(telem_ledger, exp_ledger, day, local_config,
                     config_fingerprint=None, token_shield_version=None):
    """Assemble one day's internal candidate dict. NOT a whitelisted record
    yet: build_record() below is the only path that projects this against
    the frozen schema. Returns None (NO DATA) when the day has neither
    token counters nor experiment records to report, so a quiet machine
    never produces a fabricated all-zero record."""
    counters = _day_counters(telem_ledger, day)
    experiments = _day_experiments(exp_ledger, day)
    if not counters and not experiments:
        return None

    local_config = local_config or {}
    candidate = {
        "schema": SCHEMA_VERSION,
        "date": day,
        "counters": counters,
        "experiments": experiments,
    }

    hostname = local_config.get("hostname")
    salt = local_config.get("salt")
    if isinstance(hostname, str) and hostname and isinstance(salt, str) and salt:
        candidate["machine_id"] = compute_machine_id(hostname, salt)

    team = local_config.get("team")
    if isinstance(team, str) and team:
        candidate["team"] = team
    environment = local_config.get("environment")
    if isinstance(environment, str) and environment:
        candidate["environment"] = environment

    if isinstance(config_fingerprint, str) and config_fingerprint:
        candidate["config_fingerprint"] = config_fingerprint

    version = token_shield_version or _plugin_version()
    if isinstance(version, str) and version:
        candidate["token_shield_version"] = version

    return candidate


def build_record(telem_ledger, exp_ledger, day, local_config,
                  config_fingerprint=None, token_shield_version=None):
    """Build one whitelisted fleet record for `day`, or None (NO DATA) when
    the day has nothing to report. Every value that reaches the return has
    been through signals._project against data/fleet.schema.json (the
    "experiments" array excepted, see the module docstring); nothing
    bypasses it."""
    candidate = build_candidate(telem_ledger, exp_ledger, day, local_config,
                                config_fingerprint=config_fingerprint,
                                token_shield_version=token_shield_version)
    if candidate is None:
        return None
    return sig._project(_load_schema(), candidate)


def load_record(path):
    """Parse and validate one fleet record file. Refuses (raises
    FleetSchemaError) a record whose "schema" int is newer than
    SCHEMA_VERSION, rather than guessing at fields it has never seen."""
    with open(path) as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise FleetSchemaError(f"{path}: not a JSON object")
    schema = data.get("schema")
    if not isinstance(schema, int) or isinstance(schema, bool) or schema > SCHEMA_VERSION:
        raise FleetSchemaError(
            f"{path}: record schema {schema!r} is newer than this reader "
            f"understands (schema {SCHEMA_VERSION}); refusing rather than guess")
    return data


# --- the git store adapter --------------------------------------------------

def _run_git(args, cwd=None, timeout=30):
    """Run one git subprocess call, always checking the exit code
    explicitly. Returns (ok, stdout, stderr); ok is True only on exit 0.
    Never raises for a nonzero exit or a missing git binary: both are
    exactly the "store unreachable" cases callers must handle without
    crashing a push, so both come back as ok=False with a reason in
    stderr."""
    try:
        proc = subprocess.run(["git"] + args, cwd=cwd, capture_output=True,
                              text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, "", str(e)
    if proc.returncode != 0:
        return False, proc.stdout, proc.stderr
    return True, proc.stdout, proc.stderr


def _has_staged_changes(clone_dir):
    """Whether `git diff --cached --quiet` sees staged changes in
    clone_dir. Its two meaningful exit codes mean different things (0 = no
    changes, 1 = changes present), so this checks both explicitly and
    returns None (rather than guessing True or False) on any other exit
    code, which the caller treats as a store error, not a "nothing to
    push" no-op."""
    try:
        proc = subprocess.run(["git", "diff", "--cached", "--quiet"],
                              cwd=clone_dir, capture_output=True, text=True,
                              timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode == 0:
        return False
    if proc.returncode == 1:
        return True
    return None


def _queue_locally(record, org, machine_id, date, queue_dir, reason):
    """Write `record` under the local queue dir instead of the store, print
    exactly one plain warning, and return the path written. Never raises:
    this is the landing spot for every "store unreachable" branch in
    push_record."""
    queue_dir = os.path.expanduser(queue_dir or LOCAL_QUEUE_DIR)
    os.makedirs(queue_dir, exist_ok=True)
    try:
        os.chmod(queue_dir, 0o700)
    except OSError:
        pass
    fname = f"{org}__{machine_id}__{date}.json"
    path = os.path.join(queue_dir, fname)
    with open(path, "wb") as f:
        f.write((json.dumps(record, sort_keys=True, indent=2) + "\n").encode("utf-8"))
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    print(f"warning: fleet push queued locally at {_display_path(path)} "
          f"({reason})", file=sys.stderr)
    return path


def push_record(record, store_url, org, machine_id, date, queue_dir=None):
    """Push `record` to the org's git store at
    fleet/<org>/<machine_id>/<date>.json: clone, write, add, commit, push.
    Every git subprocess call's exit code is checked explicitly (_run_git,
    _has_staged_changes). If the store cannot be reached, or any step
    fails, the record queues locally instead (_queue_locally), one plain
    warning is printed, and this function returns False without raising:
    a push never blocks the caller. Returns True once the record has
    actually reached the store (including the idempotent no-op case where
    an identical record is already there)."""
    rel_path = f"fleet/{org}/{machine_id}/{date}.json"

    with tempfile.TemporaryDirectory(prefix="fleet-push-") as tmp:
        clone_dir = os.path.join(tmp, "store")
        ok, _out, err = _run_git(["clone", "--quiet", store_url, clone_dir])
        if not ok:
            reason = _last_line(err) or "could not clone the fleet store"
            _queue_locally(record, org, machine_id, date, queue_dir, reason)
            return False

        dest = os.path.join(clone_dir, rel_path)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            f.write((json.dumps(record, sort_keys=True, indent=2) + "\n").encode("utf-8"))

        ok, _out, err = _run_git(["add", rel_path], cwd=clone_dir)
        if not ok:
            reason = _last_line(err) or "could not stage the fleet record"
            _queue_locally(record, org, machine_id, date, queue_dir, reason)
            return False

        staged = _has_staged_changes(clone_dir)
        if staged is None:
            _queue_locally(record, org, machine_id, date, queue_dir,
                           "could not tell whether the fleet record changed")
            return False
        if not staged:
            return True  # identical record already upstream: nothing to do

        ok, _out, err = _run_git([
            "-c", "user.email=fleet@token-shield.local",
            "-c", "user.name=token-shield-fleet",
            "commit", "--quiet", "-m", f"fleet: {org}/{machine_id} {date}",
        ], cwd=clone_dir)
        if not ok:
            reason = _last_line(err) or "could not commit the fleet record"
            _queue_locally(record, org, machine_id, date, queue_dir, reason)
            return False

        ok, _out, err = _run_git(["push", "--quiet"], cwd=clone_dir)
        if not ok:
            reason = _last_line(err) or "could not push to the fleet store"
            _queue_locally(record, org, machine_id, date, queue_dir, reason)
            return False

    return True


def _last_line(text):
    lines = [l for l in (text or "").strip().splitlines() if l.strip()]
    return lines[-1].strip() if lines else ""


# --- CLI ---------------------------------------------------------------------

def cmd_build(day, config_path, telem_ledger, exp_ledger, config_fingerprint,
              token_shield_version):
    day = day or time.strftime("%Y-%m-%d")
    local_config = _read_local_config(config_path or DEFAULT_FLEET_CONFIG)
    if local_config is None:
        print(f"NO DATA: no local fleet config at "
              f"{_display_path(config_path or DEFAULT_FLEET_CONFIG)} "
              f"(run `fleet join`, not yet built).", file=sys.stderr)
        return 2
    if config_fingerprint is None:
        try:
            config_fingerprint = exp.compute_fingerprint()
        except Exception:
            config_fingerprint = None
    record = build_record(telem_ledger or telem.DEFAULT_LEDGER,
                          exp_ledger or exp.LEDGER, day, local_config,
                          config_fingerprint=config_fingerprint,
                          token_shield_version=token_shield_version)
    if record is None:
        print(f"NO DATA: nothing to report for {day}.", file=sys.stderr)
        return 2
    print(json.dumps(record, sort_keys=True, indent=2))
    return 0


def cmd_push(day, config_path, telem_ledger, exp_ledger, config_fingerprint,
             token_shield_version, store_url, queue_dir):
    day = day or time.strftime("%Y-%m-%d")
    local_config = _read_local_config(config_path or DEFAULT_FLEET_CONFIG)
    if local_config is None:
        print(f"NO DATA: no local fleet config at "
              f"{_display_path(config_path or DEFAULT_FLEET_CONFIG)} "
              f"(run `fleet join`, not yet built).", file=sys.stderr)
        return 2
    if config_fingerprint is None:
        try:
            config_fingerprint = exp.compute_fingerprint()
        except Exception:
            config_fingerprint = None
    record = build_record(telem_ledger or telem.DEFAULT_LEDGER,
                          exp_ledger or exp.LEDGER, day, local_config,
                          config_fingerprint=config_fingerprint,
                          token_shield_version=token_shield_version)
    if record is None:
        print(f"NO DATA: nothing to report for {day}.", file=sys.stderr)
        return 2
    org = local_config.get("org")
    machine_id = record.get("machine_id")
    if not isinstance(org, str) or not org or not machine_id:
        print("refused: local fleet config is missing org or salt; "
              "cannot address the fleet store.", file=sys.stderr)
        return 2
    ok = push_record(record, store_url, org, machine_id, day, queue_dir=queue_dir)
    if ok:
        print(f"pushed: fleet/{org}/{machine_id}/{day}.json")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    sub = ap.add_subparsers(dest="action", required=True)

    def _common(p):
        p.add_argument("--day", default=None, help="YYYY-MM-DD, default today")
        p.add_argument("--config", default=None, help="local fleet config path")
        p.add_argument("--telemetry-ledger", default=None)
        p.add_argument("--experiment-ledger", default=None)
        p.add_argument("--config-fingerprint", default=None)
        p.add_argument("--token-shield-version", default=None)

    p_build = sub.add_parser("build", help="build and print one day's fleet record")
    _common(p_build)

    p_push = sub.add_parser("push", help="build one day's record and push it to the fleet store")
    _common(p_push)
    p_push.add_argument("--store", required=True, help="git remote URL of the org's fleet store")
    p_push.add_argument("--queue-dir", default=None)

    a = ap.parse_args()
    if a.action == "build":
        return cmd_build(a.day, a.config, a.telemetry_ledger, a.experiment_ledger,
                         a.config_fingerprint, a.token_shield_version)
    return cmd_push(a.day, a.config, a.telemetry_ledger, a.experiment_ledger,
                    a.config_fingerprint, a.token_shield_version, a.store,
                    a.queue_dir)


if __name__ == "__main__":
    sys.exit(main())
