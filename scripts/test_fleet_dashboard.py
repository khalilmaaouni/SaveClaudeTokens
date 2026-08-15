#!/usr/bin/env python3
"""Self-check for fleet_dashboard.py, Fleet F3 (the read and render side).
No framework, no fixtures beyond a temp directory laid out like a fleet
store.

    python3 scripts/test_fleet_dashboard.py

Every test builds its own fixture store under a temp dir, never a real
~/.token-shield/ checkout, and never runs git (fleet_dashboard.py is
read-only by design; nothing here spawns a subprocess).
"""

import datetime
import json
import os
import shutil
import sys
import tempfile

import fleet as fl
import fleet_dashboard as fd

HERE = os.path.dirname(os.path.abspath(__file__))


def _day_offset(n):
    """A YYYY-MM-DD string n days before today. Fixtures that must land
    inside (or outside) the default --days window are built relative to the
    real calendar, never hardcoded, so they do not silently fall out of the
    window as the months pass."""
    return (datetime.date.today() - datetime.timedelta(days=n)).isoformat()


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
        rows, empty, _meta = fd.collect_org(d, "acme", days=0)
        assert len(rows) == 2
        assert empty == []
        healthy = [r for r in rows if r["error"] is None]
        assert len(healthy) == 2

        by_day = fd.aggregate_counters_by_day(healthy)
        assert by_day["2026-08-10"]["totals"]["input_tokens"] == 300
        assert by_day["2026-08-10"]["totals"]["output_tokens"] == 125
        # Two distinct machines stand behind that day's cell, which is what
        # the minimum group size is checked against before it is published.
        assert by_day["2026-08-10"]["machines"] == 2

        by_team = fd.aggregate_totals_by_tag(healthy, "team")
        assert by_team["ios"]["total"] == 100 + 50 + 900 + 25
        assert by_team["web"]["total"] == 200 + 75 + 300 + 10
        assert by_team["ios"]["machines"] == 1

        by_env = fd.aggregate_totals_by_tag(healthy, "environment")
        assert by_env["ci"]["total"] == 100 + 50 + 900 + 25
        assert by_env["prod"]["total"] == 200 + 75 + 300 + 10

        body = fd.render(d, "acme", "2026-08-15 09:00", days=0)
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
        rows, empty, _meta = fd.collect_org(d, "acme", days=0)
        bad = [r for r in rows if r["machine_id"] == "bad-json"][0]
        healthy_row = [r for r in rows if r["machine_id"] == "healthy"][0]
        assert bad["error"] is not None
        # RED before the fix: _load_one let json.JSONDecodeError propagate out
        # of collect_org instead of catching it, so this assertion (the error
        # is captured on the row, not raised) is what would fail.
        assert "invalid JSON" in bad["error"]
        assert healthy_row["error"] is None

        body = fd.render(d, "acme", "stamp", days=0)
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
        rows, _empty, _meta = fd.collect_org(d, "acme", days=0)
        bad = [r for r in rows if r["machine_id"] == "future"][0]
        assert bad["error"] is not None
        assert "newer" in bad["error"]
        healthy_row = [r for r in rows if r["machine_id"] == "healthy"][0]
        assert healthy_row["error"] is None


# --- (d) hostile fixture: missing required field ------------------------------

def test_record_missing_required_field_gets_its_own_no_data_row():
    with tempfile.TemporaryDirectory() as d:
        _write_record(d, "acme", "no-date", "2026-08-10", {"schema": 1})
        rows, _empty, _meta = fd.collect_org(d, "acme", days=0)
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
        body = fd.render(d, "acme", "stamp", days=0)
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
        rows, empty, _meta = fd.collect_org(d, "acme", days=0)
        assert empty == ["empty-machine"]
        healthy = [r for r in rows if r["error"] is None]
        assert len(healthy) == 1

        body = fd.render(d, "acme", "stamp", days=0)
        assert "empty-machine" in body
        assert "no records found for this machine" in body


