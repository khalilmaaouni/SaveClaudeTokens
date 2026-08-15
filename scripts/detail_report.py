#!/usr/bin/env python3
"""
detail_report.py: the Consumption Report. Schema v1.

WHY A SEPARATE MODULE AND NOT A BIGGER profile.py
profile.py answers "what should I change." This module answers "where do my
tokens go, which habits cost me, and what should change," served as one
versioned JSON object three ways (an MCP tool, a dashboard Habits section, a
documented external schema). See
docs/superpowers/specs/2026-08-13-consumption-report-design.md.

It computes the full report from the same transcript data profile.py and
measure_tokens.py already read. No new data collection, no new hooks, zero
always-on cost. It composes existing functions; the only genuinely new logic
is day/hour/weekday bucketing of collect()'s per-session `started`
timestamps, which no existing function does.

SCHEMA v1
Every number in every section is an object {"value", "label", "source"}
where label is one of VERIFIED, MEASURED, INFERRED, ESTIMATED, NATIVE, or
NO DATA (per the spec's schema text). This is a deliberate naming split from
profile.py's own metric() helper, which names the same kind of field
"basis": detail_report.py's schema is the contract external MCP clients
build against, and the spec names the field "source". Labels never blend:
a sum across labels is a misuse of the data, so this module never adds a
VERIFIED number to a MEASURED one, or an ESTIMATED one to a NATIVE one.

Missing data is reported as no_data(...), a local NO DATA leaf, never a
guess and never a silent zero.

USAGE
  python3 detail_report.py                 # print schema v1 as JSON
  python3 detail_report.py --days 7
"""

import argparse
import datetime
import json
import os
import statistics
import sys

import context_lint as cl
import experiment as ex
import measure_tokens as mt
import profile as pf
import token_shield as ts

import metrics as met
SCHEMA = 1
SOURCE_LABEL = "claude-code-transcripts"

# Thresholds below are not invented here: each is copied from an existing,
# already-shipped trigger so a habit finding never introduces a new guess.
# - MODEL_SWITCH_SHARE_TRIGGER: data/strategies.json cache.fixed-parent-model
# - STARTUP_FLOOR_SHARE_TRIGGER: data/strategies.json startup.floor-ladder
# - CACHE_HIT_RATIO_TRIGGER: data/strategies.json memory.fresh-over-compact
# - SUBAGENT_OUTPUT_SHARE_TRIGGER: measure_tokens.dominant_lever's own
#   "route" threshold
MODEL_SWITCH_SHARE_TRIGGER = 0.2
STARTUP_FLOOR_SHARE_TRIGGER = 0.15
CACHE_HIT_RATIO_TRIGGER = 0.5
SUBAGENT_OUTPUT_SHARE_TRIGGER = 0.40

# Same filter token_shield.pain_points uses to flag a "rebuilt" session; kept
# as named constants here (rather than re-deriving pain_points' own filtered
# list, which that function does not expose) so the two never drift apart
# silently. pain_points() itself is still the source of rebuild_n/share.
REBUILD_REWRITE_RATIO = 0.15
REBUILD_MIN_CALLS = 10


def metric(value, label, source):
    return {"value": value, "label": label, "source": source}


def no_data(source):
    return metric(None, "NO DATA", source)


def _leaf_from_profile(prof_leaf, source_suffix=""):
    """Convert a profile.py {value,label,basis} leaf into this module's
    {value,label,source} shape, per design decision 3: reuse the VALUE and
    LABEL profile.py already computed, rename the field, never recompute."""
    if prof_leaf is None:
        return no_data("not present in profile.build_profile output" + source_suffix)
    return metric(prof_leaf["value"], prof_leaf["label"],
                  (prof_leaf.get("basis") or "profile.build_profile") + source_suffix)


def _median(values):
    return statistics.median(values) if values else None


def _bucket_by_day(sessions):
    """Group parent sessions by calendar day (UTC) of their `started`
    timestamp. Subagent-only transcripts never set `started` (measure_tokens
    read_session only sets it on a parent call, see measure_tokens.py:211-215)
    and are skipped here rather than crashing or zero-filling into day one.
    Returns {date_str: [session, ...]}, oldest day first.
    """
    from collections import defaultdict
    buckets = defaultdict(list)
    for s in sessions:
        raw_ts = s.get("started")
        if not raw_ts:
            continue
        epoch = ex._parse_ts(raw_ts)
        if epoch is None:
            continue
        day = datetime.datetime.fromtimestamp(epoch, tz=datetime.timezone.utc).strftime("%Y-%m-%d")
        buckets[day].append(s)
    return dict(sorted(buckets.items()))


