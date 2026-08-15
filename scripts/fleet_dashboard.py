#!/usr/bin/env python3
"""
fleet_dashboard.py: render an org-wide HTML dashboard from a fleet store
directory. Fleet F3, the read and render side of the fleet layer
(docs/superpowers/specs/2026-08-14-token-shield-fleet-design.md,
docs/superpowers/plans/2026-08-14-token-shield-fleet-plan.md). scripts/fleet.py
already owns the record format and the write side (build, push); this file
never writes into the store, never runs git, never sends anything anywhere.
It only reads what is already on disk.

WHAT IT READS
--------------
The layout scripts/fleet.py's push_record() writes into the org's store:
    fleet/<org>/<machine-id>/<date>.json
one JSON record per machine per calendar day, shaped by data/fleet.schema.json.
This file does not clone or pull that store; a caller (a human, `fleet pull`
in a later phase, an admin's own script) is responsible for getting a local
checkout onto disk first. --store-dir points at the root of that checkout.

LABEL RULES ARE IMPORTED, NEVER COPIED
-----------------------------------------
scripts/token_shield.py already owns how a missing number renders (esc,
human, pct) and how a confidence label renders as a badge (_cpill). This file
imports all four rather than re-implementing them, the same reuse discipline
scripts/fleet.py itself applies to signals._project. A second copy of the
label rules is the exact failure this design guards against.

NO DATA BEATS A GUESS, PER RECORD
-------------------------------------
A record that is not valid JSON, whose "schema" is newer than this repo's
reader understands (fleet.load_record's own refusal, reused here rather than
re-implemented), that is missing a required field, or that carries a
negative token count, renders as its own NO DATA row naming the reason. A
machine directory that holds zero record files renders its own NO DATA row
too. None of this ever removes another machine's row, and none of it ever
raises out of collect_org(): one hostile or unreadable file costs the org
that one row, never the whole render.

NO CROSS-LABEL TOTALS
-------------------------
Each fleet record's "experiments" array carries labeled, confidence-tagged
records (VERIFIED or NOT_PROVEN under the current schema; the renderer does
not assume that set is closed and passes any confidence string straight to
_cpill, which falls back to its bare muted badge for a label it does not
recognize). latest_experiment_by_label() picks one row per label, the newest
by timestamp, across every machine in the org: never a sum across labels,
never a sum across repeated runs of the same label, and a regression's
metric_delta renders exactly as measured, negative sign included, never
clipped to zero.

NATIVE caching is never claimed or priced here: this file does not import
pricing.py and never computes a dollar figure. There is nothing to guard
beyond that, since NATIVE savings are Anthropic's own and this page does not
touch them.

A DATE WINDOW, AND A ROW CAP THAT SAYS WHAT IT DROPPED
---------------------------------------------------------
The loader reads a WINDOW (--days, default DEFAULT_DAYS), never the whole
store history: a thousand machines over a year is hundreds of thousands of
file opens and table rows in one self-contained page. The window is applied
to the FILENAME date, before the file is opened, which costs one string
comparison instead of one file read; the filename already carries the date
and collect_org already prefers it over the record body. Every table is
capped at MAX_TABLE_ROWS rendered rows, and a table that dropped rows prints
the count: a silent truncation reads to an administrator exactly like "this
is everything".

MINIMUM GROUP SIZE: THIS PAGE IS NOT A PER-PERSON PRODUCTIVITY TABLE
------------------------------------------------------------------------
In almost every organisation one machine is one person, so a table of
per-machine token counts is a table of per-person output, which is what
employee-monitoring law is about (the UK ICO requires the least intrusive
means that achieves the purpose; German works councils hold co-determination
rights over technical systems capable of monitoring employee performance).
The remedy here is the established one, a minimum group size:

  no aggregate cell backed by fewer than MIN_GROUP_MACHINES distinct
  machines is published, it is suppressed and named as suppressed with the
  reason; the per-machine table carries operational health only (did this
  machine report, when, is it stale, which team it joined as) and never a
  per-machine token or experiment number.

An administrator may RAISE the threshold with --min-group and can never
lower it below MIN_GROUP_MACHINES: render() clamps, so no caller of this
module can lower it either. A suppressed cell is never silently dropped,
because "no row" and "a row we are not allowed to publish" are different
facts and only one of them is true.

WHY THERE IS NO PER-MODEL TABLE (defect D9)
-----------------------------------------------
The telemetry ledger these records are built from carries a token COUNT and
never a model IDENTITY (see fleet._day_counters, which buckets every counter
under the literal string "unknown" for exactly that reason). A per-model
table could therefore only ever print one row reading "unknown", which is a
promise the data cannot keep, so the day table sums across buckets and the
page says NO DATA for the model breakdown and names the reason. The real fix
is capturing model identity at the telemetry boundary, which lives outside
this file.


# --- FIX ROUND (adversarial review, F3) -------------------------------------
#
# 1. _load_one used to catch a NAMED subset of exceptions (OSError,
#    json.JSONDecodeError, FleetSchemaError), so anything outside that list
#    (a non-UTF-8 file -> UnicodeDecodeError, 200,000-deep nesting ->
#    RecursionError) propagated out of collect_org and killed the whole org
#    page instead of costing that one machine its own NO DATA row. It now
#    catches Exception: a shared store is untrusted input, so ANY exception
#    while loading one record is that record's row, never the org's outage.
#    A file over MAX_RECORD_BYTES is refused by name before it is ever read
#    into memory. A bare NaN/Infinity JSON literal is accepted silently by
#    json.load (Python's json module allows it as a non-standard extension)
#    and used to pass every comparison until it hit int() in ts.human() and
#    raised ValueError deep in the formatter; _validate_record_shape now
#    refuses it explicitly at validation time, the same place the existing
#    negative-counter check already lived, rather than leaving it to blow up
#    downstream.
# 2. A symlink anywhere under fleet/<org>/ (a whole machine directory, or one
#    record file) used to be followed: os.path.isdir/os.listdir both follow
#    symlinks, so a symlink planted in a shared store could make this reader
#    render content from outside the store. Every machine directory and
#    every record path is now checked with fleet._refuse_symlinks_under
#    (fleet.py's own hardening for the write side, reused rather than
#    reimplemented) before it is ever opened; a hit is that entry's own NO
#    DATA row naming the reason.
# 3. --org reached both a filesystem path (store_dir/fleet/<org>/) and the
#    page <title> unvalidated: "../../elsewhere" escaped the org tree, and
#    the title (unlike the body, which already escapes via ts.esc) was
#    interpolated raw, so an org name shaped like
#    "acme</title><script>alert(1)</script>" put a live script tag in the
#    page. main() now runs --org through fleet._validate_org before it
#    reaches collect_org, and token_shield.render_standalone now escapes its
#    own title (see that file).
# 4. A machine directory replaced by a plain file used to fail os.path.isdir
#    silently and be skipped with no row at all. org-profile.json is skipped
#    by name (it is not a machine entry); any other non-directory now gets
#    its own NO DATA row.
# 5. latest_experiment_by_label() kept its own copy of
#    token_shield.verified_by_label's "newest wins" tiebreak and had
#    inverted it (first-seen won a tie instead of last-seen), so two
#    machines pushing the same label at the same timestamp could disagree
#    with the single-machine page about which one won. It now calls
#    verified_by_label directly for the pick; see that function's own
#    docstring below for how the field-name and confidence mismatch between
#    the two record shapes is bridged without a second copy of the tiebreak.
# 6. A record's own "date" field was trusted over the filename it was found
#    at, so the same record could render under two different dates in two
#    tables on the same page, and a member could park tokens on a future
#    day just by lying in the record body. The two must now agree, or the
#    record is its own NO DATA row naming the disagreement.
# 7. The rendered page printed store_dir raw, including the admin's account
#    name (an absolute path like /Users/khalil/checkout/...) into a shared
#    org artifact. It now goes through fleet._display_path, the same helper
#    fleet.py itself uses to keep an account name out of its own warnings.
# 8. A timestamp cell used to truncate AFTER escaping
#    (ts.esc(text)[:19]), which can cut an HTML entity like "&amp;" in half
#    and leave a broken entity in the page. Truncation now happens on the
#    raw string, before esc() ever sees it.
#
# See docs/FLEET.md for the admin-facing version of all eight.


USAGE
  python3 fleet_dashboard.py --store-dir PATH --org ORG --out OUT.html
  python3 fleet_dashboard.py --store-dir PATH --org ORG --out OUT.html --stamp "2026-08-15 09:00"
  python3 fleet_dashboard.py --store-dir PATH --org ORG --out OUT.html --days 7 --min-group 10
"""