# --- (g) hostile fixture: negative counter ------------------------------------

def test_negative_counter_gets_its_own_no_data_row():
    with tempfile.TemporaryDirectory() as d:
        bad = _healthy_record("2026-08-10", "aaaa", input_tokens=-5)
        _write_record(d, "acme", "aaaa", "2026-08-10", bad)
        rows, _empty, _meta = fd.collect_org(d, "acme", days=0)
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

        rows, empty, _meta = fd.collect_org(d, "acme", days=0)
        assert len(rows) == 7  # every machine except no-records wrote one file
        assert empty == ["no-records"]
        bad = {r["machine_id"]: r["error"] for r in rows if r["error"] is not None}
        assert set(bad) == {"not-json", "future-schema", "missing-field", "negative-counter"}
        healthy_ids = {r["machine_id"] for r in rows if r["error"] is None}
        assert healthy_ids == {"html-label", "healthy-one", "healthy-two"}

        body = fd.render(d, "acme", "stamp", days=0)
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
        rows, _empty, _meta = fd.collect_org(d, "acme", days=0)
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

        body = fd.render(d, "acme", "stamp", days=0)
        assert "-500" in body
        assert "+1,500" in body
        # The earlier claude-md-diet run's own delta must not appear as a
        # second row: only one row per label survives to the render.
        assert body.count("claude-md-diet") == 1


# --- (j) empty store: no crash, all NO DATA -----------------------------------

def test_empty_store_renders_no_data_everywhere_no_crash():
    with tempfile.TemporaryDirectory() as d:
        rows, empty, _meta = fd.collect_org(d, "acme", days=0)
        assert rows == []
        assert empty == []
        body = fd.render(d, "acme", "stamp", days=0)
        assert "NO DATA" in body
        assert "acme" in body


# --- (k) label helpers are the imported ones, not a local re-implementation --
#
# Note: this identity check alone let the F3 fix-round's finding 5 slip
# through review once already: it proves fleet_dashboard.py IMPORTS the
# helper, but says nothing about whether anything actually CALLS it instead
# of keeping a second, drifted copy of its tiebreak.
# test_tied_timestamp_across_machines_matches_verified_by_labels_tiebreak
# below is the behavioral test that closes that gap. The pick now runs
# through latest_row_per_label (one row per label across EVERY confidence,
# which is what the page copy promises, D20), so that is the identity that
# matters here.

def test_label_helpers_are_imported_from_token_shield_not_reimplemented():
    # After the split these live in three different modules, and the point of
    # the test is unchanged: the dashboard REUSES them rather than carrying
    # its own copy of a label, a number format or a tiebreak.
    import formatting as fmt
    import metrics as met
    import token_shield as ts
    assert fd.fmt.esc is fmt.esc
    assert fd.fmt.human is fmt.human
    assert fd.fmt.pct is fmt.pct
    assert fd.ts._cpill is ts._cpill
    assert fd.met.latest_row_per_label is met.latest_row_per_label


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
        rows, _empty, _meta = fd.collect_org(d, "acme", days=0)
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
        rows, _empty, _meta = fd.collect_org(d, "acme", days=0)
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
        rows, _empty, _meta = fd.collect_org(d, "acme", days=0)
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
        rows, _empty, _meta = fd.collect_org(d, "acme", days=0)
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
        rows, _empty, _meta = fd.collect_org(d, "acme", days=0)
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

        body = fd.render(d, "acme", "stamp", days=0)
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
        rows, _empty, _meta = fd.collect_org(d, "acme", days=0)
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

        body = fd.render(d, "acme", "stamp", days=0)
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
        rows, _empty, _meta = fd.collect_org(d, "acme", days=0)
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
        rows, _empty, _meta = fd.collect_org(d, "acme", days=0)
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
        rows, _empty, _meta = fd.collect_org(d, "acme", days=0)
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

        body = fd.render(d, "acme", "stamp", days=0)
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
            body = fd.render(d, "acme", "stamp", days=0)
            # RED before the scrub: the symlink refusal reached the row as
            # "refusing to read: ... at /Users/<account>/.token-shield-..."
            assert home not in body, (
                "the rendered page carries the admin's home path, which "
                "publishes their account name to the whole org")
            assert "NO DATA" in body
            assert "healthy" in body
        finally:
            shutil.rmtree(d, ignore_errors=True)


