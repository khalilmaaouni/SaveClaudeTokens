#!/usr/bin/env python3
"""
experiment.py: the only honest way Token Shield produces a VERIFIED saving.

A prevented event is a counterfactual, so it is at best ESTIMATED, never
verified. The only thing that earns VERIFIED is a real before/after: measure,
change one thing, measure again over the SAME window, and refuse the comparison
if anything that would invalidate it changed.

  python3 experiment.py start "shrink-claude-md"   # pins a baseline now
  ...do the one change, work normally for a while...
  python3 experiment.py end "shrink-claude-md"     # compares, writes one record
  python3 experiment.py report                     # per-label rows, never summed

Each ended experiment appends ONE record to ~/.claude/token-shield/savings.jsonl,
the append-only proof ledger the dashboard reads for its VERIFIED column. The
comparison reuses the meter's own guards: it refuses across a schema change and
downgrades to NOT_PROVEN on a window mismatch or thin data, rather than print a
confident number that means nothing.

v2 adds four more guards on top of the v1 before/after:
  - cohorts are built from each usage record's own message timestamp, not the
    session file's mtime, so a transcript resumed from before the experiment
    only contributes the records that actually fall inside the window, and it
    contributes no startup floor at all because its first turn is not in there;
  - the after cohort is refused outright (no ledger write) if it would start
    at or before the before cohort ended, since touching windows put the same
    boundary record on both sides of the comparison;
  - a config fingerprint (CLAUDE.md, settings.json, ~/.claude.json, every
    skills/*/SKILL.md, installed plugin dirs) is taken at start and end; if it
    moved for any reason other than the named --treats target, the verdict
    downgrades to NOT_PROVEN rather than credit an unrelated config change.
    Whatever --treats excludes is listed on the record and printed at the end,
    because a blind spot nobody can see is worse than no guard at all;
  - a baseline pinned before those guards existed carries none of them, so it
    is not comparable under them: it can never be VERIFIED, only NOT_PROVEN
    with the legacy baseline named as the reason.
"""

import argparse
import glob
import hashlib
import json
import os
import time
from datetime import datetime, timezone

import measure_tokens as mt

HOME = os.path.expanduser("~")
STORE = os.path.join(HOME, ".claude", "token-shield")
EXP_DIR = os.path.join(STORE, "experiments")
LEDGER = os.path.join(STORE, "savings.jsonl")
CLAUDE_MD_PATH = os.path.join(HOME, ".claude", "CLAUDE.md")
SETTINGS_PATH = os.path.join(HOME, ".claude", "settings.json")
CLAUDE_JSON_PATH = os.path.join(HOME, ".claude.json")  # holds mcpServers
SKILLS_DIR = os.path.join(HOME, ".claude", "skills")
PLUGINS_CACHE = os.path.join(HOME, ".claude", "plugins", "cache")

MIN_SESSIONS = 3  # below this, coverage is too thin to call a comparison verified
EXP_SCHEMA = 2  # ledger record schema. v1 records never carried a "schema" key
                # at all, so its absence on an old record means schema 1; this
                # is a different axis than mt.SCHEMA, which is the meter's own.

# The keys a v2 baseline snapshot must carry for the v2 guards to have anything
# to check. A v1.6 snapshot has none of them, and every v2 guard is written as
# "downgrade if this moved", which a missing key silently passes.
V2_BASELINE_KEYS = ("cohort_start_ts", "cohort_end_ts", "fingerprint_start", "treats")