import argparse
import datetime
import json
import math
import os
import sys
import time

import fleet as fl
import token_shield as ts

HERE = os.path.dirname(os.path.abspath(__file__))

REQUIRED_RECORD_FIELDS = ("schema", "date")

# How many calendar days of records the loader reads, counting today, when
# --days says nothing. A month of history answers every question this page
# is for; the whole store is available with --days 0 and is opt-in because
# it is the expensive read, not the default one.
DEFAULT_DAYS = 30

# Rendered rows per table. ponytail: one flat cap for every table rather
# than a per-table knob; the page is a single self-contained HTML file, so
# the number that matters is how many rows a browser is asked to lay out.
MAX_TABLE_ROWS = 200

# Minimum distinct machines behind any published aggregate. 5 is the common
# disclosure-control convention. An admin can raise it (--min-group), never
# lower it: render() clamps every caller to this floor.
MIN_GROUP_MACHINES = 5

# A machine whose newest record on disk is older than this many days is
# reported as stale rather than as reporting.
STALE_AFTER_DAYS = 7

# A whitelisted per-day record is a few KB in normal use (a handful of
# counter buckets plus a handful of experiment entries). This cap refuses an
# attacker-sized file by name, before it is ever read into memory, rather
# than after. ponytail: a flat constant, not a per-org or per-schema knob;
# raise it if a legitimate record ever needs to be bigger than this.
MAX_RECORD_BYTES = 1_000_000


def _validate_record_shape(record):
    """Return a reason string if `record` (already parsed and schema-checked
    by fleet.load_record) is missing a field data/fleet.schema.json requires,
    carries a negative token count, or carries a non-finite one (NaN or
    +/-Infinity: json.load accepts these silently as a non-standard
    extension, and they pass every "< 0" comparison here without tripping
    it, then explode with ValueError: cannot convert float NaN to integer
    the moment ts.human() tries int() on one downstream -- caught here,
    before that, is the only place that never lets it reach the formatter).
    Returns None when the shape is usable. Never raises; this is the
    hostile-content fence collect_org() puts around every file, checked
    after fleet.load_record's own JSON and schema-version checks so the two
    refusals never overlap."""
    for field in REQUIRED_RECORD_FIELDS:
        if field not in record:
            return f"missing required field: {field}"
    counters = record.get("counters")
    if counters is not None:
        if not isinstance(counters, dict):
            return "counters is not an object"
        for bucket_name, bucket in counters.items():
            if not isinstance(bucket, dict):
                return f"counters.{bucket_name} is not an object"
            for key, value in bucket.items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    if not math.isfinite(value):
                        return f"non-finite token count in counters.{bucket_name}.{key}"
                    if value < 0:
                        return f"negative token count in counters.{bucket_name}.{key}"
    return None