def test_counter_too_big_for_a_float_is_one_row_not_the_whole_page():
    """RED before the fix: OverflowError: int too large to convert to float.
    _validate_record_shape was called OUTSIDE the try whose broad handler
    exists for exactly this, so math.isfinite raising on an int too big for
    a float killed every machine's row. 401 bytes, far under the size cap."""
    with tempfile.TemporaryDirectory() as d:
        _write_record(d, "acme", "healthy", "2026-08-10",
                      _healthy_record("2026-08-10", "healthy"))
        md = os.path.join(d, "fleet", "acme", "huge")
        os.makedirs(md)
        _write(os.path.join(md, "2026-08-10.json"),
               '{"schema":1,"date":"2026-08-10","counters":'
               '{"unknown":{"input_tokens":' + "1" + "0" * 400 + "}}}")
        rows, _e, _meta = fd.collect_org(d, "acme", days=0)
        healthy = [r for r in rows if r["machine_id"] == "healthy"][0]
        huge = [r for r in rows if r["machine_id"] == "huge"][0]
        assert healthy["error"] is None, "a hostile record cost a healthy machine its row"
        assert huge["error"] is not None
        body = fd.render(d, "acme", "stamp", days=0)
        assert "healthy" in body


def test_non_string_label_or_confidence_is_one_row_not_the_whole_page():
    """RED before the fix: TypeError: unhashable type: 'list'. label and
    confidence are attacker supplied and are used as a dict key, a set
    member and a sort key, so a list, a dict, or a number beside a string
    took the whole org page down with it."""
    with tempfile.TemporaryDirectory() as d:
        _write_record(d, "acme", "healthy", "2026-08-10",
                      _healthy_record("2026-08-10", "healthy"))
        for name, label, conf in (("badlist", ["x"], "VERIFIED"),
                                  ("baddict", "ok", {"k": 1}),
                                  ("badnum", 7, "VERIFIED")):
            rec = _healthy_record("2026-08-10", name)
            rec["experiments"] = [{"label": label, "confidence": conf,
                                   "metric_delta": 1.0,
                                   "timestamp": "2026-08-10T00:00:00Z"}]
            _write_record(d, "acme", name, "2026-08-10", rec)
        body = fd.render(d, "acme", "stamp", days=0)
        assert "healthy" in body, "hostile experiment fields killed the page"


def test_a_symlink_at_the_org_directory_itself_is_refused():
    """RED before the fix: the outside record rendered with no refusal.
    _refuse_symlinks_under walks components strictly BELOW its root, so
    passing org_dir as the root left fleet/<org> itself unchecked, and
    os.path.isdir follows symlinks."""
    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as outside:
        md = os.path.join(outside, "leaker")
        os.makedirs(md)
        _write(os.path.join(md, "2026-08-10.json"),
               json.dumps(_healthy_record("2026-08-10", "l" * 64,
                                          team="should-never-be-read")))
        os.makedirs(os.path.join(d, "fleet"))
        os.symlink(outside, os.path.join(d, "fleet", "acme"))
        body = fd.render(d, "acme", "stamp", days=0)
        assert "should-never-be-read" not in body, (
            "the reader escaped the store through a symlinked org directory")
        assert "NO DATA" in body