def _top_contributors(n=5):
    """Top always-loaded files by loaded_bytes, as reported by
    context_lint.py. Never edits, only measures; a missing target is skipped,
    not fabricated."""
    rows = []
    for path, is_mem in cl.default_targets(all_memory=False):
        if path is None:
            continue
        _findings, stats = cl.check(path, is_mem)
        if stats is None:
            continue
        rows.append({"path": path, "loaded_bytes": stats["loaded_bytes"],
                     "loaded_lines": stats["loaded_lines"]})
    rows.sort(key=lambda r: -r["loaded_bytes"])
    return rows[:n]


def _startup_floor(sm, prof, window_days):
    projected = None
    if sm.get("normalized_input_total") is not None and sm.get("normalized_sessions"):
        projected = sm["normalized_input_total"] / sm["normalized_sessions"]
    contributors = _top_contributors()
    return {
        "median_tokens": metric(sm.get("first_request_median"),
                                 "NO DATA" if sm.get("first_request_median") is None else "MEASURED",
                                 "measure_tokens.summarize: first_request_median"),
        "mean_tokens": metric(sm.get("first_request_mean"),
                               "NO DATA" if sm.get("first_request_mean") is None else "MEASURED",
                               "measure_tokens.summarize: first_request_mean"),
        "p90_tokens": metric(sm.get("first_request_p90"),
                              "NO DATA" if sm.get("first_request_p90") is None else "MEASURED",
                              "measure_tokens.summarize: first_request_p90"),
        "share_of_total_spend": _leaf_from_profile(
            prof.get("instruction", {}).get("startup_floor_share")),
        "projected_per_session_cost": metric(
            projected, "NO DATA" if projected is None else "MEASURED",
            "measure_tokens.summarize: normalized_input_total / normalized_sessions"),
        "top_contributors": metric(
            contributors if contributors else None,
            "NO DATA" if not contributors else "MEASURED",
            "context_lint.default_targets + context_lint.check, ranked by loaded_bytes"),
    }


def _subagents(sm, sessions, window_days):
    parent = [s for s in sessions if s["first_request"] > 0]
    fan_out_n = sum(1 for s in parent if s.get("sub_calls"))
    total_out = sm.get("subagent_output_total")
    fan_out_cost_per_day = (total_out / window_days) if total_out is not None and window_days else None
    return {
        "output_share": metric(sm.get("subagent_output_share"),
                                "NO DATA" if sm.get("subagent_output_share") is None else "MEASURED",
                                "measure_tokens.summarize: subagent_output_share"),
        "call_counts": metric(sm.get("subagent_calls"),
                               "NO DATA" if sm.get("subagent_calls") is None else "MEASURED",
                               "measure_tokens.summarize: subagent_calls"),
        "sessions_that_fan_out": metric(
            fan_out_n if parent else None, "NO DATA" if not parent else "MEASURED",
            "count of parent sessions in the window whose sub_calls > 0, "
            "from measure_tokens.collect"),
        "fan_out_cost_per_day": metric(
            fan_out_cost_per_day, "NO DATA" if fan_out_cost_per_day is None else "MEASURED",
            "measure_tokens.summarize: subagent_output_total / window_days"),
    }


def _cache(sm, sessions, window_days):
    by_day = _bucket_by_day([s for s in sessions if s["calls"] >= 3])
    days = list(by_day.keys())
    trend = None
    if len(days) >= 2:
        half = len(days) // 2 or 1
        first_half_ratios = [s["hit_ratio"] for d in days[:half] for s in by_day[d]]
        second_half_ratios = [s["hit_ratio"] for d in days[half:] for s in by_day[d]]
        fm, sm2 = _median(first_half_ratios), _median(second_half_ratios)
        if fm is not None and sm2 is not None:
            trend = sm2 - fm

    parent = [s for s in sessions if s["first_request"] > 0]
    pp = met.pain_points(sessions) if parent else None
    rebuilt = [s for s in parent
               if s["rewrite_ratio"] and s["rewrite_ratio"] > REBUILD_REWRITE_RATIO
               and s["calls"] >= REBUILD_MIN_CALLS]
    premium = sum(0.25 * s["write_5m"] + 1.0 * s["write_1h"] for s in rebuilt)
    cost_per_rebuild = (premium / len(rebuilt)) if rebuilt else None

    return {
        "hit_ratio_median": metric(sm.get("hit_ratio_median"),
                                    "NO DATA" if sm.get("hit_ratio_median") is None else "MEASURED",
                                    "measure_tokens.summarize: hit_ratio_median"),
        "hit_ratio_trend": metric(
            trend, "NO DATA" if trend is None else "MEASURED",
            "median session hit_ratio, second half of the window's active days "
            "minus first half, from measure_tokens per-session data"),
        "rebuild_events": metric(
            pp["rebuild_n"] if pp else None, "NO DATA" if not pp else "MEASURED",
            f"token_shield.pain_points: sessions with rewrite_ratio > "
            f"{REBUILD_REWRITE_RATIO} and calls >= {REBUILD_MIN_CALLS}"),
        "cost_per_rebuild": metric(
            cost_per_rebuild, "NO DATA" if cost_per_rebuild is None else "MEASURED",
            "cache write premium (0.25x per 5m-write token, 1.0x per 1h-write "
            "token) summed over the same rebuilt sessions, divided by their count"),
        "write_5m_tokens": metric(sm.get("write_5m_total"),
                                   "NO DATA" if sm.get("write_5m_total") is None else "MEASURED",
                                   "measure_tokens.summarize: write_5m_total"),
        "write_1h_tokens": metric(sm.get("write_1h_total"),
                                   "NO DATA" if sm.get("write_1h_total") is None else "MEASURED",
                                   "measure_tokens.summarize: write_1h_total"),
        "write_1h_share": metric(sm.get("write_1h_share"),
                                  "NO DATA" if sm.get("write_1h_share") is None else "MEASURED",
                                  "measure_tokens.summarize: write_1h_share"),
    }


