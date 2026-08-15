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

PHASE F2: INIT, JOIN, LEAVE, THE MDM ONE-LINER
-------------------------------------------------
F2 adds the admin and machine side of joining a fleet, still against the
same git store adapter F1 built:

  - `fleet init` (admin, once) prints the exact data-sharing disclosure
    BEFORE touching the store, then clones it, refuses to clobber an
    existing org-profile.json without --force, and pushes
    org-profile.json (org, salt, default_mode, telemetry, push_cadence)
    plus a fleet/ directory placeholder. Every answer (store, org, salt,
    default_mode) is also a flag, so init runs with no TTY at all (MDM,
    tests); only when a flag is missing AND stdin is a real terminal does
    it fall back to asking.
  - `fleet join <store-url>` writes the local fleet config (org, salt,
    hostname, team, environment, store) straight from flags: no step in
    join ever depends on the store being reachable, so the "an unreachable
    store never blocks a developer" rule (see the design doc) holds for
    join itself, not only for push. It then builds a REGISTRATION record
    (build_registration_record, below) and pushes it through F1's own
    push_record, so an unreachable store still queues the registration
    locally with one warning rather than failing the join.
  - `fleet leave` deletes the local fleet config; cmd_build and cmd_push
    already refuse with NO DATA when it is absent, so leaving needs no
    other code path to "stop pushes".
  - scripts/fleet-join.sh is the thin POSIX sh wrapper MDM/Jamf deploys as
    one line: it shells out to `python3 fleet.py join` with the org's
    values read from environment variables.

WHY A SEPARATE "REGISTRATION" RECORD
--------------------------------------
build_record (F1) is NO DATA on purpose when a day has no counters and no
experiments, so a brand new machine with an empty telemetry ledger would
never push anything on join, and would never appear on a fleet dashboard
at all. Joining is itself the event worth recording, so
build_registration_record always returns a record (counters={},
experiments=[]) for the day, still whitelisted through the exact same
frozen schema as every other record; it just never applies build_record's
"nothing to report" refusal.

WHAT MADE THIS UNUSABLE AT FLEET SCALE
----------------------------------------
Five mechanics, fixed together, that between them kept an org's view empty
after a rollout no matter how many machines joined:

  - `fleet push` required --store on every invocation even though `fleet
    join` had already saved the store URL locally and nothing ever read it
    back. cmd_push now defaults to the saved value (--store still
    overrides), so the daily command fits in a cron line.
  - the push clone had no depth limit, so against a store holding a year
    of records from a thousand machines it could not finish inside
    GIT_TIMEOUT_SECONDS, and that timeout was caught and downgraded to a
    local queue on every machine. It is --depth 1 now, the same flags the
    profile-check clone already used.
  - a push rejected non-fast-forward (two machines pushing on the same day,
    the ordinary case after standup) was never retried. push_record now
    pulls with rebase once and retries before falling back to the queue.
  - the queue was silent: cmd_push printed nothing and returned 0 whether
    the record reached the store or sat on disk, so a cron line reading the
    exit code saw success fleet-wide while nothing arrived. A queued push
    now says NOT DELIVERED on stderr with the number waiting and the
    command that replays them (`push --drain`, which is also how a backlog
    gets replayed at all), and exits EXIT_QUEUED, never 0.
  - records were committed under one identity shared by every machine in
    the org. Each record now commits as its own machine_id, so git history
    attributes it to the machine that CLAIMS to have written it. Records
    remain UNSIGNED and forgeable by anyone with store write access;
    signing is a separate unit and a half-signature would be worse.

USAGE
  python3 fleet.py build [--day YYYY-MM-DD] [--config PATH] [--telemetry-ledger PATH] [--experiment-ledger PATH] [--config-fingerprint STR] [--token-shield-version STR]
  python3 fleet.py push [--store URL] [--drain] [--day YYYY-MM-DD] [--config PATH] [--telemetry-ledger PATH] [--experiment-ledger PATH] [--config-fingerprint STR] [--token-shield-version STR] [--queue-dir PATH]
  python3 fleet.py init <store-url> --org NAME --salt SALT --default-mode conservative|balanced|aggressive [--force]
  python3 fleet.py join <store-url> --org NAME --salt SALT [--team TAG] [--environment TAG] [--hostname HOST] [--day YYYY-MM-DD] [--config PATH] [--queue-dir PATH]
  python3 fleet.py leave [--config PATH] [--queue-dir PATH]
