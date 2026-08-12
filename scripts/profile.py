#!/usr/bin/env python3
"""
profile.py: a deterministic usage profile for Token Shield.

WHY
---
measure_tokens.py answers "how many tokens, and where." This script answers
the questions that decide WHAT TO CHANGE: is the startup floor the biggest
lever, is the model switching mid-session, is CLAUDE.md itself the weight.
It writes one JSON snapshot (~/.token-shield/profile.json by default) that
other tools (the optimizer, the dashboard) can read without walking
transcripts themselves.

It reuses measure_tokens for every usage counter (collect/summarize): this
script never reimplements input/output/cache arithmetic. What it adds is a
second, lighter pass over the same transcript files for signals the counter
math does not carry: the top-level effort field, message timestamps for idle
gaps, and file-system facts about CLAUDE.md, the auto-memory index, and the
installed plugin count.

CONFIDENCE LABELS
Every leaf metric is {"value": ..., "label": ..., "basis": ...}:
  MEASURED  read from API usage counters or file bytes.
  SIGNAL    a derived heuristic from real records (bucket boundaries chosen
            by this script, over data that is itself real).
  INFERRED  deduced from the local environment, not portable to another
            machine or provable from the transcripts alone.
  NO DATA   value is null. Never a guess.

PRIVACY
Counters and byte sizes only. No conversation text, no transcript file paths.
CLAUDE.md and the memory-index path are config file paths, not conversation
content, and are named in the basis text because that is what was measured.

USAGE
  python3 profile.py                    # writes ~/.token-shield/profile.json
  python3 profile.py --days 7 --out FILE
"""

import argparse
import datetime
import json
import os
import sys
import time

import measure_tokens as mt
import context_lint as cl

SCHEMA = 1

IDLE_BUCKETS = ("under_5m", "5m_to_15m", "15m_to_60m", "over_60m")


def metric(value, label, basis):
    return {"value": value, "label": label, "basis": basis}


def no_data(basis):
    return metric(None, "NO DATA", basis)


