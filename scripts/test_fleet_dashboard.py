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

def test_label_helpers_are_imported_from_token_shield_not_reimplemented():
    import token_shield as ts
    assert fd.ts.esc is ts.esc
    assert fd.ts.human is ts.human
    assert fd.ts.pct is ts.pct
    assert fd.ts._cpill is ts._cpill


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