def _valid_day(text):
    """True when `text` is exactly YYYY-MM-DD AND a real calendar date.

    fleet._validate_day's own pattern is a shape check only, so "9999-99-99"
    passes it: a record filed under that name used to render as a day of the
    year in the counters table. Both checks are needed and neither is
    reimplemented here: the shape comes from fleet.py, the calendar comes
    from datetime. FleetValidationError is a ValueError subclass, so one
    except clause covers both."""
    try:
        fl._validate_day(text)
        datetime.date.fromisoformat(text)
    except ValueError:
        return False
    return True


def _window(days, today):
    """(today, cutoff): the day the window ends on and the oldest filename
    date it keeps, or None for no cutoff at all (days <= 0 reads all
    history). `days` counts today, so --days 1 is today only. An unusable
    `today` falls back to the real calendar rather than raising out of
    collect_org, which promises never to raise."""
    if not _valid_day(today):
        today = datetime.date.today().isoformat()
    if days is None or days <= 0:
        return today, None
    cutoff = datetime.date.fromisoformat(today) - datetime.timedelta(days=days - 1)
    return today, cutoff.isoformat()


def _scrub_paths(message):
    """Shorten any home-directory prefix inside a message to "~".

    Error rows are built from exception text, and the exceptions raised while
    reading a store carry absolute paths (fleet's symlink refusal names the
    offending path in full). This page is a SHARED org artifact, so an
    unscrubbed message publishes the admin's account name to everyone who
    opens it. fl._display_path only handles a string that IS a path; these are
    sentences with a path inside them, so the home prefix is replaced wherever
    it appears rather than only at position zero. Applied at the single point
    where an error reaches HTML, not at each site that builds one, so a future
    error row cannot forget it."""
    if not message:
        return message
    home = os.path.expanduser("~")
    return message.replace(home, "~") if home and home != "/" else message


def _load_one(path):
    """Load and validate one fleet record file. Returns (record, error):
    exactly one of the two is None. Never raises: a missing or unreadable
    file, invalid JSON, a schema newer than fleet.load_record understands, a
    missing required field, a negative or non-finite counter, or ANY other
    exception fleet.load_record raises (a non-UTF-8 file -> UnicodeDecodeError,
    200,000 levels of nested array -> RecursionError, or anything this
    reader has not seen before) all come back as a named reason string
    instead of propagating, so one hostile file can never take the whole
    dashboard render down. A shared store is untrusted input: the broad
    `except Exception` at the end is deliberate, not a symptom-hiding catch,
    because ANY failure to load one record is exactly and only that
    record's own NO DATA row, never the org's outage."""
    try:
        size = os.path.getsize(path)
    except OSError as e:
        return None, f"could not read file: {e}"
    if size > MAX_RECORD_BYTES:
        return None, f"refused: record file is {size} bytes, over the {MAX_RECORD_BYTES} byte cap"
    try:
        record = fl.load_record(path)
    except OSError as e:
        return None, f"could not read file: {e}"
    except json.JSONDecodeError as e:
        return None, f"invalid JSON: {e}"
    except fl.FleetSchemaError as e:
        return None, str(e)
    except Exception as e:
        return None, f"unreadable record: {type(e).__name__}: {e}"
    try:
        shape_error = _validate_record_shape(record)
    except Exception as e:
        # Inside the try, not after it. The broad handler above exists because
        # a shared store is attacker controlled, but validation was called
        # OUTSIDE its reach, so anything the validator itself raised still
        # killed the whole org page instead of this one machine's row.
        # Demonstrated with a counter of 10**400: math.isfinite raises
        # OverflowError ("int too large to convert to float") on an int too
        # big for a float, at 401 bytes, far under the size cap.
        return None, f"unreadable record: {type(e).__name__}: {e}"
    if shape_error:
        return None, shape_error
    return record, None


