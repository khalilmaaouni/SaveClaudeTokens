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
"""

import argparse
import json
import math
import os
import sys
import time

import fleet as fl
import token_shield as ts

HERE = os.path.dirname(os.path.abspath(__file__))

REQUIRED_RECORD_FIELDS = ("schema", "date")

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


def collect_org(store_dir, org):
    """Walk fleet/<org>/<machine-id>/<date>.json under `store_dir`. Returns
    (rows, empty_machines), never raising. `rows` is one entry per record
    file found: {"machine_id", "date", "record" (or None), "error" (or
    None)}. `empty_machines` lists machine ids whose directory exists but
    held zero ".json" files. A missing store, org, or machine directory
    yields empty results rather than an error: the normal state before a
    machine has ever pushed.

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
        return rows, empty_machines
    if not os.path.isdir(org_dir):
        return rows, empty_machines
    for machine_id in sorted(os.listdir(org_dir)):
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
            path = os.path.join(machine_dir, fname)
            date = fname[:-len(".json")]
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
    return rows, empty_machines


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
    """{date: {model_bucket: {field: total}}}, summed only over rows whose
    record loaded and validated cleanly. A record with an empty or absent
    counters object contributes nothing to any bucket, never a fabricated
    zero."""
    by_day = {}
    for r in healthy_rows:
        rec = r["record"]
        date = rec.get("date")
        counters = rec.get("counters")
        if not isinstance(date, str) or not isinstance(counters, dict):
            continue
        day_bucket = by_day.setdefault(date, {})
        for model, fields in counters.items():
            if not isinstance(fields, dict):
                continue
            model_bucket = day_bucket.setdefault(model, {})
            for key, value in fields.items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    model_bucket[key] = model_bucket.get(key, 0) + value
    return by_day


def aggregate_totals_by_tag(healthy_rows, tag_key):
    """{tag_value: total_tokens_across_all_counter_fields}, summed only over
    healthy rows. A record with no value for `tag_key` (team or
    environment; both are optional per data/fleet.schema.json, set by
    `fleet join`) is bucketed under "(untagged)" rather than dropped."""
    totals = {}
    for r in healthy_rows:
        rec = r["record"]
        total = _record_total(rec)
        if total is None:
            continue
        tag = rec.get(tag_key)
        tag = tag if isinstance(tag, str) and tag else "(untagged)"
        totals[tag] = totals.get(tag, 0) + total
    return totals


