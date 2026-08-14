#!/usr/bin/env python3
"""Self-check for fleet_dashboard.py, Fleet F3 (the read and render side).
No framework, no fixtures beyond a temp directory laid out like a fleet
store.

    python3 scripts/test_fleet_dashboard.py

Every test builds its own fixture store under a temp dir, never a real
~/.token-shield/ checkout, and never runs git (fleet_dashboard.py is
read-only by design; nothing here spawns a subprocess).
"""

import json
import os
import shutil
import sys
import tempfile

import fleet as fl
import fleet_dashboard as fd

HERE = os.path.dirname(os.path.abspath(__file__))


def _write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


def _machine_path(store_dir, org, machine_id, date):
    return os.path.join(store_dir, "fleet", org, machine_id, f"{date}.json")


def _healthy_record(date, machine_id="a" * 64, team="ios", environment="ci",
                    input_tokens=100, output_tokens=50, cache_read=900,
                    cache_write=25, experiments=None):
    return {
        "schema": 1,
        "date": date,
        "machine_id": machine_id,
        "team": team,
        "environment": environment,
        "counters": {
            "unknown": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_read_input_tokens": cache_read,
                "cache_creation_input_tokens": cache_write,
            }
        },
        "experiments": experiments or [],
    }


def _write_record(store_dir, org, machine_id, date, record):
    path = _machine_path(store_dir, org, machine_id, date)
    _write(path, json.dumps(record))
    return path


# --- (a) two healthy machines render correctly, aggregated -------------------

def test_two_healthy_machines_aggregate_by_day_team_and_environment():
    with tempfile.TemporaryDirectory() as d:
        _write_record(d, "acme", "aaaa", "2026-08-10",
                     _healthy_record("2026-08-10", "aaaa", team="ios", environment="ci",
                                     input_tokens=100, output_tokens=50,
                                     cache_read=900, cache_write=25))
        _write_record(d, "acme", "bbbb", "2026-08-10",
                     _healthy_record("2026-08-10", "bbbb", team="web", environment="prod",
                                     input_tokens=200, output_tokens=75,
                                     cache_read=300, cache_write=10))
        rows, empty = fd.collect_org(d, "acme")
        assert len(rows) == 2
        assert empty == []
        healthy = [r for r in rows if r["error"] is None]
        assert len(healthy) == 2

        by_day = fd.aggregate_counters_by_day(healthy)
        assert by_day["2026-08-10"]["unknown"]["input_tokens"] == 300
        assert by_day["2026-08-10"]["unknown"]["output_tokens"] == 125

        by_team = fd.aggregate_totals_by_tag(healthy, "team")
        assert by_team["ios"] == 100 + 50 + 900 + 25
        assert by_team["web"] == 200 + 75 + 300 + 10

        by_env = fd.aggregate_totals_by_tag(healthy, "environment")
        assert by_env["ci"] == 100 + 50 + 900 + 25
        assert by_env["prod"] == 200 + 75 + 300 + 10

        body = fd.render(d, "acme", "2026-08-15 09:00")
        assert "aaaa" in body
        assert "bbbb" in body
        assert "ios" in body
        assert "web" in body


# --- (b) hostile fixture: not valid JSON --------------------------------------

def test_invalid_json_record_gets_its_own_no_data_row_other_machine_still_renders():
    with tempfile.TemporaryDirectory() as d:
        _write(_machine_path(d, "acme", "bad-json", "2026-08-10"), "{not json at all")
        _write_record(d, "acme", "healthy", "2026-08-10",
                     _healthy_record("2026-08-10", "healthy"))
        rows, empty = fd.collect_org(d, "acme")
        bad = [r for r in rows if r["machine_id"] == "bad-json"][0]
        healthy_row = [r for r in rows if r["machine_id"] == "healthy"][0]
        assert bad["error"] is not None
        # RED before the fix: _load_one let json.JSONDecodeError propagate out
        # of collect_org instead of catching it, so this assertion (the error
        # is captured on the row, not raised) is what would fail.
        assert "invalid JSON" in bad["error"]
        assert healthy_row["error"] is None

        body = fd.render(d, "acme", "stamp")
        assert "bad-json" in body
        assert "invalid JSON" in body
        assert "healthy" in body