def collect_org(store_dir, org, days=DEFAULT_DAYS, today=None):
    """Walk fleet/<org>/<machine-id>/<date>.json under `store_dir`. Returns
    (rows, empty_machines, meta), never raising. `rows` is one entry per
    record file INSIDE THE WINDOW: {"machine_id", "date", "record" (or
    None), "error" (or None)}. `empty_machines` lists machine ids whose
    directory exists but held zero ".json" files. `meta` carries what the
    render needs to describe its own coverage honestly:
    {"window_days", "today", "cutoff", "outside_window", "last_seen"}.
    A missing store, org, or machine directory yields empty results rather
    than an error: the normal state before a machine has ever pushed.

    THE WINDOW IS APPLIED TO THE FILENAME, BEFORE THE FILE IS OPENED. This
    loader used to read every record in the store on every render: a
    thousand machines over a year is hundreds of thousands of file opens
    held in one list and rendered as one table. The filename already carries
    the date and this function already trusts it over the record body, so a
    record dated before the cutoff costs one string comparison and is never
    read. Every skipped file is counted into meta["outside_window"] and the
    page prints that count: a window nobody can see is indistinguishable
    from a store that holds nothing older.

    meta["last_seen"] is the newest filename date seen per machine
    REGARDLESS of the window, so a machine that stopped reporting months ago
    still gets its operational row (last report, stale) instead of silently
    vanishing from the page along with its records.

    A filename that is not a real calendar date ("9999-99-99.json") is that
    file's own NO DATA row: it cannot be windowed, it cannot be a day, and
    rendering it as one was a number about nothing.

    Every machine directory and every record path is checked with
    fleet._refuse_symlinks_under (reused from fleet.py's own write-side
    hardening, never reimplemented here) before it is trusted: os.path.isdir
    and os.listdir both follow a symlink, so without this check a symlink
    planted anywhere in a shared store could make this reader walk or render
    content from outside the store. A hit is that one entry's own NO DATA
    row, never a crash.

    org-profile.json (fleet.py's ORG_PROFILE_FILENAME) is skipped by name:
    it is not a machine entry. Any OTHER non-directory found where a machine
    directory was expected -- a machine id replaced by a plain file -- gets
    its own NO DATA row instead of silently vanishing (os.path.isdir alone
    returning False used to just `continue` with no row at all).

    A record whose own "date" field disagrees with the filename it was
    found at is refused as that file's own NO DATA row: trusting the body
    over the filename let the same record render under two different dates
    in two tables on the same page, and let a member park tokens on a
    future day just by writing a different date into the record body."""
    org_dir = os.path.join(store_dir, "fleet", org)
    rows = []
    empty_machines = []
    today, cutoff = _window(days, today)
    meta = {"window_days": days, "today": today, "cutoff": cutoff,
            "outside_window": 0, "last_seen": {}}
    # Refuse a symlink AT or ABOVE the org directory, not only below it.
    # _refuse_symlinks_under walks components strictly below its root, so
    # passing org_dir as the root left fleet/<org> and fleet/ themselves
    # unchecked: making fleet/<org> a symlink pointed the whole reader at an
    # arbitrary directory outside the store and rendered it with no refusal.
    # os.path.isdir follows symlinks, so this check has to come first.
    try:
        fl._refuse_symlinks_under(store_dir, org_dir)
    except fl.FleetSymlinkError as e:
        rows.append({"machine_id": org, "date": None, "record": None,
                     "error": f"refusing to read: {e}"})
        return rows, empty_machines, meta
    if not os.path.isdir(org_dir):
        return rows, empty_machines, meta
    try:
        machine_ids = sorted(os.listdir(org_dir))
    except OSError as e:
        # The per-machine listdir was already guarded and this one was not,
        # so an unreadable org directory raised PermissionError straight out
        # of a function whose docstring promises it never raises, and out of
        # render() with it.
        rows.append({"machine_id": org, "date": None, "record": None,
                     "error": f"could not list org directory: {e}"})
        return rows, empty_machines, meta
    for machine_id in machine_ids:
        if machine_id == fl.ORG_PROFILE_FILENAME:
            continue
        machine_dir = os.path.join(org_dir, machine_id)
        try:
            fl._refuse_symlinks_under(org_dir, machine_dir)
        except fl.FleetSymlinkError as e:
            rows.append({"machine_id": machine_id, "date": None, "record": None,
                        "error": f"refusing to read: {e}"})
            continue
        if not os.path.isdir(machine_dir):
            rows.append({"machine_id": machine_id, "date": None, "record": None,
                        "error": "not a directory (machine entry replaced by a file)"})
            continue
        try:
            entries = sorted(os.listdir(machine_dir))
        except OSError as e:
            rows.append({"machine_id": machine_id, "date": None, "record": None,
                        "error": f"could not list machine directory: {e}"})
            continue
        json_files = [e for e in entries if e.endswith(".json")]
        if not json_files:
            empty_machines.append(machine_id)
            continue
        for fname in json_files:
            date = fname[:-len(".json")]
            if not _valid_day(date):
                rows.append({"machine_id": machine_id, "date": None, "record": None,
                            "error": f"filename {fname!r} is not a real YYYY-MM-DD "
                                     f"calendar date"})
                continue
            seen = meta["last_seen"].get(machine_id)
            if seen is None or date > seen:
                meta["last_seen"][machine_id] = date
            if cutoff is not None and date < cutoff:
                # Windowed out on the FILENAME, before any open(): this is
                # the whole point of the window. Counted, never silent.
                meta["outside_window"] += 1
                continue
            path = os.path.join(machine_dir, fname)
            try:
                fl._refuse_symlinks_under(machine_dir, path)
            except fl.FleetSymlinkError as e:
                rows.append({"machine_id": machine_id, "date": date, "record": None,
                            "error": f"refusing to read: {e}"})
                continue
            record, error = _load_one(path)
            if error is None and record.get("date") != date:
                error = (f"filename date {date!r} disagrees with the record's own "
                         f"date {record.get('date')!r}")
                record = None
            rows.append({"machine_id": machine_id, "date": date,
                        "record": record, "error": error})
    return rows, empty_machines, meta


def _record_total(record):
    """Sum every numeric counter field across every model bucket in one
    record, or None when the record carries no usable counters (never a
    fabricated zero)."""
    counters = record.get("counters")
    if not isinstance(counters, dict):
        return None
    total = 0
    seen = False
    for fields in counters.values():
        if not isinstance(fields, dict):
            continue
        for value in fields.values():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                total += value
                seen = True
    return total if seen else None


def aggregate_counters_by_day(healthy_rows):
    """{date: {"totals": {field: total}, "machines": n}}, summed only over
    rows whose record loaded and validated cleanly. A record with an empty
    or absent counters object contributes nothing at all, never a fabricated
    zero and never an empty day bucket.

    "machines" is how many DISTINCT machines stand behind that day's cell,
    which is what the minimum-group-size rule is checked against before the
    cell is published (see the module docstring). The model dimension is
    gone on purpose: the ledger records a count, not an identity (D9), so
    the fields are summed across buckets."""
    by_day = {}
    for r in healthy_rows:
        rec = r["record"]
        date = rec.get("date")
        counters = rec.get("counters")
        if not isinstance(date, str) or not isinstance(counters, dict):
            continue
        one = {}
        for fields in counters.values():
            if not isinstance(fields, dict):
                continue
            for key, value in fields.items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    one[key] = one.get(key, 0) + value
        if not one:
            continue
        day = by_day.setdefault(date, {"totals": {}, "machines": set()})
        for key, value in one.items():
            day["totals"][key] = day["totals"].get(key, 0) + value
        day["machines"].add(r["machine_id"])
    return {date: {"totals": d["totals"], "machines": len(d["machines"])}
            for date, d in by_day.items()}