def test_the_page_is_written_as_utf8_whatever_the_locale_is():
    """RED before the fix: UnicodeEncodeError and a zero byte page. The page
    declares <meta charset="utf-8"> but plain open() encodes with the
    locale's codec, so under LC_ALL=C one non-ASCII byte anywhere in the
    store left nothing on disk. Asserted by encoding the rendered body with
    ascii, which is what a C locale would have done."""
    with tempfile.TemporaryDirectory() as d:
        rec = _healthy_record("2026-08-10", "healthy")
        rec["team"] = "東京"
        _write_record(d, "acme", "healthy", "2026-08-10", rec)
        body = fd.render(d, "acme", "stamp", days=0)
        try:
            body.encode("ascii")
            ascii_safe = True
        except UnicodeEncodeError:
            ascii_safe = False
        assert not ascii_safe, "fixture is not exercising the non-ASCII path"
        out = os.path.join(d, "page.html")
        with open(out, "w", encoding="utf-8") as f:
            f.write(body)
        assert os.path.getsize(out) > 0


# --- (q) SCALE: the store is read through a date window, and what the window
# left behind is counted on the page, never dropped in silence.

def test_records_outside_the_days_window_are_never_opened_and_the_count_is_named():
    with tempfile.TemporaryDirectory() as d:
        inside = _day_offset(1)
        outside = _day_offset(365)
        _write_record(d, "acme", "aaaa", inside, _healthy_record(inside, "aaaa"))
        _write_record(d, "acme", "aaaa", outside, _healthy_record(outside, "aaaa"))
        opened = []
        real_load = fl.load_record

        def spy(path):
            opened.append(path)
            return real_load(path)

        fl.load_record = spy
        try:
            rows, _empty, meta = fd.collect_org(d, "acme")
        finally:
            fl.load_record = real_load
        assert fd.DEFAULT_DAYS == 30
        # RED before the fix: collect_org read the ENTIRE store history, so
        # both records came back as rows, the year-old file WAS opened, and
        # there was no third return value carrying the skipped count at all.
        assert [r["date"] for r in rows] == [inside]
        assert meta["outside_window"] == 1
        assert not [p for p in opened if outside in p], (
            "a record outside the window was opened; the filename date must be "
            "filtered BEFORE the file is read")
        body = fd.render(d, "acme", "stamp")
        assert "1 record file" in body
        assert "outside" in body


def test_machine_rows_are_capped_and_the_dropped_count_is_named_on_the_page():
    with tempfile.TemporaryDirectory() as d:
        day = _day_offset(0)
        total = fd.MAX_TABLE_ROWS + 3
        for i in range(total):
            mid = f"m{i:04d}"
            _write_record(d, "acme", mid, day, _healthy_record(day, mid))
        body = fd.render(d, "acme", "stamp")
        last = f"m{total - 1:04d}"
        # RED before the fix: nothing capped the row count, so every one of
        # the machines rendered its own table row and the page said nothing.
        assert "m0000" in body
        assert last not in body, "the row cap did not drop anything"
        assert "3 more" in body, "rows were dropped without saying so on the page"


# --- (r) PRIVACY: minimum group size, and a per-machine table that carries
# operational health only.