def _iso(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")


def _parse_ts(s):
    """Parse a message timestamp (ISO 8601, typically 'Z' or '+00:00') to
    epoch seconds. Returns None on anything unparsable rather than guessing,
    since a record with an unreadable timestamp cannot be placed in a cohort
    window."""
    if not s or not isinstance(s, str):
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def fingerprint_files():
    """Every file whose content is inside the fingerprint's scope, sorted.
    Machine-level config only: a project's own CLAUDE.md is out of scope
    because this comparison is machine-wide and cwd-dependent (docs/CLAIMS.md
    records that gap)."""
    files = [CLAUDE_MD_PATH, SETTINGS_PATH, CLAUDE_JSON_PATH]
    try:
        files += glob.glob(os.path.join(SKILLS_DIR, "**", "SKILL.md"), recursive=True)
    except OSError:
        pass
    return sorted(set(files))


def excluded_by_treats(treats=None):
    """The in-scope files --treats blinds the fingerprint to. Returned so the
    record and the end-of-experiment output can name them: an exclusion the
    user cannot see is a confounder credited to the named treatment."""
    if not treats:
        return []
    treats_abs = os.path.abspath(os.path.expanduser(treats))
    return [p for p in fingerprint_files() if os.path.abspath(p) == treats_abs]


def _sha_file(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
    except OSError:
        return "MISSING"
    return h.hexdigest()


def compute_fingerprint(treats=None):
    """sha256 over a MANIFEST, one line per in-scope item, sorted:
    "<path>:<sha256 of its content>" for each fingerprinted file, then
    "<dir>:PLUGIN" for each installed plugin dir under plugins/cache/*/*.
    Hashing a manifest rather than concatenated bytes means two files cannot
    trade content across their boundary and leave the hash unmoved.

    `treats` names the one file this experiment's own treatment edits: its
    line becomes "<path>:EXCLUDED" so the experiment does not trip its own
    confounder guard. Call excluded_by_treats() to report that blind spot.
    """
    excluded = set(excluded_by_treats(treats))
    lines = []
    for path in fingerprint_files():
        lines.append(f"{path}:EXCLUDED" if path in excluded
                     else f"{path}:{_sha_file(path)}")
    try:
        plugin_dirs = sorted(
            d for d in glob.glob(os.path.join(PLUGINS_CACHE, "*", "*")) if os.path.isdir(d)
        )
    except OSError:
        plugin_dirs = []
    lines += [f"{d}:PLUGIN" for d in plugin_dirs]
    return hashlib.sha256("\n".join(sorted(lines)).encode("utf-8")).hexdigest()


def legacy_baseline_reason(baseline):
    """A baseline snapshot pinned by v1.6 carries none of the v2 guard fields,
    and every v2 guard passes silently when its field is absent, so such a
    snapshot would sail through to VERIFIED with nothing actually checked.
    Returns a reason string naming the legacy baseline, or None when the
    snapshot carries the whole v2 shape."""
    missing = [k for k in V2_BASELINE_KEYS if k not in baseline]
    if not missing:
        return None
    label = baseline.get("label") or "(unlabeled)"
    return (f"legacy baseline '{label}' predates the v2 guards (missing "
            f"{', '.join(missing)}), so none of them ever ran on it; it is not "
            f"comparable. Pin a fresh baseline with experiment start.")


def check_cohort_order(before_end_ts, after_start_ts):
    """Pure guard: the after cohort must start strictly after the before cohort
    ends, or the two windows hold overlapping (double-counted) sessions.
    Windows are half-open [start, end), so a shared boundary already shares no
    record; refusing the touching case too keeps the guard true even if a
    caller ever hands it a closed window.
    Returns a reason string to refuse on, or None when the order is fine."""
    if after_start_ts < before_end_ts:
        return (f"after cohort starts before the before cohort ends "
                f"(after {_iso(after_start_ts)} < before-end {_iso(before_end_ts)}); "
                f"windows overlap")
    if after_start_ts == before_end_ts:
        return (f"after cohort starts exactly where the before cohort ends "
                f"({_iso(after_start_ts)}); the boundary record would be counted "
                f"on both sides")
    return None


def _read_session_cohort(fp, start_ts, end_ts):
    """Mirror of measure_tokens.read_session, filtered to only the usage
    records whose message timestamp falls inside the half-open window
    [start_ts, end_ts). Returns the same dict shape read_session does, so
    measure_tokens.summarize can consume it unchanged. A resumed old
    transcript contributes only the records inside the window, never its
    whole history.

    A transcript whose FIRST usage record predates start_ts is a straddler:
    its earliest in-window record is a mid-conversation turn, not a startup
    floor, so it contributes NO first_request (first stays 0, which is how
    summarize already excludes a transcript from the floor stats). Its tokens
    stay in the totals, and the dict is marked "straddler" so the exclusion
    can be counted and shown."""
    first = None
    started = None
    earliest_ts = None
    tot = {"input": 0, "write_5m": 0, "write_1h": 0, "write_unsplit": 0,
           "read": 0, "output": 0}
    calls = 0
    sub_calls = 0
    sub_output = 0
    models = set()
    try:
        fh = open(fp, "r", errors="ignore")
    except OSError:
        return None
    with fh:
        for line in fh:
            if '"usage"' not in line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = _parse_ts(rec.get("timestamp"))
            msg = rec.get("message") or {}
            usage = msg.get("usage") or rec.get("usage")
            if not isinstance(usage, dict):
                continue
            inp = usage.get("input_tokens") or 0
            rd = usage.get("cache_read_input_tokens") or 0
            out = usage.get("output_tokens") or 0
            w5, w1, wu = mt.split_writes(usage)
            if inp == 0 and rd == 0 and w5 == 0 and w1 == 0 and wu == 0:
                continue

            is_sub = bool(rec.get("isSidechain"))
            # Tracked over the WHOLE transcript, before the window filter, and
            # only over the records that could ever become a first_request.
            # That is what makes the straddler test below mean "the first turn
            # of this session" rather than "the first turn inside the window".
            if not is_sub and ts is not None and (earliest_ts is None or ts < earliest_ts):
                earliest_ts = ts
            if ts is None or ts < start_ts or ts >= end_ts:
                continue

            calls += 1
            tot["input"] += inp
            tot["write_5m"] += w5
            tot["write_1h"] += w1
            tot["write_unsplit"] += wu
            tot["read"] += rd
            tot["output"] += out

            if is_sub:
                sub_calls += 1
                sub_output += out
            else:
                model = msg.get("model")
                if model and not str(model).startswith("<"):
                    models.add(model)
                if first is None:
                    first = inp + w5 + w1 + wu + rd
                    started = rec.get("timestamp")

    if calls == 0:
        return None

    straddler = earliest_ts is not None and earliest_ts < start_ts
    if straddler:
        # Mid-conversation turns are cheap relative to a real startup floor.
        # Counting one as a first_request is how a floor reduction gets
        # invented out of a resumed transcript, so this side contributes none.
        first = None
        started = None

    write_total = tot["write_5m"] + tot["write_1h"] + tot["write_unsplit"]
    raw_input = tot["input"] + write_total + tot["read"]
    if tot["write_unsplit"]:
        normalized = None
    else:
        normalized = (tot["input"] + mt.CACHE_WRITE_5M * tot["write_5m"]
                      + mt.CACHE_WRITE_1H * tot["write_1h"] + mt.CACHE_READ * tot["read"])
    first = first or 0
    return {
        "file": fp, "calls": calls, "first_request": first, "started": started,
        "first_request_share": (first * calls / raw_input) if raw_input else None,
        "hit_ratio": (tot["read"] / raw_input) if raw_input else 0.0,
        "rewrite_ratio": (write_total / tot["read"]) if tot["read"] else None,
        "write_total": write_total, "raw_input": raw_input,
        "normalized_input": normalized,
        "output_to_input": (tot["output"] / normalized) if normalized else None,
        "models": len(models), "model_names": models,
        "sub_calls": sub_calls, "sub_output": sub_output,
        "straddler": straddler,
        **tot,
    }


def collect_cohort(root, start_ts, end_ts):
    """All sessions' usage records with a message timestamp inside the
    window, across every transcript under root. A file's mtime can only be
    older than the last record it holds, so files untouched since start_ts
    cannot contain a record inside the window and are skipped."""
    out = []
    for fp in mt.iter_session_files(root, start_ts):
        s = _read_session_cohort(fp, start_ts, end_ts)
        if s:
            out.append(s)
    return out


def build_record(baseline, after_sm, ended_iso, fingerprint_end=None):
    """Pure verdict function: baseline (the start snapshot) + the after summary
    -> one ledger record with a confidence class. No I/O, so it is testable.

    Guards, each of which downgrades to NOT_PROVEN with a stated reason:
      - the baseline predates the v2 guards, so none of them ever ran on it;
      - schema changed since the baseline (the meter's own refusal);
      - window length differs (different windows hold different sessions);
      - too few sessions on EITHER side to measure a floor honestly, because a
        one-session before cohort is exactly as thin as a one-session after;
      - the config fingerprint moved between start and end (fingerprint_end
        passed in, compared against baseline["fingerprint_start"]) and the
        mover was not the file named at start's --treats;
      - the DOMINANT main-thread model (the one used in the most sessions,
        ties broken lexically) differs between the before and after cohort,
        when both sides carry main-thread model tracking at all; exactly one
        side missing it (a baseline pinned before this field existed) is
        itself a downgrade, never a silent skip, since NO DATA beats a guess.
    Non-overlap between the before and after cohort windows is a harder
    refusal, enforced by check_cohort_order before this function is ever
    called, so no ledger record gets written for it at all.
    """
    reasons = []
    b = baseline.get("summary") or {}
    legacy = legacy_baseline_reason(baseline)
    if legacy:
        reasons.append(legacy)
    if baseline.get("schema") != mt.SCHEMA:
        reasons.append(f"baseline is schema {baseline.get('schema')}, meter is {mt.SCHEMA}")
    if baseline.get("window_days") != after_sm.get("_window_days"):
        reasons.append(f"window changed ({baseline.get('window_days')} vs "
                       f"{after_sm.get('_window_days')} days)")
    if (b.get("parent_sessions") or 0) < MIN_SESSIONS:
        reasons.append(f"only {b.get('parent_sessions')} sessions before the change, "
                       f"need {MIN_SESSIONS}")
    if (after_sm.get("parent_sessions") or 0) < MIN_SESSIONS:
        reasons.append(f"only {after_sm.get('parent_sessions')} sessions after the change, "
                       f"need {MIN_SESSIONS}")

    fp_start = baseline.get("fingerprint_start")
    if fingerprint_end is not None and fp_start is not None and fingerprint_end != fp_start:
        reasons.append("config changed during experiment window")

    # Model mix is a confound the same way the config fingerprint is: a floor
    # change might come from a model switch mid-experiment, not the named
    # treatment. The trigger is the DOMINANT model per cohort (the one used
    # in the most sessions, ties broken lexically), not full-set equality:
    # a routine minor-version bump touching one session out of many would
    # otherwise downgrade every experiment. The full sets still ride along
    # on the record as models_before/models_after for transparency.
    #
    # "Neither side tracked" (both None, e.g. a legacy baseline compared
    # against another legacy-shaped summary) is not a difference and stays
    # silent. But EXACTLY ONE side missing _models is not "no data on
    # either side": it means the comparison itself cannot be trusted, and a
    # silent skip there would let a live baseline pinned before this field
    # existed sail through to VERIFIED with the guard never having run.
    # NO DATA beats a guess, so that case downgrades with a named reason.
    models_before = b.get("_models")
    models_after = after_sm.get("_models")
    if models_before is None and models_after is None:
        pass
    elif (models_before is None) != (models_after is None):
        thin_side = "before" if models_before is None else "after"
        reasons.append(
            f"model mix cannot be compared: the {thin_side} cohort predates "
            f"model tracking (no _models recorded)")
    else:
        dominant_before = b.get("_dominant_model")
        dominant_after = after_sm.get("_dominant_model")
        if (dominant_before is not None and dominant_after is not None
                and dominant_before != dominant_after):
            reasons.append(
                f"dominant model changed during experiment window "
                f"(before {dominant_before!r}, after {dominant_after!r})")

    fr_before = b.get("first_request_median")
    fr_after = after_sm.get("first_request_median")
    if fr_before is None or fr_after is None:
        reasons.append("no first-request median on one side")

    verified = not reasons
    floor_reduction = None
    if fr_before is not None and fr_after is not None:
        floor_reduction = fr_before - fr_after

    direction = None
    if floor_reduction is not None:
        if floor_reduction > 0:
            direction = "saving"
        elif floor_reduction < 0:
            direction = "regression"
        else:
            direction = "flat"

    p90_before = b.get("first_request_p90")
    p90_after = after_sm.get("first_request_p90")

    return {
        "schema": EXP_SCHEMA,
        "timestamp": ended_iso,
        "label": baseline.get("label"),
        "confidence": "VERIFIED" if verified else "NOT_PROVEN",
        "reasons": reasons,
        "window_days": baseline.get("window_days"),
        "cohort_before": {"start": baseline.get("cohort_start_ts"),
                          "end": baseline.get("cohort_end_ts")},
        "cohort_after": {"start": after_sm.get("_cohort_start_ts"),
                         "end": after_sm.get("_cohort_end_ts")},
        "fingerprint_start": fp_start,
        "fingerprint_end": fingerprint_end,
        "fingerprint_excluded": baseline.get("fingerprint_excluded") or [],
        "treats": baseline.get("treats"),
        "first_request_before": fr_before,
        "first_request_after": fr_after,
        "floor_reduction_tokens": floor_reduction,
        "direction": direction,
        "sessions_before": b.get("parent_sessions"),
        "sessions_after": after_sm.get("parent_sessions"),
        "dispersion_before": p90_before,
        "dispersion_after": p90_after,
        "normalized_input_before": b.get("normalized_input_total"),
        "normalized_input_after": after_sm.get("normalized_input_total"),
        "models_before": models_before,
        "models_after": models_after,
        "evidence": "API usage counters, before/after over the same window, "
                    "cohorted by message timestamp",
    }


def aggregate_by_label(records):
    """Group ledger records by label. One row per label, always: a floor
    reduction measured for one experiment is never summed with a floor
    reduction measured for an unrelated one, because they are not the same
    quantity."""
    by_label = {}
    for rec in records:
        label = rec.get("label") or "(unlabeled)"
        row = by_label.setdefault(label, {"count": 0, "verified": 0,
                                          "not_proven": 0, "reductions": []})
        row["count"] += 1
        if rec.get("confidence") == "VERIFIED":
            row["verified"] += 1
        else:
            row["not_proven"] += 1
        fr = rec.get("floor_reduction_tokens")
        if fr is not None:
            row["reductions"].append(fr)
    return by_label


def _measure_cohort(root, start_ts, end_ts, days):
    sessions = collect_cohort(root, start_ts, end_ts)
    sm = mt.summarize(sessions) or {}
    sm = dict(sm)
    sm["_window_days"] = days
    sm["_cohort_start_ts"] = start_ts
    sm["_cohort_end_ts"] = end_ts
    # The main-thread model names actually used in this cohort (model_names
    # is collected only from non-subagent records, see _read_session_cohort),
    # so build_record can catch a model switch between the before and after
    # cohort: a floor change might come from the new model, not the named
    # treatment. _models is the full set, kept for transparency on the
    # record; _dominant_model is the one used in the most sessions (ties
    # broken lexically) and is what the downgrade guard actually compares,
    # so a minor-version bump touching one session out of many does not by
    # itself flag every experiment.
    models = set()
    session_counts = {}
    for s in sessions:
        names = s.get("model_names") or set()
        models |= names
        for name in names:
            session_counts[name] = session_counts.get(name, 0) + 1
    sm["_models"] = sorted(models)
    sm["_dominant_model"] = (min(session_counts, key=lambda m: (-session_counts[m], m))
                             if session_counts else None)
    return sm


def print_excluded(excluded):
    """Name every file --treats hid from the fingerprint. Printed at close,
    every time, because a guard with an unannounced hole in it reads as a
    stronger guard than it is."""
    if not excluded:
        return
    print("fingerprint blind spot (named by --treats, excluded from the "
          "confounder guard):")
    for path in excluded:
        print(f"  - {path}")
    print("  Any other change to those files during the window is credited to "
          "this treatment.")


def cmd_start(label, root, days, now_ts, treats):
    os.makedirs(EXP_DIR, exist_ok=True)
    before_start_ts = now_ts - days * 86400
    before_end_ts = now_ts
    sm = _measure_cohort(root, before_start_ts, before_end_ts, days)
    fingerprint_start = compute_fingerprint(treats)
    excluded = excluded_by_treats(treats)
    snap = {"label": label, "started": _iso(now_ts), "window_days": days,
            "schema": mt.SCHEMA, "cohort_start_ts": before_start_ts,
            "cohort_end_ts": before_end_ts, "fingerprint_start": fingerprint_start,
            "treats": treats, "fingerprint_excluded": excluded, "summary": sm}
    path = os.path.join(EXP_DIR, label.replace("/", "_") + ".json")
    with open(path, "w") as f:
        json.dump(snap, f, indent=2)
    fr = sm.get("first_request_median")
    print(f"baseline pinned for '{label}': first-request median "
          f"{mt.fmt(fr)} tokens over {days:g} days.")
    print_excluded(excluded)
    print("Make ONE change now (for example diet CLAUDE.md), work normally, then run: "
          f"python3 experiment.py end \"{label}\"")
    return 0


def cmd_end(label, root, days, now_ts):
    path = os.path.join(EXP_DIR, label.replace("/", "_") + ".json")
    if not os.path.exists(path):
        print(f"NO DATA: no baseline named '{label}'. Run start first.")
        return 2
    try:
        with open(path) as f:
            baseline = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"NO DATA: cannot read baseline for '{label}' ({e}).")
        return 2

    after_start_ts = now_ts - days * 86400
    after_end_ts = now_ts
    before_end_ts = baseline.get("cohort_end_ts")
    if before_end_ts is not None:
        overlap_reason = check_cohort_order(before_end_ts, after_start_ts)
        if overlap_reason:
            print(f"REFUSED: {overlap_reason}")
            print("Nothing was written to the ledger. Wait longer, or end with a "
                  "smaller --days window, so the after cohort starts after the "
                  "before cohort ended.")
            return 2

    sm = _measure_cohort(root, after_start_ts, after_end_ts, days)
    fingerprint_end = compute_fingerprint(baseline.get("treats"))
    now_iso = _iso(now_ts)
    rec = build_record(baseline, sm, now_iso, fingerprint_end)
    os.makedirs(STORE, exist_ok=True)
    with open(LEDGER, "a") as f:
        f.write(json.dumps(rec) + "\n")
    print(f"=== experiment '{label}': {rec['confidence']} ===")
    if rec["confidence"] != "VERIFIED":
        print("NOT PROVEN, so nothing is claimed as verified. Reasons:")
        for r in rec["reasons"]:
            print(f"  - {r}")
    fr_b, fr_a = rec["first_request_before"], rec["first_request_after"]
    if fr_b is not None and fr_a is not None:
        print(f"first-request median  {mt.fmt(fr_b)} -> {mt.fmt(fr_a)} tokens "
              f"({rec['floor_reduction_tokens']:+,} per call)")
    print_excluded(rec["fingerprint_excluded"])
    print(f"one record appended to {LEDGER}")
    return 0


def cmd_report():
    if not os.path.exists(LEDGER):
        print(f"NO DATA: no ledger at {LEDGER} yet.")
        return 2
    records = []
    with open(LEDGER) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if not records:
        print("NO DATA: ledger carries no readable records.")
        return 2
    by_label = aggregate_by_label(records)
    print("=== experiments, one row per label (never summed across labels) ===")
    for label in sorted(by_label):
        row = by_label[label]
        latest = row["reductions"][-1] if row["reductions"] else None
        print(f"{label:<30} {row['count']:>3} runs  "
              f"{row['verified']:>2} VERIFIED  {row['not_proven']:>2} NOT_PROVEN  "
              f"latest floor reduction {mt.fmt(latest)} tokens/call")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("action", choices=["start", "end", "report"])
    ap.add_argument("label", nargs="?", default=None)
    ap.add_argument("--root", default=os.path.expanduser("~/.claude/projects"))
    ap.add_argument("--days", type=float, default=30)
    ap.add_argument("--treats", default=None,
                    help="path excluded from the config fingerprint (the file "
                         "this experiment's own treatment edits); start only")
    a = ap.parse_args()

    if a.action == "report":
        return cmd_report()
    if not a.label:
        print(f"NO DATA: '{a.action}' requires a label.")
        return 2
    if not os.path.isdir(a.root):
        print(f"NO DATA: {a.root} does not exist.")
        return 2
    now_ts = time.time()
    if a.action == "start":
        return cmd_start(a.label, a.root, a.days, now_ts, a.treats)
    return cmd_end(a.label, a.root, a.days, now_ts)


if __name__ == "__main__":
    import sys
    sys.exit(main())