def aggregate_totals_by_tag(healthy_rows, tag_key):
    """{tag_value: {"total": tokens, "machines": n}}, summed only over
    healthy rows. A record with no value for `tag_key` (team or
    environment; both are optional per data/fleet.schema.json, set by
    `fleet join`) is bucketed under "(untagged)" rather than dropped.

    "machines" counts DISTINCT machines behind the tag, not records, so a
    single machine pushing thirty days of records is still one machine and
    cannot pass the minimum group size on its own. "machine_ids" carries
    WHICH machines they are, because the count alone cannot answer the
    question render_tag_totals has to ask: two groups of five can share four
    machines, and only the union decides whether the residual left over
    after publishing is anonymous."""
    totals = {}
    for r in healthy_rows:
        rec = r["record"]
        total = _record_total(rec)
        if total is None:
            continue
        tag = rec.get(tag_key)
        tag = tag if isinstance(tag, str) and tag else "(untagged)"
        bucket = totals.setdefault(tag, {"total": 0, "machines": set()})
        bucket["total"] += total
        bucket["machines"].add(r["machine_id"])
    return {tag: {"total": b["total"], "machines": len(b["machines"]),
                  "machine_ids": b["machines"]}
            for tag, b in totals.items()}


def latest_experiment_by_label(healthy_rows):
    """One experiment item per LABEL, the newest by timestamp, across every
    machine AND every confidence in the org.

    D20: this used to key latest-wins on (label, confidence) while the page
    copy under the table read "One row per label, the newest record only",
    so a stale VERIFIED sat beside a newer NOT_PROVEN for the same label
    under a sentence promising it could not. The pick is now made once,
    across all confidences, and the confidence rendered is whatever the
    winning record actually carried. Fixing the copy instead would have been
    the dishonest half of that choice.

    The pick itself is token_shield.latest_row_per_label, called directly,
    never reimplemented: that function exists precisely because this rule
    had three drifting copies, and one of them (this file's own, before this
    fix) had inverted its tiebreak. Its contract is exactly what is wanted
    here, newest timestamp across EVERY confidence, ties keeping the last
    row in iteration order, and confidence filtering left to the caller.
    Because no filtering happens after it, the whole reshape-and-match-back
    bridge this function used to need for verified_by_label is gone with
    it."""
    items = []
    for r in healthy_rows:
        rec = r["record"]
        experiments = rec.get("experiments")
        if not isinstance(experiments, list):
            continue
        for item in experiments:
            if not isinstance(item, dict):
                continue
            entry = dict(item)
            # label and confidence are attacker supplied and are used as a
            # dict key, a set member and a sort key below. A list or dict
            # there raised "unhashable type", and a number beside a string
            # raised "'<' not supported between 'str' and 'int'", either of
            # which killed the whole org page rather than this one record.
            # Coerced here, where the entry is built, so no downstream user
            # of these two fields has to remember. The empty string is
            # folded into "(unlabeled)" here too, because that is what
            # latest_row_per_label keys it as.
            label = entry.get("label")
            entry["label"] = label if isinstance(label, str) and label else "(unlabeled)"
            conf = entry.get("confidence")
            entry["confidence"] = conf if isinstance(conf, str) else "NO DATA"
            entry["machine_id"] = r["machine_id"]
            items.append(entry)

    out = []
    for label, winner in ts.latest_row_per_label(items).items():
        out.append({
            "label": label,
            "confidence": winner.get("confidence"),
            "timestamp": winner.get("timestamp"),
            "target_metric": winner.get("target_metric"),
            "metric_delta": winner.get("metric_delta"),
            "direction": winner.get("direction"),
            "machine_id": winner.get("machine_id"),
        })
    return sorted(out, key=lambda x: x["label"])


# --- rendering ---------------------------------------------------------------

def _cap(rowlist):
    """(kept, dropped): at most MAX_TABLE_ROWS rows, and how many were left
    out. Every table on this page goes through it. A truncation that says
    nothing reads to an administrator exactly like "this is everything", so
    the count comes back with the rows and every caller prints it."""
    if len(rowlist) <= MAX_TABLE_ROWS:
        return rowlist, 0
    return rowlist[:MAX_TABLE_ROWS], len(rowlist) - MAX_TABLE_ROWS


def _capped_note(dropped, unit):
    if not dropped:
        return ""
    return (f'<p class="nodata">{dropped} more {unit} not shown: this table is capped at '
            f'{MAX_TABLE_ROWS} rows. Narrow the window with --days to see a different slice '
            f'of the store.</p>')


def _suppressed_note(suppressed, min_group):
    if not suppressed:
        return ""
    return (f'<p class="nodata">{suppressed} row(s) suppressed: a cell backed by fewer than '
            f'{min_group} machines can be one person\'s own work, and this is a shared org '
            f'page, so it is not published. A larger group is suppressed alongside it whenever '
            f'publishing that group would leave a residual smaller than {min_group} machines '
            f'for a reader to subtract, so what is withheld is anonymous too. The floor is '
            f'{MIN_GROUP_MACHINES} machines and an admin can raise it, never lower it.</p>')


def _suppressed_cell(min_group, span=1):
    span_attr = f' colspan="{span}"' if span > 1 else ""
    return (f'<td class="nodata"{span_attr}>suppressed: backed by fewer than {min_group} '
            f'machines</td>')


