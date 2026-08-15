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
script never reimplements input/output/cache arithmetic. What it adds is
further, lighter passes over the same transcript files for signals the
counter math does not carry: the top-level effort field, message timestamps
for idle gaps, file-system facts about CLAUDE.md, the auto-memory index, the
installed plugin count, and transcript-pressure signals (tool_result byte
share by tool, duplicate tool calls, assistant output verbosity, and the
structured-versus-typed split of user turns).

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
import math
import os
import statistics
import sys
import time

import measure_tokens as mt
import context_lint as cl

SCHEMA = 1

IDLE_BUCKETS = ("under_5m", "5m_to_15m", "15m_to_60m", "over_60m")

# The only effort values this profile will ever name. The top-level `effort`
# field is arbitrary text from outside this tool, and copying it verbatim into
# profile.json would break the "counters and byte sizes only" promise at the
# top of this file: one unexpected string in a transcript would be persisted
# to disk and rendered on the dashboard. Anything outside the whitelist is
# counted as "other" and the raw string is never stored.
EFFORT_VALUES = ("low", "medium", "high", "xhigh", "max")
EFFORT_OTHER = "other"


def effort_bucket(raw):
    """Whitelist one raw `effort` field value. Returns a known effort name or
    EFFORT_OTHER; never returns caller-supplied text."""
    return raw if raw in EFFORT_VALUES else EFFORT_OTHER


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
                    effort_values.add(effort_bucket(eff))
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


def _model_switch_volume_share(sessions):
    """Same switch detection as _model_switch_share, weighted by each
    session's own token volume (raw_input, already computed by
    measure_tokens.read_session) instead of counting sessions equally.

    docs/WASTE-SCORE.md finding C1.B (hostile review, fix round 2): a plain
    session count lets a machine dilute a genuine switcher's share for free
    by padding on many small, unswitched sessions, since every session
    counts the same regardless of size. Weighting by raw_input means a
    padded session only moves the number as much as the real tokens it
    actually spent, so sixteen near-empty sessions barely move it while
    sixteen sessions the size of the real ones would."""
    parent = [s for s in sessions if s["first_request"] > 0]
    total = sum(s.get("raw_input") or 0 for s in parent)
    if total == 0:
        return None
    switched = sum(s.get("raw_input") or 0 for s in parent if s["models"] >= 2)
    return switched / total


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


def _tool_result_bytes(content):
    """Byte size of one tool_result block's content. content is a plain
    string in most transcripts, or a list of content blocks (usually
    {"type": "text", "text": ...}) in others. Anything else contributes 0
    rather than raising, since this is a byte-counting pass, not a parser."""
    if isinstance(content, str):
        return len(content.encode("utf-8", "ignore"))
    if isinstance(content, list):
        total = 0
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                total += len(item["text"].encode("utf-8", "ignore"))
        return total
    return 0


