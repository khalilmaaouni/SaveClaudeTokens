#!/usr/bin/env python3
"""Self-check for doctor.py. No framework, no fixtures beyond the small ones
built inline below.

    python3 scripts/test_doctor.py

Calibrated: _overlap_lines' hook_footprint intersection was briefly removed
during development (every active pair reported, overlapping or not);
test_overlap_reports_shared_hook_only_for_the_actual_intersection went red
because "lonely-tool" (no shared hook) started appearing; restored to the
set-intersection check, green again.
"""

import contextlib
import io
import json
import os
import tempfile
import time

import doctor as dr


def _no_data_canary(root=None):
    """A safe stand-in for dr._canary_result in every test that calls
    dr.report() or dr.main(): never touches the founder's real
    ~/.claude/projects, and keeps rc == 0 for tests asserting the pre-canary
    contract."""
    return {"transcripts": 0, "messages": 0, "recognised": 0, "parse_health": None,
            "state": "NO DATA",
            "reason": "NO DATA: no transcripts found; nothing to check yet.",
            "exit_code": 0}


def _companion(name, hook_footprint, last_reviewed="2026-08-13"):
    return {"name": name, "hook_footprint": hook_footprint, "last_reviewed": last_reviewed,
            "tested_version_range": {"min": "0", "max": "0", "tested_on": "2026-08-13"}}


def _state(discovered):
    return {"schema": 1, "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "discovered": discovered,
            "registry_match": {d["name"]: "curated" for d in discovered}}


def test_overlap_reports_shared_hook_only_for_the_actual_intersection():
    companions = [
        _companion("ponytail", ["SessionStart", "SubagentStart", "UserPromptSubmit"]),
        _companion("caveman", ["SessionStart", "UserPromptSubmit"]),
        _companion("lonely-tool", ["PreToolUse"]),
    ]
    state = _state([
        {"name": "ponytail", "enabled": True, "source_label": "CLAUDE PROJECTED"},
        {"name": "caveman", "enabled": True, "source_label": "CLAUDE PROJECTED"},
        {"name": "lonely-tool", "enabled": True, "source_label": "CLAUDE PROJECTED"},
    ])
    lines = dr._overlap_lines(companions, state)
    joined = "\n".join(lines)
    assert "ponytail" in joined and "caveman" in joined, lines
    assert "SessionStart" in joined and "UserPromptSubmit" in joined, lines
    assert "lonely-tool" not in joined, lines
    assert not any("CONFLICT" in l.upper() for l in lines), lines


def test_overlap_empty_when_no_active_companion_shares_a_hook():
    companions = [_companion("lonely-tool", ["PreToolUse"])]
    state = _state([{"name": "lonely-tool", "enabled": True, "source_label": "CLAUDE PROJECTED"}])
    assert dr._overlap_lines(companions, state) == []


def test_staleness_flags_old_last_reviewed():
    companions = [_companion("ancient-tool", ["SessionStart"], last_reviewed="2020-01-01")]
    lines = dr._staleness_lines(companions, today="2026-08-13")
    assert any("NEEDS REVIEW" in l and "ancient-tool" in l for l in lines), lines


def test_staleness_silent_when_recent():
    companions = [_companion("fresh-tool", ["SessionStart"], last_reviewed="2026-08-01")]
    assert dr._staleness_lines(companions, today="2026-08-13") == []


def test_health_lines_uninstalled_and_unvetted():
    companions = [_companion("ponytail", ["SessionStart"])]
    state = {
        "discovered": [{"name": "mystery-plugin", "enabled": True, "source_label": "CLAUDE PROJECTED"}],
        "registry_match": {"mystery-plugin": "unknown"},
    }
    lines = dr._health_lines(companions, state)
    joined = "\n".join(lines)
    assert "curated, not installed" in joined and "ponytail" in joined, lines
    assert "unvetted" in joined and "mystery-plugin" in joined, lines


def test_health_lines_installed_and_active():
    companions = [_companion("ponytail", ["SessionStart"])]
    state = _state([{"name": "ponytail", "enabled": True, "source_label": "CLAUDE PROJECTED"}])
    lines = dr._health_lines(companions, state)
    assert any("installed and active" in l and "ponytail" in l for l in lines), lines


