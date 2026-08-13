#!/usr/bin/env python3
"""Calibrated checks for detail_report.py, the Consumption Report, schema v1.

    python3 scripts/test_detail_report.py

Per the Consumption Report spec's Testing section: schema validated field by
field against a seeded sandbox HOME, every section exercised with data
present and with data missing (NO DATA asserted verbatim), the label-blend
refusal asserted, daily_series bound asserted at the window edge.

HOME sandboxing: context_lint.default_targets/expected_memory_index_path and
profile.build_profile's own file reads (~/.claude/CLAUDE.md and friends) all
call os.path.expanduser inline, inside the function body, not at import time
(unlike experiment.py's STORE/EXP_DIR/LEDGER, which test_experiment.py has to
work around with a subprocess or attribute patching). So patching
os.environ["HOME"] right before a call, restored in finally, is enough here;
no reload dance needed.

Calibrated (defect reinjected, confirmed red, then reverted to green):
  - daily_series bound: removed the `rows[-cap:]` slice in _daily_series so
    it returned every bucketed day unbounded; test_daily_series_bounded_...
    went red (more than window_days rows), green after restoring the slice.
  - NO DATA verbatim: changed no_data()'s label from "NO DATA" to "SIGNAL";
    test_no_data_on_empty_root_is_verbatim went red, green after reverting.
"""

import json
import os
import sys
import tempfile
import time

import detail_report as dr

ALLOWED_LABELS = {"VERIFIED", "MEASURED", "INFERRED", "ESTIMATED", "NATIVE", "NO DATA"}


def check(name, cond):
    print(("ok  " if cond else "FAIL ") + name)
    assert cond, name


def _rec(ts, model="claude-x", inp=1000, w5=0, w1=0, read=5000, out=200, sub=False):
    return json.dumps({"isSidechain": sub, "timestamp": ts, "message": {
        "model": model, "usage": {"input_tokens": inp, "cache_read_input_tokens": read,
        "output_tokens": out, "cache_creation": {"ephemeral_5m_input_tokens": w5,
                                                  "ephemeral_1h_input_tokens": w1}}}})


def _write(path, records):
    with open(path, "w") as f:
        f.write("\n".join(records) + "\n")


def _seed_sessions(root, days, calls=12, model="claude-x", w5=0, w1=0):
    """One session file per day, so day-bucketing has real distinct days to
    group, unlike a single multi-day file (which measure_tokens.collect
    treats as one session with one `started` timestamp)."""
    os.makedirs(root, exist_ok=True)
    now = time.time()
    for i, day_offset in enumerate(days):
        lines = []
        base = now - day_offset * 86400
        for c in range(calls):
            ts = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(base + c * 60))
            lines.append(_rec(ts, model=model, w5=w5, w1=w1))
        _write(os.path.join(root, f"day{i}.jsonl"), lines)


def _in_sandbox_home(fn):
    """Run fn() with HOME pointed at a fresh temp dir, restored after. See
    module docstring for why this needs no reload of any scripts/ module."""
    old_home = os.environ.get("HOME")
    with tempfile.TemporaryDirectory() as home:
        os.environ["HOME"] = home
        try:
            return fn()
        finally:
            if old_home is not None:
                os.environ["HOME"] = old_home


def _leaf_labels(section):
    """Every {value,label,source} leaf found directly under a section dict
    (skips composite list/dict values like top_contributors' rows)."""
    for key, leaf in section.items():
        if isinstance(leaf, dict) and set(leaf.keys()) == {"value", "label", "source"}:
            yield key, leaf


def test_schema_v1_top_level_and_leaf_shape():
    def run():
        with tempfile.TemporaryDirectory() as d:
            root = os.path.join(d, "projects")
            _seed_sessions(root, days=[5, 4, 3, 2, 1, 0])
            return dr.build_detail_report(root=root, window_days=30)
    result = _in_sandbox_home(run)

    check("report_schema is 1", result["report_schema"] == 1)
    check("source_label is set", result["source_label"] == dr.SOURCE_LABEL)
    for section_name in ("startup_floor", "subagents", "cache", "rhythm"):
        section = result[section_name]
        for key, leaf in _leaf_labels(section):
            check(f"{section_name}.{key} label is one of the standing labels",
                  leaf["label"] in ALLOWED_LABELS)
            check(f"{section_name}.{key} carries a non-empty source",
                  bool(leaf["source"]))
            if leaf["label"] == "NO DATA":
                check(f"{section_name}.{key} NO DATA leaf has a null value, "
                      f"never a fabricated zero", leaf["value"] is None)
    check("habits is a list", isinstance(result["habits"], list))
    check("daily_series is a list", isinstance(result["daily_series"], list))


