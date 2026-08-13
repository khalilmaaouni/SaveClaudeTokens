#!/usr/bin/env python3
"""
report.py: the monthly Token Shield report.

WHY A SEPARATE REPORT AND NOT JUST A LONGER DASHBOARD
The dashboard and cli.py summary answer "what is true right now, over a
rolling window." A month-end report answers a different question: "what
happened in this specific calendar month," which needs records windowed by
their own message timestamp, not by file mtime or a trailing N days from
today. That is the same cohorting problem experiment.py already solved for
its before/after comparisons, so this script reuses experiment.py's
timestamp-cohort reader instead of re-deriving it.

TRUTH RULES, ENFORCED BY SECTION LAYOUT, NOT BY CONVENTION
VERIFIED (the experiment ledger), MEASURED (this month's usage counters),
NATIVE (Anthropic's own caching benefit), and ESTIMATED (the addressable
opportunity) are four different kinds of claim about four different
quantities. They are rendered into separate sections and never added
together anywhere in this file. The opportunity line is worded "N
addressable opportunity, estimated" and never "could have saved N", because
a recommendation is not a saving until an experiment proves it.

No model calls. Every section is either read from a counter, read from the
append-only experiment ledger, or computed by the deterministic advisor.
A section with nothing to report prints a NO DATA line and moves on.

USAGE
  python3 report.py                       # previous calendar month
  python3 report.py --month 2026-07
  python3 report.py --month 2026-07 --out /tmp/2026-07.md
"""

import argparse
import datetime
import json
import os
import sys

import advisor as adv
import experiment as ex
import measure_tokens as mt
import profile as pf

try:
    import token_shield as ts
except Exception:
    ts = None

DEFAULT_ROOT = os.path.expanduser("~/.claude/projects")
DEFAULT_OUT_DIR = os.path.expanduser("~/.token-shield/reports")


def _month_bounds(year, month):
    """[start, end) as epoch seconds for the calendar month, in UTC, matching
    how experiment.py's cohort reader parses message timestamps."""
    start = datetime.datetime(year, month, 1, tzinfo=datetime.timezone.utc)
    if month == 12:
        end = datetime.datetime(year + 1, 1, 1, tzinfo=datetime.timezone.utc)
    else:
        end = datetime.datetime(year, month + 1, 1, tzinfo=datetime.timezone.utc)
    return start.timestamp(), end.timestamp()


def _previous_month(today=None):
    today = today or datetime.date.today()
    last_day_of_prev_month = today.replace(day=1) - datetime.timedelta(days=1)
    return last_day_of_prev_month.year, last_day_of_prev_month.month


def _bounded_raw_scan(root, start_ts, end_ts):
    """A month-bounded twin of profile.py's _raw_scan.

    profile._raw_scan cannot be reused unmodified here: it selects files by
    mtime with no upper bound and then reads every timestamp and effort value
    in the file, which pulls signals from outside the requested month into a
    report about that month. This walks the same files (mt.iter_session_files)
    and parses the same two fields (effort, timestamp), but keeps only the
    records whose own timestamp falls in [start_ts, end_ts), using
    experiment._parse_ts so the same string format is understood everywhere
    in this codebase. The metrics computed FROM these values (idle gap shares,
    model switch share) are not reimplemented: they are profile.py's own
    pf._idle_gap_shares and pf._model_switch_share, called on this bounded data.
    """
    effort_values = set()
    gaps = []
    files_scanned = 0
    skipped_files = 0
    skipped_lines = 0

    for fp in mt.iter_session_files(root, start_ts):
        files_scanned += 1
        try:
            f = open(fp, "r", errors="ignore")
        except OSError:
            skipped_files += 1
            continue

        timestamps = []
        with f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    skipped_lines += 1
                    continue
                raw_ts = rec.get("timestamp")
                epoch = ex._parse_ts(raw_ts) if isinstance(raw_ts, str) else None
                if epoch is None or epoch < start_ts or epoch >= end_ts:
                    continue
                eff = rec.get("effort")
                if eff is not None:
                    effort_values.add(pf.effort_bucket(eff))
                timestamps.append(raw_ts)

        timestamps.sort()
        for a, b in zip(timestamps, timestamps[1:]):
            da, db = ex._parse_ts(a), ex._parse_ts(b)
            if da is None or db is None:
                continue
            gap = db - da
            if gap < 0 or gap > 12 * 3600:
                continue  # negative: clock skew. over 12h: a day boundary.
            gaps.append(gap)

    return effort_values, gaps, files_scanned, skipped_files, skipped_lines