def test_report_prints_shared_hook_and_never_conflict():
    companions = [
        _companion("ponytail", ["SessionStart", "SubagentStart", "UserPromptSubmit"]),
        _companion("caveman", ["SessionStart", "UserPromptSubmit"]),
    ]
    state = _state([
        {"name": "ponytail", "enabled": True, "source_label": "CLAUDE PROJECTED"},
        {"name": "caveman", "enabled": True, "source_label": "CLAUDE PROJECTED"},
    ])

    orig_load = dr.cfg.load_companions
    orig_fresh = dr._ensure_fresh_state
    orig_load_state = dr._load_state
    orig_discover = dr.dc.discover
    orig_open_exp = dr._open_experiments
    orig_canary = dr._canary_result
    dr.cfg.load_companions = lambda path: {"companions": companions, "mentions": []}
    dr._ensure_fresh_state = lambda: state
    dr._load_state = lambda path=None: None
    dr.dc.discover = lambda: []
    dr._open_experiments = lambda exp_dir=None: []
    dr._canary_result = _no_data_canary
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = dr.report()
        out = buf.getvalue()
    finally:
        dr.cfg.load_companions = orig_load
        dr._ensure_fresh_state = orig_fresh
        dr._load_state = orig_load_state
        dr.dc.discover = orig_discover
        dr._open_experiments = orig_open_exp
        dr._canary_result = orig_canary

    assert rc == 0
    assert "SHARED HOOK" in out, out
    assert "SessionStart" in out, out
    assert "conflict" not in out.lower(), out
    assert "Hook ownership" in out, out
    assert "known-safe" in out or "needs-review" in out, out


def test_ownership_lines_render_needs_review_pair_from_fixture():
    companions = [
        _companion("ponytail", ["SessionStart", "UserPromptSubmit"]),
        _companion("caveman", ["SessionStart", "UserPromptSubmit"]),
    ]
    state = _state([
        {"name": "ponytail", "enabled": True, "source_label": "CLAUDE PROJECTED"},
        {"name": "caveman", "enabled": True, "source_label": "CLAUDE PROJECTED"},
    ])
    compat_data = {
        "schema": 1,
        "pairs": [
            {
                "companions": ["ponytail", "caveman"],
                "hook_event": "UserPromptSubmit",
                "verdict": "needs-review",
                "evidence_date": "2026-08-13",
                "ownership": {"ponytail": "tracks mode on every prompt",
                              "caveman": "tracks mode on every prompt"},
            }
        ],
    }
    lines = dr._ownership_lines(companions, state, compat_data)
    joined = "\n".join(lines)
    assert "needs-review" in joined, lines
    assert "UserPromptSubmit" in joined and "ponytail" in joined and "caveman" in joined, lines
    assert "tracks mode on every prompt" in joined, lines


def test_ownership_reports_no_data_for_pair_absent_from_compatibility_file():
    """Calibrated: temporarily defaulting the missing-entry branch in
    _ownership_lines to verdict "known-safe" instead of "NO DATA" turned
    this red (both assertions failed); restored to NO DATA, green again."""
    companions = [
        _companion("ponytail", ["SessionStart"]),
        _companion("caveman", ["SessionStart"]),
    ]
    state = _state([
        {"name": "ponytail", "enabled": True, "source_label": "CLAUDE PROJECTED"},
        {"name": "caveman", "enabled": True, "source_label": "CLAUDE PROJECTED"},
    ])
    compat_data = {"schema": 1, "pairs": []}  # no evidence on file for this pair
    lines = dr._ownership_lines(companions, state, compat_data)
    joined = "\n".join(lines)
    assert "NO DATA" in joined, lines
    assert "known-safe" not in joined, lines


def test_load_compatibility_returns_reason_on_malformed_json():
    fd, path = tempfile.mkstemp(suffix=".json")
    try:
        with os.fdopen(fd, "w") as f:
            f.write("{not valid json")
        data, error = dr._load_compatibility(path)
        assert data is None, data
        assert error, "expected a parse error reason, got none"
    finally:
        os.remove(path)