def _pressure_scan(root, cutoff):
    """A third pass over the same transcript files, for transcript-pressure
    signals: how much of the transcript is tool output, whether tool calls
    repeat verbatim, how bursty assistant output is, and how much of a user
    turn is machine-generated tool_result versus a human-typed message.

    Each session file is read into memory once and walked twice: first to
    map tool_use id -> tool name and count exact repeats (same name and
    identical input JSON) within that one file, then to attribute
    tool_result bytes to a tool name and to split user-message bytes into
    tool_result versus human-typed text. Counting `*_total` alongside the
    aggregates below is what lets the caller tell "measured zero" apart from
    "no such field in this transcript" (NO DATA).
    """
    tool_result_bytes = {}
    total_bytes = 0
    tool_use_total = 0
    tool_result_total = 0
    bash_call_total = 0
    dup_calls = {}
    output_tokens = []
    structured_bytes = 0
    human_text_bytes = 0
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

        records = []
        with f:
            for line in f:
                if not line.strip():
                    continue
                total_bytes += len(line.encode("utf-8", "ignore"))
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    skipped_lines += 1

        # Pass 1: tool_use id -> tool name, and exact-repeat counts (same
        # name and identical input JSON) within this one session file.
        tool_names = {}
        seen_calls = {}
        for rec in records:
            msg = rec.get("message")
            content = msg.get("content") if isinstance(msg, dict) else None
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                tool_use_total += 1
                name = block.get("name")
                tool_id = block.get("id")
                if isinstance(tool_id, str) and isinstance(name, str):
                    tool_names[tool_id] = name
                if not isinstance(name, str):
                    continue
                if name == "Bash":
                    bash_call_total += 1
                try:
                    key = (name, json.dumps(block.get("input"), sort_keys=True))
                except TypeError:
                    continue
                seen_calls[key] = seen_calls.get(key, 0) + 1

        for (name, _input_json), count in seen_calls.items():
            if count > 1:
                dup_calls[name] = dup_calls.get(name, 0) + (count - 1)

        # Pass 2: tool_result bytes attributed by tool name, assistant
        # output_tokens per message, and the user-message structured-vs-human
        # byte split.
        for rec in records:
            rtype = rec.get("type")
            msg = rec.get("message")
            if not isinstance(msg, dict):
                continue

            if rtype == "assistant":
                usage = msg.get("usage")
                out = usage.get("output_tokens") if isinstance(usage, dict) else None
                if isinstance(out, int):
                    output_tokens.append(out)

            if rtype == "user":
                content = msg.get("content")
                if isinstance(content, str):
                    human_text_bytes += len(content.encode("utf-8", "ignore"))
                elif isinstance(content, list):
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        btype = block.get("type")
                        if btype == "tool_result":
                            tool_result_total += 1
                            b = _tool_result_bytes(block.get("content"))
                            structured_bytes += b
                            name = tool_names.get(block.get("tool_use_id"), "unknown")
                            tool_result_bytes[name] = tool_result_bytes.get(name, 0) + b
                        elif btype == "text":
                            text = block.get("text")
                            if isinstance(text, str):
                                human_text_bytes += len(text.encode("utf-8", "ignore"))

    return {
        "tool_result_bytes": tool_result_bytes,
        "total_bytes": total_bytes,
        "tool_use_total": tool_use_total,
        "tool_result_total": tool_result_total,
        "bash_call_total": bash_call_total,
        "dup_calls": dup_calls,
        "output_tokens": output_tokens,
        "structured_bytes": structured_bytes,
        "human_text_bytes": human_text_bytes,
        "files_scanned": files_scanned,
        "skipped_files": skipped_files,
        "skipped_lines": skipped_lines,
    }


