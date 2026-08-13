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
import os
import tempfile
import time

import doctor as dr


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

    orig_load = dr.ts.load_companions
    orig_fresh = dr._ensure_fresh_state
    dr.ts.load_companions = lambda path: {"companions": companions, "mentions": []}
    dr._ensure_fresh_state = lambda: state
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = dr.report()
        out = buf.getvalue()
    finally:
        dr.ts.load_companions = orig_load
        dr._ensure_fresh_state = orig_fresh

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

    orig_load = dr.ts.load_companions
    orig_fresh = dr._ensure_fresh_state
    orig_compat = dr._load_compatibility
    dr.ts.load_companions = lambda path: {"companions": companions, "mentions": []}
    dr._ensure_fresh_state = lambda: state
    dr._load_compatibility = lambda: (None, "Expecting value: line 1 column 1 (char 0)")
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = dr.report()
        out = buf.getvalue()
    finally:
        dr.ts.load_companions = orig_load
        dr._ensure_fresh_state = orig_fresh
        dr._load_compatibility = orig_compat

    assert rc == 0
    assert "malformed" in out.lower(), out
    assert "Expecting value" in out, out
    assert "Health" in out and "Staleness" in out and "Overlap" in out, out


def test_main_completes_without_traceback_with_zero_companions_active():
    orig_load = dr.ts.load_companions
    orig_fresh = dr._ensure_fresh_state
    dr.ts.load_companions = lambda path: {"companions": [], "mentions": []}
    dr._ensure_fresh_state = lambda: {"schema": 1, "checked_at": "x", "discovered": [], "registry_match": {}}
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = dr.main([])
        out = buf.getvalue()
    finally:
        dr.ts.load_companions = orig_load
        dr._ensure_fresh_state = orig_fresh
    assert rc == 0
    assert "conflict" not in out.lower(), out


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
