#!/usr/bin/env python3
"""Calibrated checks for experiment.build_record, the VERIFIED verdict logic."""
import json
import os
import tempfile

import experiment as ex
import measure_tokens as mt


def check(name, cond):
    print(("ok  " if cond else "FAIL ") + name)
    assert cond, name


def _baseline(schema=mt.SCHEMA, window=30, fr=80000, sessions=10):
    return {"label": "t", "started": "2026-08-01T00:00:00", "window_days": window,
            "schema": schema,
            "summary": {"first_request_median": fr, "normalized_input_total": 1_000_000,
                        "parent_sessions": sessions}}


def _after(window=30, fr=60000, sessions=10):
    return {"_window_days": window, "first_request_median": fr,
            "normalized_input_total": 800_000, "parent_sessions": sessions}


def test_clean_before_after_is_verified():
    rec = ex.build_record(_baseline(fr=80000), _after(fr=60000), "2026-08-30T00:00:00")
    check("clean before/after is VERIFIED", rec["confidence"] == "VERIFIED")
    check("floor reduction is measured correctly", rec["floor_reduction_tokens"] == 20000)
    check("no reasons on a verified record", rec["reasons"] == [])


def test_schema_change_is_not_proven():
    # Calibration: same inputs but a schema bump must flip VERIFIED to NOT_PROVEN.
    rec = ex.build_record(_baseline(schema=mt.SCHEMA - 1), _after(), "2026-08-30T00:00:00")
    check("schema change downgrades to NOT_PROVEN", rec["confidence"] == "NOT_PROVEN")
    check("schema change is named as the reason",
          any("schema" in r for r in rec["reasons"]))


def test_window_mismatch_is_not_proven():
    rec = ex.build_record(_baseline(window=30), _after(window=7), "2026-08-30T00:00:00")
    check("window mismatch downgrades to NOT_PROVEN", rec["confidence"] == "NOT_PROVEN")
    check("window mismatch is named", any("window" in r for r in rec["reasons"]))


def test_thin_data_is_not_proven():
    rec = ex.build_record(_baseline(sessions=10), _after(sessions=1), "2026-08-30T00:00:00")
    check("thin post-change data downgrades to NOT_PROVEN", rec["confidence"] == "NOT_PROVEN")


def test_no_verified_record_without_a_real_floor_on_both_sides():
    b = _baseline(); b["summary"]["first_request_median"] = None
    rec = ex.build_record(b, _after(), "2026-08-30T00:00:00")
    check("missing before-floor cannot be VERIFIED", rec["confidence"] == "NOT_PROVEN")


# --- v2: cohorts by message timestamp, non-overlap, config fingerprint, --treats ---

def test_overlap_refusal():
    reason_bad = ex.check_cohort_order(before_end_ts=1000, after_start_ts=500)
    check("overlapping windows return a reason", reason_bad is not None)
    check("reason names the overlap", "overlap" in reason_bad)
    reason_touching = ex.check_cohort_order(before_end_ts=1000, after_start_ts=1000)
    check("after starting exactly where before ends is fine (at or after)",
          reason_touching is None)
    reason_ok = ex.check_cohort_order(before_end_ts=1000, after_start_ts=1500)
    check("non-overlapping windows are fine", reason_ok is None)


def test_fingerprint_mismatch_is_not_proven():
    b = _baseline()
    b["fingerprint_start"] = "aaa"
    rec = ex.build_record(b, _after(), "2026-08-30T00:00:00", fingerprint_end="bbb")
    check("fingerprint mismatch downgrades to NOT_PROVEN", rec["confidence"] == "NOT_PROVEN")
    check("config-change reason is named",
          any("config changed during experiment window" in r for r in rec["reasons"]))
    rec_same = ex.build_record(b, _after(), "2026-08-30T00:00:00", fingerprint_end="aaa")
    check("matching fingerprints add no config-change reason",
          not any("config changed" in r for r in rec_same["reasons"]))


def test_treats_exclusion_keeps_treatment_edit_from_tripping_the_downgrade():
    with tempfile.TemporaryDirectory() as td:
        claude_md = os.path.join(td, "CLAUDE.md")
        settings = os.path.join(td, "settings.json")
        plugins = os.path.join(td, "plugins", "cache")
        os.makedirs(plugins)
        with open(claude_md, "w") as f:
            f.write("original content")
        with open(settings, "w") as f:
            f.write("{}")

        orig = (ex.CLAUDE_MD_PATH, ex.SETTINGS_PATH, ex.PLUGINS_CACHE)
        ex.CLAUDE_MD_PATH, ex.SETTINGS_PATH, ex.PLUGINS_CACHE = claude_md, settings, plugins
        try:
            fp_before_excluded = ex.compute_fingerprint(treats=claude_md)
            fp_before_plain = ex.compute_fingerprint(treats=None)
            with open(claude_md, "w") as f:
                f.write("edited by the treatment")
            fp_after_excluded = ex.compute_fingerprint(treats=claude_md)
            fp_after_plain = ex.compute_fingerprint(treats=None)
            check("excluding the treatment target keeps the fingerprint stable "
                  "across its own edit", fp_before_excluded == fp_after_excluded)
            check("without --treats the same edit changes the fingerprint",
                  fp_before_plain != fp_after_plain)
        finally:
            ex.CLAUDE_MD_PATH, ex.SETTINGS_PATH, ex.PLUGINS_CACHE = orig


def test_timestamp_cohorting_ignores_records_outside_window_in_same_file():
    with tempfile.TemporaryDirectory() as td:
        fp = os.path.join(td, "session.jsonl")

        def usage_line(ts, inp):
            return {"timestamp": ts, "isSidechain": False,
                    "message": {"model": "claude-x", "usage": {
                        "input_tokens": inp, "cache_read_input_tokens": 0,
                        "output_tokens": 5,
                        "cache_creation": {"ephemeral_5m_input_tokens": 0,
                                           "ephemeral_1h_input_tokens": 0}}}}

        with open(fp, "w") as f:
            f.write(json.dumps(usage_line("2020-01-01T00:00:00+00:00", 999999)) + "\n")
            f.write(json.dumps(usage_line("2026-08-10T00:00:00+00:00", 111)) + "\n")

        start_ts = ex._parse_ts("2026-08-01T00:00:00+00:00")
        end_ts = ex._parse_ts("2026-08-20T00:00:00+00:00")
        cohort = ex.collect_cohort(td, start_ts, end_ts)
        check("only the in-window record contributes to the cohort", len(cohort) == 1)
        check("the resumed old record's tokens are excluded from the totals",
              cohort[0]["input"] == 111)


def test_per_label_aggregation_never_sums_across_labels():
    records = [
        {"label": "a", "confidence": "VERIFIED", "floor_reduction_tokens": 1000},
        {"label": "a", "confidence": "VERIFIED", "floor_reduction_tokens": 2000},
        {"label": "b", "confidence": "NOT_PROVEN", "floor_reduction_tokens": 500000},
    ]
    by_label = ex.aggregate_by_label(records)
    check("each label gets its own row", set(by_label) == {"a", "b"})
    check("label a's reductions never include label b's number",
          500000 not in by_label["a"]["reductions"])
    check("label b's reductions never include label a's numbers",
          1000 not in by_label["b"]["reductions"]
          and 2000 not in by_label["b"]["reductions"])


if __name__ == "__main__":
    import sys
    n = 0
    for name in sorted(dir(sys.modules[__name__])):
        if name.startswith("test_"):
            globals()[name]()
            n += 1
    print(f"\n{n} passed")