# --- (c) hostile fixture: schema newer than this reader understands ----------

def test_newer_schema_record_gets_its_own_no_data_row():
    with tempfile.TemporaryDirectory() as d:
        _write_record(d, "acme", "future", "2026-08-10",
                     {"schema": fl.SCHEMA_VERSION + 1, "date": "2026-08-10"})
        _write_record(d, "acme", "healthy", "2026-08-10",
                     _healthy_record("2026-08-10", "healthy"))
        rows, _empty = fd.collect_org(d, "acme")
        bad = [r for r in rows if r["machine_id"] == "future"][0]
        assert bad["error"] is not None
        assert "newer" in bad["error"]
        healthy_row = [r for r in rows if r["machine_id"] == "healthy"][0]
        assert healthy_row["error"] is None


# --- (d) hostile fixture: missing required field ------------------------------

def test_record_missing_required_field_gets_its_own_no_data_row():
    with tempfile.TemporaryDirectory() as d:
        _write_record(d, "acme", "no-date", "2026-08-10", {"schema": 1})
        rows, _empty = fd.collect_org(d, "acme")
        bad = rows[0]
        assert bad["error"] is not None
        # RED before the fix: _validate_record_shape did not exist and a
        # record missing "date" loaded cleanly (fleet.load_record does not
        # itself require "date"), so this exact string would not appear.
        assert bad["error"] == "missing required field: date"


# --- (e) hostile fixture: experiment label containing HTML --------------------

def test_experiment_label_with_html_is_escaped_not_injected():
    with tempfile.TemporaryDirectory() as d:
        record = _healthy_record(
            "2026-08-10", "aaaa",
            experiments=[{
                "label": "<script>alert(1)</script>",
                "confidence": "VERIFIED",
                "timestamp": "2026-08-10T12:00:00",
                "target_metric": "first_request_median",
                "metric_delta": 1000,
                "direction": "saving",
            }])
        _write_record(d, "acme", "aaaa", "2026-08-10", record)
        body = fd.render(d, "acme", "stamp")
        # RED before the fix: rendering the raw label instead of ts.esc(...)
        # would put the literal tag into the page, so this assertion (the
        # raw tag is absent) is the one a missing esc() call would fail.
        assert "<script>alert(1)</script>" not in body
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body


# --- (f) hostile fixture: machine directory with no records at all -----------

def test_machine_directory_with_no_records_gets_its_own_no_data_row():
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "fleet", "acme", "empty-machine"))
        _write_record(d, "acme", "healthy", "2026-08-10",
                     _healthy_record("2026-08-10", "healthy"))
        rows, empty = fd.collect_org(d, "acme")
        assert empty == ["empty-machine"]
        healthy = [r for r in rows if r["error"] is None]
        assert len(healthy) == 1

        body = fd.render(d, "acme", "stamp")
        assert "empty-machine" in body
        assert "no records found for this machine" in body


# --- (g) hostile fixture: negative counter ------------------------------------

def test_negative_counter_gets_its_own_no_data_row():
    with tempfile.TemporaryDirectory() as d:
        bad = _healthy_record("2026-08-10", "aaaa", input_tokens=-5)
        _write_record(d, "acme", "aaaa", "2026-08-10", bad)
        rows, _empty = fd.collect_org(d, "acme")
        row = rows[0]
        assert row["error"] is not None
        # RED before the fix: minimum:0 in data/fleet.schema.json documents
        # the constraint but fleet.load_record does not itself enforce it
        # (fl.load_record only checks the top-level "schema" field), so a
        # record with a negative counter would load cleanly and this exact
        # string would never appear.
        assert row["error"] == "negative token count in counters.unknown.input_tokens"


# --- (h) one hostile record never removes another machine's row --------------