def test_report_stays_clean_when_compatibility_file_is_malformed():
    companions = [
        _companion("ponytail", ["SessionStart", "UserPromptSubmit"]),
        _companion("caveman", ["SessionStart", "UserPromptSubmit"]),
    ]
    state = _state([
        {"name": "ponytail", "enabled": True, "source_label": "CLAUDE PROJECTED"},
        {"name": "caveman", "enabled": True, "source_label": "CLAUDE PROJECTED"},
    ])

    orig_load = dr.cfg.load_companions
    orig_fresh = dr._ensure_fresh_state
    orig_compat = dr._load_compatibility
    orig_load_state = dr._load_state
    orig_discover = dr.dc.discover
    orig_open_exp = dr._open_experiments
    orig_canary = dr._canary_result
    dr.cfg.load_companions = lambda path: {"companions": companions, "mentions": []}
    dr._ensure_fresh_state = lambda: state
    dr._load_compatibility = lambda: (None, "Expecting value: line 1 column 1 (char 0)")
    dr._load_state = lambda path=None: None
    dr.dc.discover = lambda: []
    dr._open_experiments = lambda exp_dir=None: []
    dr._canary_result = _no_data_canary
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = dr.report()
        out = buf.getvalue()
    finally:
        dr.cfg.load_companions = orig_load
        dr._ensure_fresh_state = orig_fresh
        dr._load_compatibility = orig_compat
        dr._load_state = orig_load_state
        dr.dc.discover = orig_discover
        dr._open_experiments = orig_open_exp
        dr._canary_result = orig_canary

    assert rc == 0
    assert "malformed" in out.lower(), out
    assert "Expecting value" in out, out
    assert "Health" in out and "Staleness" in out and "Overlap" in out, out


def test_main_completes_without_traceback_with_zero_companions_active():
    orig_load = dr.cfg.load_companions
    orig_fresh = dr._ensure_fresh_state
    orig_load_state = dr._load_state
    orig_discover = dr.dc.discover
    orig_open_exp = dr._open_experiments
    orig_canary = dr._canary_result
    dr.cfg.load_companions = lambda path: {"companions": [], "mentions": []}
    dr._ensure_fresh_state = lambda: {"schema": 1, "checked_at": "x", "discovered": [], "registry_match": {}}
    dr._load_state = lambda path=None: None
    dr.dc.discover = lambda: []
    dr._open_experiments = lambda exp_dir=None: []
    dr._canary_result = _no_data_canary
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = dr.main([])
        out = buf.getvalue()
    finally:
        dr.cfg.load_companions = orig_load
        dr._ensure_fresh_state = orig_fresh
        dr._load_state = orig_load_state
        dr.dc.discover = orig_discover
        dr._open_experiments = orig_open_exp
        dr._canary_result = orig_canary
    assert rc == 0
    assert "conflict" not in out.lower(), out


def test_version_drift_lines_render_drift_with_recorded_date():
    drift = {"no_data": False,
             "drifted": [{"name": "ponytail", "recorded_version": "4.9.0",
                          "live_version": "5.0.0", "recorded_at": "2026-08-12T00:00:00Z"}],
             "missing": []}
    lines = dr._version_drift_lines(drift)
    joined = "\n".join(lines)
    assert "ponytail" in joined and "4.9.0" in joined and "5.0.0" in joined, lines
    assert "2026-08-12T00:00:00Z" in joined, lines


def test_version_drift_lines_no_data_row_for_missing_recorded_version():
    drift = {"no_data": False, "drifted": [],
             "missing": [{"name": "caveman", "live_version": "0d95a81d35a9"}]}
    lines = dr._version_drift_lines(drift)
    joined = "\n".join(lines)
    assert "NO DATA" in joined and "caveman" in joined, lines


def test_version_drift_lines_empty_when_no_drift():
    # Calibrated: report() treats an empty list here as the trigger for its
    # "no version drift" clean line (see test_report_version_drift_clean_
    # line_when_no_drift below); this function itself must never
    # editorialize a "no drift" string, just return no lines.
    drift = {"no_data": False, "drifted": [], "missing": []}
    assert dr._version_drift_lines(drift) == []