def _file_bytes(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return None


def _file_metric(path, what):
    size = _file_bytes(path)
    if size is None:
        return no_data(f"{what}: no file at {path}")
    return metric(size, "MEASURED", f"{what}: byte size of {path} via os.path.getsize")


def _raw_scan(root, cutoff):
    """One extra pass over the same transcript files collect() walks, for the
    signals usage counters do not carry: the top-level effort field and
    message timestamps for idle-gap bucketing. Reuses mt.iter_session_files so
    the file selection matches the usage numbers exactly.

    Returns (effort_values, gaps_seconds, files_scanned, skipped_files, skipped_lines).
    gaps_seconds already excludes negative gaps (clock skew) and gaps over 12h
    (treated as a day boundary, not an idle wait worth bucketing).
    """
    effort_values = set()
    gaps = []
    files_scanned = 0
    skipped_files = 0
    skipped_lines = 0

    for fp in mt.iter_session_files(root, cutoff):
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
                eff = rec.get("effort")
                if eff is not None:
                    effort_values.add(eff)
                ts = rec.get("timestamp")
                if isinstance(ts, str):
                    timestamps.append(ts)

        timestamps.sort()
        for a, b in zip(timestamps, timestamps[1:]):
            try:
                da = datetime.datetime.fromisoformat(a.replace("Z", "+00:00"))
                db = datetime.datetime.fromisoformat(b.replace("Z", "+00:00"))
            except ValueError:
                continue
            gap = (db - da).total_seconds()
            if gap < 0 or gap > 12 * 3600:
                continue  # negative: clock skew. over 12h: a day boundary, not an idle wait.
            gaps.append(gap)

    return effort_values, gaps, files_scanned, skipped_files, skipped_lines


def _idle_gap_shares(gaps):
    if not gaps:
        return None
    counts = {k: 0 for k in IDLE_BUCKETS}
    for g in gaps:
        if g < 300:
            counts["under_5m"] += 1
        elif g < 900:
            counts["5m_to_15m"] += 1
        elif g < 3600:
            counts["15m_to_60m"] += 1
        else:
            counts["over_60m"] += 1
    n = len(gaps)
    return {k: v / n for k, v in counts.items()}


def _model_switch_share(sessions):
    """Share of parent sessions whose assistant records carried 2+ distinct
    message.model values. Reuses the per-session model count measure_tokens
    already computes (s["models"]); no new counter math."""
    parent = [s for s in sessions if s["first_request"] > 0]
    if not parent:
        return None
    switched = sum(1 for s in parent if s["models"] >= 2)
    return switched / len(parent)


def _plugin_count(cache_root):
    if not os.path.isdir(cache_root):
        return None
    count = 0
    for marketplace in os.listdir(cache_root):
        mpath = os.path.join(cache_root, marketplace)
        if not os.path.isdir(mpath):
            continue
        for plugin in os.listdir(mpath):
            if os.path.isdir(os.path.join(mpath, plugin)):
                count += 1
    return count


def _ttl_regime(sm):
    w5 = sm.get("write_5m_total") or 0
    w1 = sm.get("write_1h_total") or 0
    total = w5 + w1
    if total == 0:
        return None
    share_1h = w1 / total
    if share_1h >= 0.6:
        return "subscription-1h"
    if share_1h <= 0.4:
        return "api-5m"
    return "mixed"


def build_profile(root=None, days=30):
    root = root or os.path.expanduser("~/.claude/projects")
    sessions = mt.collect(root, days)
    sm = mt.summarize(sessions) or {}
    mt_skip = mt.skip_counts()

    cutoff = time.time() - days * 86400
    effort_values, gaps, files_scanned, raw_skip_files, raw_skip_lines = _raw_scan(root, cutoff)

    n_sessions = sm.get("sessions")
    window_note = f"measure_tokens.summarize() over the {days:g}-day window"

    def usage_metric(key):
        v = sm.get(key)
        return metric(v, "NO DATA" if v is None else "MEASURED",
                      f"{key} from {window_note}")

    usage = {
        "first_request_median_tokens": usage_metric("first_request_median"),
        "cache_hit_ratio_median": usage_metric("hit_ratio_median"),
        "output_tokens_total": usage_metric("output_total"),
        "subagent_output_share": usage_metric("subagent_output_share"),
        "cache_write_5m_tokens": usage_metric("write_5m_total"),
        "cache_write_1h_tokens": usage_metric("write_1h_total"),
    }

    switch_share = _model_switch_share(sessions)
    idle_shares = _idle_gap_shares(gaps)
    sub_share = (sm["subagent_transcripts"] / sm["sessions"]) if sm.get("sessions") else None

    behavior = {
        "sessions": (metric(n_sessions, "MEASURED", f"parent-plus-subagent transcript count from {window_note}")
                     if n_sessions else no_data("no session transcripts found in window")),
        "model_switch_session_share": (
            no_data("no parent sessions in window") if switch_share is None else
            metric(switch_share, "MEASURED",
                   "share of parent sessions whose assistant records carried 2+ "
                   "distinct message.model values, from measure_tokens per-session "
                   "model counts")),
        "effort_values_seen": (
            metric(sorted(effort_values, key=str), "MEASURED",
                   f"distinct top-level effort field values across {files_scanned} "
                   f"scanned transcripts")
            if files_scanned else no_data("no transcript files found in window")),
        "idle_gap_shares": (
            no_data("no consecutive same-session timestamp pairs under 12h found")
            if idle_shares is None else
            metric(idle_shares, "SIGNAL",
                   "gaps between consecutive message timestamps within a session, "
                   "bucketed under 5m / 5-15m / 15-60m / over 60m; gaps over 12h "
                   "dropped as day boundaries")),
        "subagent_transcript_share": (
            no_data("no transcripts found in window") if sub_share is None else
            metric(sub_share, "MEASURED",
                   "subagent_transcripts / sessions from measure_tokens.summarize()")),
    }

    user_claude_md = os.path.expanduser("~/.claude/CLAUDE.md")
    project_claude_md = os.path.join(os.getcwd(), "CLAUDE.md")
    memory_index = cl.expected_memory_index_path()
    floor_share = sm.get("first_request_share_median")

    instruction = {
        "claude_md_user_bytes": _file_metric(user_claude_md, "user CLAUDE.md"),
        "claude_md_project_bytes": _file_metric(project_claude_md, "project CLAUDE.md"),
        "startup_floor_share": (
            no_data("first_request_share_median not available") if floor_share is None else
            metric(floor_share, "MEASURED", f"first_request_share_median from {window_note}")),
        "memory_index_bytes": _file_metric(memory_index, "project auto-memory index, "
                                            "located via context_lint's slug logic"),
    }

    plugin_cache_root = os.path.expanduser("~/.claude/plugins/cache")
    plugin_count = _plugin_count(plugin_cache_root)
    ttl_regime = _ttl_regime(sm)

    environment = {
        "plugin_count": (
            no_data(f"no plugin cache directory at {plugin_cache_root}") if plugin_count is None else
            metric(plugin_count, "INFERRED",
                   f"count of directories two levels under {plugin_cache_root} on this "
                   f"machine right now; not portable to another install")),
        "ttl_regime": (
            no_data("no cache writes in window") if ttl_regime is None else
            metric(ttl_regime, "INFERRED",
                   "derived from the cache_write_5m_tokens vs cache_write_1h_tokens "
                   "split in usage: whichever class holds 60% or more of writes wins, "
                   "otherwise mixed")),
    }

    skipped = {
        "files": metric(mt_skip["files"] + raw_skip_files, "MEASURED",
                         "unreadable files across the usage walk plus the behavior scan"),
        "lines": metric(mt_skip["lines"] + raw_skip_lines, "MEASURED",
                         "lines that failed JSON decoding across the usage walk plus "
                         "the behavior scan"),
    }

    return {
        "schema": SCHEMA,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "window_days": days,
        "usage": usage,
        "behavior": behavior,
        "instruction": instruction,
        "environment": environment,
        "skipped": skipped,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--root", default=os.path.expanduser("~/.claude/projects"))
    ap.add_argument("--days", type=float, default=30)
    ap.add_argument("--out", default=os.path.expanduser("~/.token-shield/profile.json"))
    a = ap.parse_args()

    if not os.path.isdir(a.root) or next(mt.iter_session_files(a.root, 0), None) is None:
        print("NO DATA: no transcripts found.", file=sys.stderr)
        return 2

    prof = build_profile(a.root, a.days)

    out_dir = os.path.dirname(a.out)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(a.out, "w") as f:
        json.dump(prof, f, indent=2)

    u, b, i, sk = prof["usage"], prof["behavior"], prof["instruction"], prof["skipped"]
    print(f"profile written: {a.out}")
    print(f"sessions in window: {mt.fmt(b['sessions']['value'])} over {a.days:g} days")
    print(f"first-request floor: {mt.fmt(u['first_request_median_tokens']['value'])} tokens "
          f"median, {mt.fmt(i['startup_floor_share']['value'])} share of everything read")
    print(f"cache hit ratio median: {mt.fmt(u['cache_hit_ratio_median']['value'])}")
    print(f"model switches mid-session: {mt.fmt(b['model_switch_session_share']['value'])} "
          f"of sessions")
    print(f"skipped while reading: {mt.fmt(sk['files']['value'])} files, "
          f"{mt.fmt(sk['lines']['value'])} lines")
    return 0


if __name__ == "__main__":
    sys.exit(main())
