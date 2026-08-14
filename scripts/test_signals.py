#!/usr/bin/env python3
"""Self-check for signals.py, Signals S1. No framework, no fixtures.

    python3 scripts/test_signals.py

Every test runs on a fixture ledger under a temp dir, never the real
~/.claude/ or ~/.token-shield/.
"""

import datetime
import json
import os
import stat
import tempfile

import signals as sig

HERE = os.path.dirname(os.path.abspath(__file__))


def _row(recorded_at, session_id="sess-x", input=0, cache_read=0,
         cache_write_5m=0, cache_write_1h=0, cache_write_unsplit=0,
         first_request=0, calls=1):
    """One fixture ledger row, shaped like session_end_telemetry.record()'s
    output. Only the fields build_candidate() actually reads are given
    meaningful defaults; the rest of a real row (transcript, models, ...)
    is not needed to drive the rollup."""
    return {
        "recorded_at": recorded_at,
        "session_id": session_id,
        "input": input,
        "cache_read": cache_read,
        "cache_write_5m": cache_write_5m,
        "cache_write_1h": cache_write_1h,
        "cache_write_unsplit": cache_write_unsplit,
        "first_request": first_request,
        "calls": calls,
    }


def _write_ledger(path, rows):
    with open(path, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


# (a) allowlist serialization: a field outside the schema cannot leave -------

def test_field_not_named_by_schema_never_survives_the_projection():
    with tempfile.TemporaryDirectory() as d:
        ledger = os.path.join(d, "ledger.jsonl")
        _write_ledger(ledger, [
            _row("2026-08-10T09:00:00", input=100, cache_read=900,
                 first_request=100, calls=5),
        ])
        candidate = sig.build_candidate(ledger, "2026-08-10")
    assert candidate is not None

    # Bypass the schema walk entirely: bolt fields onto the candidate the
    # way a careless future edit to build_candidate() might, one that a
    # schema bump never authorized.
    candidate["machine_hostname"] = "khalils-mbp.local"
    candidate["environment"]["repo_path"] = "/Users/khalil/SaveClaudeTokens"
    # RED: looking at the raw candidate (pre-projection), the leak is there.
    assert candidate["machine_hostname"] == "khalils-mbp.local"
    assert candidate["environment"]["repo_path"] == "/Users/khalil/SaveClaudeTokens"

    schema = sig._load_schema()
    projected = sig._project(schema, candidate)

    # GREEN: the schema walk is what stops it, not luck.
    assert "machine_hostname" not in projected
    assert "repo_path" not in projected["environment"]
    # And the legitimate fields the schema does name still made it through.
    assert projected["schema_version"] == 1
    assert projected["report_date"] == "2026-08-10"
    assert projected["environment"]["platform"] in ("mac", "linux", "windows", "unknown")


def test_build_report_output_matches_schema_top_level_keys_only():
    with tempfile.TemporaryDirectory() as d:
        ledger = os.path.join(d, "ledger.jsonl")
        _write_ledger(ledger, [
            _row("2026-08-10T09:00:00", input=100, cache_read=900,
                 first_request=100, calls=5),
        ])
        report = sig.build_report(ledger, "2026-08-10")
    schema = sig._load_schema()
    allowed = set(schema["properties"].keys())
    assert set(report.keys()) <= allowed
    # S1 populates no error_classes, no overspend_markers, no
    # treatment_outcomes, no submission_id: the schema itself says those
    # have no honest local basis yet, and build_candidate never invents one.
    assert "error_classes" not in report
    assert "overspend_markers" not in report
    assert "treatment_outcomes" not in report
    assert "submission_id" not in report


# (b) quantization boundaries -------------------------------------------------

def test_quantize_5_boundaries():
    # Exactly halfway between buckets rounds up.
    assert sig.quantize_5(0.025) == 5      # 2.5% -> 5
    assert sig.quantize_5(0.075) == 10     # 7.5% -> 10
    # Just under halfway stays in the lower bucket.
    assert sig.quantize_5(0.0249999) == 0
    assert sig.quantize_5(0.0749999) == 5
    # Exact multiples of 5 land on themselves.
    assert sig.quantize_5(0.20) == 20
    assert sig.quantize_5(0.0) == 0
    assert sig.quantize_5(1.0) == 100
    # Out-of-range fractions clamp before rounding rather than produce an
    # out-of-schema bucket.
    assert sig.quantize_5(1.5) == 100
    assert sig.quantize_5(-0.5) == 0
    # Every bucket quantize_5 can return is schema-legal: 0..100, step 5.
    for i in range(0, 201):
        b = sig.quantize_5(i / 200.0)
        assert 0 <= b <= 100 and b % 5 == 0, b


# (c) two reports share no identifying or connecting value ------------------

def test_two_overlapping_day_reports_share_no_linking_value():
    with tempfile.TemporaryDirectory() as d:
        ledger = os.path.join(d, "ledger.jsonl")
        # The same session_id shows up on both days (a session resumed past
        # midnight): the exact overlap case the design calls out. Two
        # reports built from this must still be unlinkable to each other.
        _write_ledger(ledger, [
            _row("2026-08-10T23:50:00", session_id="sess-fixed-1",
                 input=1000, cache_read=9000, first_request=1000, calls=5),
            _row("2026-08-11T00:10:00", session_id="sess-fixed-1",
                 input=1200, cache_read=8000, first_request=1200, calls=4),
        ])
        report_a = sig.build_report(ledger, "2026-08-10")
        report_b = sig.build_report(ledger, "2026-08-11")

    assert report_a is not None and report_b is not None
    assert report_a["report_date"] != report_b["report_date"]
    for report in (report_a, report_b):
        assert "session_id" not in report
        assert "submission_id" not in report
        # No raw (un-quantized) count anywhere in the payload.
        blob = json.dumps(report, sort_keys=True)
        assert "sess-fixed-1" not in blob
        for v in report.get("waste_shares", {}).values():
            assert v % 5 == 0

    # Calibration: prove the schema projector is the thing that stops a
    # stable id from leaking, not that the ledger happens not to carry one.
    # Build a candidate the normal way, then bolt a raw session_id onto it
    # directly, bypassing the projector, the way a careless edit to
    # build_candidate() might do it by accident.
    with tempfile.TemporaryDirectory() as d:
        ledger = os.path.join(d, "ledger.jsonl")
        _write_ledger(ledger, [
            _row("2026-08-10T09:00:00", session_id="sess-fixed-1",
                 input=1000, cache_read=9000, first_request=1000, calls=5),
        ])
        raw_candidate = sig.build_candidate(ledger, "2026-08-10")
    raw_candidate["session_id"] = "sess-fixed-1"
    # RED: present before projection.
    assert raw_candidate["session_id"] == "sess-fixed-1"
    projected = sig._project(sig._load_schema(), raw_candidate)
    # GREEN: the whitelist walk drops it, since "session_id" is not a name
    # the schema carries anywhere (only "submission_id" is, and only S2
    # populates that).
    assert "session_id" not in projected


# (d) outbox cap: the 91st entry evicts the oldest ---------------------------

_FIXTURE_EPOCH = datetime.date(2026, 1, 1)


def _fixture_day(n):
    """A distinct calendar day per n (epoch + n days). Distinct on purpose:
    finding 7 makes queue_report replace same-day files instead of adding a
    second one, so an outbox-capacity fixture needs one file per n to stay
    a capacity test rather than a same-day-replacement test."""
    return (_FIXTURE_EPOCH + datetime.timedelta(days=n)).isoformat()


def _fixture_report(n):
    return {"schema_version": 1, "report_date": _fixture_day(n),
            "waste_shares": {"unknown": 100}}


def test_outbox_evicts_oldest_past_the_cap():
    # RED: without eviction (bypassing queue_report's cap check by writing
    # files directly the way it does internally, minus the cap logic),
    # nothing stops the outbox from growing past OUTBOX_CAP.
    with tempfile.TemporaryDirectory() as d:
        for n in range(sig.OUTBOX_CAP + 1):
            path = os.path.join(d, f"{n:08d}-x.json")
            with open(path, "wb") as f:
                f.write(sig.serialize(_fixture_report(n)))
        assert len(sig._outbox_files(d)) == sig.OUTBOX_CAP + 1  # 91, uncapped

    # GREEN: the real queue_report() path caps at OUTBOX_CAP and evicts the
    # oldest (lowest sequence number) first.
    with tempfile.TemporaryDirectory() as d:
        for n in range(sig.OUTBOX_CAP + 1):
            sig.queue_report(_fixture_report(n), outbox_dir=d)
        files = sig._outbox_files(d)
        assert len(files) == sig.OUTBOX_CAP
        # The oldest (n=0) is gone; the newest (n=OUTBOX_CAP) survived.
        with open(files[0], "rb") as f:
            oldest_left = json.loads(f.read())
        with open(files[-1], "rb") as f:
            newest = json.loads(f.read())
        assert oldest_left["report_date"] == _fixture_day(1)
        assert newest["report_date"] == _fixture_day(sig.OUTBOX_CAP)


def test_outbox_stays_at_cap_when_filled_exactly():
    with tempfile.TemporaryDirectory() as d:
        for n in range(sig.OUTBOX_CAP):
            sig.queue_report(_fixture_report(n), outbox_dir=d)
        assert len(sig._outbox_files(d)) == sig.OUTBOX_CAP


# (e) preview bytes equal the stored payload bytes exactly ------------------

def _capture_preview(outbox_dir):
    """Run cmd_preview(outbox_dir) with sys.stdout swapped for an in-memory
    buffer, and return (returncode, raw_bytes_written). cmd_preview writes to
    sys.stdout.buffer directly (never print()), so this captures the exact
    bytes rather than going through any text encode/decode step that could
    hide a byte-level mismatch."""
    import io
    import sys
    buf = io.BytesIO()
    real_stdout = sys.stdout

    class _Wrap:
        buffer = buf

    sys.stdout = _Wrap()
    try:
        rc = sig.cmd_preview(outbox_dir)
    finally:
        sys.stdout = real_stdout
    return rc, buf.getvalue()


def _capture_stderr(fn, *args, **kwargs):
    """Run fn(*args, **kwargs) with sys.stderr swapped for an in-memory text
    buffer; return (result, captured_text). Mirrors _capture_preview above,
    for the refusal-line assertions below."""
    import io
    import sys
    buf = io.StringIO()
    real_stderr = sys.stderr
    sys.stderr = buf
    try:
        result = fn(*args, **kwargs)
    finally:
        sys.stderr = real_stderr
    return result, buf.getvalue()


def test_preview_prints_exact_stored_bytes():
    with tempfile.TemporaryDirectory() as d:
        report = {"schema_version": 1, "report_date": "2026-08-10",
                  "waste_shares": {"startup_rent": 20, "unknown": 40}}
        path = sig.queue_report(report, outbox_dir=d)
        with open(path, "rb") as f:
            stored_bytes = f.read()
        rc, printed = _capture_preview(d)
    assert rc == 0
    assert stored_bytes == sig.serialize(report)
    assert printed == stored_bytes


def test_preview_on_empty_outbox_is_no_data():
    with tempfile.TemporaryDirectory() as d:
        empty = os.path.join(d, "empty-outbox")
        rc, printed = _capture_preview(empty)
    assert rc == 2
    assert printed == b""  # nothing on stdout; NO DATA goes to stderr


def test_preview_picks_the_newest_when_several_are_queued():
    with tempfile.TemporaryDirectory() as d:
        for n in range(3):
            sig.queue_report(_fixture_report(n), outbox_dir=d)
        newest_path = sig._outbox_files(d)[-1]
        with open(newest_path, "rb") as f:
            expected = f.read()
        rc, printed = _capture_preview(d)
    assert rc == 0
    assert printed == expected


# (f) absent or unparseable ledger yields NO DATA ----------------------------

def test_absent_ledger_yields_no_data():
    with tempfile.TemporaryDirectory() as d:
        missing = os.path.join(d, "does-not-exist.jsonl")
        assert sig.build_candidate(missing, "2026-08-10") is None
        assert sig.build_report(missing, "2026-08-10") is None


def test_unparseable_ledger_yields_no_data_never_a_fabricated_report():
    with tempfile.TemporaryDirectory() as d:
        ledger = os.path.join(d, "ledger.jsonl")
        with open(ledger, "w") as f:
            f.write("not json at all\n")
            f.write('{"recorded_at": "2026-08-10T09:00:00", "input": truncated\n')
            f.write("\n")  # a blank line, also tolerated
        assert sig.build_candidate(ledger, "2026-08-10") is None
        assert sig.build_report(ledger, "2026-08-10") is None


def test_day_with_zero_token_rows_yields_no_data_not_a_zero_report():
    with tempfile.TemporaryDirectory() as d:
        ledger = os.path.join(d, "ledger.jsonl")
        _write_ledger(ledger, [
            _row("2026-08-10T09:00:00", input=0, cache_read=0, first_request=0, calls=1),
        ])
        assert sig.build_candidate(ledger, "2026-08-10") is None


# waste_shares computation, direct check -------------------------------------

def test_startup_rent_and_cache_cold_rebuilds_computed_from_ledger_fields():
    with tempfile.TemporaryDirectory() as d:
        ledger = os.path.join(d, "ledger.jsonl")
        # raw_input = input + cache_read + write_5m + write_1h + write_unsplit
        #           = 100 + 700 + 200 + 0 + 0 = 1000
        # startup_paid = first_request * calls = 100 * 2 = 200 -> 20%
        # write_total = 200 -> 20%
        _write_ledger(ledger, [
            _row("2026-08-10T09:00:00", input=100, cache_read=700,
                 cache_write_5m=200, first_request=100, calls=2),
        ])
        report = sig.build_report(ledger, "2026-08-10")
    ws = report["waste_shares"]
    assert ws["startup_rent"] == 20
    assert ws["cache_cold_rebuilds"] == 20
    assert ws["unknown"] == 60


# (g) value-level checks in _project, finding 1 -------------------------------

def test_non_conforming_leaf_values_are_dropped_not_copied_or_guessed():
    schema = sig._load_schema()
    candidate = {
        "schema_version": 2,               # wrong: const is 1
        "report_date": "08/10/2026",       # wrong: pattern mismatch
        "environment": {
            "platform": "windows98",       # wrong: not in enum
        },
        "waste_shares": {
            "startup_rent": 23,            # wrong: not a multiple of 5
            "unknown": 150,                # wrong: over the maximum
            "cache_cold_rebuilds": 40,     # valid: should survive
        },
    }
    projected = sig._project(schema, candidate)
    assert "schema_version" not in projected
    assert "report_date" not in projected
    assert "platform" not in projected["environment"]
    assert "startup_rent" not in projected["waste_shares"]
    assert "unknown" not in projected["waste_shares"]
    assert projected["waste_shares"]["cache_cold_rebuilds"] == 40


def test_dict_or_list_under_a_scalar_typed_key_is_dropped():
    schema = sig._load_schema()
    candidate = {
        "schema_version": {"nested": "dict, not the required integer"},
        "report_date": ["a", "list", "not", "a", "string"],
    }
    projected = sig._project(schema, candidate)
    assert "schema_version" not in projected
    assert "report_date" not in projected


# (h) fail closed on schema shape, finding 2 -----------------------------------

def test_object_node_recognized_without_explicit_type_annotation():
    schema = json.loads(json.dumps(sig._load_schema()))  # deep copy
    assert schema["properties"]["environment"]["type"] == "object"
    del schema["properties"]["environment"]["type"]
    candidate = {
        "schema_version": 1,
        "report_date": "2026-08-10",
        "environment": {"platform": "mac", "leak_me": "should not survive"},
    }
    projected = sig._project(schema, candidate)
    assert "leak_me" not in projected["environment"]
    assert projected["environment"]["platform"] == "mac"


# (i) schema tightening on version fields, finding 3 ---------------------------

def test_schema_tightened_version_fields_drop_when_non_conforming():
    schema = sig._load_schema()
    candidate = {
        "schema_version": 1,
        "report_date": "2026-08-10",
        "environment": {
            "platform": "mac",
            "token_shield_version": "1.8.0-dev",     # not X.Y.Z
            "claude_code_minor_version": "1.8-beta",  # not X.Y
        },
    }
    projected = sig._project(schema, candidate)
    assert "token_shield_version" not in projected["environment"]
    assert "claude_code_minor_version" not in projected["environment"]

    candidate["environment"]["token_shield_version"] = "1.8.0"
    candidate["environment"]["claude_code_minor_version"] = "1.8"
    projected = sig._project(schema, candidate)
    assert projected["environment"]["token_shield_version"] == "1.8.0"
    assert projected["environment"]["claude_code_minor_version"] == "1.8"


# (j) cmd_rollup refuses a non-conforming --day, finding 4 --------------------

def test_rollup_refuses_the_literal_bad_day_from_the_done_check():
    with tempfile.TemporaryDirectory() as d:
        outbox = os.path.join(d, "outbox")
        rc, err = _capture_stderr(sig.cmd_rollup, "not-a-date", "/dev/null", outbox)
    assert rc == 2
    assert "not-a-date" in err
    assert not os.path.isdir(outbox)  # refused before the outbox was ever touched


def test_rollup_refuses_a_path_like_day_instead_of_crashing_in_queue_report():
    # RED calibration: pre-fix, a day string containing a slash sails past
    # cmd_rollup unchecked, reaches build_candidate (which matches ledger
    # rows on recorded_at[:10] == day, slash and all), produces a real
    # candidate, and queue_report then embeds the raw day in a filename
    # ("00000000-2026/08/10.json"), which raises FileNotFoundError because
    # the "00000000-2026" path component does not exist as a directory.
    with tempfile.TemporaryDirectory() as d:
        ledger = os.path.join(d, "ledger.jsonl")
        bad_day = "2026/08/10"
        _write_ledger(ledger, [
            _row(bad_day + "T09:00:00", input=100, cache_read=900,
                 first_request=100, calls=5),
        ])
        outbox = os.path.join(d, "outbox")
        rc, err = _capture_stderr(sig.cmd_rollup, bad_day, ledger, outbox)
    assert rc == 2
    assert bad_day in err


# (k) non-finite ledger constants and computed shares, finding 5 --------------

def test_ledger_row_with_infinity_or_nan_token_is_skipped_like_malformed():
    with tempfile.TemporaryDirectory() as d:
        ledger = os.path.join(d, "ledger.jsonl")
        with open(ledger, "w") as f:
            f.write(json.dumps(_row("2026-08-10T09:00:00", input=100,
                                     cache_read=900, first_request=100, calls=5)) + "\n")
            # json.loads accepts a literal Infinity/NaN token by default
            # (not standard JSON); pre-fix these rows silently join the
            # aggregate and corrupt total_raw with a non-finite value.
            f.write('{"recorded_at": "2026-08-10T10:00:00", "input": Infinity, '
                     '"cache_read": 100, "first_request": 10, "calls": 1}\n')
            f.write('{"recorded_at": "2026-08-10T11:00:00", "input": NaN, '
                     '"cache_read": 100, "first_request": 10, "calls": 1}\n')
        rows = list(sig._day_rows(ledger, "2026-08-10"))
    assert len(rows) == 1
    assert rows[0]["input"] == 100


def test_non_finite_computed_share_is_absent_not_quantized():
    assert sig._share_or_absent(float("nan")) is None
    assert sig._share_or_absent(float("inf")) is None
    assert sig._share_or_absent(float("-inf")) is None
    assert sig._share_or_absent(0.2) == 20
    assert sig._share_or_absent(0.0) == 0


# (l) cmd_preview validates the stored file before printing, finding 6 --------

def test_preview_refuses_a_stored_file_that_fails_schema_projection():
    with tempfile.TemporaryDirectory() as d:
        # Bypass queue_report entirely: write a payload straight to the
        # outbox the way corruption, or a future bug, might.
        bad = {"schema_version": 1, "report_date": "2026-08-10",
               "waste_shares": {"unknown": 40}, "leaked_field": "should not print"}
        path = os.path.join(d, "00000000-2026-08-10.json")
        with open(path, "wb") as f:
            f.write(sig.serialize(bad))
        rc, printed = _capture_preview(d)
    assert rc == 1
    assert printed == b""


def test_preview_accepts_a_stored_file_that_matches_its_projection():
    with tempfile.TemporaryDirectory() as d:
        report = {"schema_version": 1, "report_date": "2026-08-10",
                  "waste_shares": {"unknown": 40}}
        sig.queue_report(report, outbox_dir=d)
        rc, printed = _capture_preview(d)
    assert rc == 0
    assert printed == sig.serialize(report)


# (m) duplicate days replace, finding 7 ----------------------------------------

def test_queueing_same_day_twice_replaces_not_duplicates():
    with tempfile.TemporaryDirectory() as d:
        report1 = {"schema_version": 1, "report_date": "2026-03-01",
                   "waste_shares": {"unknown": 40}}
        report2 = {"schema_version": 1, "report_date": "2026-03-01",
                   "waste_shares": {"unknown": 60}}
        sig.queue_report(report1, outbox_dir=d)
        sig.queue_report(report2, outbox_dir=d)
        files = sig._outbox_files(d)
        assert len(files) == 1
        with open(files[0], "rb") as f:
            stored = json.loads(f.read())
        assert stored["waste_shares"]["unknown"] == 60


# (n) outbox hygiene: restrictive permissions, finding 8 -----------------------

def test_outbox_dir_and_files_have_restrictive_permissions():
    with tempfile.TemporaryDirectory() as d:
        outbox = os.path.join(d, "outbox")
        report = {"schema_version": 1, "report_date": "2026-04-01",
                  "waste_shares": {"unknown": 20}}
        path = sig.queue_report(report, outbox_dir=outbox)
        dir_mode = stat.S_IMODE(os.stat(outbox).st_mode)
        file_mode = stat.S_IMODE(os.stat(path).st_mode)
    assert dir_mode == 0o700, oct(dir_mode)
    assert file_mode == 0o600, oct(file_mode)


# (o) the rollup NO DATA message shortens home to "~", finding 9 --------------

def test_rollup_no_data_message_uses_tilde_for_home_not_the_account_name():
    with tempfile.TemporaryDirectory() as fake_home:
        old_home = os.environ.get("HOME")
        os.environ["HOME"] = fake_home
        try:
            ledger = os.path.join(fake_home, "does-not-exist.jsonl")
            outbox = os.path.join(fake_home, "outbox")
            rc, err = _capture_stderr(sig.cmd_rollup, "2026-08-10", ledger, outbox)
        finally:
            if old_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = old_home
    assert rc == 2
    assert fake_home not in err
    assert "~/does-not-exist.jsonl" in err


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
