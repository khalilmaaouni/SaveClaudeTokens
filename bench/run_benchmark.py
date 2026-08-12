#!/usr/bin/env python3
"""
run_benchmark.py: run the real meter over a synthetic corpus and check its
output against the numbers the corpus was built to contain.

    python3 bench/run_benchmark.py --corpus /path/to/dir

Loads scripts/measure_tokens.py the same way scripts/test_measure_tokens.py
does (importlib, by file path, not installed), so this exercises the actual
shipped module, not a copy of it.

Every row printed is labeled CONSTRUCTED (from bench/generate_corpus.py,
computed by arithmetic on the numbers it wrote, before the meter ever ran)
or MEASURED (read back out of the corpus files by scripts/measure_tokens.py
itself). The two numbers must match: that is the entire proof this script
exists to run. It proves the meter reads counters correctly. It does not
prove anything about a real user's savings.

Exit code 0 only when every row passes.
"""

import argparse
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)

# Token counts are integers by construction, so exact equality is the
# default check. A tolerance applies only to the four rows where floating
# point division makes exact equality unreasonable to demand: a per-session
# or aggregate hit ratio, and the first-request mean or median (a median
# over an even count of sessions can land on the exact average of two
# integers, which is still exact in IEEE 754 for the small sums here, but
# the tolerance is kept as a safety margin rather than relied upon).
TOLERANCE = {
    "hit_ratio": 1e-9,
    "hit_ratio_median": 1e-9,
    "first_request_mean": 1e-6,
    "first_request_median": 1e-6,
}


def _load_measure_tokens():
    spec = importlib.util.spec_from_file_location(
        "mt", os.path.join(REPO_ROOT, "scripts", "measure_tokens.py"))
    mt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mt)
    return mt


def _check(label, expected, measured):
    if expected is None or measured is None:
        return expected == measured
    tol = TOLERANCE.get(label, 0)
    if tol:
        return abs(expected - measured) <= tol
    return expected == measured


def compare(expected, sessions, sm):
    """Return a list of (label, expected_value, measured_value, passed)."""
    rows = []
    measured_by_file = {os.path.basename(s["file"]): s for s in sessions}

    per_session_fields = ("input", "read", "write_5m", "write_1h", "output",
                           "first_request", "hit_ratio")
    for exp_s in expected["sessions"]:
        fn = exp_s["file"]
        meas_s = measured_by_file.get(fn)
        if meas_s is None:
            rows.append((f"{fn}:present in measured output", True, False, False))
            continue
        for field in per_session_fields:
            exp_v = exp_s[field]
            meas_v = meas_s[field]
            rows.append((f"{fn}:{field}", exp_v, meas_v, _check(field, exp_v, meas_v)))

    aggregate_fields = ("input_total", "read_total", "write_5m_total",
                         "write_1h_total", "output_total",
                         "first_request_median", "first_request_mean",
                         "first_request_p90", "hit_ratio_median")
    agg = expected["aggregate"]
    for field in aggregate_fields:
        exp_v = agg[field]
        meas_v = sm.get(field) if sm else None
        rows.append((f"aggregate:{field}", exp_v, meas_v, _check(field, exp_v, meas_v)))

    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--corpus", required=True,
                     help="directory generate_corpus.py wrote (holds expected.json)")
    a = ap.parse_args()

    expected_path = os.path.join(a.corpus, "expected.json")
    try:
        with open(expected_path) as f:
            expected = json.load(f)
    except OSError as e:
        print(f"FAIL: cannot read {expected_path}: {e}")
        return 2

    mt = _load_measure_tokens()
    # days is set far larger than any corpus could be old, so the mtime
    # filter in scripts/measure_tokens.py never excludes a freshly
    # generated corpus.
    sessions = mt.collect(a.corpus, days=1_000_000)
    sm = mt.summarize(sessions)

    rows = compare(expected, sessions, sm)

    print(f"{'metric':<34} {'expected (CONSTRUCTED)':>24} {'measured (MEASURED)':>22}  status")
    all_pass = True
    for label, exp_v, meas_v, ok in rows:
        status = "PASS" if ok else "FAIL"
        all_pass = all_pass and ok
        print(f"{label:<34} {str(exp_v):>24} {str(meas_v):>22}  {status}")

    print()
    if all_pass:
        print(f"ALL PASS ({len(rows)} checks)")
        return 0
    failed = sum(1 for *_, ok in rows if not ok)
    print(f"FAIL: {failed} of {len(rows)} checks did not match")
    return 1


if __name__ == "__main__":
    sys.exit(main())
