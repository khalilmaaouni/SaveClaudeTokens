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
    assert "wave 2" in out.lower(), out


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