def test_report_version_drift_detects_change_and_clean_line_when_matched():
    companions = [_companion("ponytail", ["SessionStart"])]
    matching_state = _state([{"name": "ponytail", "enabled": True,
                              "source_label": "CLAUDE PROJECTED", "version": "4.9.0"}])
    live_matching = [{"name": "ponytail", "version": "4.9.0", "enabled": True,
                      "source_label": "CLAUDE PROJECTED"}]

    orig_load = dr.cfg.load_companions
    orig_fresh = dr._ensure_fresh_state
    orig_load_state = dr._load_state
    orig_discover = dr.dc.discover
    orig_open_exp = dr._open_experiments
    orig_canary = dr._canary_result
    dr.cfg.load_companions = lambda path: {"companions": companions, "mentions": []}
    dr._ensure_fresh_state = lambda: matching_state
    dr._load_state = lambda path=None: matching_state
    dr.dc.discover = lambda: live_matching
    dr._open_experiments = lambda exp_dir=None: []
    dr._canary_result = _no_data_canary
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = dr.report()
        out = buf.getvalue()
    finally:
        dr.cfg.load_companions = orig_load
        dr._ensure_fresh_state = orig_fresh
        dr._load_state = orig_load_state
        dr.dc.discover = orig_discover
        dr._open_experiments = orig_open_exp
        dr._canary_result = orig_canary

    assert rc == 0
    assert "Version drift" in out, out
    assert "no version drift" in out.lower(), out
    assert "DRIFT:" not in out, out


def test_report_version_drift_no_data_when_state_missing():
    # Absent state file: doctor must render NO DATA, never "no drift".
    companions = [_companion("ponytail", ["SessionStart"])]
    live = [{"name": "ponytail", "version": "4.9.0", "enabled": True,
             "source_label": "CLAUDE PROJECTED"}]

    orig_load = dr.cfg.load_companions
    orig_fresh = dr._ensure_fresh_state
    orig_load_state = dr._load_state
    orig_discover = dr.dc.discover
    orig_open_exp = dr._open_experiments
    orig_canary = dr._canary_result
    dr.cfg.load_companions = lambda path: {"companions": companions, "mentions": []}
    dr._ensure_fresh_state = lambda: None
    dr._load_state = lambda path=None: None
    dr.dc.discover = lambda: live
    dr._open_experiments = lambda exp_dir=None: []
    dr._canary_result = _no_data_canary
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = dr.report()
        out = buf.getvalue()
    finally:
        dr.cfg.load_companions = orig_load
        dr._ensure_fresh_state = orig_fresh
        dr._load_state = orig_load_state
        dr.dc.discover = orig_discover
        dr._open_experiments = orig_open_exp
        dr._canary_result = orig_canary

    assert rc == 0
    assert "Version drift" in out, out
    assert "NO DATA" in out, out
    assert "no version drift" not in out.lower(), out


def test_open_experiments_reads_baseline_snapshots_from_a_directory():
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "shrink-claude-md.json"), "w") as f:
            json.dump({"label": "shrink-claude-md", "started": "2026-08-12T00:00:00+0000"}, f)
        with open(os.path.join(d, "not-json.txt"), "w") as f:
            f.write("ignore me")
        result = dr._open_experiments(exp_dir=d)
        assert result == [{"label": "shrink-claude-md", "started": "2026-08-12T00:00:00+0000"}], result


def test_open_experiments_empty_when_directory_missing():
    assert dr._open_experiments(exp_dir="/nonexistent/path/for/sure/token-shield-u1") == []


def test_spanning_warning_fires_when_experiment_open_and_change_inside_window():
    open_experiments = [{"label": "shrink-claude-md", "started": "2026-08-12T00:00:00+0000"}]
    # recorded_at is AFTER started: the actual bump (strictly after
    # recorded_at) is guaranteed to fall inside the experiment's window.
    drifted = [{"name": "ponytail", "recorded_version": "4.9.0", "live_version": "5.0.0",
                "recorded_at": "2026-08-12T06:00:00Z"}]
    lines = dr._spanning_warning_lines(open_experiments, drifted)
    joined = "\n".join(lines)
    assert "SPANNING EXPERIMENT WARNING" in joined, lines
    assert "shrink-claude-md" in joined and "ponytail" in joined, lines
    assert "4.9.0" in joined and "5.0.0" in joined, lines