def test_an_aggregate_backed_by_fewer_than_the_minimum_group_is_suppressed_with_a_reason():
    with tempfile.TemporaryDirectory() as d:
        day = _day_offset(0)
        for i in range(6):
            mid = f"big{i}"
            _write_record(d, "acme", mid, day,
                          _healthy_record(day, mid, team="bigteam", environment="ci",
                                          input_tokens=1000, output_tokens=0,
                                          cache_read=0, cache_write=0))
        for i in range(3):
            mid = f"small{i}"
            _write_record(d, "acme", mid, day,
                          _healthy_record(day, mid, team="smallteam", environment="ci",
                                          input_tokens=1000, output_tokens=0,
                                          cache_read=0, cache_write=0))
        assert fd.MIN_GROUP_MACHINES == 5
        body = fd.render(d, "acme", "stamp")
        # RED before the fix: every tag total was published whatever the group
        # size, so the three-machine team's 3.0K sat on the page beside the
        # six-machine team's 6.0K.
        #
        # CORRECTED, not weakened, when the differencing hole was found: this
        # assertion used to read `assert "6.0K" in body, "a team backed by six
        # machines must still publish"`, which asserted the defect. Publishing
        # bigteam's 6.0K next to an org total of 9.0K hands a reader the
        # three-machine smallteam residual by subtraction, so suppressing
        # smallteam's cell while publishing bigteam's withheld nothing at all.
        # The six-machine group is withheld alongside it: whatever is withheld
        # must itself stand on at least five machines.
        assert "6.0K" not in body, (
            "the six-machine team was published while a three-machine team was "
            "suppressed, so 9.0K minus 6.0K returns the suppressed team exactly")
        assert "3.0K" not in body, "a team backed by three machines was published"
        assert "bigteam" in body, "the group withheld to protect the residual must name itself"
        assert "smallteam" in body, "the suppressed row must still name itself"
        assert "suppressed" in body
        assert "fewer than 5 machines" in body


def test_the_machines_table_publishes_operational_health_not_per_machine_tokens():
    with tempfile.TemporaryDirectory() as d:
        day = _day_offset(0)
        for i, value in enumerate((137, 241, 353, 467, 571)):
            mid = f"mach{i}"
            _write_record(d, "acme", mid, day,
                          _healthy_record(day, mid, team="ios", environment="ci",
                                          input_tokens=value, output_tokens=0,
                                          cache_read=0, cache_write=0))
        rows, empty, meta = fd.collect_org(d, "acme")
        table = fd.render_machines_table(rows, empty, meta)
        # RED before the fix: the machines table carried a Tokens column with
        # one machine's own total in it, which in almost every org is one
        # person's own output, published to the whole org.
        assert "<th>Tokens</th>" not in table
        for value in ("137", "241", "353", "467", "571"):
            assert value not in table, (
                f"the per-machine table published one machine's own {value} tokens")
        assert "mach0" in table, "the operational row itself must stay"
        assert "Status" in table
        body = fd.render(d, "acme", "stamp")
        assert "1.8K" in body, (
            "the five-machine aggregate must still publish; suppression is about "
            "small groups, not about hiding the org's own totals")


def test_a_machine_that_stopped_reporting_is_named_stale_with_its_last_report_date():
    with tempfile.TemporaryDirectory() as d:
        fresh_day = _day_offset(0)
        old_day = _day_offset(20)
        _write_record(d, "acme", "freshmachine", fresh_day,
                      _healthy_record(fresh_day, "freshmachine"))
        _write_record(d, "acme", "oldmachine", old_day,
                      _healthy_record(old_day, "oldmachine"))
        rows, empty, meta = fd.collect_org(d, "acme")
        table = fd.render_machines_table(rows, empty, meta)
        old_row = [chunk for chunk in table.split("<tr>") if "oldmachine" in chunk][0]
        fresh_row = [chunk for chunk in table.split("<tr>") if "freshmachine" in chunk][0]
        # RED before the fix: the table had no status at all, so a machine
        # that stopped reporting three weeks ago looked exactly like one that
        # reported this morning.
        assert "stale" in old_row
        assert old_day in old_row
        assert "stale" not in fresh_row
        assert "reporting" in fresh_row