def test_all_six_hostile_fixtures_alongside_two_healthy_machines_in_one_render():
    with tempfile.TemporaryDirectory() as d:
        _write(_machine_path(d, "acme", "not-json", "2026-08-10"), "{broken")
        _write_record(d, "acme", "future-schema", "2026-08-10",
                     {"schema": fl.SCHEMA_VERSION + 1, "date": "2026-08-10"})
        _write_record(d, "acme", "missing-field", "2026-08-10", {"schema": 1})
        _write_record(d, "acme", "negative-counter", "2026-08-10",
                     _healthy_record("2026-08-10", "negative-counter", input_tokens=-1))
        os.makedirs(os.path.join(d, "fleet", "acme", "no-records"))
        _write_record(d, "acme", "html-label", "2026-08-10",
                     _healthy_record("2026-08-10", "html-label", experiments=[{
                         "label": "<b>x</b>", "confidence": "VERIFIED",
                         "timestamp": "2026-08-10T00:00:00"}]))
        _write_record(d, "acme", "healthy-one", "2026-08-10",
                     _healthy_record("2026-08-10", "healthy-one", team="ios"))
        _write_record(d, "acme", "healthy-two", "2026-08-11",
                     _healthy_record("2026-08-11", "healthy-two", team="web"))

        rows, empty = fd.collect_org(d, "acme")
        assert len(rows) == 7  # every machine except no-records wrote one file
        assert empty == ["no-records"]
        bad = {r["machine_id"]: r["error"] for r in rows if r["error"] is not None}
        assert set(bad) == {"not-json", "future-schema", "missing-field", "negative-counter"}
        healthy_ids = {r["machine_id"] for r in rows if r["error"] is None}
        assert healthy_ids == {"html-label", "healthy-one", "healthy-two"}

        body = fd.render(d, "acme", "stamp")
        for mid in ("not-json", "future-schema", "missing-field", "negative-counter",
                   "no-records", "html-label", "healthy-one", "healthy-two"):
            assert mid in body
        assert "&lt;b&gt;x&lt;/b&gt;" in body
        assert "<b>x</b>" not in body


# --- (i) experiments: latest per label, never summed, regression stays negative

def test_latest_experiment_per_label_never_summed_across_labels_or_runs():
    with tempfile.TemporaryDirectory() as d:
        _write_record(d, "acme", "aaaa", "2026-08-10",
                     _healthy_record("2026-08-10", "aaaa", experiments=[
                         {"label": "claude-md-diet", "confidence": "VERIFIED",
                          "timestamp": "2026-08-10T09:00:00", "metric_delta": 1000,
                          "direction": "saving"},
                         {"label": "companion-x", "confidence": "NOT_PROVEN",
                          "timestamp": "2026-08-10T09:00:00", "metric_delta": -500,
                          "direction": "regression"},
                     ]))
        _write_record(d, "acme", "bbbb", "2026-08-11",
                     _healthy_record("2026-08-11", "bbbb", experiments=[
                         # Same label as aaaa's, later timestamp: this one wins,
                         # it does not add to the earlier run's 1000.
                         {"label": "claude-md-diet", "confidence": "VERIFIED",
                          "timestamp": "2026-08-11T09:00:00", "metric_delta": 1500,
                          "direction": "saving"},
                     ]))
        rows, _empty = fd.collect_org(d, "acme")
        healthy = [r for r in rows if r["error"] is None]
        items = fd.latest_experiment_by_label(healthy)
        by_label = {i["label"]: i for i in items}

        assert len(items) == 2
        # RED before the fix: a naive implementation might sum metric_delta
        # for repeated labels (1000 + 1500 = 2500), or drop the earlier
        # timestamp check and keep the wrong record. This is the exact
        # assertion that catches either mistake.
        assert by_label["claude-md-diet"]["metric_delta"] == 1500
        assert by_label["claude-md-diet"]["timestamp"] == "2026-08-11T09:00:00"
        # A regression stays negative, never clipped to zero.
        assert by_label["companion-x"]["metric_delta"] == -500
        assert by_label["companion-x"]["direction"] == "regression"

        body = fd.render(d, "acme", "stamp")
        assert "-500" in body
        assert "+1,500" in body
        # The earlier claude-md-diet run's own delta must not appear as a
        # second row: only one row per label survives to the render.
        assert body.count("claude-md-diet") == 1