def test_spanning_warning_does_not_fire_with_no_open_experiment():
    drifted = [{"name": "ponytail", "recorded_version": "4.9.0", "live_version": "5.0.0",
                "recorded_at": "2026-08-12T06:00:00Z"}]
    lines = dr._spanning_warning_lines([], drifted)
    assert lines == [], lines


def test_spanning_warning_does_not_fire_for_change_predating_experiment():
    # recorded_at is well BEFORE started: the bump could have happened
    # before the experiment opened, so the guard suppresses the warning.
    open_experiments = [{"label": "shrink-claude-md", "started": "2026-08-12T12:00:00+0000"}]
    drifted = [{"name": "ponytail", "recorded_version": "4.9.0", "live_version": "5.0.0",
                "recorded_at": "2026-08-10T00:00:00Z"}]
    lines = dr._spanning_warning_lines(open_experiments, drifted)
    assert lines == [], lines


def _fact(fid, statement="a platform fact", source="code.claude.com/docs/en/x",
          verified="2026-08-13", review_interval_days=90):
    return {"id": fid, "statement": statement, "source": source,
            "verified": verified, "review_interval_days": review_interval_days}


def test_fact_staleness_flags_stale_fact_with_age():
    facts = [_fact("A1", verified="2026-01-01", review_interval_days=90)]
    lines = dr._fact_staleness_lines(facts, today="2026-08-13")
    joined = "\n".join(lines)
    assert "NEEDS REVIEW" in joined and "A1" in joined, lines
    assert "2026-01-01" in joined, lines
    # age: 2026-01-01 -> 2026-08-13 is 224 days, past the 90 day interval
    assert "224" in joined, lines


def test_fact_staleness_silent_for_fresh_fact():
    facts = [_fact("A2", verified="2026-08-01", review_interval_days=90)]
    assert dr._fact_staleness_lines(facts, today="2026-08-13") == []


def test_load_facts_refuses_fact_missing_source():
    fd, path = tempfile.mkstemp(suffix=".json")
    try:
        fact = _fact("A3")
        del fact["source"]
        with os.fdopen(fd, "w") as f:
            json.dump({"schema": 1, "facts": [fact]}, f)
        facts, refused, error = dr._load_facts(path)
        assert error is None, error
        assert facts == [], facts
        assert any(fid == "A3" and "source" in reason for fid, reason in refused), refused
    finally:
        os.remove(path)


def test_load_facts_refuses_fact_missing_verified_date():
    fd, path = tempfile.mkstemp(suffix=".json")
    try:
        fact = _fact("A4")
        del fact["verified"]
        with os.fdopen(fd, "w") as f:
            json.dump({"schema": 1, "facts": [fact]}, f)
        facts, refused, error = dr._load_facts(path)
        assert error is None, error
        assert facts == [], facts
        assert any(fid == "A4" and "verified" in reason for fid, reason in refused), refused
    finally:
        os.remove(path)


def test_load_facts_malformed_json_is_no_data():
    fd, path = tempfile.mkstemp(suffix=".json")
    try:
        with os.fdopen(fd, "w") as f:
            f.write("{not valid json")
        facts, refused, error = dr._load_facts(path)
        assert facts == [], facts
        assert refused == [], refused
        assert error, "expected a parse error reason, got none"
    finally:
        os.remove(path)


def test_load_facts_missing_file_is_no_data():
    facts, refused, error = dr._load_facts("/nonexistent/path/for/sure/token-shield-facts.json")
    assert facts == [], facts
    assert refused == [], refused
    assert error, "expected a not-found reason, got none"