def _stale(last_seen, today):
    """True when `last_seen` (a filename date) is more than STALE_AFTER_DAYS
    older than `today`. An unusable date on either side is not stale: NO
    DATA is said elsewhere, and a guess here would be worse."""
    if not _valid_day(last_seen) or not _valid_day(today):
        return False
    gap = datetime.date.fromisoformat(today) - datetime.date.fromisoformat(last_seen)
    return gap.days > STALE_AFTER_DAYS


def _machine_health(entry, last_seen, today):
    """(status, detail) for one machine's operational row. Neither carries a
    token count: see render_machines_table's own docstring for the rule."""
    detail = []
    if entry["records"]:
        detail.append(f'team {ts.esc(entry["team"] or "(untagged)")}, '
                      f'env {ts.esc(entry["env"] or "(untagged)")}')
    elif last_seen is None:
        detail.append("no records found for this machine")
    else:
        detail.append("no records inside this window")
    if entry["errors"]:
        detail.append(f'{entry["errors"]} record(s) unreadable: '
                      f'{ts.esc(_scrub_paths(entry["reason"]))}')
    detail = "; ".join(detail)
    if last_seen is None:
        return '<span class="nodata">NO DATA</span>', detail
    if _stale(last_seen, today):
        return f"stale (no report for over {STALE_AFTER_DAYS} days)", detail
    return "reporting", detail


def render_machines_table(rows, empty_machines, meta):
    """One row per MACHINE, carrying operational health only: did it report,
    when was its newest record, is it stale, which team and environment it
    joined as, and how many of its records could not be read.

    THE RULE THIS TABLE IMPLEMENTS: no per-machine token count and no
    per-machine experiment result is published anywhere on this page.
    In almost every organisation one machine is one person, so the Tokens
    column this table used to carry was a per-person output column on a
    shared org artifact. What is left is the operational half an
    administrator actually needs (is this machine reporting at all), which
    is not a measure of anybody's output; every published NUMBER on the page
    is an aggregate standing on at least min_group distinct machines."""
    summaries = {}

    def _entry(machine_id):
        return summaries.setdefault(machine_id, {"records": 0, "errors": 0, "reason": None,
                                                 "team": None, "env": None})

    for r in rows:
        entry = _entry(r["machine_id"])
        if r["error"] is not None:
            entry["errors"] += 1
            if entry["reason"] is None:
                entry["reason"] = r["error"]
            continue
        entry["records"] += 1
        rec = r["record"]
        team = rec.get("team")
        env = rec.get("environment")
        # isinstance, not `or`: a dict in "team" reached ts.esc(), which
        # calls str(), and printed a Python repr into the org's page.
        if isinstance(team, str) and team:
            entry["team"] = team
        if isinstance(env, str) and env:
            entry["env"] = env
    for machine_id in empty_machines:
        _entry(machine_id)
    for machine_id in meta.get("last_seen", {}):
        _entry(machine_id)

    parts = ['<h2>Machines reporting</h2>']
    if not summaries:
        parts.append('<p class="nodata">NO DATA: no machines found for this org in the store.'
                     '</p>')
        return "".join(parts)
    last_seen = meta.get("last_seen", {})
    today = meta.get("today")
    shown, dropped = _cap(sorted(summaries))
    rowlist = []
    for machine_id in shown:
        seen = last_seen.get(machine_id)
        status, detail = _machine_health(summaries[machine_id], seen, today)
        rowlist.append(f'<tr><td>{ts.esc(machine_id)}</td><td>{ts.esc(seen or "n/a")}</td>'
                       f'<td>{status}</td><td>{detail}</td></tr>')
    parts.append('<div class="scroll"><table class="se"><thead><tr>'
                 '<th>Machine</th><th>Last report</th><th>Status</th><th>Detail</th>'
                 '</tr></thead><tbody>' + "".join(rowlist) + '</tbody></table></div>')
    parts.append(_capped_note(dropped, "machines"))
    parts.append('<p class="n">Operational health only. No per-machine token count and no '
                 'per-machine experiment result is published here: one machine is one person '
                 'in most organisations, so such a column would be a per-person productivity '
                 'table on a page the whole org can open.</p>')
    return "".join(parts)


def render_counters_by_day(by_day, min_group):
    parts = ['<h2>Token counters by day</h2>']
    # D9. The model breakdown is absent and says why, rather than rendering
    # a table whose only row could ever read "unknown".
    parts.append('<p class="nodata">NO DATA: per-model breakdown. The telemetry ledger these '
                 'records are built from carries a token COUNT and never a model identity, so '
                 'every counter arrives in one unnamed bucket and a per-model table could only '
                 'ever print one row reading "unknown". The day totals below are summed across '
                 'buckets instead. Capturing model identity at the telemetry boundary is the '
                 'real fix and lives outside this page.</p>')
    if not by_day:
        parts.append('<p class="nodata">NO DATA: no healthy records carried token counters.</p>')
        return "".join(parts)
    rowlist = []
    suppressed = 0
    for date in sorted(by_day):
        cell = by_day[date]
        if cell["machines"] < min_group:
            suppressed += 1
            rowlist.append(f'<tr><td>{ts.esc(date)}</td>{_suppressed_cell(min_group, span=4)}'
                           '</tr>')
            continue
        f = cell["totals"]
        rowlist.append(
            f'<tr><td>{ts.esc(date)}</td>'
            f'<td>{ts.human(f.get("input_tokens"))}</td>'
            f'<td>{ts.human(f.get("output_tokens"))}</td>'
            f'<td>{ts.human(f.get("cache_read_input_tokens"))}</td>'
            f'<td>{ts.human(f.get("cache_creation_input_tokens"))}</td></tr>')
    shown, dropped = _cap(rowlist)
    parts.append('<div class="scroll"><table class="se"><thead><tr>'
                 '<th>Date</th><th>Input</th><th>Output</th>'
                 '<th>Cache read</th><th>Cache write</th></tr></thead><tbody>'
                 + "".join(shown) + '</tbody></table></div>')
    parts.append(_capped_note(dropped, "days"))
    parts.append(_suppressed_note(suppressed, min_group))
    return "".join(parts)


