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

USAGE
  python3 fleet_dashboard.py --store-dir PATH --org ORG --out OUT.html
  python3 fleet_dashboard.py --store-dir PATH --org ORG --out OUT.html --stamp "2026-08-15 09:00"
"""

import argparse
import json
import os
import sys
import time

import fleet as fl
import token_shield as ts

HERE = os.path.dirname(os.path.abspath(__file__))

REQUIRED_RECORD_FIELDS = ("schema", "date")


def _validate_record_shape(record):
    """Return a reason string if `record` (already parsed and schema-checked
    by fleet.load_record) is missing a field data/fleet.schema.json requires,
    or carries a negative token count. Returns None when the shape is
    usable. Never raises; this is the hostile-content fence collect_org()
    puts around every file, checked after fleet.load_record's own JSON and
    schema-version checks so the two refusals never overlap."""
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
                if (isinstance(value, (int, float)) and not isinstance(value, bool)
                        and value < 0):
                    return f"negative token count in counters.{bucket_name}.{key}"
    return None


def _load_one(path):
    """Load and validate one fleet record file. Returns (record, error):
    exactly one of the two is None. Never raises: a missing or unreadable
    file, invalid JSON, a schema newer than fleet.load_record understands, a
    missing required field, or a negative counter all come back as a named
    reason string instead of an exception, so one bad file can never take
    the whole dashboard render down."""
    try:
        record = fl.load_record(path)
    except OSError as e:
        return None, f"could not read file: {e}"
    except json.JSONDecodeError as e:
        return None, f"invalid JSON: {e}"
    except fl.FleetSchemaError as e:
        return None, str(e)
    shape_error = _validate_record_shape(record)
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
    machine has ever pushed."""
    org_dir = os.path.join(store_dir, "fleet", org)
    rows = []
    empty_machines = []
    if not os.path.isdir(org_dir):
        return rows, empty_machines
    for machine_id in sorted(os.listdir(org_dir)):
        machine_dir = os.path.join(org_dir, machine_id)
        if not os.path.isdir(machine_dir):
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
            record, error = _load_one(path)
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
    """One experiment item per label, the newest by timestamp across every
    machine in the org, mirroring the "never sum, latest wins" contract
    token_shield.verified_by_label applies to the single-machine ledger. A
    tie on timestamp keeps whichever row was seen first (rows are walked in
    machine_id, then filename order); repeated runs of the same label are
    never added together, and a regression's metric_delta is carried
    through exactly as recorded, negative sign included."""
    newest_ts = {}
    out = {}
    for r in healthy_rows:
        rec = r["record"]
        experiments = rec.get("experiments")
        if not isinstance(experiments, list):
            continue
        for item in experiments:
            if not isinstance(item, dict):
                continue
            label = item.get("label")
            label = label if isinstance(label, str) and label else "(unlabeled)"
            ts_val = item.get("timestamp") if isinstance(item.get("timestamp"), str) else ""
            if label in newest_ts and ts_val <= newest_ts[label]:
                continue
            newest_ts[label] = ts_val
            out[label] = {
                "label": label,
                "confidence": item.get("confidence"),
                "timestamp": item.get("timestamp"),
                "target_metric": item.get("target_metric"),
                "metric_delta": item.get("metric_delta"),
                "direction": item.get("direction"),
                "machine_id": r["machine_id"],
            }
    return [out[k] for k in sorted(out)]


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
                f'<td>{ts.esc(r["error"])}</td></tr>')
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
            f'<td>{ts.esc(str(item.get("timestamp") or "n/a"))[:19]}</td>'
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
                 f'{ts.esc(store_dir)}. Read-only: this page never writes to the store, never '
                 f'runs git, never sends anything anywhere.</p>')
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
    with open(out, "w") as f:
        f.write(out_html)
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