def test_report_prints_facts_staleness_section_live():
    companions = []
    state = _state([])

    orig_load = dr.cfg.load_companions
    orig_fresh = dr._ensure_fresh_state
    orig_load_state = dr._load_state
    orig_discover = dr.dc.discover
    orig_open_exp = dr._open_experiments
    orig_load_facts = dr._load_facts
    orig_canary = dr._canary_result
    dr.cfg.load_companions = lambda path: {"companions": companions, "mentions": []}
    dr._ensure_fresh_state = lambda: state
    dr._load_state = lambda path=None: None
    dr.dc.discover = lambda: []
    dr._open_experiments = lambda exp_dir=None: []
    dr._load_facts = lambda path=None: ([_fact("A1", verified="2026-01-01", review_interval_days=90)], [], None)
    dr._canary_result = _no_data_canary
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = dr.report()
        out = buf.getvalue()
    finally:
        dr.cfg.load_companions = orig_load
        dr._ensure_fresh_state = orig_fresh
        dr._load_state = orig_load_state
        dr.dc.discover = orig_discover
        dr._open_experiments = orig_open_exp
        dr._load_facts = orig_load_facts
        dr._canary_result = orig_canary

    assert rc == 0
    assert "Facts" in out, out
    assert "NEEDS REVIEW" in out and "A1" in out, out


def test_report_facts_section_is_no_data_when_facts_file_malformed():
    companions = []
    state = _state([])

    orig_load = dr.cfg.load_companions
    orig_fresh = dr._ensure_fresh_state
    orig_load_state = dr._load_state
    orig_discover = dr.dc.discover
    orig_open_exp = dr._open_experiments
    orig_load_facts = dr._load_facts
    orig_canary = dr._canary_result
    dr.cfg.load_companions = lambda path: {"companions": companions, "mentions": []}
    dr._ensure_fresh_state = lambda: state
    dr._load_state = lambda path=None: None
    dr.dc.discover = lambda: []
    dr._open_experiments = lambda exp_dir=None: []
    dr._load_facts = lambda path=None: ([], [], "Expecting value: line 1 column 1 (char 0)")
    dr._canary_result = _no_data_canary
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = dr.report()
        out = buf.getvalue()
    finally:
        dr.cfg.load_companions = orig_load
        dr._ensure_fresh_state = orig_fresh
        dr._load_state = orig_load_state
        dr.dc.discover = orig_discover
        dr._open_experiments = orig_open_exp
        dr._load_facts = orig_load_facts
        dr._canary_result = orig_canary

    assert rc == 0
    facts_section = out.split("Facts (staleness", 1)[1]
    assert "NO DATA: Expecting value" in facts_section, out



def test_fact_without_its_own_interval_uses_the_thirty_day_default():
    # A fact that states no review_interval_days falls back to
    # DEFAULT_FACT_REVIEW_DAYS. That default is 30 days, not a quarter: a
    # documented default, a cache rule or a price can change in any week, and
    # a fact going stale must surface within one monthly reporting cycle.
    bare = {"id": "A9", "statement": "a platform fact",
            "source": "code.claude.com/docs/en/x", "verified": "2026-07-01"}
    assert "review_interval_days" not in bare
    # 2026-07-01 to 2026-08-05 is 35 days: past 30, inside 90.
    flagged = dr._fact_staleness_lines([bare], today="2026-08-05")
    assert flagged and "NEEDS REVIEW" in "\n".join(flagged), flagged
    assert "A9" in "\n".join(flagged), flagged
    # 2026-07-01 to 2026-07-20 is 19 days: inside 30, so silent.
    assert dr._fact_staleness_lines([bare], today="2026-07-20") == []


def test_canary_result_delegates_to_measure_tokens_without_touching_real_transcripts():
    """_canary_result(root=...) must call through to
    measure_tokens.format_canary with the given root rather than always
    reading TRANSCRIPT_ROOT, so a test can point it at a temp directory
    instead of the founder's real ~/.claude/projects."""
    with tempfile.TemporaryDirectory() as d:
        result = dr._canary_result(root=d)
    assert result["state"] == "NO DATA", result
    assert result["transcripts"] == 0, result
    assert result["exit_code"] == 0, result


def test_canary_lines_healthy_state_is_not_needs_review():
    canary = {"reason": "5/5 assistant message(s) across 1 transcript(s) yielded "
                        "a recognised usage key.", "parse_health": None}
    lines = dr._canary_lines(canary)
    joined = "\n".join(lines)
    assert "NEEDS REVIEW" not in joined, lines
    assert "5/5" in joined, lines