def _month_profile(root, start_ts, end_ts, sessions, sm):
    """Build a profile dict shaped exactly like profile.build_profile's
    output (the dotted-key {value,label,basis} contract advisor.py reads),
    but windowed to this calendar month instead of a rolling N days from now.
    Reuses profile.py's own metric builders and formulas throughout; only the
    file-walk that gathers effort values and idle gaps is month-bounded here
    because profile.py has no such bound to reuse.
    """
    effort_values, gaps, files_scanned, raw_skip_files, raw_skip_lines = (
        _bounded_raw_scan(root, start_ts, end_ts))

    window_note = "experiment.collect_cohort over the requested calendar month"

    def usage_metric(key):
        v = sm.get(key)
        return pf.metric(v, "NO DATA" if v is None else "MEASURED",
                          f"{key} from {window_note}")

    usage = {
        "first_request_median_tokens": usage_metric("first_request_median"),
        "cache_hit_ratio_median": usage_metric("hit_ratio_median"),
        "output_tokens_total": usage_metric("output_total"),
        "subagent_output_share": usage_metric("subagent_output_share"),
        "cache_write_5m_tokens": usage_metric("write_5m_total"),
        "cache_write_1h_tokens": usage_metric("write_1h_total"),
    }

    switch_share = pf._model_switch_share(sessions)
    idle_shares = pf._idle_gap_shares(gaps)
    sub_share = (sm["subagent_transcripts"] / sm["sessions"]) if sm.get("sessions") else None
    n_sessions = sm.get("sessions")

    behavior = {
        "sessions": (
            pf.metric(n_sessions, "MEASURED",
                      f"parent-plus-subagent transcript count from {window_note}")
            if n_sessions else pf.no_data("no session transcripts found in month")),
        "model_switch_session_share": (
            pf.no_data("no parent sessions in month") if switch_share is None else
            pf.metric(switch_share, "MEASURED",
                      "share of parent sessions whose assistant records carried 2+ "
                      "distinct message.model values, from measure_tokens per-session "
                      "model counts")),
        "effort_values_seen": (
            pf.metric(sorted(effort_values, key=str), "MEASURED",
                      f"distinct top-level effort field values across {files_scanned} "
                      f"scanned transcripts, whitelisted to "
                      f"{', '.join(pf.EFFORT_VALUES)}; anything else counts as "
                      f"{pf.EFFORT_OTHER} and its raw text is never stored")
            if files_scanned else pf.no_data("no transcript files found in month")),
        "idle_gap_shares": (
            pf.no_data("no consecutive same-session timestamp pairs under 12h found")
            if idle_shares is None else
            pf.metric(idle_shares, "SIGNAL",
                      "gaps between consecutive message timestamps within the month, "
                      "bucketed under 5m / 5-15m / 15-60m / over 60m; gaps over 12h "
                      "dropped as day boundaries")),
        "subagent_transcript_share": (
            pf.no_data("no transcripts found in month") if sub_share is None else
            pf.metric(sub_share, "MEASURED",
                      "subagent_transcripts / sessions from measure_tokens.summarize()")),
    }

    user_claude_md = os.path.expanduser("~/.claude/CLAUDE.md")
    project_claude_md = os.path.join(os.getcwd(), "CLAUDE.md")
    memory_index = pf.cl.expected_memory_index_path()
    floor_share = sm.get("first_request_share_median")

    instruction = {
        "claude_md_user_bytes": pf._file_metric(user_claude_md, "user CLAUDE.md"),
        "claude_md_project_bytes": pf._file_metric(project_claude_md, "project CLAUDE.md"),
        "startup_floor_share": (
            pf.no_data("first_request_share_median not available") if floor_share is None else
            pf.metric(floor_share, "MEASURED", f"first_request_share_median from {window_note}")),
        "memory_index_bytes": pf._file_metric(memory_index, "project auto-memory index, "
                                              "located via context_lint's slug logic"),
    }

    plugin_cache_root = os.path.expanduser("~/.claude/plugins/cache")
    plugin_count = pf._plugin_count(plugin_cache_root)
    ttl_regime = pf._ttl_regime(sm)

    environment = {
        "plugin_count": (
            pf.no_data(f"no plugin cache directory at {plugin_cache_root}") if plugin_count is None else
            pf.metric(plugin_count, "INFERRED",
                      f"count of directories two levels under {plugin_cache_root} on this "
                      f"machine right now; plugin installs are not timestamped, so this is "
                      f"not scoped to the report month")),
        "ttl_regime": (
            pf.no_data("no cache writes in month") if ttl_regime is None else
            pf.metric(ttl_regime, "INFERRED",
                      "derived from the cache_write_5m_tokens vs cache_write_1h_tokens "
                      "split in usage: whichever class holds 60% or more of writes wins, "
                      "otherwise mixed")),
    }

    skipped = {
        "files": pf.metric(raw_skip_files, "MEASURED", "unreadable files during the bounded raw scan"),
        "lines": pf.metric(raw_skip_lines, "MEASURED",
                            "lines that failed JSON decoding during the bounded raw scan"),
    }

    return {
        "schema": pf.SCHEMA,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "window_days": None,
        "usage": usage,
        "behavior": behavior,
        "instruction": instruction,
        "environment": environment,
        "skipped": skipped,
    }


