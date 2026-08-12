#!/usr/bin/env python3
"""Calibrated checks for experiment.build_record, the VERIFIED verdict logic."""
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


if __name__ == "__main__":
    import sys
    n = 0
    for name in sorted(dir(sys.modules[__name__])):
        if name.startswith("test_"):
            globals()[name]()
            n += 1
    print(f"\n{n} passed")