def test_the_minimum_group_size_can_be_raised_but_never_lowered():
    with tempfile.TemporaryDirectory() as d:
        day = _day_offset(0)
        for i in range(6):
            mid = f"m{i}"
            _write_record(d, "acme", mid, day,
                          _healthy_record(day, mid, team="sixteam", environment="ci",
                                          input_tokens=1000, output_tokens=0,
                                          cache_read=0, cache_write=0))
        # RED before the fix: render() took no min_group argument at all.
        lowered = fd.render(d, "acme", "stamp", min_group=1)
        assert "6.0K" in lowered, "six machines clear the floor of five"
        raised = fd.render(d, "acme", "stamp", min_group=10)
        assert "6.0K" not in raised, "an admin raised the threshold and it was ignored"
        assert "fewer than 10 machines" in raised

        with tempfile.TemporaryDirectory() as d2:
            for i in range(3):
                mid = f"m{i}"
                _write_record(d2, "acme", mid, day,
                              _healthy_record(day, mid, team="threeteam", environment="ci",
                                              input_tokens=1000, output_tokens=0,
                                              cache_read=0, cache_write=0))
            body = fd.render(d2, "acme", "stamp", min_group=1)
            assert "3.0K" not in body, (
                "min_group was lowered below the MIN_GROUP_MACHINES floor")
            assert "fewer than 5 machines" in body


# --- (s) D20: one row per label ACROSS confidences, matching the page copy.

def test_a_newer_not_proven_supersedes_an_older_verified_for_the_same_label():
    with tempfile.TemporaryDirectory() as d:
        older = _day_offset(2)
        newer = _day_offset(1)
        _write_record(d, "acme", "aaaa", older,
                      _healthy_record(older, "aaaa", experiments=[
                          {"label": "cohort-skip", "confidence": "VERIFIED",
                           "timestamp": f"{older}T09:00:00", "metric_delta": 1500,
                           "target_metric": "first_request_median",
                           "direction": "saving"}]))
        _write_record(d, "acme", "bbbb", newer,
                      _healthy_record(newer, "bbbb", experiments=[
                          {"label": "cohort-skip", "confidence": "NOT_PROVEN",
                           "timestamp": f"{newer}T09:00:00", "metric_delta": -400,
                           "target_metric": "first_request_median",
                           "direction": "regression"}]))
        rows, _empty, _meta = fd.collect_org(d, "acme")
        healthy = [r for r in rows if r["error"] is None]
        items = fd.latest_experiment_by_label(healthy)
        # RED before the fix: latest-wins was keyed on (label, confidence), so
        # BOTH rows survived and the stale VERIFIED +1,500 sat beside the
        # newer NOT_PROVEN -400 under a sentence promising one row per label.
        assert len(items) == 1, "one row per label, across every confidence"
        assert items[0]["confidence"] == "NOT_PROVEN"
        assert items[0]["metric_delta"] == -400
        body = fd.render(d, "acme", "stamp")
        assert body.count("cohort-skip") == 1
        assert "+1,500" not in body


# --- (t) D9: no per-model table, a named NO DATA statement instead.

def test_no_model_column_only_a_named_no_data_statement_about_model_identity():
    with tempfile.TemporaryDirectory() as d:
        day = _day_offset(0)
        for i in range(5):
            mid = f"m{i}"
            _write_record(d, "acme", mid, day, _healthy_record(day, mid))
        body = fd.render(d, "acme", "stamp")
        # RED before the fix: the counters table carried a Model column whose
        # every cell read "unknown", because the telemetry ledger records a
        # model COUNT and never a model IDENTITY.
        assert "<th>Model</th>" not in body
        assert "<td>unknown</td>" not in body
        assert "model identity" in body


# --- (u) D21 items that live in this file.

def test_an_unreadable_org_directory_is_one_row_not_an_exception_out_of_render():
    with tempfile.TemporaryDirectory() as d:
        day = _day_offset(0)
        _write_record(d, "acme", "healthy", day, _healthy_record(day, "healthy"))
        real_listdir = os.listdir

        def deny_org(path, *args, **kwargs):
            if os.path.basename(path) == "acme":
                raise PermissionError(13, "Permission denied")
            return real_listdir(path, *args, **kwargs)

        os.listdir = deny_org
        try:
            # RED before the fix: os.listdir(org_dir) was unguarded while the
            # per-machine listdir was, so this raised PermissionError straight
            # out of collect_org and out of render, against a docstring
            # promising it never raises.
            rows, _empty, _meta = fd.collect_org(d, "acme")
            body = fd.render(d, "acme", "stamp")
        finally:
            os.listdir = real_listdir
        assert len(rows) == 1
        assert rows[0]["error"] is not None
        assert "could not list" in rows[0]["error"]
        assert "NO DATA" in body