def render_tag_totals(title, totals, min_group):
    """SECONDARY SUPPRESSION, and why a per-cell check is not enough.

    Checking each cell against the minimum group size only decides what to
    PRINT. It says nothing about what the printed cells let a reader DERIVE.
    Reproduced on a store of five machines tagged "eng" and one tagged
    "ops": the team table published eng at 24.2M and the environment table
    published the whole org at 27.3M, so the difference returned 3.1M
    against a true 3,030,000 and recovered one person's total token volume
    to within 2.3 percent, out of two cells this page had just declared safe
    to publish. The day table hands over the same complement exactly.

    The rule, which is the standard disclosure-control one: whatever is
    withheld must ITSELF stand on at least min_group machines. So when any
    group is too small, the smallest published groups are withheld with it
    (cheapest to lose first) until the union of withheld machines reaches
    the floor. On a five-plus-one split that withholds both groups, because
    the complement of the five is the one. A table where nothing was small
    is untouched: two teams of five each publish, since each is the other's
    complement and each stands on five machines."""
    parts = [f'<h2>{ts.esc(title)}</h2>']
    if not totals:
        parts.append('<p class="nodata">NO DATA: no healthy records carried this tag.</p>')
        return "".join(parts)
    published = sorted((kv for kv in totals.items() if kv[1]["machines"] >= min_group),
                       key=lambda kv: -kv[1]["total"])
    # Suppressed tags are ordered by NAME, never by their own hidden total:
    # ranking them would republish the ordering the suppression exists to
    # withhold.
    withheld = sorted((kv for kv in totals.items() if kv[1]["machines"] < min_group),
                      key=lambda kv: kv[0])
    if withheld:
        residual = set()
        for _tag, b in withheld:
            residual |= b["machine_ids"]
        # Smallest total first: the group whose loss costs the reader least.
        while len(residual) < min_group and published:
            tag, b = published.pop()
            withheld.append((tag, b))
            residual |= b["machine_ids"]
        withheld.sort(key=lambda kv: kv[0])
    rowlist = [f'<tr><td>{ts.esc(tag)}</td><td>{ts.human(b["total"])}</td></tr>'
               for tag, b in published]
    rowlist += [f'<tr><td>{ts.esc(tag)}</td>{_suppressed_cell(min_group)}</tr>'
                for tag, _b in withheld]
    shown, dropped = _cap(rowlist)
    parts.append('<div class="scroll"><table class="se"><thead><tr>'
                 '<th>Tag</th><th>Tokens</th></tr></thead><tbody>'
                 + "".join(shown) + '</tbody></table></div>')
    parts.append(_capped_note(dropped, "tags"))
    parts.append(_suppressed_note(len(withheld), min_group))
    return "".join(parts)


def _delta_text(delta):
    """A metric delta exactly as measured, or a named non-number. NaN used
    to render as "+nan", which reads like a measured saving with a plus sign
    in front of it. math.isfinite raises OverflowError on an int too big for
    a float; such an int is still finite and still formats, so that case
    falls through to the formatter rather than being called NO DATA."""
    if isinstance(delta, bool) or not isinstance(delta, (int, float)):
        return "n/a"
    try:
        if not math.isfinite(delta):
            return "NO DATA"
    except OverflowError:
        pass
    return f"{delta:+,}"


def render_experiments(items):
    parts = ['<h2>Experiments, latest per label</h2>']
    if not items:
        parts.append('<p class="nodata">NO DATA: no experiment records exported by any machine.'
                     '</p>')
        return "".join(parts)
    rowlist = []
    for item in items:
        conf = item.get("confidence") if isinstance(item.get("confidence"), str) else "NO DATA"
        rowlist.append(
            f'<tr><td>{ts.esc(item["label"])}</td><td>{ts._cpill(conf)}</td>'
            f'<td>{ts.esc(item.get("target_metric") or "n/a")}</td>'
            f'<td>{_delta_text(item.get("metric_delta"))}</td>'
            f'<td>{ts.esc(item.get("direction") or "n/a")}</td>'
            f'<td>{ts.esc(str(item.get("timestamp") or "n/a")[:19])}</td></tr>')
    shown, dropped = _cap(rowlist)
    parts.append('<div class="scroll"><table class="se"><thead><tr>'
                 '<th>Label</th><th>Confidence</th><th>Metric</th><th>Delta</th>'
                 '<th>Direction</th><th>Timestamp</th>'
                 '</tr></thead><tbody>' + "".join(shown) + '</tbody></table></div>')
    parts.append(_capped_note(dropped, "labels"))
    parts.append('<p class="n">One row per label, the newest record only, across every '
                 'confidence: a newer NOT_PROVEN supersedes an older VERIFIED for the same '
                 'label. Never summed across labels or across repeated runs of the same label; '
                 'a regression shows its delta exactly as measured, never clipped to zero. '
                 'Which machine ran an experiment is withheld: the result describes a '
                 'configuration change, not a person.</p>')
    return "".join(parts)