def test_canary_lines_unrecognised_state_is_needs_review():
    canary = {"reason": "FORMAT UNRECOGNISED: 4 assistant message(s) across "
                        "1 transcript(s), 0 recognised a usage key.",
              "parse_health": "UNRECOGNISED"}
    lines = dr._canary_lines(canary)
    joined = "\n".join(lines)
    assert "NEEDS REVIEW" in joined, lines
    assert "FORMAT UNRECOGNISED" in joined, lines


def test_report_surfaces_format_unrecognised_and_returns_nonzero():
    """The alarm this whole task exists to wire: when the canary reports
    FORMAT UNRECOGNISED, doctor's report() must print it beside the other
    NEEDS REVIEW lines AND return a nonzero exit code, unlike every other
    finding in this module which is informational only."""
    companions = []
    state = _state([])
    unrecognised_canary = {
        "transcripts": 2, "messages": 6, "recognised": 0,
        "parse_health": "UNRECOGNISED", "state": "FORMAT UNRECOGNISED",
        "reason": "FORMAT UNRECOGNISED: 6 assistant message(s) across 2 "
                  "transcript(s), 0 recognised a usage key.",
        "exit_code": 1,
    }

    orig_load = dr.cfg.load_companions
    orig_fresh = dr._ensure_fresh_state
    orig_load_state = dr._load_state
    orig_discover = dr.dc.discover
    orig_open_exp = dr._open_experiments
    orig_canary = dr._canary_result
    dr.cfg.load_companions = lambda path: {"companions": companions, "mentions": []}
    dr._ensure_fresh_state = lambda: state
    dr._load_state = lambda path=None: None
    dr.dc.discover = lambda: []
    dr._open_experiments = lambda exp_dir=None: []
    dr._canary_result = lambda root=None: unrecognised_canary
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = dr.report()
        out = buf.getvalue()
    finally:
        dr.cfg.load_companions = orig_load
        dr._ensure_fresh_state = orig_fresh
        dr._load_state = orig_load_state
        dr.dc.discover = orig_discover
        dr._open_experiments = orig_open_exp
        dr._canary_result = orig_canary

    assert rc != 0, rc
    assert "NEEDS REVIEW" in out and "FORMAT UNRECOGNISED" in out, out
    assert "Transcript format canary" in out, out


def test_missing_companions_json_still_runs_and_honours_the_canary():
    """Defect D from the review: report() returned rc 0 before the canary
    ever ran when data/companions.json was missing or unreadable, an
    unrelated file silently disabling the layer 0 parser-health alarm. The
    canary must run and its exit code must be honoured regardless of any
    earlier optional section failing."""
    orig_load = dr.cfg.load_companions
    orig_canary = dr._canary_result
    called = {"n": 0}
    unrecognised_canary = {
        "transcripts": 1, "messages": 3, "recognised": 0,
        "parse_health": "UNRECOGNISED", "state": "FORMAT UNRECOGNISED",
        "reason": "FORMAT UNRECOGNISED: 3 assistant message(s) across 1 "
                  "transcript(s), 0 recognised a usage key.",
        "exit_code": 1,
    }

    def spy(root=None):
        called["n"] += 1
        return unrecognised_canary

    dr.cfg.load_companions = lambda path: None
    dr._canary_result = spy
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = dr.report()
        out = buf.getvalue()
    finally:
        dr.cfg.load_companions = orig_load
        dr._canary_result = orig_canary

    assert called["n"] > 0, "the canary was never called when companions.json was missing"
    assert rc == 1, rc
    assert "NO DATA: data/companions.json not found or unreadable." in out, out
    assert "Transcript format canary" in out, out
    assert "FORMAT UNRECOGNISED" in out, out


def test_missing_companions_json_with_healthy_canary_still_returns_zero():
    """The mirror case: the canary's own exit code is what must be honoured,
    not a hardcoded value. Missing companions.json plus a healthy canary
    must still return 0, so this fix does not turn every missing-registry
    run into a false alarm."""
    orig_load = dr.cfg.load_companions
    orig_canary = dr._canary_result
    dr.cfg.load_companions = lambda path: None
    dr._canary_result = _no_data_canary
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = dr.report()
    finally:
        dr.cfg.load_companions = orig_load
        dr._canary_result = orig_canary
    assert rc == 0, rc


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