def latest_experiment_by_label(healthy_rows):
    """One experiment item per (label, confidence), the newest by timestamp
    across every machine in the org.

    This used to keep its OWN copy of the "newest wins" tiebreak
    token_shield.verified_by_label already applies on the single-machine
    ledger, and had drifted to the OPPOSITE rule: on a timestamp tie it kept
    whichever row was seen FIRST, while verified_by_label keeps whichever is
    seen LAST (ledger order is append-only, so the row written most
    recently should win a tie, not the one written first). Two machines
    pushing the same label at the same timestamp could therefore disagree
    with the single-machine page about which record won. Fixed by calling
    verified_by_label directly for the pick, so the tiebreak itself runs in
    exactly one place.

    Bridging the two record shapes: verified_by_label was built for the
    single-machine proof ledger, so it (a) hard-filters to rows whose
    "confidence" key is the literal string "VERIFIED" and (b) requires a
    "floor_reduction_tokens" field that is a plain number, that ledger's own
    name and type-gate for its default-metric delta. A fleet experiment
    item's confidence can also be "NOT_PROVEN" (the fleet schema
    deliberately keeps both, so a regression still gets its own row), its
    delta field is the generic "metric_delta" (any target_metric, not just
    the floor), and it can carry no numeric delta at all. Neither difference
    is bridged by reimplementing the tiebreak itself, which depends only on
    timestamp and iteration order, never on the delta's value (see
    verified_by_label's own docstring): verified_by_label is called once
    per confidence value actually present in the data, against a throwaway
    reshaped copy of each row (confidence forced to "VERIFIED" so its
    filter passes; a missing or non-numeric metric_delta is replaced with a
    0.0 placeholder purely to satisfy its type gate, since that placeholder
    cannot change which row the timestamp/index tiebreak picks). The
    winning (label, timestamp) pick is then matched back to the LAST
    original fleet item with that label, confidence, and timestamp in
    iteration order -- matching verified_by_label's own tie resolution
    exactly -- to recover the REAL metric_delta, target_metric, direction,
    and machine_id for rendering: verified_by_label's own return shape
    (built from the reshaped, placeholder-bearing copy) is used only to
    learn WHICH (label, timestamp) won, never to source a rendered value."""
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
            # of these two fields has to remember.
            label = entry.get("label")
            entry["label"] = label if isinstance(label, str) else "(unlabeled)"
            conf = entry.get("confidence")
            entry["confidence"] = conf if isinstance(conf, str) else "NO DATA"
            entry["machine_id"] = r["machine_id"]
            items.append(entry)

    confidences = sorted({item.get("confidence") for item in items},
                         key=lambda c: (c is None, str(c)))
    out = []
    for confidence in confidences:
        subset = [it for it in items if it.get("confidence") == confidence]
        shaped = []
        for it in subset:
            delta = it.get("metric_delta")
            if isinstance(delta, bool) or not isinstance(delta, (int, float)):
                # verified_by_label's numeric-type gate is a coarse "is this
                # a number at all" check that has nothing to do with WHICH
                # row it picks (the pick is timestamp/index only, see its
                # own docstring); a real fleet item can carry no
                # metric_delta at all (an experiment with no numeric metric
                # comparison on either side, or an F2 registration record's
                # own experiments list), and must still be eligible to win
                # its label. 0.0 is a throwaway placeholder that satisfies
                # the gate without affecting the pick; the REAL delta shown
                # to a reader always comes from `match` below, never from
                # this placeholder or from verified_by_label's own return.
                delta = 0.0
            shaped.append({
                "label": it.get("label"),
                "confidence": "VERIFIED",  # forced: this is only how verified_by_label's own filter passes
                "timestamp": it.get("timestamp"),
                "floor_reduction_tokens": delta,
            })
        for w in ts.verified_by_label(shaped, exp_mod=None):
            w_ts = w.get("timestamp") if isinstance(w.get("timestamp"), str) else ""
            match = None
            for it in subset:
                label = it.get("label")
                label = label if isinstance(label, str) and label else "(unlabeled)"
                it_ts = it.get("timestamp") if isinstance(it.get("timestamp"), str) else ""
                if label == w["label"] and it_ts == w_ts:
                    match = it  # last match in iteration order is the real tiebreak winner
            out.append({
                "label": w["label"],
                "confidence": confidence,
                "timestamp": w.get("timestamp"),
                "target_metric": match.get("target_metric") if match else None,
                "metric_delta": match.get("metric_delta") if match else None,
                "direction": match.get("direction") if match else None,
                "machine_id": match.get("machine_id") if match else None,
            })
    return sorted(out, key=lambda x: x["label"])


# --- rendering ---------------------------------------------------------------

def render_machines_table(rows, empty_machines):
    parts = ['<h2>Machines reporting</h2>']
    if not rows and not empty_machines:
        parts.append('<p class="nodata">NO DATA: no machines found for this org in the store.'
                     '</p>')
        return "".join(parts)
    rowlist = []
    for r in sorted(rows, key=lambda r: (r["machine_id"], r["date"] or "")):
        mid = ts.esc(r["machine_id"])
        date = ts.esc(r["date"] or "n/a")
        if r["error"] is not None:
            rowlist.append(
                f'<tr><td>{mid}</td><td>{date}</td><td class="nodata">NO DATA</td>'
                f'<td>{ts.esc(_scrub_paths(r["error"]))}</td></tr>')
            continue
        rec = r["record"]
        team = ts.esc(rec.get("team") or "(untagged)")
        env = ts.esc(rec.get("environment") or "(untagged)")
        total = _record_total(rec)
        rowlist.append(
            f'<tr><td>{mid}</td><td>{date}</td><td>{ts.human(total)}</td>'
            f'<td>team {team}, env {env}</td></tr>')
    for machine_id in sorted(empty_machines):
        rowlist.append(
            f'<tr><td>{ts.esc(machine_id)}</td><td>n/a</td><td class="nodata">NO DATA</td>'
            f'<td>no records found for this machine</td></tr>')
    parts.append('<div class="scroll"><table class="se"><thead><tr>'
                 '<th>Machine</th><th>Date</th><th>Tokens</th><th>Detail</th>'
                 '</tr></thead><tbody>' + "".join(rowlist) + '</tbody></table></div>')
    return "".join(parts)