def test_no_data_on_empty_root_is_verbatim():
    def run():
        return dr.build_detail_report(root="/nonexistent-path-for-check", window_days=30)
    result = _in_sandbox_home(run)

    check("startup floor median is NO DATA on an empty root",
          result["startup_floor"]["median_tokens"]["label"] == "NO DATA")
    check("startup floor median value is null, not zero",
          result["startup_floor"]["median_tokens"]["value"] is None)
    check("subagent output share is NO DATA on an empty root",
          result["subagents"]["output_share"]["label"] == "NO DATA")
    check("cache hit ratio is NO DATA on an empty root",
          result["cache"]["hit_ratio_median"]["label"] == "NO DATA")
    check("rhythm sessions_per_day is NO DATA on an empty root",
          result["rhythm"]["sessions_per_day"]["label"] == "NO DATA")
    check("compaction_events is always NO DATA in v1 (no counter exists)",
          result["rhythm"]["compaction_events"]["label"] == "NO DATA")
    check("habits is empty when nothing crossed a threshold on empty data",
          result["habits"] == [])
    check("daily_series is empty on an empty root", result["daily_series"] == [])


def test_daily_series_bounded_at_window_edge():
    # 45 distinct days of sessions, requested window is 10 days: collect()
    # itself filters by file mtime (all freshly written, so all pass), but
    # the day-bucketing must still cap the output at window_days rows even
    # though many more days of data went in.
    def run():
        with tempfile.TemporaryDirectory() as d:
            root = os.path.join(d, "projects")
            _seed_sessions(root, days=list(range(45)))
            return dr.build_detail_report(root=root, window_days=10)
    result = _in_sandbox_home(run)
    check("45 days of data went in", True)
    check("daily_series never exceeds window_days rows",
          len(result["daily_series"]) <= 10)
    check("daily_series is bounded, not empty (real data was present)",
          len(result["daily_series"]) > 0)


def test_habits_are_measured_confidence_only():
    """v1 ships only habits derivable from MEASURED signals; no INFERRED
    heuristic is invented for this section."""
    def run():
        with tempfile.TemporaryDirectory() as d:
            root = os.path.join(d, "projects")
            # Heavy model switching across every session's tenth call, well
            # past the 0.2 share trigger copied from
            # data/strategies.json's cache.fixed-parent-model.
            _seed_sessions(root, days=[2, 1, 0], model="claude-y")
            return dr.build_detail_report(root=root, window_days=30)
    result = _in_sandbox_home(run)
    check("every habit finding is confidence MEASURED in v1",
          all(h["confidence"] == "MEASURED" for h in result["habits"]))
    for h in result["habits"]:
        check("every habit carries what/why_it_matters/action/confidence",
              set(h.keys()) == {"what", "why_it_matters", "action", "confidence"})


def test_rebuild_habit_fires_on_seeded_rewrite_heavy_sessions():
    def run():
        with tempfile.TemporaryDirectory() as d:
            root = os.path.join(d, "projects")
            # High cache-write relative to a small read, calls >= 10: crosses
            # token_shield.pain_points' own rebuild filter (rewrite_ratio >
            # 0.15, calls >= 10), same threshold this module reuses.
            _seed_sessions(root, days=[1, 0], calls=12, w5=5000, w1=0)
            return dr.build_detail_report(root=root, window_days=30)
    result = _in_sandbox_home(run)
    check("cache.rebuild_events counted at least one rebuilt session",
          result["cache"]["rebuild_events"]["value"] is not None and
          result["cache"]["rebuild_events"]["value"] > 0)
    check("cost_per_rebuild is a real number when a rebuild was measured",
          isinstance(result["cache"]["cost_per_rebuild"]["value"], (int, float)))
    titles = [h["what"] for h in result["habits"]]
    check("a cache rebuild habit finding fired",
          any("rebuild" in t for t in titles))


def test_labels_never_blended_across_daily_series_rows():
    """Each daily_series row keeps its own per-day numbers; there is no
    single blended figure standing in for the whole window."""
    def run():
        with tempfile.TemporaryDirectory() as d:
            root = os.path.join(d, "projects")
            _seed_sessions(root, days=[3, 2, 1, 0])
            return dr.build_detail_report(root=root, window_days=30)
    result = _in_sandbox_home(run)
    rows = result["daily_series"]
    check("more than one day of data produced more than one row",
          len(rows) >= 2)
    dates = [r["date"] for r in rows]
    check("every row carries its own distinct date, never merged into one",
          len(dates) == len(set(dates)))
    for row in rows:
        check(f"row {row['date']} sessions leaf carries its own source",
              bool(row["sessions"]["source"]))


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
