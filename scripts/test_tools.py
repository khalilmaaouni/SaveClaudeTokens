#!/usr/bin/env python3
"""Self-check for the three opt-in tools. No framework, no fixtures.

    python3 scripts/test_tools.py

Covers context_lint.py, session_end_telemetry.py and obsidian_export.py. The
meter itself is covered by test_measure_tokens.py.
"""

import importlib.util
import json
import os
import subprocess
import sys
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
shield = _load("token_shield")
mt = _load("measure_tokens")
adv = _load("advisor")


def test_loaded_content_matches_what_claude_code_loads():
    # Frontmatter and block-level HTML comments are stripped before loading, so
    # counting them against a limit would report a file as too big when it is
    # not, and would hide the fact that comments are the free place for notes.
    raw = "---\ntitle: x\n---\nreal line\n<!-- a note\nspanning lines -->\nsecond\n"
    body = lint.loaded_content(raw)
    assert "title: x" not in body
    assert "spanning lines" not in body
    assert "real line" in body and "second" in body

    # Block comment on its own line is stripped; a comment inline in a line of
    # prose is not, because Claude Code strips block-level comments only, and
    # over-stripping would under-report the bytes that actually load.
    assert "note" not in lint.loaded_content("<!-- note -->\nkept\n")
    assert "inline" in lint.loaded_content("a rule <!-- inline --> and text\n")


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

    # Exact boundary: 200 lines fit, 201 cut at 200.
    assert lint.truncation_report("\n".join("l" for _ in range(200)) + "\n",
                                  200, 25 * 1024) is None
    assert lint.truncation_report("\n".join("l" for _ in range(201)) + "\n",
                                  200, 25 * 1024)["cut_at_line"] == 200

    # CRLF: each line's terminator is 2 bytes, so the byte cut must count them.
    # 3 lines of 10 chars are 12 bytes each with CRLF; a 25 byte limit fits 2.
    crlf = "\r\n".join("x" * 10 for _ in range(3)) + "\r\n"
    t = lint.truncation_report(crlf, 200, 25)
    assert t["reason"] == "byte limit" and t["cut_at_line"] == 2, t


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


def test_project_slug_replaces_every_non_alphanumeric():
    # The bug this catches: a username with a dot (like jane.doe) has its
    # directory slugged with every non-alphanumeric turned to a dash, not just
    # the path separator. A separator-only replace misses its own project's
    # memory and then silently reports nothing.
    # Assert on the slug segment only: the expanded ~ prefix is the real home
    # path, which may legitimately contain non-alphanumerics of its own.
    p = lint.expected_memory_index_path("/Users/jane.doe/My_Proj (v2)")
    slug = p.split(os.sep + "projects" + os.sep, 1)[1].split(os.sep, 1)[0]
    assert slug == "-Users-jane-doe-My-Proj--v2-", slug
    assert p.endswith(os.path.join("memory", "MEMORY.md"))


def test_ledger_main_writes_only_allowed_keys():
    # test_ledger_row_carries_counters covers record(). This covers the actual
    # bytes main() puts on disk, which is where a future widening edit would
    # land and where record()'s test cannot see.
    with tempfile.TemporaryDirectory() as d:
        transcript = os.path.join(d, "sess.jsonl")
        with open(transcript, "w") as f:
            f.write(json.dumps({
                "isSidechain": False,
                "message": {"model": "m", "content": "PRIVATE PROMPT TEXT",
                            "usage": {"input_tokens": 5,
                                      "cache_creation": {"ephemeral_5m_input_tokens": 10,
                                                         "ephemeral_1h_input_tokens": 0},
                                      "cache_read_input_tokens": 20,
                                      "output_tokens": 7}}}) + "\n")
        ledger = os.path.join(d, "ledger.jsonl")
        r = subprocess.run(
            [sys.executable, os.path.join(HERE, "session_end_telemetry.py"),
             "--transcript", transcript, "--ledger", ledger],
            capture_output=True, text=True)
        assert r.returncode == 0
        assert r.stdout == "", f"stdout must be empty, got: {r.stdout!r}"
        written = open(ledger).read()
    assert "PRIVATE PROMPT TEXT" not in written
    row = json.loads(written)
    allowed = {"recorded_at", "session_id", "transcript", "schema", "calls",
               "first_request", "first_request_share", "input", "cache_read",
               "cache_write_5m", "cache_write_1h", "cache_write_unsplit",
               "normalized_input", "output", "hit_ratio", "rewrite_ratio",
               "models", "subagent_calls", "subagent_output"}
    assert set(row) == allowed, set(row) ^ allowed