def test_a_non_finite_metric_delta_never_renders_as_nan():
    with tempfile.TemporaryDirectory() as d:
        day = _day_offset(0)
        path = _machine_path(d, "acme", "deltamachine", day)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        raw = ('{"schema": 1, "date": "' + day + '", "machine_id": "' + "a" * 64 + '", '
               '"counters": {}, "experiments": [{"label": "delta-label", '
               '"confidence": "VERIFIED", "timestamp": "' + day + 'T09:00:00", '
               '"target_metric": "first_request_median", "metric_delta": NaN, '
               '"direction": "saving"}]}')
        with open(path, "wb") as f:
            f.write(raw.encode("utf-8"))
        body = fd.render(d, "acme", "stamp")
        # RED before the fix: the delta cell was formatted with f"{delta:+,}"
        # for anything numeric, and NaN is numeric, so the page published
        # "+nan" as if it were a measured saving.
        assert "delta-label" in body
        assert "nan" not in body
        assert "+nan" not in body


def test_a_filename_that_is_not_a_real_calendar_date_gets_its_own_no_data_row():
    with tempfile.TemporaryDirectory() as d:
        day = _day_offset(0)
        _write_record(d, "acme", "healthy", day, _healthy_record(day, "healthy"))
        _write_record(d, "acme", "bogus", "9999-99-99",
                      _healthy_record("9999-99-99", "bogus"))
        rows, _empty, _meta = fd.collect_org(d, "acme")
        bogus = [r for r in rows if r["machine_id"] == "bogus"][0]
        healthy_row = [r for r in rows if r["machine_id"] == "healthy"][0]
        # RED before the fix: the filename was never validated, so
        # "9999-99-99" loaded cleanly and rendered as a day of the year in
        # the counters table.
        assert bogus["error"] is not None
        assert "calendar date" in bogus["error"]
        assert bogus["date"] is None
        assert healthy_row["error"] is None
        body = fd.render(d, "acme", "stamp")
        assert "<td>9999-99-99</td>" not in body


def test_a_non_string_team_never_renders_a_python_repr():
    with tempfile.TemporaryDirectory() as d:
        day = _day_offset(0)
        rec = _healthy_record(day, "dictteam")
        rec["team"] = {"k": 1}
        _write_record(d, "acme", "dictteam", day, rec)
        rows, empty, meta = fd.collect_org(d, "acme")
        table = fd.render_machines_table(rows, empty, meta)
        # RED before the fix: the cell was ts.esc(rec.get("team") or ...),
        # and esc() calls str(), so a dict team printed a Python repr into
        # the org's page.
        assert "&#x27;" not in table
        assert "(untagged)" in table


def test_main_takes_days_and_min_group_and_refuses_a_negative_window():
    with tempfile.TemporaryDirectory() as d:
        day = _day_offset(0)
        for i in range(6):
            mid = f"m{i}"
            _write_record(d, "acme", mid, day,
                          _healthy_record(day, mid, team="sixteam", environment="ci",
                                          input_tokens=1000, output_tokens=0,
                                          cache_read=0, cache_write=0))
        out = os.path.join(d, "out.html")
        argv_backup = sys.argv
        try:
            sys.argv = ["fleet_dashboard.py", "--store-dir", d, "--org", "acme",
                        "--out", out, "--days", "7", "--min-group", "9"]
            # RED before the fix: main() had no --days and no --min-group, so
            # argparse exited 2 with "unrecognized arguments" before any page
            # was written.
            assert fd.main() == 0
            with open(out, encoding="utf-8") as f:
                page = f.read()
            assert "6.0K" not in page, "--min-group 9 was ignored"
            assert "fewer than 9 machines" in page
            sys.argv = ["fleet_dashboard.py", "--store-dir", d, "--org", "acme",
                        "--out", out, "--days", "-1"]
            assert fd.main() == 2
        finally:
            sys.argv = argv_backup