def render_counters_by_day(by_day):
    parts = ['<h2>Token counters by day</h2>']
    if not by_day:
        parts.append('<p class="nodata">NO DATA: no healthy records carried token counters.</p>')
        return "".join(parts)
    rowlist = []
    for date in sorted(by_day):
        for model in sorted(by_day[date]):
            f = by_day[date][model]
            rowlist.append(
                f'<tr><td>{ts.esc(date)}</td><td>{ts.esc(model)}</td>'
                f'<td>{ts.human(f.get("input_tokens"))}</td>'
                f'<td>{ts.human(f.get("output_tokens"))}</td>'
                f'<td>{ts.human(f.get("cache_read_input_tokens"))}</td>'
                f'<td>{ts.human(f.get("cache_creation_input_tokens"))}</td></tr>')
    parts.append('<div class="scroll"><table class="se"><thead><tr>'
                 '<th>Date</th><th>Model</th><th>Input</th><th>Output</th>'
                 '<th>Cache read</th><th>Cache write</th></tr></thead><tbody>'
                 + "".join(rowlist) + '</tbody></table></div>')
    return "".join(parts)


def render_tag_totals(title, totals):
    parts = [f'<h2>{ts.esc(title)}</h2>']
    if not totals:
        parts.append('<p class="nodata">NO DATA: no healthy records carried this tag.</p>')
        return "".join(parts)
    rowlist = "".join(
        f'<tr><td>{ts.esc(tag)}</td><td>{ts.human(total)}</td></tr>'
        for tag, total in sorted(totals.items(), key=lambda kv: -kv[1]))
    parts.append('<div class="scroll"><table class="se"><thead><tr>'
                 '<th>Tag</th><th>Tokens</th></tr></thead><tbody>'
                 + rowlist + '</tbody></table></div>')
    return "".join(parts)


def render_experiments(items):
    parts = ['<h2>Experiments, latest per label</h2>']
    if not items:
        parts.append('<p class="nodata">NO DATA: no experiment records exported by any machine.'
                     '</p>')
        return "".join(parts)
    rowlist = []
    for item in items:
        delta = item.get("metric_delta")
        delta_txt = (f'{delta:+,}' if isinstance(delta, (int, float))
                    and not isinstance(delta, bool) else "n/a")
        conf = item.get("confidence") if isinstance(item.get("confidence"), str) else "NO DATA"
        rowlist.append(
            f'<tr><td>{ts.esc(item["label"])}</td><td>{ts._cpill(conf)}</td>'
            f'<td>{ts.esc(item.get("target_metric") or "n/a")}</td>'
            f'<td>{delta_txt}</td><td>{ts.esc(item.get("direction") or "n/a")}</td>'
            f'<td>{ts.esc(str(item.get("timestamp") or "n/a")[:19])}</td>'
            f'<td>{ts.esc(item.get("machine_id") or "n/a")}</td></tr>')
    parts.append('<div class="scroll"><table class="se"><thead><tr>'
                 '<th>Label</th><th>Confidence</th><th>Metric</th><th>Delta</th>'
                 '<th>Direction</th><th>Timestamp</th><th>Machine</th>'
                 '</tr></thead><tbody>' + "".join(rowlist) + '</tbody></table></div>')
    parts.append('<p class="n">One row per label, the newest record only. Never summed across '
                 'labels or across repeated runs of the same label; a regression shows its '
                 'delta exactly as measured, never clipped to zero.</p>')
    return "".join(parts)


def render(store_dir, org, stamp):
    """Render the full dashboard body (no <html> wrapper) for one org. Reads
    only; never writes into `store_dir`, never runs git."""
    rows, empty_machines = collect_org(store_dir, org)
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
    if not rows and not empty_machines:
        parts.append(f'<p class="nodata">NO DATA: no machines found for org '
                     f'&quot;{ts.esc(org)}&quot; in this store.</p>')
    parts.append(render_machines_table(rows, empty_machines))
    parts.append(render_counters_by_day(by_day))
    parts.append(render_tag_totals("Tokens by team", by_team))
    parts.append(render_tag_totals("Tokens by environment", by_env))
    parts.append(render_experiments(experiments))
    parts.append('<footer>Token Shield Fleet dashboard. Every figure is read from records '
                 'machines pushed themselves; a machine that has not pushed, or whose record '
                 'could not be read, renders its own NO DATA row and never blocks the rest of '
                 'this page. No cross-label totals anywhere.</footer>')
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
    a = ap.parse_args()

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

    body = render(store_dir, a.org, stamp)
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