def test_telemetry_never_breaks_the_session():
    # The headline safety claim: hostile input exits 0 and prints nothing to
    # stdout, so a wired-in hook can never fail the session it measures.
    script = os.path.join(HERE, "session_end_telemetry.py")
    for stdin_text in ("not json", "", "[1,2,3]", '{"no_transcript":true}',
                       '{"transcript_path":"/does/not/exist"}'):
        r = subprocess.run([sys.executable, script], input=stdin_text,
                           capture_output=True, text=True)
        assert r.returncode == 0, f"nonzero on {stdin_text!r}"
        assert r.stdout == "", f"stdout not empty on {stdin_text!r}: {r.stdout!r}"


def test_lever_naming_follows_the_measurement():
    # Both renderers map the shared mt.dominant_lever key to their own wording.
    shrink = {"first_request_share_median": 0.36, "hit_ratio_median": 0.95,
              "subagent_output_share": 0.1}
    assert export.lever(shrink, mt)[0] == "Shrink the always-loaded context"
    assert shield.lever(shrink, mt)[0] == "Shrink the always-loaded context"

    cache = {"first_request_share_median": 0.05, "hit_ratio_median": 0.4,
             "subagent_output_share": 0.1}
    assert export.lever(cache, mt)[0] == "Keep the cache hot"
    assert shield.lever(cache, mt)[0] == "Keep the cache hot"

    routing = {"first_request_share_median": 0.05, "hit_ratio_median": 0.95,
               "subagent_output_share": 0.5}
    assert export.lever(routing, mt)[0] == "Route work deliberately"

    healthy = {"first_request_share_median": 0.05, "hit_ratio_median": 0.95,
               "subagent_output_share": 0.1}
    assert export.lever(healthy, mt)[0] == "No single dominant lever"

    # Nothing measured must never produce a confident recommendation.
    nodata = {"first_request_share_median": None, "hit_ratio_median": None,
              "subagent_output_share": None}
    assert export.lever(nodata, mt)[0] == "NO DATA"
    assert shield.lever(nodata, mt)[0].startswith("Not enough")


def test_shield_saving_is_ninety_percent_of_cache_reads():
    # The hero number is the honest one: a cached token bills at 0.1x, so the
    # saving against the uncached price is 0.9x per read token.
    assert shield.CACHE_READ == 0.1
    assert shield.human(1_500_000) == "1.5M"
    assert shield.human(76_300_000_000) == "76.3B"
    assert shield.human(None) == "NO DATA"


def test_shield_saving_is_net_of_the_write_premium():
    # The headline must be NET: the gross read saving minus the cache-write
    # premium (0.25x on 5m writes, 1.0x on 1h writes). Reporting the gross as
    # the net was the exact overstatement an audit flagged.
    sm = {"read_total": 100.0, "write_5m_total": 40.0, "write_1h_total": 10.0,
          "input_total": 5.0}
    sv = shield.savings_breakdown(sm)
    assert sv["gross"] == 90.0                      # 0.9 * 100
    assert sv["write_premium"] == 0.25 * 40 + 1.0 * 10   # 20.0
    assert sv["saved"] == 90.0 - 20.0               # 70.0 net, not 90 gross


def test_dashboard_attributes_the_saving_to_native_caching():
    # The load-bearing honesty: the hero saving is Claude Code's native caching,
    # not this tool's doing. A future edit that quietly re-claims it as the
    # plugin's own must fail here.
    sm = {"read_total": 1000, "write_5m_total": 100, "write_1h_total": 50,
          "input_total": 10, "first_request_median": 8000,
          "first_request_share_median": 0.36, "hit_ratio_median": 0.9,
          "subagent_output_share": 0.2, "output_total": 0}
    sessions = [{"first_request": 8000, "calls": 20, "models": 2,
                 "rewrite_ratio": 0.02, "read": 1000, "hit_ratio": 0.9}]
    html = shield.render(mt, sm, sessions, 30, "stamp", include_sessions=False)
    assert "not this tool" in html.lower()          # "Not this tool's doing"
    assert "does not claim it" in html              # the hero's explicit disclaimer
    assert "native" in html.lower()
    # The three confidence-labeled columns must stay distinct, never merged.
    assert "Verified" in html and "Native" in html and "Opportunity" in html
    # The tool's own value must be framed as separate and additional.
    assert "separate from" in html.lower() or "on top of" in html.lower()