# --- (j) empty store: no crash, all NO DATA -----------------------------------

def test_empty_store_renders_no_data_everywhere_no_crash():
    with tempfile.TemporaryDirectory() as d:
        rows, empty = fd.collect_org(d, "acme")
        assert rows == []
        assert empty == []
        body = fd.render(d, "acme", "stamp")
        assert "NO DATA" in body
        assert "acme" in body


# --- (k) label helpers are the imported ones, not a local re-implementation --
#
# Note: this identity check alone let the F3 fix-round's finding 5 slip
# through review once already: it proves fleet_dashboard.py IMPORTS
# token_shield.verified_by_label, but says nothing about whether anything
# actually CALLS it instead of keeping a second, drifted copy of its
# tiebreak. test_tied_timestamp_across_machines_matches_verified_by_labels_tiebreak
# below is the behavioral test that closes that gap.

def test_label_helpers_are_imported_from_token_shield_not_reimplemented():
    import token_shield as ts
    assert fd.ts.esc is ts.esc
    assert fd.ts.human is ts.human
    assert fd.ts.pct is ts.pct
    assert fd.ts._cpill is ts._cpill
    assert fd.ts.verified_by_label is ts.verified_by_label


# --- (l) finding 5: the tiebreak must match token_shield.verified_by_label's
# own rule (newest timestamp; on a tie, last-seen in iteration order wins),
# not the inverted first-seen-wins rule the old local copy had drifted to.

def test_tied_timestamp_across_machines_matches_verified_by_labels_tiebreak():
    with tempfile.TemporaryDirectory() as d:
        _write_record(d, "acme", "aaaa", "2026-08-10",
                     _healthy_record("2026-08-10", "aaaa", experiments=[
                         {"label": "tied-label", "confidence": "VERIFIED",
                          "timestamp": "2026-08-10T09:00:00", "metric_delta": 100,
                          "direction": "saving"},
                     ]))
        _write_record(d, "acme", "bbbb", "2026-08-10",
                     _healthy_record("2026-08-10", "bbbb", experiments=[
                         {"label": "tied-label", "confidence": "VERIFIED",
                          "timestamp": "2026-08-10T09:00:00", "metric_delta": 200,
                          "direction": "saving"},
                     ]))
        rows, _empty = fd.collect_org(d, "acme")
        healthy = [r for r in rows if r["error"] is None]
        items = fd.latest_experiment_by_label(healthy)
        by_label = {i["label"]: i for i in items}
        # RED before the fix: the old local tiebreak kept whichever row was
        # seen FIRST on a tied timestamp (rows walked in sorted machine_id
        # order, "aaaa" before "bbbb"), so it kept "aaaa" with metric_delta
        # 100. token_shield.verified_by_label's own rule keeps whichever is
        # seen LAST on a tie, so "bbbb" (walked after "aaaa") must win with
        # metric_delta 200 -- the opposite answer from the pre-fix code.
        assert by_label["tied-label"]["metric_delta"] == 200
        assert by_label["tied-label"]["machine_id"] == "bbbb"


# --- (m) finding 6: a record's own "date" must agree with the filename it --
# was found at.

def test_filename_date_disagreeing_with_record_date_gets_its_own_no_data_row():
    with tempfile.TemporaryDirectory() as d:
        # The record's OWN "date" field says 2026-08-11, but it is filed
        # under 2026-08-10.json.
        record = _healthy_record("2026-08-11", "aaaa")
        _write_record(d, "acme", "aaaa", "2026-08-10", record)
        rows, _empty = fd.collect_org(d, "acme")
        row = rows[0]
        # RED before the fix: the record's own "date" field was trusted
        # as-is, with nothing checking it against the filename it was found
        # at, so this row would have loaded cleanly with error=None and
        # date="2026-08-10" while record["date"]=="2026-08-11", letting the
        # same record render under two different dates in two tables on one
        # page.
        assert row["error"] is not None
        assert "disagrees" in row["error"]