def test_a_suppressed_group_cannot_be_recovered_by_subtraction():
    """The minimum group size is defeated by arithmetic unless the groups it
    withholds are also withheld from the COMPLEMENT of what is published.

    REPRODUCED BEFORE THE FIX, on a 5 plus 1 store: the team table published
    "eng" at 24.2M over five machines and the environment table published
    "prod" at 27.3M over all six, so 27.3M minus 24.2M returned 3.1M against
    a true 3,030,000, recovering one machine's (one person's) total token
    volume to within 2.3 percent from two cells the page had just declared
    safe to publish. The day table gives the same complement exactly.

    The rule enforced here: whatever is withheld must itself stand on at
    least min_group machines, so the residual an administrator can subtract
    is an aggregate too. On a 5 plus 1 split that means the five-machine
    group is withheld as well, because its complement is one person."""
    with tempfile.TemporaryDirectory() as d:
        day = _day_offset(0)
        for i in range(5):
            mid = f"eng{i}"
            _write_record(d, "acme", mid, day,
                          _healthy_record(day, mid, team="eng", environment="prod",
                                          input_tokens=1_200_000, output_tokens=400_000,
                                          cache_read=3_000_000, cache_write=250_000))
        _write_record(d, "acme", "ops0", day,
                      _healthy_record(day, "ops0", team="ops", environment="prod",
                                      input_tokens=830_000, output_tokens=210_000,
                                      cache_read=1_900_000, cache_write=90_000))

        healthy = [r for r in fd.collect_org(d, "acme", days=0)[0] if r["error"] is None]
        by_team = fd.aggregate_totals_by_tag(healthy, "team")
        # The aggregate must carry WHICH machines stand behind it, not only
        # how many: two groups of five can share four machines, and only the
        # union decides whether the withheld residual is anonymous.
        assert by_team["eng"]["machine_ids"] == {f"eng{i}" for i in range(5)}

        page = fd.render_tag_totals("Tokens by team", by_team, 5)
        assert "24.2M" not in page, (
            "the five-machine group was published while a one-machine group was "
            "suppressed, so subtracting it from the org total recovers that one "
            "machine exactly")
        # Both groups are named as withheld: "no row" and "a row we are not
        # allowed to publish" stay different facts.
        assert "eng" in page and "ops" in page
        assert "suppressed" in page

        # The whole page, not just one table, because the leak lived BETWEEN
        # two tables that each passed on their own. The org-wide 27.3M stays
        # published and must: it stands on all six machines and its
        # complement is empty. What may not appear anywhere is the
        # five-machine 24.2M, whose complement is one person.
        body = fd.render(d, "acme", "2026-08-15 09:00", days=0)
        assert "27.3M" in body
        assert "24.2M" not in body


def test_a_tag_table_still_publishes_when_nothing_is_withheld():
    """The secondary suppression above must not swallow a table that had no
    small group in it: ten machines in two teams of five publish both rows,
    because the complement of either is the other, and the other stands on
    five machines."""
    with tempfile.TemporaryDirectory() as d:
        day = _day_offset(0)
        for team in ("eng", "ops"):
            for i in range(5):
                mid = f"{team}{i}"
                _write_record(d, "acme", mid, day,
                              _healthy_record(day, mid, team=team, environment="prod",
                                              input_tokens=1000, output_tokens=0,
                                              cache_read=0, cache_write=0))
        healthy = [r for r in fd.collect_org(d, "acme", days=0)[0] if r["error"] is None]
        page = fd.render_tag_totals("Tokens by team", fd.aggregate_totals_by_tag(healthy, "team"), 5)
        assert page.count("5.0K") == 2
        assert "suppressed" not in page


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