def test_prescriptions_are_adaptive_and_carry_the_math():
    mt2 = mt

    def sess(first, calls, models=1, rewrite=0.0, read=0):
        return {"first_request": first, "calls": calls, "models": models,
                "rewrite_ratio": rewrite, "read": read}

    # A profile with model switching and a heavy floor.
    sessions = ([sess(90000, 300, models=2) for _ in range(6)]
                + [sess(90000, 300, models=1) for _ in range(4)])
    sm = {"first_request_median": 90000, "first_request_share_median": 0.36,
          "read_total": 0, "write_5m_total": 0, "write_1h_total": 0, "input_total": 0}
    rx = shield.prescriptions(sm, sessions)
    titles = [r["title"] for r in rx]
    assert "Switching model mid-session" in titles
    assert "The always-loaded startup floor" in titles
    # The switch card carries its own measured count and a real saving figure.
    sw = next(r for r in rx if r["title"].startswith("Switching"))
    assert "6 of 10" in sw["measure"] and sw["saving"] > 0
    assert sw["tag"] == "PROVEN"

    # A clean profile gets no prescriptions: the dashboard is adaptive, not
    # a fixed lecture.
    clean = [sess(9000, 50, models=1) for _ in range(5)]
    sm_clean = {"first_request_median": 9000, "first_request_share_median": 0.10,
                "read_total": 0, "write_5m_total": 0, "write_1h_total": 0, "input_total": 0}
    assert shield.prescriptions(sm_clean, clean) == []


def _leaf(v, label="MEASURED"):
    return {"value": v, "label": label, "basis": "test basis"}


def _synthetic_profile(switch_share=0.5, floor_share=0.05, output_total=1000,
                        hit_ratio=0.9, first_request=9000):
    return {
        "schema": 1,
        "usage": {
            "first_request_median_tokens": _leaf(first_request),
            "cache_hit_ratio_median": _leaf(hit_ratio),
            "output_tokens_total": _leaf(output_total),
            "subagent_output_share": _leaf(0.1),
            "cache_write_5m_tokens": _leaf(0),
            "cache_write_1h_tokens": _leaf(0),
        },
        "behavior": {
            "sessions": _leaf(10),
            "model_switch_session_share": _leaf(switch_share),
            "effort_values_seen": _leaf([]),
            "idle_gap_shares": _leaf(0.0),
            "subagent_transcript_share": _leaf(0.1),
        },
        "instruction": {
            "claude_md_user_bytes": _leaf(500),
            "claude_md_project_bytes": _leaf(500),
            "startup_floor_share": _leaf(floor_share),
            "memory_index_bytes": _leaf(500),
        },
        "environment": {
            "plugin_count": _leaf(1, "INFERRED"),
            "ttl_regime": _leaf("api-5m", "INFERRED"),
        },
        "skipped": {"files": _leaf(0), "lines": _leaf(0)},
    }


def _mini_strategy(sid, category, metric, op, value, band):
    return {
        "id": sid, "category": category, "title": f"title-{sid}",
        "trigger": {"metric": metric, "op": op, "value": value, "band": band},
        "what_it_changes": "x", "expected_benefit": "x", "evidence": "ESTIMATED",
        "drawback": "x", "quality_risk": "LOW", "reversibility": "x", "how_measured": "x",
        "if_you_say_no": "x", "alternatives": [], "companion": None,
        "requires_confirmation": False, "source": "test",
    }


def _sm_and_sessions():
    sm = {"read_total": 1000, "write_5m_total": 100, "write_1h_total": 50,
          "input_total": 10, "first_request_median": 9000,
          "first_request_share_median": 0.36, "hit_ratio_median": 0.9,
          "subagent_output_share": 0.1, "output_total": 1000}
    sessions = [{"first_request": 9000, "calls": 20, "models": 2,
                 "rewrite_ratio": 0.02, "read": 1000, "hit_ratio": 0.9}]
    return sm, sessions


def test_dashboard_new_sections_render_with_all_sources_present():
    # Calibrated: with the six shield.render_*() calls commented out of
    # render(), this test goes red (markers missing); restored, it is green.
    with tempfile.TemporaryDirectory() as d:
        profile = shield.load_profile(_write_json(d, "profile.json",
                                                    _synthetic_profile(switch_share=0.5)))
        strategies = adv.load_strategies()
        advise_result = adv.advise(profile, {}, strategies)
        assert advise_result["best"] is not None  # 0.5 switch share fires a HIGH card

        companions_data = shield.load_companions(_write_json(d, "companions.json", {
            "companions": [{"name": "ponytail", "when": "test when",
                            "benefit": "smaller diffs", "drawback": "can under-build"}],
            "mentions": [{"name": "ccusage", "repo": "github.com/ccusage/ccusage",
                         "reason": "usage accounting", "status": "not vetted"}],
        }))
        cache_root = os.path.join(d, "plugins", "cache")
        os.makedirs(os.path.join(cache_root, "claude-community", "ponytail"))

        with open(os.path.join(d, "savings.jsonl"), "w") as f:
            f.write(json.dumps({"label": "shrink-claude-md", "confidence": "VERIFIED",
                                "floor_reduction_tokens": 500,
                                "timestamp": "2026-08-12T10:00:00+0000"}) + "\n")
        experiment_rows = shield.load_experiment_rows(os.path.join(d, "savings.jsonl"))

        sm, sessions = _sm_and_sessions()
        html = shield.render(mt, sm, sessions, 30, "stamp", include_sessions=False,
                             profile=profile, advise_result=advise_result, suppressed_n=0,
                             companions_data=companions_data, experiment_rows=experiment_rows,
                             plugin_cache_root=cache_root)

    for marker in ("Next best move", "Observed pattern", "Recommendation queue",
                   "Companions", "Experiment history", "Alerts"):
        assert marker in html, marker
    assert "installed" in html.lower()
    assert "shrink-claude-md" in html


