#!/usr/bin/env python3
"""Calibrated checks for report.py, the monthly Token Shield report.

    python3 scripts/test_report.py

Each test isolates report.py from this machine's real ledger and treatment
store (ex.LEDGER, adv.load_treatments) the same way test_experiment.py
isolates compute_fingerprint from the real CLAUDE.md and settings.json: patch
the module attribute the code reads, restore it in finally. adv.load_treatments
is swapped as a whole function rather than pointed at a new path, because its
`path` parameter defaults to TREATMENTS_PATH at function-definition time, so
reassigning advisor.TREATMENTS_PATH after import would not change what an
argument-less call reads.

Calibrated (defect reinjected, confirmed red, then reverted to green):
  - month windowing: widened the cohort filter from `< end_ts` to `<= end_ts`
    so the September boundary record leaked in; the windowing test caught it.
  - VERIFIED section: dropped the confidence filter in _verified_rows_for_month
    so NOT_PROVEN rows appeared too; the VERIFIED-only test caught it.
  - ESTIMATED wording: swapped in the literal string "could have saved" for
    the opportunity line; the wording test caught it.
  - label separation: merged the Verified and Addressable Opportunity bullets
    onto one line; the never-merge test caught it.
  - NO DATA rendering: made _read_ledger raise instead of returning [] when
    the ledger path is absent; the NO DATA test caught the crash.
  - file-write path: hardcoded the output path instead of honoring --out; the
    file-written test caught the mismatch.
"""

import json
import os
import sys
import tempfile

import advisor as adv
import experiment as ex
import measure_tokens as mt
import report as rp


def check(name, cond):
    print(("ok  " if cond else "FAIL ") + name)
    assert cond, name


def _usage_rec(ts, inp=1000, read=5000, out=500, model="claude-x", sidechain=False):
    return json.dumps({
        "isSidechain": sidechain,
        "timestamp": ts,
        "message": {"model": model, "usage": {
            "input_tokens": inp,
            "cache_creation": {"ephemeral_5m_input_tokens": 100, "ephemeral_1h_input_tokens": 0},
            "cache_creation_input_tokens": 100,
            "cache_read_input_tokens": read,
            "output_tokens": out}}})


def _write(path, records):
    with open(path, "w") as f:
        f.write("\n".join(records) + "\n")