# --- (n) finding 4: org-profile.json is not a machine entry; anything else --
# non-directory found where a machine directory was expected gets its own row.

def test_org_profile_json_sibling_is_skipped_not_treated_as_a_machine():
    with tempfile.TemporaryDirectory() as d:
        org_dir = os.path.join(d, "fleet", "acme")
        os.makedirs(org_dir)
        _write(os.path.join(org_dir, "org-profile.json"), "{}")
        _write_record(d, "acme", "healthy", "2026-08-10",
                     _healthy_record("2026-08-10", "healthy"))
        rows, _empty = fd.collect_org(d, "acme")
        assert len(rows) == 1
        assert rows[0]["machine_id"] == "healthy"


def test_machine_entry_replaced_by_plain_file_gets_its_own_no_data_row():
    with tempfile.TemporaryDirectory() as d:
        org_dir = os.path.join(d, "fleet", "acme")
        os.makedirs(org_dir)
        with open(os.path.join(org_dir, "not-a-directory"), "wb") as f:
            f.write(b"just a file, not a machine directory")
        _write_record(d, "acme", "healthy", "2026-08-10",
                     _healthy_record("2026-08-10", "healthy"))
        rows, _empty = fd.collect_org(d, "acme")
        bad = [r for r in rows if r["machine_id"] == "not-a-directory"]
        healthy_row = [r for r in rows if r["machine_id"] == "healthy"][0]
        # RED before the fix: `if not os.path.isdir(machine_dir): continue`
        # skipped this entry with no row appended at all, so `bad` would be
        # an empty list here instead of holding one NO DATA row.
        assert len(bad) == 1
        assert bad[0]["error"] is not None
        assert "not a directory" in bad[0]["error"]
        assert healthy_row["error"] is None


# --- (o) finding 3: --org is refused before it ever reaches a filesystem ----
# path or the page <title>.

def test_main_refuses_hostile_org_before_touching_the_filesystem():
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "out.html")
        argv_backup = sys.argv
        try:
            for hostile_org in ("acme</title><script>alert(1)</script>",
                                "../../elsewhere"):
                sys.argv = ["fleet_dashboard.py", "--store-dir", d, "--org", hostile_org,
                           "--out", out]
                rc = fd.main()
                # RED before the fix: main() never validated --org at all,
                # so this returned 0 (an empty-store NO DATA page written to
                # `out`, with the raw hostile string interpolated straight
                # into the page <title> for the script-tag case, or used
                # as-is to build a path for the traversal case) instead of
                # refusing with rc 2 and writing nothing.
                assert rc == 2
                assert not os.path.exists(out)
        finally:
            sys.argv = argv_backup


def test_render_standalone_title_is_escaped_defense_in_depth():
    import token_shield as ts
    html = ts.render_standalone("<body/>", title="acme</title><script>alert(1)</script>")
    # RED before the fix: render_standalone interpolated `title` raw into
    # the page, so the literal "<script>alert(1)</script>" tag would appear
    # inside <head>, live. fleet_dashboard.py's own --org validation (see
    # the test above) already refuses this string before it would reach
    # here in practice; this is the second, independent layer.
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


# --- (p) hostile fixtures written as raw BYTES, never json.dumps -------------
#
# Every fixture above this point was written by json.dumps, which cannot
# produce invalid UTF-8, cannot produce a bare NaN/Infinity JSON literal (a
# real Python object 200,000 lists deep cannot even be BUILT without hitting
# CPython's own recursion limit, let alone serialized), and will not produce
# an oversized file or a symlink. That gap is exactly why five real findings
# (criticals 1-3, the symlink escape, the file-cap gap) survived eleven
# passing tests in the original F3 submission. These fixtures are written
# with plain open(path, "wb") instead.