def _write_json(d, name, data):
    p = os.path.join(d, name)
    with open(p, "w") as f:
        json.dump(data, f)
    return p


def test_dashboard_new_sections_show_no_data_with_every_source_absent():
    sm = {"read_total": 0, "write_5m_total": 0, "write_1h_total": 0, "input_total": 0,
          "first_request_median": None, "first_request_share_median": None,
          "hit_ratio_median": None, "subagent_output_share": None, "output_total": 0}
    html = shield.render(mt, sm, [], 30, "stamp", include_sessions=False,
                         profile=None, advise_result=None, suppressed_n=0,
                         companions_data=None, experiment_rows=None)
    assert html.count("NO DATA") >= 5  # next best move, observed pattern, queue, companions, alerts
    assert "No experiments yet." in html


def test_recommendation_queue_never_renders_more_than_three_items():
    # Calibrated: dropping the `[:3]` slice in render_recommendation_queue lets
    # this go red (5 rendered instead of 3); restored, it is green.
    fake_cards = [{"id": f"c{i}", "title": f"t{i}", "evidence": "ESTIMATED", "drawback": "d"}
                  for i in range(5)]
    fake_result = {"best": fake_cards[0], "alternatives": fake_cards[1:], "companion": None,
                   "queue": fake_cards, "do_nothing": False, "advisor_cost_tokens": 0,
                   "insufficient": []}
    html = shield.render_recommendation_queue(fake_result, 0)
    assert html.count('class="pain-item"') == 3, html.count('class="pain-item"')


def test_suppressed_treatment_reduces_the_rendered_queue():
    # Calibrated: passing {} instead of `treatments` to the "with" advise()
    # call makes both queues equal length and this test goes red; restored,
    # the suppressed queue is the shorter one and it is green.
    strategies = [
        _mini_strategy("cache.a", "cache", "usage.m1", ">=", 1, "HIGH"),
        _mini_strategy("startup.b", "startup", "usage.m2", ">=", 1, "HIGH"),
    ]
    profile = {"usage": {"m1": _leaf(5), "m2": _leaf(5)}}
    treatments = {"cache.a": {"decision": "rejected", "until": "2999-01-01T00:00:00"}}

    without = adv.advise(profile, {}, strategies)
    with_t = adv.advise(profile, treatments, strategies)
    assert len(without["queue"]) == 2
    assert len(with_t["queue"]) == 1

    n = shield.suppressed_recommendation_count(adv, profile, treatments, strategies)
    assert n == 1

    html_without = shield.render_recommendation_queue(without, 0)
    html_with = shield.render_recommendation_queue(with_t, n)
    assert html_without.count('class="pain-item"') == 2
    assert html_with.count('class="pain-item"') == 1
    assert "suppressed by your earlier choices" in html_with


def test_dashboard_html_contains_no_en_or_em_dash():
    profile = _synthetic_profile(switch_share=0.5, floor_share=0.36)
    strategies = adv.load_strategies()
    advise_result = adv.advise(profile, {}, strategies)
    sm, sessions = _sm_and_sessions()
    html = shield.render(mt, sm, sessions, 30, "stamp", include_sessions=False,
                         profile=profile, advise_result=advise_result,
                         companions_data={"companions": [], "mentions": []},
                         experiment_rows=[])
    assert "–" not in html, "en dash found in rendered dashboard"
    assert "—" not in html, "em dash found in rendered dashboard"


def test_experiment_history_never_sums_across_labels():
    # Calibrated: adding a "total" row with 500 + 700 = 1200 to
    # render_experiment_history makes this go red; without it, green.
    rows = [
        {"label": "shrink-claude-md", "confidence": "VERIFIED", "floor_reduction_tokens": 500,
         "timestamp": "2026-08-01T10:00:00+0000"},
        {"label": "prune-plugins", "confidence": "VERIFIED", "floor_reduction_tokens": 700,
         "timestamp": "2026-08-05T10:00:00+0000"},
    ]
    html = shield.render_experiment_history(rows)
    assert "shrink-claude-md" in html and "prune-plugins" in html
    assert "1,200" not in html and "1200" not in html


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