def _rhythm(sm, sessions, window_days):
    parent = [s for s in sessions if s["first_request"] > 0]
    # No parent sessions is NO DATA, not a measured zero: mirrors
    # profile.build_profile's own "sessions" leaf (profile.py's
    # `if n_sessions else no_data(...)`), which treats an empty window the
    # same way rather than reporting a computed 0.0 rate.
    sessions_per_day = (len(parent) / window_days) if parent and window_days else None

    by_hour, by_weekday = {}, {}
    for s in parent:
        epoch = ex._parse_ts(s.get("started")) if s.get("started") else None
        if epoch is None:
            continue
        dt = datetime.datetime.fromtimestamp(epoch, tz=datetime.timezone.utc)
        by_hour[dt.hour] = by_hour.get(dt.hour, 0) + (s.get("raw_input") or 0)
        by_weekday[dt.weekday()] = by_weekday.get(dt.weekday(), 0) + (s.get("raw_input") or 0)

    tail_cost = None
    if parent:
        by_calls = sorted(parent, key=lambda s: -s["calls"])
        tail_n = max(1, len(by_calls) // 10)
        tail_cost = sum(s.get("raw_input") or 0 for s in by_calls[:tail_n])

    return {
        "sessions_per_day": metric(
            sessions_per_day, "NO DATA" if sessions_per_day is None else "MEASURED",
            "measure_tokens.summarize: parent_sessions / window_days"),
        "spend_by_hour_utc": metric(
            by_hour or None, "NO DATA" if not by_hour else "MEASURED",
            "raw_input summed per UTC hour-of-day of each parent session's "
            "started timestamp"),
        "spend_by_weekday": metric(
            by_weekday or None, "NO DATA" if not by_weekday else "MEASURED",
            "raw_input summed per UTC weekday (0=Monday) of each parent "
            "session's started timestamp"),
        "long_session_tail_cost": metric(
            tail_cost, "NO DATA" if tail_cost is None else "MEASURED",
            "raw_input summed over the top decile of sessions by call count"),
        "compaction_events": no_data(
            "no compaction-event counter exists in scripts/ yet; auto-compact "
            "turns are not distinguishable from other assistant turns in the "
            "current transcript schema"),
    }


def _habits(sm, sessions, prof):
    """Named findings, MEASURED confidence only in v1: every trigger here is
    copied from an already-shipped strategies.json trigger or an existing
    dominant_lever threshold, never a new heuristic invented for this report.
    """
    out = []
    switch_leaf = prof.get("behavior", {}).get("model_switch_session_share")
    if switch_leaf and switch_leaf.get("value") is not None and \
            switch_leaf["value"] >= MODEL_SWITCH_SHARE_TRIGGER:
        out.append({
            "what": f"{switch_leaf['value']:.0%} of your sessions ran more than one model",
            "why_it_matters": {"value": switch_leaf["value"], "label": "MEASURED",
                                "source": "profile.build_profile: behavior.model_switch_session_share"},
            "action": "Pick a model and effort once at session start; route a "
                      "cheaper sub-task to a subagent instead of switching the parent model.",
            "confidence": "MEASURED",
        })

    floor_leaf = prof.get("instruction", {}).get("startup_floor_share")
    if floor_leaf and floor_leaf.get("value") is not None and \
            floor_leaf["value"] >= STARTUP_FLOOR_SHARE_TRIGGER:
        out.append({
            "what": f"the always-loaded startup floor is {floor_leaf['value']:.0%} "
                    f"of everything your sessions read",
            "why_it_matters": {"value": floor_leaf["value"], "label": "MEASURED",
                                "source": "profile.build_profile: instruction.startup_floor_share"},
            "action": "Run context_lint.py, then diet CLAUDE.md and prune unused "
                      "plugins and MCP servers.",
            "confidence": "MEASURED",
        })

    hit = sm.get("hit_ratio_median")
    if hit is not None and hit <= CACHE_HIT_RATIO_TRIGGER:
        out.append({
            "what": f"your median cache hit ratio is {hit:.2f}",
            "why_it_matters": {"value": hit, "label": "MEASURED",
                                "source": "measure_tokens.summarize: hit_ratio_median"},
            "action": "Look for model or effort switches, idle gaps past the "
                      "cache TTL, or a toolset change mid-session.",
            "confidence": "MEASURED",
        })

    sub = sm.get("subagent_output_share")
    if sub is not None and sub >= SUBAGENT_OUTPUT_SHARE_TRIGGER:
        out.append({
            "what": f"subagents produced {sub:.0%} of your output",
            "why_it_matters": {"value": sub, "label": "MEASURED",
                                "source": "measure_tokens.summarize: subagent_output_share"},
            "action": "Check whether that fan-out is isolating real exploration "
                      "or doing work a script should have done.",
            "confidence": "MEASURED",
        })

    parent = [s for s in sessions if s["first_request"] > 0]
    pp = met.pain_points(sessions) if parent else None
    if pp and pp["rebuild_n"] > 0:
        out.append({
            "what": f"{pp['rebuild_n']} of your sessions show a cache rebuild signal "
                    f"(rewrite ratio over {REBUILD_REWRITE_RATIO} across {REBUILD_MIN_CALLS}+ calls)",
            "why_it_matters": {"value": pp["rebuild_n"], "label": "MEASURED",
                                "source": "token_shield.pain_points: rebuild_n"},
            "action": "Check those sessions for a model switch, an idle gap past "
                      "the cache TTL, or a mid-session toolset change.",
            "confidence": "MEASURED",
        })

    return out


def _daily_series(sessions, window_days):
    by_day = _bucket_by_day([s for s in sessions if s["first_request"] > 0])
    rows = []
    for day, day_sessions in by_day.items():
        hit_vals = [s["hit_ratio"] for s in day_sessions if s["calls"] >= 3]
        rows.append({
            "date": day,
            "sessions": metric(len(day_sessions), "MEASURED",
                               "count of parent sessions started on this day"),
            "raw_input": metric(sum(s.get("raw_input") or 0 for s in day_sessions),
                                "MEASURED", "raw_input summed over this day's sessions"),
            "output": metric(sum(s.get("output") or 0 for s in day_sessions),
                             "MEASURED", "output summed over this day's sessions"),
            "hit_ratio_median": metric(_median(hit_vals),
                                       "NO DATA" if not hit_vals else "MEASURED",
                                       "median hit_ratio over this day's sessions with 3+ calls"),
        })
    # Bounded on purpose: never more than window_days rows, even if a resumed
    # transcript's started timestamp lands outside the collect() cutoff window
    # in a way that produces more distinct day buckets than the window itself.
    cap = max(1, int(round(window_days))) if window_days else len(rows)
    return rows[-cap:]


def build_detail_report(root=None, window_days=30):
    """Pure function of disk state: no printing, no writing, so it stays
    directly testable. Composes measure_tokens, profile, context_lint, and
    token_shield; the only new logic is the day/hour/weekday bucketing this
    module needs and nothing existing already provides."""
    root = root or os.path.expanduser("~/.claude/projects")
    sessions = mt.collect(root, window_days)
    sm = mt.summarize(sessions) or {}
    prof = pf.build_profile(root, window_days)

    return {
        "report_schema": SCHEMA,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "window_days": window_days,
        "source_label": SOURCE_LABEL,
        "startup_floor": _startup_floor(sm, prof, window_days),
        "subagents": _subagents(sm, sessions, window_days),
        "cache": _cache(sm, sessions, window_days),
        "rhythm": _rhythm(sm, sessions, window_days),
        "habits": _habits(sm, sessions, prof),
        "daily_series": _daily_series(sessions, window_days),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--root", default=os.path.expanduser("~/.claude/projects"))
    ap.add_argument("--days", type=float, default=30)
    a = ap.parse_args()

    if not os.path.isdir(a.root):
        print(f"NO DATA: {a.root} does not exist.", file=sys.stderr)
        return 2

    report = build_detail_report(a.root, a.days)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