def test_invalid_utf8_bytes_get_their_own_no_data_row():
    with tempfile.TemporaryDirectory() as d:
        path = _machine_path(d, "acme", "bad-bytes", "2026-08-10")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"\xff\xfe\x00\x01binary")
        _write_record(d, "acme", "healthy", "2026-08-10",
                     _healthy_record("2026-08-10", "healthy"))
        rows, _empty = fd.collect_org(d, "acme")
        bad = [r for r in rows if r["machine_id"] == "bad-bytes"][0]
        healthy_row = [r for r in rows if r["machine_id"] == "healthy"][0]
        # RED before the fix: _load_one caught only OSError,
        # json.JSONDecodeError, and fl.FleetSchemaError. fl.load_record's
        # `with open(path) as f: json.load(f)` decodes as UTF-8 by default,
        # so this file raised
        #   UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff in
        #   position 0: invalid start byte
        # which is none of those three types, so it propagated straight out
        # of collect_org and killed the whole org render.
        assert bad["error"] is not None
        assert "unreadable record" in bad["error"]
        assert healthy_row["error"] is None

        body = fd.render(d, "acme", "stamp")
        assert "bad-bytes" in body
        assert "healthy" in body


def test_nan_counter_gets_its_own_no_data_row():
    with tempfile.TemporaryDirectory() as d:
        path = _machine_path(d, "acme", "nan-counter", "2026-08-10")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        raw = ('{"schema": 1, "date": "2026-08-10", "machine_id": "' + "a" * 64 + '", '
              '"counters": {"unknown": {"input_tokens": 10, "output_tokens": NaN, '
              '"cache_read_input_tokens": 5, "cache_creation_input_tokens": 1}}, '
              '"experiments": []}')
        with open(path, "wb") as f:
            f.write(raw.encode("utf-8"))
        _write_record(d, "acme", "healthy", "2026-08-10",
                     _healthy_record("2026-08-10", "healthy"))
        rows, _empty = fd.collect_org(d, "acme")
        bad = [r for r in rows if r["machine_id"] == "nan-counter"][0]
        healthy_row = [r for r in rows if r["machine_id"] == "healthy"][0]
        # RED before the fix: json.load accepts a bare NaN token by default
        # (Python's json module treats it as a non-standard extension, not
        # an error), so this record loaded cleanly with error=None. It then
        # passed every "< 0" comparison in the old _validate_record_shape
        # silently (NaN < 0 is False), reached ts.human() by way of
        # _record_total's summation, and raised
        #   ValueError: cannot convert float NaN to integer
        # from inside int(n) the first time a table tried to render it.
        assert bad["error"] is not None
        assert "non-finite" in bad["error"]
        assert healthy_row["error"] is None

        body = fd.render(d, "acme", "stamp")
        assert "nan-counter" in body
        assert "healthy" in body


def test_stack_exhausting_nested_array_gets_its_own_no_data_row():
    with tempfile.TemporaryDirectory() as d:
        path = _machine_path(d, "acme", "deep-nest", "2026-08-10")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        raw = ("[" * 200000) + ("]" * 200000)
        with open(path, "wb") as f:
            f.write(raw.encode("utf-8"))
        assert os.path.getsize(path) < fd.MAX_RECORD_BYTES  # exercises the
                                                             # recursion catch,
                                                             # not the size cap
        _write_record(d, "acme", "healthy", "2026-08-10",
                     _healthy_record("2026-08-10", "healthy"))
        rows, _empty = fd.collect_org(d, "acme")
        bad = [r for r in rows if r["machine_id"] == "deep-nest"][0]
        healthy_row = [r for r in rows if r["machine_id"] == "healthy"][0]
        # RED before the fix: json's recursive-descent parser raises
        # RecursionError (a RuntimeError subclass) well before it can even
        # return a value to fl.load_record's isinstance(data, dict) check.
        # _load_one caught none of OSError/json.JSONDecodeError/
        # FleetSchemaError, so this propagated out of collect_org and
        # killed the whole org render, the same as the invalid-UTF-8 case.
        assert bad["error"] is not None
        assert "unreadable record" in bad["error"]
        assert healthy_row["error"] is None