def render(store_dir, org, stamp, days=DEFAULT_DAYS, min_group=MIN_GROUP_MACHINES,
           today=None):
    """Render the full dashboard body (no <html> wrapper) for one org. Reads
    only; never writes into `store_dir`, never runs git.

    `days` is the read window (0 for all history), `min_group` the minimum
    number of distinct machines behind any published aggregate. min_group is
    CLAMPED to MIN_GROUP_MACHINES here, not in main(), so no caller of this
    module can publish a smaller group than the floor by any route."""
    try:
        min_group = max(int(min_group), MIN_GROUP_MACHINES)
    except (TypeError, ValueError):
        min_group = MIN_GROUP_MACHINES
    rows, empty_machines, meta = collect_org(store_dir, org, days=days, today=today)
    healthy = [r for r in rows if r["error"] is None]
    by_day = aggregate_counters_by_day(healthy)
    by_team = aggregate_totals_by_tag(healthy, "team")
    by_env = aggregate_totals_by_tag(healthy, "environment")
    experiments = latest_experiment_by_label(healthy)

    parts = [f"<style>{ts.CSS}</style>", '<div class="wrap">']
    parts.append(f'<div class="top">{ts.SHIELD_SVG}<div>'
                 f'<p class="eyebrow">Token Shield Fleet</p>'
                 f'<h1>{ts.esc(org)}: org-wide dashboard</h1></div></div>')
    parts.append(f'<p class="stamp">Rendered {ts.esc(stamp)} from the fleet store at '
                 f'{ts.esc(fl._display_path(store_dir))}. Read-only: this page never writes to '
                 f'the store, never runs git, never sends anything anywhere.</p>')
    window = (f'the {meta["window_days"]} days ending {ts.esc(meta["today"])}'
              if meta["cutoff"] else "all history (--days 0)")
    parts.append(f'<p class="n">Window: {window}. {meta["outside_window"]} record file(s) '
                 f'dated outside it were skipped on their filename and never opened. Minimum '
                 f'group size {min_group}: no aggregate backed by fewer than {min_group} '
                 f'distinct machines is published, it is marked suppressed instead, and the '
                 f'machines table carries operational health only, never a per-machine token '
                 f'count.</p>')
    if not rows and not empty_machines and not meta["last_seen"]:
        parts.append(f'<p class="nodata">NO DATA: no machines found for org '
                     f'&quot;{ts.esc(org)}&quot; in this store.</p>')
    parts.append(render_machines_table(rows, empty_machines, meta))
    parts.append(render_counters_by_day(by_day, min_group))
    parts.append(render_tag_totals("Tokens by team", by_team, min_group))
    parts.append(render_tag_totals("Tokens by environment", by_env, min_group))
    parts.append(render_experiments(experiments))
    parts.append('<footer>Token Shield Fleet dashboard. Every figure is read from records '
                 'machines pushed themselves; a machine that has not pushed, or whose record '
                 'could not be read, renders its own NO DATA row and never blocks the rest of '
                 'this page. No cross-label totals anywhere. Nothing here is a per-person '
                 'measure: numbers are published only as aggregates over the minimum group '
                 'size named above, and what a window or a row cap left out is counted on the '
                 'page rather than dropped in silence.</footer>')
    parts.append("</div>")
    return "\n".join(parts) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--store-dir", required=True,
                    help="local path to a checked-out fleet store (contains fleet/<org>/...)")
    ap.add_argument("--org", required=True, help="org name, matches the store path fleet/<org>/")
    ap.add_argument("--out", required=True, help="HTML file to write")
    ap.add_argument("--stamp", default=None, help="snapshot label for the header")
    ap.add_argument("--body-only", action="store_true",
                    help="emit body content without the html wrapper (for artifact publish)")
    ap.add_argument("--days", type=int, default=DEFAULT_DAYS,
                    help=f"read only records dated within the last N calendar days, counting "
                         f"today (default {DEFAULT_DAYS}); 0 reads the whole store history")
    ap.add_argument("--min-group", type=int, default=MIN_GROUP_MACHINES,
                    help=f"minimum distinct machines behind any published aggregate "
                         f"(default and floor {MIN_GROUP_MACHINES}); may be raised, never "
                         f"lowered")
    a = ap.parse_args()

    if a.days < 0:
        print(f"refused: --days {a.days} must be 0 (whole history) or a positive number of "
              f"days", file=sys.stderr)
        return 2
    min_group = max(a.min_group, MIN_GROUP_MACHINES)
    if a.min_group < MIN_GROUP_MACHINES:
        print(f"--min-group {a.min_group} is below the floor of {MIN_GROUP_MACHINES} machines; "
              f"using {MIN_GROUP_MACHINES}", file=sys.stderr)

    # --org reaches a filesystem path (store_dir/fleet/<org>/...) below, via
    # collect_org: refused here, before that, rather than letting something
    # like "../../elsewhere" walk out of the org tree. Reused from fleet.py
    # (already used the same way at `fleet init`/`join`/`push`), never
    # reimplemented.
    try:
        fl._validate_org(a.org)
    except fl.FleetValidationError as e:
        print(str(e), file=sys.stderr)
        return 2

    store_dir = os.path.expanduser(a.store_dir)
    if not os.path.isdir(store_dir):
        print(f"NO DATA: {store_dir} does not exist.", file=sys.stderr)
        return 2

    stamp = a.stamp
    if stamp is None:
        stamp = time.strftime("%Y-%m-%d %H:%M")

    body = render(store_dir, a.org, stamp, days=a.days, min_group=min_group)
    out_html = (body if a.body_only
               else ts.render_standalone(body, title=f"Token Shield Fleet: {a.org}"))
    out = os.path.expanduser(a.out)
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    # encoding pinned: the page declares <meta charset="utf-8">, but a plain
    # open() encodes with the locale's codec, so under LC_ALL=C (cron,
    # launchd, CI, ssh without LANG) one non-ASCII byte anywhere in the store
    # raised UnicodeEncodeError and left a zero byte page.
    with open(out, "w", encoding="utf-8") as f:
        f.write(out_html)
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