def _output_verbosity(output_tokens):
    if not output_tokens:
        return None
    vals = sorted(output_tokens)
    n = len(vals)
    over_1000 = sum(1 for v in vals if v > 1000)
    return {
        "median_output_tokens": statistics.median(vals),
        # p90 needs a real tail to mean anything; below 10 samples it stays
        # unset rather than reading one arbitrary record as "the 90th
        # percentile", matching measure_tokens.summarize()'s first_request_p90.
        "p90_output_tokens": vals[int(n * 0.9)] if n >= 10 else None,
        "over_1000_tokens_share": over_1000 / n,
        "n_assistant_messages": n,
    }


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
    switch_volume_share = _model_switch_volume_share(sessions)
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
        "model_switch_volume_share": (
            no_data("no parent sessions with measured token volume in window")
            if switch_volume_share is None else
            metric(switch_volume_share, "MEASURED",
                   "same switch detection as model_switch_session_share, weighted by "
                   "each parent session's own raw_input (measure_tokens.read_session's "
                   "total token volume) instead of counting every session equally; "
                   "used instead of model_switch_session_share by the waste score "
                   "(docs/WASTE-SCORE.md) so padding on many small unswitched sessions "
                   "cannot dilute a genuine switcher's share for free")),
        "effort_values_seen": (
            metric(sorted(effort_values, key=str), "MEASURED",
                   f"distinct top-level effort field values across {files_scanned} "
                   f"scanned transcripts, whitelisted to "
                   f"{', '.join(EFFORT_VALUES)}; anything else counts as "
                   f"{EFFORT_OTHER} and its raw text is never stored")
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

    pa = _pressure_scan(root, cutoff)

    tool_share = ({name: b / pa["total_bytes"] for name, b in sorted(pa["tool_result_bytes"].items())}
                  if pa["tool_result_total"] and pa["total_bytes"] else None)
    verbosity = _output_verbosity(pa["output_tokens"])
    structured_denom = pa["structured_bytes"] + pa["human_text_bytes"]

    pressure = {
        "tool_output_share_by_tool": (
            no_data("no tool_result blocks found in window") if tool_share is None else
            metric(tool_share, "MEASURED",
                   "per tool, share of transcript bytes (sum of raw JSONL line "
                   "bytes across scanned transcripts) that were tool_result "
                   "content, attributed by matching tool_result.tool_use_id "
                   "to the name on the earlier tool_use block")),
        "duplicate_reads": (
            no_data("no tool_use blocks found in window") if pa["tool_use_total"] == 0 else
            metric(dict(sorted(pa["dup_calls"].items())), "MEASURED",
                   "per tool, count of tool_use calls beyond the first with "
                   "the exact same name and identical input JSON, within one "
                   "session transcript file")),
        "duplicate_commands": (
            no_data("no Bash tool_use calls found in window") if pa["bash_call_total"] == 0 else
            metric(pa["dup_calls"].get("Bash", 0), "MEASURED",
                   "duplicate_reads narrowed to the Bash tool: count of Bash "
                   "calls beyond the first with identical input JSON, within "
                   "one session transcript file")),
        "output_verbosity": (
            no_data("no assistant messages with usage.output_tokens found in window")
            if verbosity is None else
            metric(verbosity, "MEASURED",
                   "distribution of usage.output_tokens per assistant message "
                   "across scanned transcripts: median, p90 (needs 10+ "
                   "messages, else null), and the share of messages over "
                   "1000 output tokens")),
        "structured_input_share": (
            no_data("no user-message tool_result or text bytes found in window")
            if structured_denom == 0 else
            metric(pa["structured_bytes"] / structured_denom, "MEASURED",
                   "share of user-message bytes (tool_result content plus "
                   "human-typed text blocks) that were tool_result content, "
                   "i.e. machine-generated rather than typed by a person")),
        "tool_result_avg_bytes": (
            no_data("no tool_result blocks found in window") if pa["tool_result_total"] == 0 else
            metric(pa["structured_bytes"] / pa["tool_result_total"], "MEASURED",
                   "average bytes per tool_result block: structured_bytes (sum of "
                   "tool_result content bytes, the same numerator structured_input_share "
                   "uses) divided by tool_result_total; used instead of "
                   "structured_input_share by the waste score (docs/WASTE-SCORE.md) "
                   "because it does not move when a person pastes more human-typed "
                   "text into the conversation, only when the tool output itself "
                   "gets bigger")),
    }

    skipped = {
        "files": metric(mt_skip["files"] + raw_skip_files + pa["skipped_files"], "MEASURED",
                         "unreadable files across the usage walk, the behavior scan, "
                         "and the pressure scan"),
        "lines": metric(mt_skip["lines"] + raw_skip_lines + pa["skipped_lines"], "MEASURED",
                         "lines that failed JSON decoding across the usage walk, "
                         "the behavior scan, and the pressure scan"),
    }

    return {
        "schema": SCHEMA,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "window_days": days,
        "usage": usage,
        "behavior": behavior,
        "instruction": instruction,
        "environment": environment,
        "pressure": pressure,
        "skipped": skipped,
    }


# WASTE SCORE (docs/WASTE-SCORE.md)
# ----------------------------------
# One 0-100 number: how much measurable waste a machine's Claude Code usage
# carries. The formula, the anchors, the bands and the all-or-nothing rule
# are all ratified and published in docs/WASTE-SCORE.md; this is only the
# implementation of that already-published spec. Do not change an anchor,
# a weight or the rounding rule here without bumping WASTE_SCORE_VERSION
# and updating that document first: a score is only comparable between
# machines when it was computed the same way, and the version string is
# how a later change can never be compared silently against an older one.
#
# waste-score/2 (fix round 2, docs/WASTE-SCORE.md "Version history"): a
# hostile review found three ways to raise the score by strictly adding
# tokens (pasting human text, farming trivial sessions, appending filler
# messages) plus two soundness holes (no sample floor, no guard on a
# non-finite or out-of-domain input). Components 3-5 changed metric; a
# sample floor and a finite/domain guard were added. See the doc's "How
# this score can be gamed" section for what changed and what is still open.
WASTE_SCORE_VERSION = "waste-score/2"

# Below this many sessions, or this many assistant messages with a measured
# output_tokens, the whole score is NO DATA rather than a number computed on
# too thin a sample to mean anything (docs/WASTE-SCORE.md's sample floor).
WASTE_SCORE_MIN_SESSIONS = 10
WASTE_SCORE_MIN_ASSISTANT_MESSAGES = 10

# name, problem_class, weight, profile group, profile key, good anchor (no
# penalty), bad anchor (full penalty), the plausible domain (min, max) a
# MEASURED value must fall inside before it is trusted (max of None means
# no upper bound), and how to pull the scalar metric out of that leaf's
# "value" (identity for every metric except output_verbosity, whose leaf
# value is the {"p90_output_tokens": ..., ...} dict that
# _output_verbosity() builds).
_WASTE_COMPONENTS = (
    {"name": "cache_hit_ratio", "problem_class": "cache_health", "weight": 30,
     "group": "usage", "key": "cache_hit_ratio_median", "good": 0.90, "bad": 0.50,
     "domain": (0.0, 1.0), "extract": lambda v: v},
    {"name": "startup_floor", "problem_class": "startup_rent", "weight": 25,
     "group": "instruction", "key": "startup_floor_share", "good": 0.15, "bad": 0.45,
     "domain": (0.0, 1.0), "extract": lambda v: v},
    {"name": "model_switch", "problem_class": "cache_health", "weight": 20,
     "group": "behavior", "key": "model_switch_volume_share", "good": 0.05, "bad": 0.35,
     "domain": (0.0, 1.0), "extract": lambda v: v},
    {"name": "tool_result_avg_bytes", "problem_class": "tool_output", "weight": 15,
     "group": "pressure", "key": "tool_result_avg_bytes", "good": 2000, "bad": 20000,
     "domain": (0.0, None), "extract": lambda v: v},
    {"name": "output_verbosity", "problem_class": "verbosity", "weight": 10,
     "group": "pressure", "key": "output_verbosity", "good": 800, "bad": 2500,
     "domain": (0.0, None), "extract": lambda v: v.get("p90_output_tokens") if isinstance(v, dict) else None},
)

WASTE_BANDS = (
    (90, "LEAN"),
    (70, "OK"),
    (50, "WASTEFUL"),
)


def _linear_penalty(value, good, bad, weight):
    """Straight-line penalty between two anchors: 0 at `good`, `weight` at
    `bad`, linear in between, clamped to [0, weight] past either anchor.
    `good` may be larger or smaller than `bad` (cache_hit_ratio runs
    backward: higher is better); the fraction-of-the-way formula does not
    care which direction the anchors point."""
    frac = (value - good) / (bad - good)
    frac = max(0.0, min(1.0, frac))
    return weight * frac


def _round_half_up(x, ndigits=1):
    """Round half up (0.05 -> 0.1, never banker's-rounded down to 0.0).
    Waste scores are always >= 0, so a plain floor-based half-up is exact;
    this is not a general-purpose rounder for negative numbers."""
    factor = 10 ** ndigits
    return math.floor(x * factor + 0.5) / factor


def _waste_band(score):
    for floor, name in WASTE_BANDS:
        if score >= floor:
            return name
    return "HEAVY WASTE"


def _waste_sample_counts(profile):
    """(n_sessions, n_assistant_messages) for the sample floor, read from
    leaves build_profile already computes: behavior.sessions, and
    pressure.output_verbosity's own n_assistant_messages count. Either
    leaf being NO DATA (or absent) reads as 0, not as "unknown": the floor
    exists to refuse a too-thin sample, and a metric that could not even be
    measured is the thinnest sample of all."""
    sessions_leaf = profile.get("behavior", {}).get("sessions") or {}
    n_sessions = sessions_leaf.get("value") if sessions_leaf.get("label") == "MEASURED" else 0

    verbosity_leaf = profile.get("pressure", {}).get("output_verbosity") or {}
    verbosity_value = verbosity_leaf.get("value") if verbosity_leaf.get("label") == "MEASURED" else None
    n_messages = verbosity_value.get("n_assistant_messages") if isinstance(verbosity_value, dict) else 0

    return (n_sessions or 0), (n_messages or 0)


def compute_waste_score(profile):
    """Score = 100 minus the sum of five component penalties, per
    docs/WASTE-SCORE.md. All-or-nothing: computed only when every one of
    the five inputs carries the MEASURED label, is a finite number, and
    falls inside its plausible domain, AND the sample clears the published
    floor (WASTE_SCORE_MIN_SESSIONS sessions, WASTE_SCORE_MIN_ASSISTANT_MESSAGES
    assistant messages); otherwise the whole result is NO DATA, naming
    every input that failed and why. Never substitutes a zero and never
    scores over a subset: a score computed over a varying subset of
    components is not comparable between machines, and comparability is
    the entire reason this score exists."""
    n_sessions, n_messages = _waste_sample_counts(profile)
    floor_failures = []
    if n_sessions < WASTE_SCORE_MIN_SESSIONS:
        floor_failures.append(
            f"sample floor: {n_sessions} session(s) in window, need at least "
            f"{WASTE_SCORE_MIN_SESSIONS}")
    if n_messages < WASTE_SCORE_MIN_ASSISTANT_MESSAGES:
        floor_failures.append(
            f"sample floor: {n_messages} assistant message(s) with a measured "
            f"output_tokens in window, need at least {WASTE_SCORE_MIN_ASSISTANT_MESSAGES}")
    if floor_failures:
        return {
            "version": WASTE_SCORE_VERSION,
            "score": None,
            "band": None,
            "label": "NO DATA",
            "missing": floor_failures,
        }

    values = {}
    failures = []

    for comp in _WASTE_COMPONENTS:
        leaf = profile.get(comp["group"], {}).get(comp["key"])
        path = f"{comp['group']}.{comp['key']}"
        if leaf is None:
            failures.append(f"{comp['name']} ({path}): metric absent from profile")
            continue
        label = leaf.get("label")
        if label != "MEASURED":
            failures.append(f"{comp['name']} ({path}): label is {label}, not MEASURED")
            continue
        value = comp["extract"](leaf.get("value"))
        if value is None:
            failures.append(f"{comp['name']} ({path}): required field missing from value")
            continue
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            failures.append(f"{comp['name']} ({path}): value {value!r} is not a finite number")
            continue
        dmin, dmax = comp["domain"]
        if value < dmin or (dmax is not None and value > dmax):
            bound = f"[{dmin}, {dmax if dmax is not None else 'unbounded'}]"
            failures.append(f"{comp['name']} ({path}): value {value} is outside its plausible domain {bound}")
            continue
        values[comp["name"]] = value

    if failures:
        return {
            "version": WASTE_SCORE_VERSION,
            "score": None,
            "band": None,
            "label": "NO DATA",
            "missing": failures,
        }

    components = {}
    total_penalty = 0.0
    for comp in _WASTE_COMPONENTS:
        v = values[comp["name"]]
        penalty = _linear_penalty(v, comp["good"], comp["bad"], comp["weight"])
        total_penalty += penalty
        components[comp["name"]] = {
            "problem_class": comp["problem_class"],
            "weight": comp["weight"],
            "metric_value": v,
            "penalty": penalty,
        }

    score = _round_half_up(100.0 - total_penalty)
    return {
        "version": WASTE_SCORE_VERSION,
        "score": score,
        "band": _waste_band(score),
        "label": "MEASURED",
        "components": components,
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

    u, b, i, p, sk = (prof["usage"], prof["behavior"], prof["instruction"],
                       prof["pressure"], prof["skipped"])
    print(f"profile written: {a.out}")
    print(f"sessions in window: {mt.fmt(b['sessions']['value'])} over {a.days:g} days")
    print(f"first-request floor: {mt.fmt(u['first_request_median_tokens']['value'])} tokens "
          f"median, {mt.fmt(i['startup_floor_share']['value'])} share of everything read")
    print(f"cache hit ratio median: {mt.fmt(u['cache_hit_ratio_median']['value'])}")
    print(f"model switches mid-session: {mt.fmt(b['model_switch_session_share']['value'])} "
          f"of sessions")

    print("--- pressure ---")
    tool_share = p["tool_output_share_by_tool"]["value"]
    if tool_share is None:
        print("tool output share by tool: NO DATA")
    else:
        top = sorted(tool_share.items(), key=lambda kv: kv[1], reverse=True)[:3]
        print("tool output share by tool (top 3): "
              + ", ".join(f"{name} {mt.fmt(share)}" for name, share in top))
    dup_reads = p["duplicate_reads"]["value"]
    if dup_reads is None:
        print("duplicate tool reads: NO DATA")
    else:
        print(f"duplicate tool reads (total): {mt.fmt(sum(dup_reads.values()))}")
    print(f"duplicate Bash commands: {mt.fmt(p['duplicate_commands']['value'])}")
    verbosity = p["output_verbosity"]["value"]
    if verbosity is None:
        print("assistant output verbosity: NO DATA")
    else:
        print(f"assistant output verbosity: median {mt.fmt(verbosity['median_output_tokens'])} "
              f"tokens, p90 {mt.fmt(verbosity['p90_output_tokens'])}, "
              f"{mt.fmt(verbosity['over_1000_tokens_share'])} of messages over 1000 tokens")
    print(f"structured (tool_result) share of user turns: "
          f"{mt.fmt(p['structured_input_share']['value'])}")

    print(f"skipped while reading: {mt.fmt(sk['files']['value'])} files, "
          f"{mt.fmt(sk['lines']['value'])} lines")

    ws = compute_waste_score(prof)
    print(f"--- waste score ({ws['version']}) ---")
    if ws["label"] == "NO DATA":
        print("waste score: NO DATA")
        for reason in ws["missing"]:
            print(f"  - {reason}")
    else:
        print(f"waste score: {ws['score']} ({ws['band']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