def test_oversized_record_file_is_refused_by_name_not_read_into_memory():
    with tempfile.TemporaryDirectory() as d:
        path = _machine_path(d, "acme", "too-big", "2026-08-10")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"x" * (fd.MAX_RECORD_BYTES + 100))
        _write_record(d, "acme", "healthy", "2026-08-10",
                     _healthy_record("2026-08-10", "healthy"))
        rows, _empty = fd.collect_org(d, "acme")
        bad = [r for r in rows if r["machine_id"] == "too-big"][0]
        healthy_row = [r for r in rows if r["machine_id"] == "healthy"][0]
        # RED before the fix: there was no size cap at all; _load_one went
        # straight to fl.load_record(path), which reads and json.load()s
        # the whole file regardless of size (this fixture is not even valid
        # JSON, so before the fix it would have surfaced as "invalid JSON"
        # instead of a byte-cap refusal, after reading it all into memory).
        assert bad["error"] is not None
        assert "byte cap" in bad["error"]
        assert healthy_row["error"] is None


def test_symlink_record_pointing_outside_store_is_refused():
    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as outside:
        secret_path = os.path.join(outside, "secret.json")
        # Schema-VALID on purpose: a record shaped like {"secret": ...} gets
        # rejected by fl.load_record's own "schema" field check regardless
        # of the symlink, which would make this test pass even against the
        # pre-fix code for the WRONG reason (a schema refusal, not a
        # symlink refusal). A record fl.load_record accepts cleanly is the
        # only way to prove the symlink itself is what gets refused.
        _write(secret_path, json.dumps(
            _healthy_record("2026-08-10", "b" * 64, team="should-never-be-read")))
        machine_dir = os.path.join(d, "fleet", "acme", "sym-machine")
        os.makedirs(machine_dir)
        os.symlink(secret_path, os.path.join(machine_dir, "2026-08-10.json"))
        _write_record(d, "acme", "healthy", "2026-08-10",
                     _healthy_record("2026-08-10", "healthy"))
        rows, _empty = fd.collect_org(d, "acme")
        bad = [r for r in rows if r["machine_id"] == "sym-machine"][0]
        healthy_row = [r for r in rows if r["machine_id"] == "healthy"][0]
        # RED before the fix: collect_org built `path` with a plain
        # os.path.join and handed it straight to _load_one/fl.load_record,
        # neither of which checked os.path.islink anywhere; fl.load_record's
        # plain open(path) follows a symlink like any other path, so this
        # schema-valid record would have loaded cleanly from OUTSIDE the
        # store and rendered "should-never-be-read" as this machine's team.
        assert bad["error"] is not None
        assert "refusing" in bad["error"]
        assert healthy_row["error"] is None

        body = fd.render(d, "acme", "stamp")
        assert "should-never-be-read" not in body
        assert "healthy" in body


def test_error_rows_never_publish_the_admins_home_path_to_the_org():
    """This page is a SHARED org artifact, and error rows are built from
    exception text carrying absolute paths (the symlink refusal names the
    offending path in full). Unscrubbed, opening the page tells every member
    of the org the admin's account name. The store therefore has to live
    UNDER the home directory for this test to mean anything: a store in a
    temp directory has no home prefix to leak, which is exactly why the
    original finding survived a suite whose fixtures all used tempfile."""
    home = os.path.expanduser("~")
    d = os.path.join(home, ".token-shield-test-store-scrub")
    with tempfile.TemporaryDirectory() as outside:
        try:
            secret_path = os.path.join(outside, "secret.json")
            _write(secret_path, json.dumps(
                _healthy_record("2026-08-10", "b" * 64)))
            machine_dir = os.path.join(d, "fleet", "acme", "sym-machine")
            os.makedirs(machine_dir)
            os.symlink(secret_path, os.path.join(machine_dir, "2026-08-10.json"))
            _write_record(d, "acme", "healthy", "2026-08-10",
                          _healthy_record("2026-08-10", "healthy"))
            body = fd.render(d, "acme", "stamp")
            # RED before the scrub: the symlink refusal reached the row as
            # "refusing to read: ... at /Users/<account>/.token-shield-..."
            assert home not in body, (
                "the rendered page carries the admin's home path, which "
                "publishes their account name to the whole org")
            assert "NO DATA" in body
            assert "healthy" in body
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