def _read_ledger():
    if not os.path.exists(ex.LEDGER):
        return []
    records = []
    with open(ex.LEDGER, errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def _in_month(iso_ts, start_ts, end_ts):
    epoch = ex._parse_ts(iso_ts) if isinstance(iso_ts, str) else None
    return epoch is not None and start_ts <= epoch < end_ts


def _verified_rows_for_month(records, start_ts, end_ts):
    month_verified = [r for r in records
                      if r.get("confidence") == "VERIFIED" and _in_month(r.get("timestamp"), start_ts, end_ts)]
    return ex.aggregate_by_label(month_verified)


def _what_did_not_work(records, treatments, start_ts, end_ts):
    """Rows for the "What did not work" section, plus a count of companion
    (reason "companion") suppressions excluded from it this month.

    A companion suppression is sync_companion_suppressions writing over a
    strategy an active companion plugin already owns; it is not a rejected
    or failed treatment, so it is excluded here rather than filed under a
    section the project treats as evidence something did not pan out. The
    excluded count is still surfaced (never silently dropped) so the section
    stays honest about what happened this month, without misfiling it.
    """
    rows = []
    not_proven = [r for r in records
                  if r.get("confidence") == "NOT_PROVEN" and _in_month(r.get("timestamp"), start_ts, end_ts)]
    for r in not_proven:
        reasons = "; ".join(r.get("reasons") or []) or "no reason recorded"
        rows.append(f"experiment '{r.get('label') or '(unlabeled)'}' NOT_PROVEN: {reasons}")
    companion_excluded = 0
    for sid, rec in sorted((treatments or {}).items()):
        if not _in_month(rec.get("at"), start_ts, end_ts):
            continue
        if rec.get("reason") == "companion":
            if rec.get("decision") in ("rejected", "suppressed"):
                companion_excluded += 1
            continue
        decision = rec.get("decision")
        if decision in ("rejected", "suppressed"):
            note = f": {rec['note']}" if rec.get("note") else ""
            rows.append(f"strategy '{sid}' {decision}{note}")
    return rows, companion_excluded


def build_report(year, month, root=None):
    """Return the plain-markdown monthly report as a string. Pure function of
    disk state: no printing, no writing, so it stays directly testable."""
    root = root or DEFAULT_ROOT
    start_ts, end_ts = _month_bounds(year, month)
    month_label = f"{year:04d}-{month:02d}"

    # _month_bounds returns a half-open [start, end) calendar month, and
    # experiment.collect_cohort's window is now half-open too, so end_ts passes
    # through unchanged: a record stamped at next month's first instant falls
    # outside both. This used to back the end off by one second to compensate
    # for a cohort window that was inclusive on both ends; doing that now would
    # drop a record stamped at the month's very last second.
    sessions = ex.collect_cohort(root, start_ts, end_ts)
    sm = mt.summarize(sessions) or {}

    lines = [f"# Token Shield monthly report: {month_label}", ""]
    lines.append(f"Window: calendar month {month_label}, UTC, by each record's own "
                 f"message timestamp (not file modification time).")
    lines.append("")

    # USAGE (MEASURED)
    lines.append("## Usage (MEASURED)")
    if not sm:
        lines.append("NO DATA: no transcript record carried a usage counter inside this month.")
    else:
        lines.append(f"- sessions: {mt.fmt(sm.get('sessions'))} "
                     f"({mt.fmt(sm.get('parent_sessions'))} parent, "
                     f"{mt.fmt(sm.get('subagent_transcripts'))} subagent transcripts)")
        lines.append(f"- normalized input: {mt.fmt(sm.get('normalized_input_total'))} "
                     f"base-input units over {mt.fmt(sm.get('normalized_sessions'))} transcripts")
        lines.append(f"- output: {mt.fmt(sm.get('output_total'))} tokens")
    lines.append("")

    # VERIFIED IMPROVEMENTS
    lines.append("## Verified improvements (VERIFIED)")
    records = _read_ledger()
    verified_rows = _verified_rows_for_month(records, start_ts, end_ts)
    if not verified_rows:
        lines.append("NO DATA: no VERIFIED experiment ledger record ended inside this month.")
    else:
        for label in sorted(verified_rows):
            row = verified_rows[label]
            latest = row["reductions"][-1] if row["reductions"] else None
            lines.append(f"- {label}: {row['verified']} VERIFIED run(s), "
                         f"latest floor reduction {mt.fmt(latest)} tokens/call")
    lines.append("")

    # NATIVE BENEFIT
    lines.append("## Native caching benefit (NATIVE)")
    if ts is None:
        lines.append("NO DATA: token_shield module not importable, so the native benefit "
                     "could not be computed.")
    elif not sm:
        lines.append("NO DATA: no usage this month to compute a native benefit from.")
    else:
        native = ts.savings_breakdown(sm)
        lines.append(f"- net caching benefit: {mt.fmt(native['saved'])} base-input units "
                     f"(Anthropic's own caching, not this tool's)")
    lines.append("")

    # TOP ISSUES
    lines.append("## Top issues")
    treatments = adv.load_treatments()
    month_profile = _month_profile(root, start_ts, end_ts, sessions, sm)
    advice = adv.advise(month_profile, treatments)
    top_cards = advice["queue"][:3]
    if not top_cards:
        lines.append("NO DATA: no advisor card fired for this month's profile.")
    else:
        for i, card in enumerate(top_cards, 1):
            lines.append(f"{i}. [{card['rank']}] {card['title']} ({card['id']}) -- "
                         f"{card['why_selected']}")
    lines.append("")

    # ADDRESSABLE OPPORTUNITY (ESTIMATED)
    lines.append("## Addressable opportunity (ESTIMATED)")
    if ts is None or not sm:
        lines.append("NO DATA: cannot estimate an addressable opportunity without "
                     "measured usage this month.")
    else:
        rx = ts.prescriptions(sm, sessions)
        if not rx:
            lines.append("NO DATA: no prescription triggered against this month's sessions.")
        else:
            total = sum(r["saving"] for r in rx)
            lines.append(f"- {mt.fmt(total)} base-input units addressable opportunity, "
                         f"estimated, across {len(rx)} prescription(s) from this month's "
                         f"own sessions")
    lines.append("")

    # WHAT DID NOT WORK
    lines.append("## What did not work")
    not_worked, companion_excluded = _what_did_not_work(records, treatments, start_ts, end_ts)
    if not not_worked and not companion_excluded:
        lines.append("NO DATA: no NOT_PROVEN experiment and no rejected or suppressed "
                     "strategy recorded this month.")
    else:
        for row in not_worked:
            lines.append(f"- {row}")
    if companion_excluded:
        lines.append(f"({companion_excluded} companion suppression(s) excluded: an installed "
                     f"companion plugin already owned that capability, not a failed treatment.)")
    lines.append("")

    # NEXT MONTH
    lines.append("## Next month")
    if top_cards:
        best = top_cards[0]
        lines.append(f"Single best action: {best['title']} ({best['id']}). "
                     f"{best['what_it_changes']}")
    else:
        lines.append("NO DATA: no advisor card fired, so there is no single best action to name.")

    return "\n".join(lines) + "\n"


def _parse_month(s):
    parts = s.split("-")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f"--month must be YYYY-MM, got {s!r}")
    try:
        year, month = int(parts[0]), int(parts[1])
    except ValueError:
        raise argparse.ArgumentTypeError(f"--month must be YYYY-MM, got {s!r}")
    if not (1 <= month <= 12):
        raise argparse.ArgumentTypeError(f"--month must be YYYY-MM with month 01-12, got {s!r}")
    return year, month


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--root", default=DEFAULT_ROOT)
    ap.add_argument("--month", type=_parse_month, default=None,
                    help="YYYY-MM, default the previous calendar month")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    year, month = a.month if a.month else _previous_month()
    month_label = f"{year:04d}-{month:02d}"
    out_path = a.out or os.path.join(DEFAULT_OUT_DIR, f"{month_label}.md")

    if not os.path.isdir(a.root) or next(mt.iter_session_files(a.root, 0), None) is None:
        print(f"NO DATA: no transcripts found under {a.root}.", file=sys.stderr)
        return 2

    report = build_report(year, month, root=a.root)

    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    try:
        with open(out_path, "w") as f:
            f.write(report)
    except OSError as e:
        print(f"NO DATA: could not write {out_path} ({e}).", file=sys.stderr)
        return 2

    print(f"report written: {out_path}")
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