def _section(report, heading_contains):
    """The lines between a '## ...' heading containing this text and the next
    '## ' heading, so an assertion about one section cannot be satisfied by
    text that actually lives in a different one."""
    lines = report.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.startswith("## ") and heading_contains in line:
            start = i + 1
            break
    if start is None:
        return ""
    end = len(lines)
    for j in range(start, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break
    return "\n".join(lines[start:end])


def _no_treatments():
    """Stand in for adv.load_treatments during a test: no rejected/suppressed
    strategies, and no read of the real machine's treatments.json."""
    return {}


def test_month_windowing_includes_only_records_inside_the_calendar_month():
    with tempfile.TemporaryDirectory() as d:
        root = os.path.join(d, "projects")
        os.makedirs(root)
        _write(os.path.join(root, "s.jsonl"), [
            _usage_rec("2026-07-31T23:59:59+00:00", out=700000),  # just before August: excluded
            _usage_rec("2026-08-01T00:00:00+00:00", out=100),     # month start: included
            _usage_rec("2026-08-31T23:59:59+00:00", out=150),     # month end: included
            _usage_rec("2026-09-01T00:00:00+00:00", out=800000),  # next month start: excluded
        ])
        ledger = os.path.join(d, "savings.jsonl")

        orig_ledger, orig_load = ex.LEDGER, adv.load_treatments
        ex.LEDGER, adv.load_treatments = ledger, _no_treatments
        try:
            report = rp.build_report(2026, 8, root=root)
        finally:
            ex.LEDGER, adv.load_treatments = orig_ledger, orig_load

    usage = _section(report, "Usage")
    check("only the two in-month records' output is counted (100 + 150 = 250)",
          "output: 250 tokens" in usage)
    check("the July record's huge output never appears anywhere in the report",
          "700,000" not in report)
    check("the September record's huge output never appears anywhere in the report",
          "800,000" not in report)


def test_final_subsecond_of_the_month_belongs_to_that_month():
    # Calibrated: restoring the old `end_ts - 1` bound in build_report makes
    # the 23:59:59.500 record vanish from BOTH months and this test goes red
    # on the July check; with the half-open bound, green.
    #
    # A record in the last second of a month must land in exactly one month.
    # The workaround that backed the cohort's inclusive end off by a whole
    # second put it in neither.
    def month_report(root, year, month, ledger):
        orig_ledger, orig_load = ex.LEDGER, adv.load_treatments
        ex.LEDGER, adv.load_treatments = ledger, _no_treatments
        try:
            return rp.build_report(year, month, root=root)
        finally:
            ex.LEDGER, adv.load_treatments = orig_ledger, orig_load

    with tempfile.TemporaryDirectory() as d:
        root = os.path.join(d, "projects")
        os.makedirs(root)
        _write(os.path.join(root, "s.jsonl"), [
            _usage_rec("2026-07-31T23:59:59.500000+00:00", out=333),  # July's last half-second
            _usage_rec("2026-08-01T00:00:00.000000+00:00", out=444),  # August's first instant
        ])
        ledger = os.path.join(d, "savings.jsonl")
        july = month_report(root, 2026, 7, ledger)
        august = month_report(root, 2026, 8, ledger)

    july_usage, august_usage = _section(july, "Usage"), _section(august, "Usage")
    check("the 23:59:59.500 record is counted in July",
          "output: 333 tokens" in july_usage)
    check("the 23:59:59.500 record is not counted in August",
          "333" not in august_usage)
    check("August's first instant is counted in August",
          "output: 444 tokens" in august_usage)
    check("August's first instant is not counted in July",
          "444" not in july_usage)


def test_verified_section_lists_only_verified_records_ended_in_the_month():
    with tempfile.TemporaryDirectory() as d:
        root = os.path.join(d, "projects")
        os.makedirs(root)
        _write(os.path.join(root, "s.jsonl"), [_usage_rec("2026-08-10T00:00:00+00:00")])
        ledger = os.path.join(d, "savings.jsonl")
        records = [
            {"label": "shrink-claude-md", "confidence": "VERIFIED",
             "timestamp": "2026-08-05T00:00:00+00:00", "floor_reduction_tokens": 5000},
            {"label": "prune-plugins", "confidence": "NOT_PROVEN",
             "timestamp": "2026-08-06T00:00:00+00:00", "reasons": ["thin data"]},
            {"label": "earlier-experiment", "confidence": "VERIFIED",
             "timestamp": "2026-07-20T00:00:00+00:00", "floor_reduction_tokens": 9999},
        ]
        with open(ledger, "w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

        orig_ledger, orig_load = ex.LEDGER, adv.load_treatments
        ex.LEDGER, adv.load_treatments = ledger, _no_treatments
        try:
            report = rp.build_report(2026, 8, root=root)
        finally:
            ex.LEDGER, adv.load_treatments = orig_ledger, orig_load

    verified = _section(report, "Verified improvements")
    check("the in-month VERIFIED label is listed", "shrink-claude-md" in verified)
    check("the NOT_PROVEN label from the same month is not in the Verified section",
          "prune-plugins" not in verified)
    check("the VERIFIED label from the prior month is excluded", "earlier-experiment" not in verified)


def test_addressable_opportunity_uses_required_wording_never_could_have_saved():
    with tempfile.TemporaryDirectory() as d:
        root = os.path.join(d, "projects")
        os.makedirs(root)
        # One session, two distinct models: token_shield.prescriptions fires its
        # "Switching model mid-session" card on this, giving a real, positive
        # estimated saving to render.
        _write(os.path.join(root, "s.jsonl"), [
            _usage_rec("2026-08-10T00:00:00+00:00", model="claude-a"),
            _usage_rec("2026-08-10T00:05:00+00:00", model="claude-b"),
        ])
        ledger = os.path.join(d, "savings.jsonl")

        orig_ledger, orig_load = ex.LEDGER, adv.load_treatments
        ex.LEDGER, adv.load_treatments = ledger, _no_treatments
        try:
            report = rp.build_report(2026, 8, root=root)
        finally:
            ex.LEDGER, adv.load_treatments = orig_ledger, orig_load

    opportunity = _section(report, "Addressable opportunity")
    check("a prescription actually fired for this fixture", "NO DATA" not in opportunity)
    check("uses the required phrasing 'addressable opportunity, estimated'",
          "addressable opportunity, estimated" in opportunity)
    check("never uses the forbidden phrasing anywhere in the whole report",
          "could have saved" not in report.lower())


def test_verified_and_estimated_figures_never_share_a_line():
    with tempfile.TemporaryDirectory() as d:
        root = os.path.join(d, "projects")
        os.makedirs(root)
        _write(os.path.join(root, "s.jsonl"), [
            _usage_rec("2026-08-10T00:00:00+00:00", model="claude-a"),
            _usage_rec("2026-08-10T00:05:00+00:00", model="claude-b"),
        ])
        ledger = os.path.join(d, "savings.jsonl")
        with open(ledger, "w") as f:
            f.write(json.dumps({"label": "shrink-claude-md", "confidence": "VERIFIED",
                                "timestamp": "2026-08-05T00:00:00+00:00",
                                "floor_reduction_tokens": 5000}) + "\n")

        orig_ledger, orig_load = ex.LEDGER, adv.load_treatments
        ex.LEDGER, adv.load_treatments = ledger, _no_treatments
        try:
            report = rp.build_report(2026, 8, root=root)
        finally:
            ex.LEDGER, adv.load_treatments = orig_ledger, orig_load

    check("both a VERIFIED row and an estimated row are present in this fixture",
          "VERIFIED" in report and "estimated" in report.lower())
    bad_lines = [line for line in report.splitlines()
                 if "VERIFIED" in line and "estimated" in line.lower()]
    check("no single line mixes a VERIFIED figure with an estimated one", not bad_lines)


def test_companion_suppression_never_filed_as_what_did_not_work():
    # Calibrated: _what_did_not_work selected any rejected or suppressed
    # treatment record with no filter on reason, so a companion-caused
    # suppression (reason "companion", written by sync_companion_suppressions,
    # not a failed treatment) landed in a section the project treats as
    # evidence something did not pan out. It must be excluded there, and the
    # exclusion itself must be visible, not silently dropped.
    with tempfile.TemporaryDirectory() as d:
        root = os.path.join(d, "projects")
        os.makedirs(root)
        _write(os.path.join(root, "s.jsonl"), [_usage_rec("2026-08-10T00:00:00+00:00")])
        ledger = os.path.join(d, "savings.jsonl")

        def _mixed_treatments():
            return {
                "companion.ponytail": {"decision": "suppressed", "at": "2026-08-05T00:00:00",
                                       "until": "2999-01-01T00:00:00", "reason": "companion",
                                       "note": "companion ponytail already owns this capability"},
                "overbuild.git-instructions-off": {"decision": "rejected",
                                                    "at": "2026-08-06T00:00:00",
                                                    "until": "2999-01-01T00:00:00",
                                                    "note": "not for me"},
            }

        orig_ledger, orig_load = ex.LEDGER, adv.load_treatments
        ex.LEDGER, adv.load_treatments = ledger, _mixed_treatments
        try:
            report = rp.build_report(2026, 8, root=root)
        finally:
            ex.LEDGER, adv.load_treatments = orig_ledger, orig_load

    not_worked = _section(report, "What did not work")
    check("the user's own rejected strategy is listed",
          "overbuild.git-instructions-off" in not_worked)
    check("the companion suppression's strategy id never appears in the section",
          "companion.ponytail" not in not_worked)
    check("the exclusion is still surfaced, not silently dropped",
          "companion suppression" in not_worked.lower())


def test_no_data_rendering_when_ledger_absent():
    with tempfile.TemporaryDirectory() as d:
        root = os.path.join(d, "projects")
        os.makedirs(root)
        _write(os.path.join(root, "s.jsonl"), [_usage_rec("2026-08-10T00:00:00+00:00")])
        missing_ledger = os.path.join(d, "does-not-exist.jsonl")

        orig_ledger, orig_load = ex.LEDGER, adv.load_treatments
        ex.LEDGER, adv.load_treatments = missing_ledger, _no_treatments
        try:
            report = rp.build_report(2026, 8, root=root)
        finally:
            ex.LEDGER, adv.load_treatments = orig_ledger, orig_load

    check("Verified improvements renders NO DATA rather than erroring",
          "NO DATA" in _section(report, "Verified improvements"))
    check("What did not work renders NO DATA when the ledger and treatments are both empty",
          "NO DATA" in _section(report, "What did not work"))


def test_report_file_written_at_the_requested_out_path():
    with tempfile.TemporaryDirectory() as d:
        root = os.path.join(d, "projects")
        os.makedirs(root)
        _write(os.path.join(root, "s.jsonl"), [_usage_rec("2026-08-10T00:00:00+00:00")])
        out_path = os.path.join(d, "somewhere", "custom-name.md")
        ledger = os.path.join(d, "savings.jsonl")

        orig_ledger, orig_load = ex.LEDGER, adv.load_treatments
        ex.LEDGER, adv.load_treatments = ledger, _no_treatments
        argv = sys.argv
        sys.argv = ["report.py", "--root", root, "--month", "2026-08", "--out", out_path]
        try:
            rc = rp.main()
        finally:
            sys.argv = argv
            ex.LEDGER, adv.load_treatments = orig_ledger, orig_load

        # Checked inside the TemporaryDirectory block: it deletes the tree
        # (out_path included) the moment the `with` exits.
        check("main() exits 0 on a month with data", rc == 0)
        check("the file was written at the exact --out path", os.path.isfile(out_path))
        with open(out_path) as f:
            content = f.read()
        check("the written file is the same report build_report would produce",
              "# Token Shield monthly report: 2026-08" in content)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
