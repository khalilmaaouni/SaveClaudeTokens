#!/usr/bin/env python3
"""Self-check for the three opt-in tools. No framework, no fixtures.

    python3 scripts/test_tools.py

Covers context_lint.py, session_end_telemetry.py and obsidian_export.py. The
meter itself is covered by test_measure_tokens.py.
"""

import importlib.util
import json
import os
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


lint = _load("context_lint")
telem = _load("session_end_telemetry")
export = _load("obsidian_export")
mt = _load("measure_tokens")


def test_loaded_content_matches_what_claude_code_loads():
    # Frontmatter and block-level HTML comments are stripped before loading, so
    # counting them against a limit would report a file as too big when it is
    # not, and would hide the fact that comments are the free place for notes.
    raw = "---\ntitle: x\n---\nreal line\n<!-- a note\nspanning lines -->\nsecond\n"
    body = lint.loaded_content(raw)
    assert "title: x" not in body
    assert "spanning lines" not in body
    assert "real line" in body and "second" in body


def test_memory_index_truncation_is_reported_where_it_actually_cuts():
    # Under both limits: nothing is dropped.
    assert lint.truncation_report("a\nb\nc\n", 200, 25 * 1024) is None

    # Over the line limit: cut at the line limit, and the count of lines that
    # never reach a session is what makes this worth reporting.
    over = "\n".join(f"line {i}" for i in range(250)) + "\n"
    t = lint.truncation_report(over, 200, 25 * 1024)
    assert t["cut_at_line"] == 200 and t["dropped_lines"] == 50
    assert t["reason"] == "line limit"

    # Over the byte limit first: the byte limit must win, because whichever
    # comes first is what Claude Code applies.
    fat = "\n".join("x" * 500 for _ in range(100)) + "\n"
    t = lint.truncation_report(fat, 200, 1000)
    assert t["reason"] == "byte limit"
    assert t["cut_at_line"] < 200
    assert t["dropped_lines"] > 0

    # Frontmatter must not push a compliant file over the limit.
    padded = "---\n" + "k: v\n" * 60 + "---\n" + "\n".join("l" for _ in range(150)) + "\n"
    assert lint.truncation_report(padded, 200, 25 * 1024) is None


def test_lint_finds_duplicate_rules():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "CLAUDE.md")
        with open(p, "w") as f:
            f.write("- always run the full test suite before pushing anything\n"
                    "- something else entirely that is quite different here\n"
                    "- Always run the full test suite before pushing anything.\n")
        findings, stats = lint.check(p, is_memory_index=False)
    assert any("duplicate rule" in m for _, m in findings)
    assert stats["loaded_lines"] == 3


def test_lint_never_reports_a_procedure_as_a_duplicate_of_itself():
    # A run of numbered steps is a procedure finding, not three duplicates.
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "CLAUDE.md")
        with open(p, "w") as f:
            f.write("1. first step of the documented release procedure here\n"
                    "2. second step of the documented release procedure here\n"
                    "3. third step of the documented release procedure here\n"
                    "4. fourth step of the documented release procedure here\n")
        findings, _ = lint.check(p, is_memory_index=False)
    assert any("step procedure" in m for _, m in findings)
    assert not any("duplicate rule" in m for _, m in findings)


def test_ledger_row_carries_counters_and_nothing_else():
    # The privacy contract: a row is counters. If a future edit lets message
    # text into this dict, this test is the thing that catches it.
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "s.jsonl")
        with open(p, "w") as f:
            f.write(json.dumps({
                "isSidechain": False,
                "message": {"model": "m", "content": "SECRET CONVERSATION TEXT",
                            "usage": {"input_tokens": 5,
                                      "cache_creation": {"ephemeral_5m_input_tokens": 10,
                                                         "ephemeral_1h_input_tokens": 0},
                                      "cache_read_input_tokens": 20,
                                      "output_tokens": 7}}}) + "\n")
        row = telem.record(mt, p, "sess-1")

    assert row["calls"] == 1 and row["first_request"] == 35 and row["output"] == 7
    assert row["cache_write_5m"] == 10 and row["cache_write_1h"] == 0
    blob = json.dumps(row)
    assert "SECRET CONVERSATION TEXT" not in blob
    # Only the basename, never the full path, which can name a private project.
    assert row["transcript"] == "s.jsonl" and os.sep not in row["transcript"]
    allowed = {"recorded_at", "session_id", "transcript", "schema", "calls",
               "first_request", "first_request_share", "input", "cache_read",
               "cache_write_5m", "cache_write_1h", "cache_write_unsplit",
               "normalized_input", "output", "hit_ratio", "rewrite_ratio",
               "models", "subagent_calls", "subagent_output"}
    assert set(row) == allowed, set(row) ^ allowed


def test_lever_naming_follows_the_measurement():
    shrink = {"first_request_share_median": 0.36, "hit_ratio_median": 0.95,
              "subagent_output_share": 0.1}
    assert export.lever(shrink)[0] == "Shrink the always-loaded context"

    cache = {"first_request_share_median": 0.05, "hit_ratio_median": 0.4,
             "subagent_output_share": 0.1}
    assert export.lever(cache)[0] == "Keep the cache hot"

    routing = {"first_request_share_median": 0.05, "hit_ratio_median": 0.95,
               "subagent_output_share": 0.5}
    assert export.lever(routing)[0] == "Route work deliberately"

    healthy = {"first_request_share_median": 0.05, "hit_ratio_median": 0.95,
               "subagent_output_share": 0.1}
    assert export.lever(healthy)[0] == "No single dominant lever"

    # Nothing measured must never produce a confident recommendation.
    assert export.lever({"first_request_share_median": None,
                         "hit_ratio_median": None,
                         "subagent_output_share": None})[0] == "NO DATA"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