"""

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
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

ORG_PROFILE_FILENAME = "org-profile.json"
ORG_PROFILE_SCHEMA_VERSION = 1
VALID_DEFAULT_MODES = ("conservative", "balanced", "aggressive")

# The local copy of DISCLOSURE_TEXT `fleet join` leaves next to the fleet
# config, so the owner of an MDM-enrolled machine can read offline what
# their machine shares (see cmd_join).
DISCLOSURE_FILENAME = "fleet-disclosure.txt"

# Every git subprocess in this file runs under this one timeout, named here
# so an org with a slow store can see it and change it in one place instead
# of hunting for a number inside a call. It is not a per-call knob on
# purpose: a fleet where one git call needs longer than another is a fleet
# with a store problem to fix, not a timeout to tune.
GIT_TIMEOUT_SECONDS = 30

# cmd_push's exit status when the record was QUEUED LOCALLY rather than
# delivered to the store. Distinct from 0 (delivered) and from 2 (refused,
# or NO DATA) precisely so a cron line that reads only the exit code can
# tell "the store has this record" from "this machine is holding it": that
# gap is how a fleet-wide delivery failure stayed invisible.
EXIT_QUEUED = 3


# --- SECURITY REVIEW FIXES (post-F2 independent review) --------------------
#
# 1. Symlink write-through: every write into a freshly cloned fleet store or
#    the local queue dir now goes through _write_bytes_no_symlink /
#    _makedirs_no_symlink, which refuse (FleetSymlinkError) rather than
#    follow a symlink planted anywhere in either tree. cmd_init's "refuse to
#    overwrite without --force" guard switched from os.path.isfile (follows
#    a symlink, reads a dangling one as absent) to os.path.lexists (a
#    symlink, dangling or not, counts as present).
# 2. Path injection: org, machine_id, and date are validated against strict
#    anchored patterns (_validate_org, _validate_machine_id, _validate_day)
#    before they are ever interpolated into fleet/<org>/<machine_id>/
#    <date>.json or a local-queue filename, or trusted as a record's "date".
#    A value that fails is a named refusal (rc 2), never a raw exception and
#    never a path outside the queue/store root.
# 3. Tags silently dropped: team/environment are validated at join time
#    against the frozen schema's own tag pattern (_validate_tag), using a
#    \Z-anchored regex rather than the schema's own $-anchored one (Python's
#    $ matches just before a trailing newline, so "ios\n" would otherwise
#    survive sig._project's own check and reach a pushed record with an
#    embedded newline). A tag that would not survive into the record is
#    refused loudly instead of silently dropped.
# 4. Salt reversibility: `fleet init` now writes salt_fingerprint
#    (sha256(salt).hexdigest()) to org-profile.json instead of the raw
#    salt, so a fleet member who can only read the store (never handed the
#    salt directly) cannot recover it. `fleet join` checks the store's
#    profile (when reachable) and refuses a mismatched --org or --salt
#    before ever writing the local config, catching a salt typo that would
#    otherwise silently create a phantom machine_id for a real machine.
# 5. `fleet leave` now removes the local queue dir (LOCAL_QUEUE_DIR) along
#    with the config file, so "uninstall leaves no trace" is actually true.
# 6. fleet-join.sh no longer puts the salt on argv (world-readable via
#    /proc/PID/cmdline while the process runs): it stays in the environment
#    (FLEET_SALT), and cmd_join falls back to os.environ.get("FLEET_SALT")
#    when --salt is not given as a flag.
#
# See docs/FLEET.md for the admin-facing version of all six.


_ORG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*\Z")
_MACHINE_ID_RE = re.compile(r"^[0-9a-f]{64}\Z")
_DAY_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
_TAG_RE = re.compile(r"^[a-z0-9_-]+\Z")


class FleetValidationError(ValueError):
    """Raised when org, machine_id, a day, or a team/environment tag fails
    its anchored pattern before it is interpolated into a filesystem path
    (fleet/<org>/<machine_id>/<date>.json, or a local-queue filename) or
    copied into a pushed record. Every pattern here is anchored with \\Z,
    never a trailing $: Python's $ matches just before a trailing newline
    at the end of the string, which would let a value like "ios\\n" slip
    through a naive $-anchored check silently (see _validate_tag)."""


def _validate_org(org):
    """org must be one filesystem-safe path component: lowercase letters,
    digits, underscore, hyphen; no slash, no dot, no dotdot. Refused
    (FleetValidationError) before it is ever interpolated into
    fleet/<org>/<machine_id>/<date>.json (push_record's rel_path) or a
    local-queue filename, so "acme/platform" or "../escaped" is a named
    refusal at the CLI (rc 2), never a FileNotFoundError or a write that
    lands outside the queue or store root."""
    if not isinstance(org, str) or not _ORG_RE.match(org):
        raise FleetValidationError(
            f"refused: org {org!r} must match ^[a-z0-9][a-z0-9_-]*$ "
            f"(lowercase letters, digits, underscore, hyphen only; no "
            f"slash, no dot)")


def _validate_machine_id(machine_id):
    """machine_id must be exactly the 64-char lowercase hex sha256 digest
    compute_machine_id produces. Defense in depth: every CLI path that
    reaches push_record already computes machine_id itself via
    compute_machine_id, but push_record is a public function, and this
    guard means no caller can make it interpolate an arbitrary string into
    a filesystem path."""
    if not isinstance(machine_id, str) or not _MACHINE_ID_RE.match(machine_id):
        raise FleetValidationError(
            "refused: machine_id must be a 64-character lowercase hex "
            "sha256 digest")


def _validate_day(day):
    """day must be exactly YYYY-MM-DD. Refused before it is interpolated
    into a filesystem path or trusted as a record's "date" field. Without
    this, a malformed day like "2026-8-4" would still build and push a
    record (build/push never fail on their own), just one whose "date" key
    silently disappeared at schema projection (the pattern fails
    _value_conforms, so sig._project drops the key rather than keeping a
    bad one) -- a worse failure than a loud, named refusal."""
    if not isinstance(day, str) or not _DAY_RE.match(day):
        raise FleetValidationError(f"refused: --day {day!r} must match YYYY-MM-DD")


def _validate_tag(flag_name, value):
    """team/environment must match the frozen schema's own tag pattern
    (data/fleet.schema.json: "^[a-z0-9_-]+$"), checked here with a
    \\Z-anchored regex rather than the schema's own $-anchored one, and
    checked at JOIN time rather than relying on sig._project to silently
    drop a non-conforming value at build time. A tag that would not
    survive into the pushed record must never be accepted quietly: "iOS"
    (a capital), "prod us" (a space), and "ios\\n" (a trailing newline,
    which a $-anchored check alone would miss) are all refused, named,
    with the allowed charset stated in the message. None or "" is fine:
    the tag is optional."""
    if value is None or value == "":
        return
    if not isinstance(value, str) or not _TAG_RE.match(value):
        raise FleetValidationError(
            f"refused: --{flag_name} {value!r} must match ^[a-z0-9_-]+$ "
            f"(lowercase letters, digits, underscore, hyphen only: no "
            f"capitals, spaces, or newlines); this tag would otherwise be "
            f"silently dropped from the pushed record")


# Printed by `fleet init`, unconditionally, before any file is created or
# any commit made: exactly the "deliberately absent" list the design doc
# names, restated as what IS shared so an admin never has to infer it.
DISCLOSURE_TEXT = """\
DATA THIS FLEET WILL SHARE, PER MACHINE, PER PUSH:
  - token counters (input, output, cache read, cache write), bucketed by day
  - labeled experiment results (VERIFIED or NOT_PROVEN) with their fingerprints
  - this machine's config fingerprint and installed token-shield version
  - the team and environment tags set at join time
  - a machine id: a one-way hash of the hostname and this org's salt, never
    the raw hostname
NEVER SHARED, by design: prompts, file contents, repo names, session
transcripts, or user names."""


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


def _harden(path, mode):
    """chmod `path` to `mode`, and SAY SO when it does not take.

    Every one of these calls used to be `except OSError: pass`. Swallowing an
    error about somebody else's bad data is this module's documented design: a
    record that cannot be read becomes its own NO DATA row rather than killing
    the run. Swallowing an error about OUR OWN promise not being kept is a
    different thing. The docstrings here state that the config is 0600 and its
    directory 0700 because they hold an org's store URL and its salt, and on a
    filesystem where chmod does not take (a network mount, a synced folder,
    some container overlays) the file kept the umask default while the
    docstring went on asserting otherwise.

    Best effort is still the right behaviour, so this never raises: refusing to
    save a config because a permission could not be tightened would lose the
    user's work over a warning. It just stops being silent. stderr, not stdout,
    so a caller piping this command's output is unaffected."""
    try:
        os.chmod(path, mode)
    except OSError as e:
        print(f"warning: could not set permissions {oct(mode)} on "
              f"{_display_path(path)} ({e}). It keeps whatever mode it was "
              f"created with, which may be readable by other accounts on this "
              f"machine.", file=sys.stderr)


def _write_local_config(path, config):
    """Write `fleet join`'s local fleet config as JSON, private to this
    account: parent dir at 0700, file at 0600. Never raises on a chmod
    that fails (some filesystems do not support the bits), matching the
    same best-effort permission discipline _queue_locally already applies
    to queued records."""
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
        _harden(d, 0o700)
    with open(path, "wb") as f:
        f.write((json.dumps(config, sort_keys=True, indent=2) + "\n").encode("utf-8"))
    _harden(path, 0o600)


def _disclosure_path(config_path):
    """Where `fleet join` leaves the machine owner's readable copy of
    DISCLOSURE_TEXT: beside the local fleet config, so `fleet leave` can
    remove it along with the rest of this machine's trace."""
    return os.path.join(os.path.dirname(config_path) or ".", DISCLOSURE_FILENAME)


def _write_disclosure_copy(config_path):
    """Write DISCLOSURE_TEXT beside the local fleet config, with the same
    permission discipline _write_local_config applies (parent dir 0700,
    file 0600). Printing the disclosure during `fleet join` tells whoever
    ran the join; the copy is what lets the machine's owner read it again
    later, offline, long after an MDM one-liner scrolled past. Returns the
    path written."""
    path = _disclosure_path(config_path)
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
        _harden(d, 0o700)
    with open(path, "wb") as f:
        f.write((DISCLOSURE_TEXT + "\n").encode("utf-8"))
    _harden(path, 0o600)
    return path


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


def build_registration_record(day, local_config, config_fingerprint=None,
                              token_shield_version=None):
    """The minimal record `fleet join` pushes so a machine appears on the
    fleet dashboard immediately, even before any telemetry ledger row
    exists for `day`. Unlike build_record, this never returns None for an
    empty day: registering is itself the event being recorded, not a data
    day, so counters={} and experiments=[] are the honest content, not a
    NO DATA case. Still whitelisted through the exact same frozen schema
    as every other record (sig._project), so it can never carry more than
    those two constants plus the identity and version fields every other
    record carries (machine_id, team, environment, config_fingerprint,
    token_shield_version)."""
    local_config = local_config or {}
    candidate = {
        "schema": SCHEMA_VERSION,
        "date": day,
        "counters": {},
        "experiments": [],
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

def _run_git(args, cwd=None, timeout=GIT_TIMEOUT_SECONDS):
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
                              timeout=GIT_TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode == 0:
        return False
    if proc.returncode == 1:
        return True
    return None


class FleetSymlinkError(OSError):
    """Raised when a fleet write's target path, or a parent directory
    component strictly inside the tree being written to, is a symlink
    (dangling or not). Every fleet write lands inside a tree this process
    does not fully control (a freshly cloned fleet store, whose content is
    whatever the store holds; the local queue dir, which any other process
    on this machine can have pre-populated): a symlink planted anywhere in
    either tree must be refused, never followed, or the write could land
    on an arbitrary file outside that tree."""


def _refuse_symlinks_under(root, path):
    """Walk every path component strictly between `root` (exclusive,
    trusted: a directory this process itself created, like a fresh
    tempfile.mkdtemp() clone dir) and `path` (inclusive), raising
    FleetSymlinkError the moment one exists and is a symlink.
    os.path.islink is checked, never os.path.isfile/isdir: those follow a
    symlink to ask about its target, which is exactly the wrong check here
    (a dangling symlink islinks True but isfiles False, so islink is also
    what "counts a symlink as present regardless of what it points to"
    actually requires)."""
    root_abs = os.path.abspath(root)
    path_abs = os.path.abspath(path)
    rel = os.path.relpath(path_abs, root_abs)
    if rel == os.pardir or rel.startswith(os.pardir + os.sep):
        raise FleetSymlinkError(f"refused: {path_abs} is outside {root_abs}")
    cur = root_abs
    for part in rel.split(os.sep):
        cur = os.path.join(cur, part)
        if os.path.islink(cur):
            raise FleetSymlinkError(
                f"refused: refusing to write through symlink at {cur}")


def _makedirs_no_symlink(root, dir_path):
    """Create `dir_path` (which must be under `root`) one path component at
    a time, refusing the moment an existing component is a symlink. Never
    plain os.makedirs(..., exist_ok=True): that treats a symlinked
    directory component as "already exists" (os.path.isdir follows the
    symlink) and happily creates the rest of the path inside whatever the
    symlink points to."""
    root_abs = os.path.abspath(root)
    dir_abs = os.path.abspath(dir_path)
    if dir_abs == root_abs:
        return
    _refuse_symlinks_under(root, dir_path)
    rel = os.path.relpath(dir_abs, root_abs)
    cur = root_abs
    for part in rel.split(os.sep):
        cur = os.path.join(cur, part)
        if not os.path.isdir(cur):
            os.mkdir(cur)


def _write_bytes_no_symlink(root, path, data, mode=0o600):
    """Write `data` (bytes) to `path`, refusing (FleetSymlinkError) if
    `path` itself, or any parent directory component between `root`
    (exclusive) and `path`, is a symlink. Used for every write into a
    freshly cloned fleet store (root=clone_dir) or the local queue dir
    (root=the queue dir's own parent, so the queue dir itself is checked
    too, not just what is inside it). Opens the final file with O_NOFOLLOW
    as a second, independent check: even a symlink planted at the exact
    target path in the gap between the walk above and this open is
    refused, not followed (a TOCTOU window this closes rather than
    ignores)."""
    d = os.path.dirname(path)
    if d:
        _makedirs_no_symlink(root, d)
    _refuse_symlinks_under(root, path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, mode)
    except OSError as e:
        raise FleetSymlinkError(
            f"refused: refusing to write through symlink at {path}: {e}") from e
    with os.fdopen(fd, "wb") as f:
        f.write(data)


def _queue_locally(record, org, machine_id, date, queue_dir, reason):
    """Write `record` under the local queue dir instead of the store, print
    exactly one plain warning, and return the path written. Never raises
    for an ordinary "store unreachable" case: this is the landing spot for
    every such branch in push_record. DOES raise FleetSymlinkError if
    queue_dir itself, or the record's filename inside it, is a symlink
    (see _write_bytes_no_symlink): that is a different failure class (a
    symlink planted by another process on this machine, not an
    unreachable store) and must never be silently absorbed here."""
    _validate_org(org)
    _validate_machine_id(machine_id)
    _validate_day(date)
    queue_dir = os.path.expanduser(queue_dir or LOCAL_QUEUE_DIR)
    queue_root = os.path.dirname(os.path.normpath(queue_dir)) or queue_dir
    fname = f"{org}__{machine_id}__{date}.json"
    path = os.path.join(queue_dir, fname)
    data = (json.dumps(record, sort_keys=True, indent=2) + "\n").encode("utf-8")
    _write_bytes_no_symlink(queue_root, path, data, mode=0o600)
    _harden(queue_dir, 0o700)
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
    an identical record is already there).

    Raises FleetValidationError immediately, before any clone or write, if
    org, machine_id, or date fails its anchored pattern (see _validate_org
    et al.): defense in depth, since every CLI caller already validates
    these before calling push_record. Raises FleetSymlinkError, also
    before any write completes, if the cloned store already contains a
    symlink at the record's path or one of its parent directories: this is
    the one failure push_record does NOT downgrade to a local queue
    fallback, because writing the queued copy instead would silently mask
    a store that has been tampered with rather than refuse loudly.

    THE CLONE IS SHALLOW (--depth 1), the same flags _fetch_org_profile
    already used: a store holding a year of records from a thousand
    machines is hundreds of thousands of files and commits, and a full
    clone of it cannot finish inside GIT_TIMEOUT_SECONDS. That timeout is
    caught and downgraded to a local queue, so an unbounded clone here
    meant every push on every machine quietly stopped reaching the store
    while each one still looked like it had worked. This push needs one
    commit's worth of tree, never the history.

    A REJECTED PUSH IS RETRIED ONCE, after `git pull --rebase`: when two
    machines push on the same day the second is rejected non-fast-forward,
    which is the ordinary case at any fleet size (a hundred machines
    pushing after standup collide constantly), not an exceptional one. One
    rebase and one retry resolves it; anything still failing after that
    falls through to the local queue exactly as before."""
    _validate_org(org)
    _validate_machine_id(machine_id)
    _validate_day(date)
    rel_path = f"fleet/{org}/{machine_id}/{date}.json"
    # Commit as the machine, not as one identity shared by the whole org:
    # git history can then attribute each record to the machine that
    # CLAIMS to have written it. machine_id is 64-char lowercase hex by
    # _validate_machine_id above, so it is safe to interpolate here.
    # Records stay UNSIGNED and forgeable by anyone with write access to
    # the store; real signing is a separate unit, and a half-signature
    # would be worse than none.
    identity = ["-c", f"user.name={machine_id}",
                "-c", f"user.email={machine_id}@fleet.token-shield.local"]

    with tempfile.TemporaryDirectory(prefix="fleet-push-") as tmp:
        clone_dir = os.path.join(tmp, "store")
        ok, _out, err = _run_git(
            ["clone", "--quiet", "--depth", "1", store_url, clone_dir])
        if not ok:
            reason = _last_line(err) or "could not clone the fleet store"
            _queue_locally(record, org, machine_id, date, queue_dir, reason)
            return False

        dest = os.path.join(clone_dir, rel_path)
        data = (json.dumps(record, sort_keys=True, indent=2) + "\n").encode("utf-8")
        _write_bytes_no_symlink(clone_dir, dest, data, mode=0o644)

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

        ok, _out, err = _run_git(
            identity + ["commit", "--quiet", "-m",
                        f"fleet: {org}/{machine_id} {date}"],
            cwd=clone_dir)
        if not ok:
            reason = _last_line(err) or "could not commit the fleet record"
            _queue_locally(record, org, machine_id, date, queue_dir, reason)
            return False

        ok, _out, err = _run_git(["push", "--quiet"], cwd=clone_dir)
        if not ok:
            # Almost always a same-day collision with another machine, so
            # rebase this one commit on top of whatever landed first and
            # try once more. The identity is passed here too: a rebase
            # rewrites a commit and needs a committer, which a machine with
            # no git identity configured at all would otherwise not have.
            rebased, _out, rebase_err = _run_git(
                identity + ["pull", "--rebase", "--quiet"], cwd=clone_dir)
            if rebased:
                ok, _out, err = _run_git(["push", "--quiet"], cwd=clone_dir)
            else:
                err = rebase_err or err
            if not ok:
                reason = _last_line(err) or "could not push to the fleet store"
                _queue_locally(record, org, machine_id, date, queue_dir, reason)
                return False

    return True


def _last_line(text):
    lines = [l for l in (text or "").strip().splitlines() if l.strip()]
    return lines[-1].strip() if lines else ""


def queued_record_files(queue_dir=None):
    """Every .json file the local queue is currently holding, sorted by
    name. An unreadable or absent queue dir is an empty queue, never an
    error: the queue only exists once something has been queued into it."""
    queue_dir = os.path.expanduser(queue_dir or LOCAL_QUEUE_DIR)
    try:
        names = sorted(os.listdir(queue_dir))
    except OSError:
        return []
    return [os.path.join(queue_dir, n) for n in names if n.endswith(".json")]


def _parse_queued_name(path):
    """Recover (org, machine_id, date) from a local-queue filename, the
    inverse of _queue_locally's f"{org}__{machine_id}__{date}.json". Splits
    from the RIGHT because org may legally contain underscores (_ORG_RE
    allows them, so an org can contain a double underscore too) while
    machine_id (64 hex chars) and date (YYYY-MM-DD) never can. Returns None
    when the name does not parse, or when any of the three fails its own
    anchored pattern: a file this queue did not write is reported by the
    caller, never guessed at."""
    base = os.path.basename(path)
    if not base.endswith(".json"):
        return None
    stem = base[:-len(".json")]
    try:
        rest, date = stem.rsplit("__", 1)
        org, machine_id = rest.rsplit("__", 1)
    except ValueError:
        return None
    try:
        _validate_org(org)
        _validate_machine_id(machine_id)
        _validate_day(date)
    except FleetValidationError:
        return None
    return org, machine_id, date


def drain_queue(store_url, queue_dir=None):
    """Replay every record the local queue is holding into the store, and
    return (delivered, left). Each delivered record's queued copy is
    removed; a record whose push fails again is re-queued by push_record
    itself (same filename, same content) and stays for the next drain, so a
    drain is safe to run on every cadence.

    Nothing is dropped quietly: a queued file this queue did not write, or
    one that no longer parses as a record, is counted, NAMED on stderr, and
    left exactly where it is, and it still counts toward `left`. A drain
    that says "0 still queued" means the queue is genuinely empty.

    One clone per queued record (push_record's own): a drain is normally
    one or two days of backlog, and batching every queued record into a
    single clone is worth writing the day a fleet actually shows a backlog
    deep enough to notice."""
    delivered = 0
    skipped = []
    for path in queued_record_files(queue_dir):
        parsed = _parse_queued_name(path)
        if parsed is None:
            skipped.append(os.path.basename(path))
            continue
        org, machine_id, date = parsed
        try:
            record = load_record(path)
        except (OSError, ValueError):
            # Includes FleetSchemaError (a ValueError): a queued record from
            # a NEWER token-shield than this one is refused, not guessed at.
            skipped.append(os.path.basename(path))
            continue
        if push_record(record, store_url, org, machine_id, date,
                       queue_dir=queue_dir):
            try:
                os.remove(path)
                delivered += 1
            except OSError as e:
                # Delivered, but still on disk: the next drain will push it
                # again (an identical record is an idempotent no-op), and
                # `left` below still counts it, so this never reads as done.
                print(f"warning: {_display_path(path)} reached the store but "
                      f"could not be removed from the queue: {e}",
                      file=sys.stderr)

    left = len(queued_record_files(queue_dir))
    if skipped:
        print(f"warning: {len(skipped)} queued file(s) left untouched, not a "
              f"fleet record this queue wrote: {', '.join(skipped)}",
              file=sys.stderr)
    print(f"drained: {delivered} record(s) delivered, {left} still queued.")
    return delivered, left


def _fetch_org_profile(store_url):
    """Best-effort read of org-profile.json from the fleet store, used only
    to validate a join's --org/--salt against what `fleet init` actually
    wrote. Returns None when the store cannot be reached at all, or the
    profile is absent or unparseable there: exactly the same "unreachable
    never blocks" rule every other fleet write already follows, so a join
    still proceeds without a mismatch check in that case."""
    with tempfile.TemporaryDirectory(prefix="fleet-check-") as tmp:
        clone_dir = os.path.join(tmp, "store")
        ok, _out, _err = _run_git(
            ["clone", "--quiet", "--depth", "1", store_url, clone_dir])
        if not ok:
            return None
        profile_path = os.path.join(clone_dir, ORG_PROFILE_FILENAME)
        if not os.path.isfile(profile_path):
            return None
        try:
            with open(profile_path) as f:
                data = json.load(f)
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None


def _check_org_profile_matches(store_url, org, salt):
    """Refuse (FleetValidationError) a join whose --org or --salt does not
    match the org profile `fleet init` wrote, when the store is reachable
    enough to read it. Catches a salt typo before it silently creates a
    phantom machine (a different machine_id for the same real machine,
    since compute_machine_id hashes the salt verbatim): a wrong salt is
    not a "store unreachable" case, it is a value this machine got wrong,
    and it is caught here before the local config is ever written with it.
    Never refuses for an unreachable store or a store with no profile yet
    (_fetch_org_profile returns None either way): that keeps the "an
    unreachable store never blocks a developer" rule join already follows
    for its own registration push."""
    profile = _fetch_org_profile(store_url)
    if profile is None:
        return
    stored_org = profile.get("org")
    if isinstance(stored_org, str) and stored_org and stored_org != org:
        raise FleetValidationError(
            f"refused: --org {org!r} does not match this store's org "
            f"{stored_org!r} (from {ORG_PROFILE_FILENAME})")
    stored_fingerprint = profile.get("salt_fingerprint")
    if isinstance(stored_fingerprint, str) and stored_fingerprint:
        if hashlib.sha256(salt.encode("utf-8")).hexdigest() != stored_fingerprint:
            raise FleetValidationError(
                f"refused: --salt does not match this org's salt "
                f"(salt_fingerprint mismatch in {ORG_PROFILE_FILENAME}); "
                f"check for a typo")


# --- CLI ---------------------------------------------------------------------

def _maybe_prompt(value, prompt_text):
    """Return `value` unchanged whenever it is already set, or whenever
    stdin is not a real terminal (MDM, a test harness, a CI runner): every
    answer `fleet init` needs is also a flag, so a missing flag in a
    non-interactive context stays missing and is reported by the caller's
    own validation, never guessed. Only prompts (input()) when a human is
    actually there to answer. Never raises on EOF; a missing answer just
    leaves `value` as it was. KeyboardInterrupt is NOT caught here (unlike
    EOFError): it propagates to the caller, so Ctrl-C during any one
    prompt exits cmd_init on the spot instead of silently moving on to
    prompt for the NEXT field too (which is what swallowing it here used
    to do: up to four Ctrl-C's to actually escape, one per prompt)."""
    if value:
        return value
    if not sys.stdin.isatty():
        return value
    try:
        entered = input(prompt_text)
    except EOFError:
        return value
    entered = entered.strip()
    return entered or value


def cmd_init(store, org, salt, default_mode, force):
    try:
        store = _maybe_prompt(store, "Fleet store git URL: ")
        org = _maybe_prompt(org, "Org name: ")
        salt = _maybe_prompt(
            salt, "Org salt (every machine that joins must use this exact "
            "value): ")
        default_mode = _maybe_prompt(
            default_mode, f"Default mode ({'/'.join(VALID_DEFAULT_MODES)}): ")
    except KeyboardInterrupt:
        # Exits on the FIRST interrupt: _maybe_prompt no longer swallows
        # KeyboardInterrupt itself, so this is the only place it is caught,
        # once, for the whole prompt sequence.
        print("\nrefused: interrupted", file=sys.stderr)
        return 2

    missing = [name for name, v in (("store", store), ("--org", org),
                                    ("--salt", salt),
                                    ("--default-mode", default_mode))
              if not v]
    if missing:
        print(f"refused: missing required value(s): {', '.join(missing)}",
              file=sys.stderr)
        return 2
    if default_mode not in VALID_DEFAULT_MODES:
        print(f"refused: --default-mode must be one of "
              f"{', '.join(VALID_DEFAULT_MODES)} (got {default_mode!r})",
              file=sys.stderr)
        return 2
    try:
        _validate_org(org)
    except FleetValidationError as e:
        print(str(e), file=sys.stderr)
        return 2

    # Printed before any git operation, so an admin sees exactly what will
    # be shared even if the clone below fails.
    print(DISCLOSURE_TEXT)

    with tempfile.TemporaryDirectory(prefix="fleet-init-") as tmp:
        clone_dir = os.path.join(tmp, "store")
        ok, _out, err = _run_git(["clone", "--quiet", store, clone_dir])
        if not ok:
            reason = _last_line(err) or "could not clone the fleet store"
            print(f"refused: {reason}", file=sys.stderr)
            return 2

        profile_path = os.path.join(clone_dir, ORG_PROFILE_FILENAME)
        # os.path.lexists (never os.path.isfile) so a symlink at this path
        # counts as "already exists" whether or not it is dangling:
        # isfile() follows a symlink to ask about its TARGET, and a
        # dangling symlink then reads as absent, which would let a second
        # `fleet init` skip the --force requirement entirely against a
        # path an attacker planted.
        if os.path.lexists(profile_path) and not force:
            print(f"refused: {ORG_PROFILE_FILENAME} already exists in "
                  f"{store}; pass --force to overwrite", file=sys.stderr)
            return 2

        # The store never holds the raw salt, only a one-way fingerprint:
        # a fleet member who can read the store but was never handed the
        # salt directly cannot recover it from org-profile.json. See
        # docs/FLEET.md for exactly what this does and does not protect
        # against (a salt-holder can still correlate hostnames).
        salt_fingerprint = hashlib.sha256(salt.encode("utf-8")).hexdigest()
        profile = {
            "schema": ORG_PROFILE_SCHEMA_VERSION,
            "org": org,
            "salt_fingerprint": salt_fingerprint,
            "default_mode": default_mode,
            "telemetry": "counters_only",
            "push_cadence": "manual",
        }
        profile_data = (json.dumps(profile, sort_keys=True, indent=2) + "\n").encode("utf-8")
        try:
            _write_bytes_no_symlink(clone_dir, profile_path, profile_data, mode=0o644)
        except FleetSymlinkError as e:
            print(str(e), file=sys.stderr)
            return 2

        fleet_dir = os.path.join(clone_dir, "fleet")
        try:
            _makedirs_no_symlink(clone_dir, fleet_dir)
        except FleetSymlinkError as e:
            print(str(e), file=sys.stderr)
            return 2
        keep_path = os.path.join(fleet_dir, ".gitkeep")
        if not os.path.lexists(keep_path):
            try:
                _write_bytes_no_symlink(clone_dir, keep_path, b"", mode=0o644)
            except FleetSymlinkError as e:
                print(str(e), file=sys.stderr)
                return 2

        ok, _out, err = _run_git(
            ["add", ORG_PROFILE_FILENAME, os.path.join("fleet", ".gitkeep")],
            cwd=clone_dir)
        if not ok:
            reason = _last_line(err) or "could not stage the org profile"
            print(f"refused: {reason}", file=sys.stderr)
            return 2

        staged = _has_staged_changes(clone_dir)
        if staged is None:
            print("refused: could not tell whether the org profile changed",
                  file=sys.stderr)
            return 2
        if not staged:
            print(f"nothing to do: {ORG_PROFILE_FILENAME} in {store} "
                  f"already matches.")
            return 0

        ok, _out, err = _run_git([
            "-c", "user.email=fleet@token-shield.local",
            "-c", "user.name=token-shield-fleet",
            "commit", "--quiet", "-m", f"fleet: init {org}",
        ], cwd=clone_dir)
        if not ok:
            reason = _last_line(err) or "could not commit the org profile"
            print(f"refused: {reason}", file=sys.stderr)
            return 2

        ok, _out, err = _run_git(["push", "--quiet"], cwd=clone_dir)
        if not ok:
            reason = _last_line(err) or "could not push the org profile"
            print(f"refused: {reason}", file=sys.stderr)
            return 2

    print(f"initialized fleet store: org={org} default_mode={default_mode} "
          f"store={store}")
    return 0


def cmd_join(store, org, salt, team, environment, hostname, day,
             config_path, queue_dir, config_fingerprint,
             token_shield_version):
    # fleet-join.sh (the MDM wrapper) passes the salt through the
    # environment rather than argv: argv is world-readable via
    # /proc/PID/cmdline on Linux while the process runs, an environment
    # variable is not exposed that way. A --salt flag still wins if given.
    salt = salt or os.environ.get("FLEET_SALT")

    missing = [name for name, v in (("store", store), ("--org", org),
                                    ("--salt", salt))
              if not v]
    if missing:
        print(f"refused: missing required value(s): {', '.join(missing)}",
              file=sys.stderr)
        return 2

    try:
        _validate_org(org)
        _validate_tag("team", team)
        _validate_tag("environment", environment)
    except FleetValidationError as e:
        print(str(e), file=sys.stderr)
        return 2

    day = day or time.strftime("%Y-%m-%d")
    try:
        _validate_day(day)
    except FleetValidationError as e:
        print(str(e), file=sys.stderr)
        return 2

    hostname = hostname or platform.node()
    if not hostname:
        print("refused: could not determine this machine's hostname; "
              "pass --hostname", file=sys.stderr)
        return 2

    config_path = config_path or DEFAULT_FLEET_CONFIG

    # The OWNER of this machine has to be told what it will share, and told
    # BEFORE it is enrolled. cmd_init prints this too, but init is run once
    # by the ADMIN on the ADMIN's own machine: on a managed rollout
    # (scripts/fleet-join.sh, deployed by MDM) join is the only command
    # that ever runs here, so the developer sitting at this machine never
    # saw the disclosure at all. Telling them is a legal requirement, not a
    # courtesy: the UK ICO's guidance on monitoring workers requires that
    # workers be informed about monitoring, and New York Civil Rights Law
    # 52-c requires prior written notice of electronic monitoring. Printed
    # before the store is contacted and before the local config is written,
    # so it is shown even when the join then refuses or the store is down.
    print(DISCLOSURE_TEXT)
    try:
        disclosure_path = _write_disclosure_copy(config_path)
        print(f"a copy of the above is at {_display_path(disclosure_path)}")
    except OSError as e:
        print(f"warning: could not write the disclosure copy beside "
              f"{_display_path(config_path)}: {e}", file=sys.stderr)

    # When the store is reachable, catch a salt (or org) typo before it
    # ever creates a phantom machine: a wrong salt still hashes to SOME
    # machine_id, just not the one every other push from this same
    # physical machine already uses. An unreachable store is never treated
    # as a mismatch (see _check_org_profile_matches): that follows the
    # same "never blocks on availability" rule as every other fleet write.
    try:
        _check_org_profile_matches(store, org, salt)
    except FleetValidationError as e:
        print(str(e), file=sys.stderr)
        return 2

    local_config = {"org": org, "salt": salt, "hostname": hostname,
                    "store": store}
    if team:
        local_config["team"] = team
    if environment:
        local_config["environment"] = environment
    try:
        _write_local_config(config_path, local_config)
    except OSError as e:
        print(f"refused: could not write the local fleet config at "
              f"{_display_path(config_path)}: {e}", file=sys.stderr)
        return 2

    machine_id = compute_machine_id(hostname, salt)
    if config_fingerprint is None:
        try:
            config_fingerprint = exp.compute_fingerprint()
        except Exception:
            config_fingerprint = None

    record = build_registration_record(day, local_config,
                                       config_fingerprint=config_fingerprint,
                                       token_shield_version=token_shield_version)
    # Never blocks the join on an unreachable store: queues the
    # registration locally with one warning (push_record's own contract).
    # A symlink planted in the cloned store or the local queue dir is a
    # different failure class and is refused loudly instead (rc 2), never
    # silently downgraded to the queue fallback, which would just move the
    # same attack surface rather than close it.
    try:
        pushed = push_record(record, store, org, machine_id, day,
                             queue_dir=queue_dir)
    except FleetSymlinkError as e:
        print(str(e), file=sys.stderr)
        return 2

    print(f"joined fleet: org={org} machine_id={machine_id} "
          f"team={team or '(none)'} environment={environment or '(none)'}")
    if not pushed:
        print("this machine will appear on the dashboard once the queued "
              "record reaches the store.")
    return 0


def cmd_leave(config_path, queue_dir=None):
    """Remove the local fleet config and the local queue dir
    (LOCAL_QUEUE_DIR, or `--queue-dir` when given): every file this
    machine's fleet participation ever wrote. Before this fix, leave
    removed only the config file: cmd_build/cmd_push already refuse (NO
    DATA) once the config is gone, so pushes did stop, but any record a
    prior push had queued locally (because the store was unreachable at
    the time) survived on disk, which made "uninstalling leaves no trace"
    false. A harmless no-op when the machine was never joined (both paths
    absent already)."""
    config_path = config_path or DEFAULT_FLEET_CONFIG
    queue_dir = os.path.expanduser(queue_dir or LOCAL_QUEUE_DIR)
    disclosure_path = _disclosure_path(config_path)

    had_config = os.path.isfile(config_path)
    if had_config:
        os.remove(config_path)
    # The disclosure copy cmd_join leaves for the machine's owner is part
    # of the same trace, so it goes with the rest.
    had_disclosure = os.path.isfile(disclosure_path)
    if had_disclosure:
        os.remove(disclosure_path)
    removed_queue = os.path.isdir(queue_dir)
    if removed_queue:
        shutil.rmtree(queue_dir)

    if not had_config and not had_disclosure and not removed_queue:
        print(f"not joined: no local fleet config at "
              f"{_display_path(config_path)}")
        return 0

    removed = []
    if had_config:
        removed.append(_display_path(config_path))
    if had_disclosure:
        removed.append(_display_path(disclosure_path))
    if removed_queue:
        removed.append(_display_path(queue_dir))
    print(f"left the fleet: removed {' and '.join(removed)}")
    return 0


def cmd_build(day, config_path, telem_ledger, exp_ledger, config_fingerprint,
              token_shield_version):
    day = day or time.strftime("%Y-%m-%d")
    try:
        _validate_day(day)
    except FleetValidationError as e:
        print(str(e), file=sys.stderr)
        return 2
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
             token_shield_version, store_url, queue_dir, drain=False):
    """Build one day's record and push it. Returns 0 only when the record
    actually reached the store, EXIT_QUEUED when it is sitting in the local
    queue instead, and 2 for a refusal or NO DATA: a cron line that reads
    only the exit code can tell those apart, which is the whole point."""
    day = day or time.strftime("%Y-%m-%d")
    try:
        _validate_day(day)
    except FleetValidationError as e:
        print(str(e), file=sys.stderr)
        return 2
    local_config = _read_local_config(config_path or DEFAULT_FLEET_CONFIG)
    if local_config is None:
        print(f"NO DATA: no local fleet config at "
              f"{_display_path(config_path or DEFAULT_FLEET_CONFIG)} "
              f"(run `fleet join`, not yet built).", file=sys.stderr)
        return 2

    # `fleet join` has always saved the store URL into the local config and
    # nothing ever read it back, so --store was required on every single
    # invocation: too long for a cron line, which is how the daily push
    # stopped happening. The flag still wins when given.
    if not store_url:
        saved = local_config.get("store")
        if isinstance(saved, str) and saved:
            store_url = saved
    if not store_url:
        print(f"refused: no fleet store URL: none saved in "
              f"{_display_path(config_path or DEFAULT_FLEET_CONFIG)} and no "
              f"--store given. Run `fleet join <store-url> --org NAME` to "
              f"save one, or pass --store.", file=sys.stderr)
        return 2

    drain_left = 0
    if drain:
        try:
            _delivered, drain_left = drain_queue(store_url, queue_dir=queue_dir)
        except FleetSymlinkError as e:
            print(str(e), file=sys.stderr)
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
    try:
        _validate_org(org)
        _validate_machine_id(machine_id)
    except FleetValidationError as e:
        print(str(e), file=sys.stderr)
        return 2
    try:
        ok = push_record(record, store_url, org, machine_id, day, queue_dir=queue_dir)
    except FleetSymlinkError as e:
        print(str(e), file=sys.stderr)
        return 2

    # A queued record has NOT been delivered. Before this, cmd_push printed
    # nothing on this path and returned 0, so an unreachable store looked
    # exactly like a successful push to every cron line in the fleet while
    # the org view stayed empty. The queue stays the last resort it always
    # was; what changed is that it now reports itself, on stderr and in the
    # exit status, with the count waiting and the command that replays them.
    if not ok:
        waiting = len(queued_record_files(queue_dir))
        print(f"NOT DELIVERED: this record is queued on this machine, not in "
              f"the fleet store. {waiting} record(s) waiting. Replay them "
              f"with: python3 fleet.py push --drain", file=sys.stderr)
        return EXIT_QUEUED

    print(f"pushed: fleet/{org}/{machine_id}/{day}.json")
    if drain_left:
        print(f"NOT DELIVERED: {drain_left} record(s) are still queued on "
              f"this machine after the drain.", file=sys.stderr)
        return EXIT_QUEUED
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
    p_push.add_argument("--store", default=None,
                        help="git remote URL of the org's fleet store; "
                             "default: the one `fleet join` saved locally")
    p_push.add_argument("--drain", action="store_true",
                        help="first replay every record waiting in the local queue")
    p_push.add_argument("--queue-dir", default=None)

    p_init = sub.add_parser("init", help="admin, once: create the org profile in the fleet store")
    p_init.add_argument("store", nargs="?", default=None,
                        help="git URL of the org's fleet store")
    p_init.add_argument("--org", default=None, help="org name")
    p_init.add_argument("--salt", default=None,
                        help="org salt; every machine that joins must use this exact value")
    p_init.add_argument("--default-mode", default=None,
                        help="conservative, balanced, or aggressive")
    p_init.add_argument("--force", action="store_true",
                        help="overwrite an existing org-profile.json in the store")

    p_join = sub.add_parser("join", help="each machine, one line: register and push once immediately")
    p_join.add_argument("store", help="git URL of the org's fleet store")
    p_join.add_argument("--org", default=None, help="org name (from `fleet init`)")
    p_join.add_argument("--salt", default=None, help="org salt (from `fleet init`)")
    p_join.add_argument("--team", default=None, help="free team tag")
    p_join.add_argument("--environment", default=None, help="free environment tag")
    p_join.add_argument("--hostname", default=None, help="default: this machine's hostname")
    p_join.add_argument("--day", default=None, help="YYYY-MM-DD, default today")
    p_join.add_argument("--config", default=None, help="local fleet config path")
    p_join.add_argument("--queue-dir", default=None)
    p_join.add_argument("--config-fingerprint", default=None)
    p_join.add_argument("--token-shield-version", default=None)

    p_leave = sub.add_parser("leave", help="remove local fleet config and any queued records; stops all future pushes and leaves no trace")
    p_leave.add_argument("--config", default=None, help="local fleet config path")
    p_leave.add_argument("--queue-dir", default=None)

    a = ap.parse_args()
    if a.action == "build":
        return cmd_build(a.day, a.config, a.telemetry_ledger, a.experiment_ledger,
                         a.config_fingerprint, a.token_shield_version)
    if a.action == "push":
        return cmd_push(a.day, a.config, a.telemetry_ledger, a.experiment_ledger,
                        a.config_fingerprint, a.token_shield_version, a.store,
                        a.queue_dir, a.drain)
    if a.action == "init":
        return cmd_init(a.store, a.org, a.salt, a.default_mode, a.force)
    if a.action == "join":
        return cmd_join(a.store, a.org, a.salt, a.team, a.environment, a.hostname,
                        a.day, a.config, a.queue_dir, a.config_fingerprint,
                        a.token_shield_version)
    return cmd_leave(a.config, a.queue_dir)


if __name__ == "__main__":
    sys.exit(main())
