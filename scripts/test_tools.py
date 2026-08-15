#!/usr/bin/env python3
"""Self-check for the three opt-in tools. No framework, no fixtures.

    python3 scripts/test_tools.py

Covers context_lint.py, session_end_telemetry.py and obsidian_export.py. The
meter itself is covered by test_measure_tokens.py.
"""

import importlib.util
import json
import os
import re
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
met = _load("metrics")
fmt = _load("formatting")
cfg = _load("config")
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
    assert met.lever(shrink, mt)[0] == "Shrink the always-loaded context"

    cache = {"first_request_share_median": 0.05, "hit_ratio_median": 0.4,
             "subagent_output_share": 0.1}
    assert export.lever(cache, mt)[0] == "Keep the cache hot"
    assert met.lever(cache, mt)[0] == "Keep the cache hot"

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
    assert met.lever(nodata, mt)[0].startswith("Not enough")


def test_shield_saving_is_ninety_percent_of_cache_reads():
    # The hero number is the honest one: a cached token bills at 0.1x, so the
    # saving against the uncached price is 0.9x per read token.
    assert met.CACHE_READ == 0.1
    assert fmt.human(1_500_000) == "1.5M"
    assert fmt.human(76_300_000_000) == "76.3B"
    assert fmt.human(None) == "NO DATA"


def test_shield_saving_is_net_of_the_write_premium():
    # The headline must be NET: the gross read saving minus the cache-write
    # premium (0.25x on 5m writes, 1.0x on 1h writes). Reporting the gross as
    # the net was the exact overstatement an audit flagged.
    sm = {"read_total": 100.0, "write_5m_total": 40.0, "write_1h_total": 10.0,
          "input_total": 5.0}
    sv = met.savings_breakdown(sm)
    assert sv["gross"] == 90.0                      # 0.9 * 100
    assert sv["write_premium"] == 0.25 * 40 + 1.0 * 10   # 20.0
    assert sv["saved"] == 90.0 - 20.0               # 70.0 net, not 90 gross


def test_native_charges_a_premium_for_writes_whose_ttl_is_unknown():
    """A cache write with no TTL split cannot be priced: measure_tokens sets
    normalized input to NO DATA for exactly that data, at measure_tokens.py
    around the split_writes docstring. Charging it nothing made the NATIVE
    headline LARGEST precisely where the evidence was WEAKEST.

    NATIVE is the one row attributed to Anthropic rather than claimed by this
    tool, so it has to be a lower bound. Unsplit writes are therefore charged
    at the most expensive TTL (1.0x, the 1 hour rate), which understates the
    saving rather than overstating it. Understating Anthropic's benefit is a
    caveat; overstating it is the dishonesty the whole product exists against.

    Calibrated by reinjection: dropping write_unsplit_total back out of the
    premium makes the unsplit fixture report 90.0 saved against the split
    fixture's 40.0, and the first assertion fails.
    """
    common = {"read_total": 100.0, "input_total": 5.0}
    split = dict(common, write_5m_total=0.0, write_1h_total=50.0,
                 write_unsplit_total=0.0)
    unsplit = dict(common, write_5m_total=0.0, write_1h_total=0.0,
                   write_unsplit_total=50.0)

    sv_split = met.savings_breakdown(split)
    sv_unsplit = met.savings_breakdown(unsplit)

    assert sv_unsplit["saved"] <= sv_split["saved"], (
        f"unknown-TTL writes reported a LARGER saving ({sv_unsplit['saved']}) "
        f"than the same volume at the most expensive known TTL "
        f"({sv_split['saved']})")
    assert sv_unsplit["write_premium"] == 50.0
    # The count travels with the number so a surface can disclose it rather
    # than printing a quietly weaker figure that looks identical.
    assert sv_unsplit["write_unsplit"] == 50.0
    assert sv_split["write_unsplit"] == 0.0


def test_native_discloses_unpriceable_writes_and_stays_silent_without_them():
    """A NATIVE figure computed partly from writes that could not be priced
    must SAY so on the same line as the number. Charging them conservatively
    (the test above) stops the overstatement; without the disclosure the
    weaker figure still prints identically to a fully priced one, and a reader
    cannot tell which they are looking at.

    The note names the volume, not a transcript count: the volume is what the
    counters actually carry. NO DATA beats a guess, including a guessed count.
    """
    none_unsplit = met.savings_breakdown(
        {"read_total": 100.0, "write_5m_total": 40.0, "write_1h_total": 10.0,
         "write_unsplit_total": 0.0, "input_total": 5.0})
    some_unsplit = met.savings_breakdown(
        {"read_total": 1e9, "write_5m_total": 0.0, "write_1h_total": 0.0,
         "write_unsplit_total": 1_200_000.0, "input_total": 5.0})

    assert shield.native_note(none_unsplit) == "", (
        "a fully priced figure must carry no caveat at all")
    note = shield.native_note(some_unsplit)
    assert "1.2M" in note, note
    assert "TTL" in note, note


def test_savings_breakdown_survives_a_summary_missing_the_unsplit_key():
    # Callers pass partial summary dicts (the sibling premium test does), and
    # a summary written by an older schema has no unsplit key at all. A missing
    # key is zero, never a crash on a caller's first run.
    sv = met.savings_breakdown({"read_total": 100.0, "write_5m_total": 40.0,
                                   "write_1h_total": 10.0, "input_total": 5.0})
    assert sv["write_unsplit"] == 0
    assert sv["saved"] == 70.0


def test_dashboard_attributes_the_saving_to_native_caching():
    # The load-bearing honesty: the native caching saving is Claude Code's,
    # not this tool's doing. A future edit that quietly re-claims it as the
    # plugin's own must fail here. Since v1.7.1 the dashboard shows only
    # what the user can act on: native caching is one pointer sentence, no
    # numbers, no bars, pointing at docs/METHODOLOGY.md for the accounting.
    sm = {"read_total": 1000, "write_5m_total": 100, "write_1h_total": 50,
          "input_total": 10, "first_request_median": 8000,
          "first_request_share_median": 0.36, "hit_ratio_median": 0.9,
          "subagent_output_share": 0.2, "output_total": 0}
    sessions = [{"first_request": 8000, "calls": 20, "models": 2,
                 "rewrite_ratio": 0.02, "read": 1000, "hit_ratio": 0.9}]
    html = shield.render(mt, sm, sessions, 30, "stamp", include_sessions=False)
    assert "not this tool" in html.lower()          # "not this tool's, and it does not claim it"
    assert "does not claim it" in html              # the pointer line's explicit disclaimer
    assert "native" in html.lower()
    assert "docs/METHODOLOGY.md" in html
    # Verified and the addressable opportunity both still appear, kept apart
    # from native by construction (native carries no number on this page).
    assert "Verified" in html and "Opportunity" in html
    # The tool's own value must be framed as separate and additional.
    assert "separate from" in html.lower() or "on top of" in html.lower()


def test_dashboard_shows_no_native_bars_or_dollars_only_a_methodology_pointer():
    # Calibrated: reinjecting the old hero3 dollar fragment and the "Where
    # the native saving comes from" bars section makes this go red; with
    # both removed and the single pointer line in their place, it is green.
    sm = {"read_total": 1000, "write_5m_total": 100, "write_1h_total": 50,
          "input_total": 10, "first_request_median": 8000,
          "first_request_share_median": 0.36, "hit_ratio_median": 0.9,
          "subagent_output_share": 0.2, "output_total": 0}
    sessions = [{"first_request": 8000, "calls": 20, "models": 2,
                 "rewrite_ratio": 0.02, "read": 1000, "hit_ratio": 0.9}]
    usd_res = {"status": "OK", "usd": 401962, "snapshot": "2026-08-01",
               "rows": [], "unpriced_units": 0}
    html = shield.render(mt, sm, sessions, 30, "stamp", include_sessions=False, usd_res=usd_res)
    assert "API-equivalent" not in html
    assert "$" not in html
    assert "Where the native saving comes from" not in html
    assert 'class="compare"' not in html
    assert "docs/METHODOLOGY.md" in html


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
    rx = met.prescriptions(sm, sessions)
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
    assert met.prescriptions(sm_clean, clean) == []


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
        profile = met.load_profile(_write_json(d, "profile.json",
                                                    _synthetic_profile(switch_share=0.5)))
        strategies = adv.load_strategies()
        advise_result = adv.advise(profile, {}, strategies)
        assert advise_result["best"] is not None  # 0.5 switch share fires a HIGH card

        companions_data = cfg.load_companions(_write_json(d, "companions.json", {
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
        experiment_rows = met.load_experiment_rows(os.path.join(d, "savings.jsonl"))

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


def test_alerts_band_fires_on_a_bad_profile_and_stays_quiet_on_a_healthy_one():
    # Calibrated: raising ALERT_THRESHOLDS well above what the bad profile
    # carries (or deleting the fired-card loop) makes the first assert go
    # red; restored, all three thresholds fire and it is green. The healthy
    # profile below crosses none of them, by construction: no alert ever
    # fires on healthy data.
    bad = _synthetic_profile(switch_share=0.9, floor_share=0.9, hit_ratio=0.1)
    bad_html = shield.render_alerts(bad)
    assert bad_html.count('class="alert"') == 3, bad_html.count('class="alert"')
    assert "Why it matters" in bad_html and "Action" in bad_html and "When" in bad_html
    assert "no active alerts" not in bad_html

    healthy = _synthetic_profile(switch_share=0.1, floor_share=0.05, hit_ratio=0.95)
    healthy_html = shield.render_alerts(healthy)
    assert 'class="alert"' not in healthy_html
    assert "no active alerts" in healthy_html

    # The meter itself reporting NO DATA (no profile.json at all) is its own
    # alert-shaped state, distinct from a healthy read.
    nodata_html = shield.render_alerts(None)
    assert "NO DATA" in nodata_html


def test_card_renders_its_numbered_how_steps_and_command():
    # Calibrated: removing the _render_how()/_render_chips() calls from
    # render_next_best_move makes this go red (no "How, exactly" block, no
    # command); restored, both render and the command is copy-pasteable.
    # The chips moved to the Next best move card ALONE: they used to repeat
    # under every queued card, printing the same three commands three times.
    real = adv.load_strategies()
    profile = _nest_flat({"behavior.model_switch_session_share": _leaf(0.5)})
    result = adv.advise(profile, {}, real)
    assert result["best"] is not None

    best_html = shield.render_next_best_move(result)
    assert "How, exactly" in best_html
    assert "<code>python3 scripts/cli.py advise --decide" in best_html
    assert "not-now" in best_html and "never" in best_html and " done</code>" in best_html
    assert ("Did it" in best_html and "Not now (90 days quiet)" in best_html
            and "Never recommend" in best_html)
    assert "/token-shield:advisor" in best_html

    # A queued card still shows its steps, and still names where to decide.
    two = _nest_flat({"behavior.model_switch_session_share": _leaf(0.5),
                      "instruction.startup_floor_share": _leaf(0.9)})
    queued = adv.advise(two, {}, real)
    assert len(queued["queue"]) >= 2, queued["queue"]
    html = shield.render_recommendation_queue(queued, 0)
    assert "How, exactly" in html
    assert "/token-shield:advisor" in html


def _nest_flat(flat):
    profile = {}
    for dotted, val in flat.items():
        node = profile
        parts = dotted.split(".")
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = val
    return profile


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

    n = met.suppressed_recommendation_count(adv, profile, treatments, strategies)
    assert n == 1

    # One fewer card renders once suppression bites. The rendered counts are
    # one below the queue lengths above because the best card is shown in its
    # own section and is no longer repeated here.
    html_without = shield.render_recommendation_queue(without, 0)
    html_with = shield.render_recommendation_queue(with_t, n)
    assert html_without.count('class="pain-item"') == 1
    assert html_with.count('class="pain-item"') == 0
    assert "suppressed by your earlier choices" in html_with


def test_companion_only_suppression_never_reads_as_the_users_own_choice():
    # Calibrated: before this split, suppressed_recommendation_count folded
    # a companion-caused suppression (reason "companion", written by
    # sync_companion_suppressions, nothing the user ever decided) into the
    # same count as a user's rejected/not-now choice, and the dashboard
    # rendered "suppressed by your earlier choices" over a decision the user
    # never made. suppressed_recommendation_counts must split the two, and
    # each count must render its own honest line, never the other's.
    strategies = [
        _mini_strategy("cache.a", "cache", "usage.m1", ">=", 1, "HIGH"),
        _mini_strategy("startup.b", "startup", "usage.m2", ">=", 1, "HIGH"),
    ]
    profile = {"usage": {"m1": _leaf(5), "m2": _leaf(5)}}
    treatments = {
        "cache.a": {"decision": "rejected", "until": "2999-01-01T00:00:00"},
        "startup.b": {"decision": "suppressed", "until": "2999-01-01T00:00:00",
                      "reason": "companion"},
    }

    with_t = adv.advise(profile, treatments, strategies)
    assert len(with_t["queue"]) == 0

    user_n, companion_n = met.suppressed_recommendation_counts(adv, profile, treatments, strategies)
    assert user_n == 1, user_n
    assert companion_n == 1, companion_n

    html = shield.render_recommendation_queue(with_t, user_n, companion_n)
    assert "1 recommendation(s) suppressed by your earlier choices" in html, html
    assert "1 recommendation(s) suppressed because an already installed companion" in html, html
    assert "not your choice" in html, html

    # A companion-only suppression, with no user-caused one at all, must
    # never render the "your earlier choices" line: that is the exact
    # honesty defect this fix closes.
    companion_only = {"startup.b": treatments["startup.b"]}
    with_c = adv.advise(profile, companion_only, strategies)
    user_n2, companion_n2 = met.suppressed_recommendation_counts(adv, profile, companion_only, strategies)
    assert user_n2 == 0, user_n2
    assert companion_n2 == 1, companion_n2
    html_c = shield.render_recommendation_queue(with_c, user_n2, companion_n2)
    assert "your earlier choices" not in html_c, html_c
    assert "not your choice" in html_c, html_c


def test_dashboard_html_contains_no_en_or_em_dash():
    profile = _synthetic_profile(switch_share=0.5, floor_share=0.36)
    strategies = adv.load_strategies()
    advise_result = adv.advise(profile, {}, strategies)
    sm, sessions = _sm_and_sessions()
    html = shield.render(mt, sm, sessions, 30, "stamp", include_sessions=False,
                         profile=profile, advise_result=advise_result,
                         companions_data={"companions": [], "mentions": []},
                         experiment_rows=[])
    assert "\u2013" not in html, "en dash found in rendered dashboard"
    assert "\u2014" not in html, "em dash found in rendered dashboard"


def test_verified_headline_is_per_label_and_never_a_cross_label_total():
    # Calibrated: restoring the old headline (sum of floor_reduction_tokens
    # with max(0, ...) per record) makes the page show 10,000 and this test
    # goes red on both the total check and the regression check; with
    # verified_by_label, green.
    #
    # The ledger below is the reviewer's repro: one label measured twice at
    # +5000, and a second label that REGRESSED by 8000. The old headline
    # clipped the regression to zero and added the repeats, printing 10,000,
    # a number about nothing, on a page that says one paragraph later that
    # floor deltas are never summed across labels.
    rows = [
        {"label": "diet-claude-md", "confidence": "VERIFIED", "direction": "saving",
         "floor_reduction_tokens": 5000, "timestamp": "2026-08-01T10:00:00+0000"},
        {"label": "diet-claude-md", "confidence": "VERIFIED", "direction": "saving",
         "floor_reduction_tokens": 5000, "timestamp": "2026-08-02T10:00:00+0000"},
        {"label": "prune-mcp", "confidence": "VERIFIED", "direction": "regression",
         "floor_reduction_tokens": -8000, "timestamp": "2026-08-03T10:00:00+0000"},
    ]
    verified = met.verified_by_label(rows)
    assert [r["label"] for r in verified] == ["diet-claude-md", "prune-mcp"], verified
    assert [r["floor_reduction"] for r in verified] == [5000, -8000], verified
    # M3/m1. A regression must never carry the same shape as a saving on the
    # way OUT of verified_by_label, not just on the fixture going in: if the
    # function dropped the field, the input carrying it would prove nothing.
    assert [r["direction"] for r in verified] == ["saving", "regression"], verified

    big, under = shield.render_verified_hero(verified)
    hero = big + under
    assert "10,000" not in hero and "10000" not in hero, hero
    assert "2 LABELS" in big, big
    assert "diet-claude-md +5,000" in under, under
    assert "prune-mcp -8,000" in under, under

    sm, sessions = _sm_and_sessions()
    html = shield.render(mt, sm, sessions, 30, "stamp", include_sessions=False,
                         verified=verified, profile=None, advise_result=None,
                         companions_data=None, experiment_rows=rows)
    assert "10,000" not in html and "10000" not in html
    assert "prune-mcp -8,000" in html
    # The regression is visible as a negative in the history table too, and
    # the repeated label is one row per record there by design (the table is
    # a log), while the headline carries the latest state only.
    assert "-8,000" in html


def test_verified_headline_shows_one_labels_own_number():
    rows = [{"label": "diet-claude-md", "confidence": "VERIFIED",
             "floor_reduction_tokens": 5000, "timestamp": "2026-08-01T10:00:00+0000"},
            {"label": "diet-claude-md", "confidence": "VERIFIED",
             "floor_reduction_tokens": 7000, "timestamp": "2026-08-04T10:00:00+0000"},
            {"label": "half-done", "confidence": "NOT_PROVEN",
             "floor_reduction_tokens": 900, "timestamp": "2026-08-05T10:00:00+0000"}]
    verified = met.verified_by_label(rows)
    assert len(verified) == 1, verified              # NOT_PROVEN is not VERIFIED
    assert verified[0]["floor_reduction"] == 7000    # latest run of the label wins
    big, under = shield.render_verified_hero(verified)
    assert "7.0K" in big, big
    assert "12,000" not in big + under
    assert "diet-claude-md" in under

    # No VERIFIED record at all still reads NONE YET rather than a zero.
    empty_big, empty_under = shield.render_verified_hero([])
    assert "NONE YET" in empty_big
    assert "No verified saving yet" in empty_under


def test_experiment_label_is_escaped_before_it_reaches_the_page():
    # Calibrated: dropping esc() from render_experiment_history puts the raw
    # <img> tag in the page and this test goes red; with esc(), green.
    #
    # An experiment label is typed by the user and rendered into HTML, so it
    # is script-injection shaped. The dashboard is written to a file the user
    # opens in a browser, so an unescaped label executes there.
    payload = '<img src=x onerror=alert(1)>'
    rows = [{"label": payload, "confidence": '"><script>alert(2)</script>',
             "floor_reduction_tokens": 100, "timestamp": "2026-08-01T10:00:00+0000"}]

    history = shield.render_experiment_history(rows)
    assert payload not in history, history
    assert "<script>" not in history, history
    assert "&lt;img src=x onerror=alert(1)&gt;" in history, history

    hero_big, hero_under = shield.render_verified_hero(met.verified_by_label(rows))
    assert payload not in hero_big + hero_under

    companions = shield.render_companions(
        {"companions": [{"name": payload, "when": payload, "benefit": payload,
                         "drawback": payload}],
         "mentions": [{"name": payload, "repo": payload, "reason": payload,
                       "status": payload}]},
        None, "/nonexistent-cache-root")
    assert payload not in companions, companions

    card = {"id": "x", "title": payload, "rank": "RECOMMENDED", "evidence": "ESTIMATED",
            "why_selected": payload, "expected_benefit": payload, "drawback": payload,
            "quality_risk": payload, "reversibility": payload, "if_you_say_no": payload,
            "source": payload}
    advice = {"best": card, "alternatives": [], "companion": None, "queue": [card],
              "do_nothing": False, "advisor_cost_tokens": 0, "insufficient": []}
    assert payload not in shield.render_next_best_move(advice)
    assert payload not in shield.render_recommendation_queue(advice, 0)

    sm, sessions = _sm_and_sessions()
    html = shield.render(mt, sm, sessions, 30, "stamp", include_sessions=False,
                         verified=met.verified_by_label(rows), profile=None,
                         advise_result=advice, companions_data=None, experiment_rows=rows)
    assert payload not in html
    assert "onerror=alert(1)>" not in html


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


def test_waterfall_never_sums_percentages_or_marginal_deltas():
    # Calibrated: the central assertion this unit exists for. core moves A
    # (1,000,000) to B (800,000), a 20% saving of A. companion moves its own
    # measured B (810,000, a SEPARATE measurement of the same nominal state)
    # to C (400,000), a 51% saving of B. Naive-summed percentages would say
    # 20% + 51% = 71% of A saved overall, implying C should be around
    # 290,000; naive-summed token deltas would say 200,000 + 410,000 =
    # 610,000 tokens saved. Both are wrong. The true total, computed straight
    # from A and C, is 600,000 tokens, 60% of A. If build_waterfall ever adds
    # core_delta_pct + companion_delta_pct (or core_delta + companion_delta)
    # instead of deriving the total from A and C directly, this goes red.
    rows = [
        {"label": "core", "confidence": "VERIFIED", "timestamp": "2026-08-01T10:00:00+0000",
         "first_request_before": 1000000, "first_request_after": 800000,
         "floor_reduction_tokens": 200000, "fingerprint_start": "fpA",
         "fingerprint_end": "fpB", "cohort_after": {"start": 2000, "end": 3000}},
        {"label": "companion", "confidence": "VERIFIED", "timestamp": "2026-08-05T10:00:00+0000",
         "first_request_before": 810000, "first_request_after": 400000,
         "floor_reduction_tokens": 410000, "fingerprint_start": "fpB",
         "fingerprint_end": "fpC", "cohort_before": {"start": 3000, "end": 4000}},
    ]
    wf = met.build_waterfall(rows, "core", "companion")
    assert wf["separable"] is True, wf
    assert wf["baseline_a"] == 1000000 and wf["point_b"] == 800000 and wf["point_c"] == 400000
    assert wf["core_delta"] == 200000 and wf["companion_delta"] == 410000
    # The never-sum assertion, at the token level: B was measured twice (once
    # by core's after-cohort, once by companion's before-cohort) and the two
    # readings differ (800,000 vs 810,000), so the marginal deltas do not sum
    # to the true total; the total is read straight off A and C instead.
    assert wf["total_delta"] == 600000, wf["total_delta"]
    assert wf["total_delta"] != wf["core_delta"] + wf["companion_delta"], wf
    # The never-sum assertion, at the percentage level: 20% of A plus 51% of
    # B is not a meaningful 71%, because the two percentages are shares of
    # different baselines.
    assert wf["core_delta_pct"] == 0.2
    assert abs(wf["companion_delta_pct"] - (410000 / 810000)) < 1e-9
    assert wf["total_delta_pct"] == 0.6
    assert wf["total_delta_pct"] != wf["core_delta_pct"] + wf["companion_delta_pct"], wf

    html = shield.render_waterfall(wf, "core", "companion")
    assert "20%" in html and "51%" in html and "60%" in html
    assert "600,000" in html
    assert "610,000" not in html   # the naive token sum must never appear
    assert "71%" not in html       # the naive percentage sum must never appear


def test_waterfall_declares_interaction_not_separable_on_fingerprint_break():
    # Calibrated: simulates exactly what a companion version change looks
    # like on the ledger, reusing the SAME fingerprint fields
    # experiment.build_record already writes (fingerprint_start,
    # fingerprint_end), never a second version-tracking mechanism. If
    # build_waterfall ever chained across a fingerprint break, this goes red
    # on the separable assertion.
    rows = [
        {"label": "core", "confidence": "VERIFIED", "timestamp": "2026-08-01T10:00:00+0000",
         "first_request_before": 1000000, "first_request_after": 800000,
         "floor_reduction_tokens": 200000, "fingerprint_start": "fpA",
         "fingerprint_end": "fpB", "cohort_after": {"start": 2000, "end": 3000}},
        {"label": "companion", "confidence": "VERIFIED", "timestamp": "2026-08-05T10:00:00+0000",
         "first_request_before": 810000, "first_request_after": 400000,
         "floor_reduction_tokens": 410000, "fingerprint_start": "fpB-companion-v2",
         "fingerprint_end": "fpC", "cohort_before": {"start": 3000, "end": 4000}},
    ]
    wf = met.build_waterfall(rows, "core", "companion")
    assert wf["separable"] is False, wf
    assert wf["total_delta"] is None and wf["total_delta_pct"] is None, wf
    assert "NOT SEPARABLE" in wf["interaction_note"], wf["interaction_note"]
    assert "fingerprint" in wf["interaction_note"], wf["interaction_note"]

    html = shield.render_waterfall(wf, "core", "companion")
    assert "NOT SEPARABLE" in html, html
    # No credit is split by a guess: no total figure renders at all.
    assert "600,000" not in html and "610,000" not in html


def test_waterfall_declares_interaction_not_separable_on_overlapping_windows():
    # Calibrated: companion's before-cohort window (2500-4000) starts before
    # core's after-cohort window (2000-3000) ends, so the same session could
    # be counted on both sides. If build_waterfall only checked the
    # fingerprint and ignored window overlap, this goes red.
    rows = [
        {"label": "core", "confidence": "VERIFIED", "timestamp": "2026-08-01T10:00:00+0000",
         "first_request_before": 1000000, "first_request_after": 800000,
         "floor_reduction_tokens": 200000, "fingerprint_start": "fpA",
         "fingerprint_end": "fpB", "cohort_after": {"start": 2000, "end": 3000}},
        {"label": "companion", "confidence": "VERIFIED", "timestamp": "2026-08-05T10:00:00+0000",
         "first_request_before": 810000, "first_request_after": 400000,
         "floor_reduction_tokens": 410000, "fingerprint_start": "fpB",
         "fingerprint_end": "fpC", "cohort_before": {"start": 2500, "end": 4000}},
    ]
    wf = met.build_waterfall(rows, "core", "companion")
    assert wf["separable"] is False, wf
    assert "NOT SEPARABLE" in wf["interaction_note"], wf["interaction_note"]
    assert "overlap" in wf["interaction_note"], wf["interaction_note"]


def test_waterfall_empty_ledger_is_no_data_not_zero():
    # Calibrated: an empty ledger must never render a total of 0 or a blank
    # section; it must say NO DATA. If build_waterfall silently defaulted
    # missing records to 0 instead of NO DATA, this goes red.
    wf = met.build_waterfall([], "core", "companion")
    assert wf["core"]["status"] == "NO DATA" and wf["companion"]["status"] == "NO DATA", wf
    assert wf["separable"] is False and wf["total_delta"] is None, wf
    html = shield.render_waterfall(wf, "core", "companion")
    assert "NO DATA" in html, html
    assert "core" in html and "companion" in html


def test_waterfall_confidence_labels_never_blend_on_one_line():
    # Calibrated: core is VERIFIED, companion never ran (NOT_PROVEN with a
    # thin-data reason), so the chain cannot be separable. Each step's own
    # confidence label must stand alone; a rendered line combining
    # "VERIFIED" and "NOT_PROVEN" would blend two different confidences into
    # one claim. If the renderer ever merged the two step lines into one
    # paragraph, this goes red.
    rows = [
        {"label": "core", "confidence": "VERIFIED", "timestamp": "2026-08-01T10:00:00+0000",
         "first_request_before": 1000000, "first_request_after": 800000,
         "floor_reduction_tokens": 200000, "fingerprint_start": "fpA",
         "fingerprint_end": "fpB", "cohort_after": {"start": 2000, "end": 3000}},
        {"label": "companion", "confidence": "NOT_PROVEN", "timestamp": "2026-08-05T10:00:00+0000",
         "reasons": ["only 1 sessions after the change, need 3"]},
    ]
    wf = met.build_waterfall(rows, "core", "companion")
    assert wf["core"]["status"] == "VERIFIED" and wf["companion"]["status"] == "NOT_PROVEN", wf
    assert wf["separable"] is False, wf

    html = shield.render_waterfall(wf, "core", "companion")
    for para in html.split("</p>"):
        assert not ("VERIFIED" in para and "NOT_PROVEN" in para), para


def test_top_strip_shows_confidence_labelled_cells_when_data_is_present():
    # Calibrated: with render_top_strip's call removed from render(), this
    # goes red (no "topstrip" marker, no per-cell confidence pills); restored
    # it is green. Every cell reuses a number render() already computed
    # elsewhere on the page: verified_by_label rows, the same companion
    # install check render_companions() runs, the ranked prescriptions list,
    # and the advisor's own top pick.
    with tempfile.TemporaryDirectory() as d:
        profile = met.load_profile(_write_json(d, "profile.json",
                                                    _synthetic_profile(switch_share=0.5)))
        strategies = adv.load_strategies()
        advise_result = adv.advise(profile, {}, strategies)
        assert advise_result["best"] is not None  # 0.5 switch share fires a HIGH card
        best_title = advise_result["best"]["title"]

        companions_data = cfg.load_companions(_write_json(d, "companions.json", {
            "companions": [{"name": "ponytail", "when": "test when",
                            "benefit": "smaller diffs", "drawback": "can under-build"}],
            "mentions": [],
        }))
        cache_root = os.path.join(d, "plugins", "cache")
        os.makedirs(os.path.join(cache_root, "claude-community", "ponytail"))

        with open(os.path.join(d, "savings.jsonl"), "w") as f:
            f.write(json.dumps({"label": "shrink-claude-md", "confidence": "VERIFIED",
                                "floor_reduction_tokens": 500,
                                "timestamp": "2026-08-12T10:00:00+0000"}) + "\n")
        experiment_rows = met.load_experiment_rows(os.path.join(d, "savings.jsonl"))
        verified = met.verified_by_label(experiment_rows)

        sm, sessions = _sm_and_sessions()
        html = shield.render(mt, sm, sessions, 30, "stamp", include_sessions=False,
                             verified=verified, profile=profile, advise_result=advise_result,
                             suppressed_n=0, companions_data=companions_data,
                             experiment_rows=experiment_rows, plugin_cache_root=cache_root)

    assert 'class="grid topstrip"' in html
    strip = html.split("<h2>At a glance</h2>")[1].split("<h2>Alerts</h2>")[0]
    assert "Verified improvement" in strip and "cpill ver" in strip and "+500" in strip
    assert "Current stack" in strip and "MEASURED" in strip and "1/1" in strip
    assert "Largest remaining problem" in strip
    assert ("Switching model mid-session" in strip
            or "The always-loaded startup floor" in strip), strip
    assert "Next best move" in strip and best_title in strip


def test_top_strip_renders_no_data_never_zero_on_an_empty_ledger():
    # Calibrated: swapping the "not verified" NO DATA branch in
    # render_top_strip for a literal "0" (as if summing an empty ledger)
    # makes this go red; restored to NO DATA text, green.
    sm = {"read_total": 0, "write_5m_total": 0, "write_1h_total": 0, "input_total": 0,
          "first_request_median": None, "first_request_share_median": None,
          "hit_ratio_median": None, "subagent_output_share": None, "output_total": 0}
    html = shield.render(mt, sm, [], 30, "stamp", include_sessions=False,
                         verified=None, profile=None, advise_result=None,
                         companions_data=None, experiment_rows=None)
    assert 'class="grid topstrip"' in html
    strip = html.split("<h2>At a glance</h2>")[1].split("<h2>Alerts</h2>")[0]
    # Verified improvement, current stack, and next best move all have no
    # source to read from; every one of them must say NO DATA, never 0.
    assert strip.count("NO DATA") >= 3, strip
    assert "None ranked" in strip
    assert '<div class="v">0</div>' not in strip


class _FakeExpMod:
    """Fixture double for experiment.py: a fixed "current" fingerprint and
    schema, so verified_by_label's historical check is deterministic here
    and never touches this machine's real ~/.claude files."""
    EXP_SCHEMA = 2

    def compute_fingerprint(self, treats=None):
        return "current-fp"


def test_verified_row_with_matching_fingerprint_renders_verified_not_historical():
    exp_mod = _FakeExpMod()
    rows = [{"label": "diet-claude-md", "confidence": "VERIFIED",
             "floor_reduction_tokens": 5000, "timestamp": "2026-08-01T10:00:00+0000",
             "fingerprint_end": "current-fp", "schema": 2, "treats": None}]
    verified = met.verified_by_label(rows, exp_mod)
    assert verified[0]["historical"] is False, verified
    assert verified[0]["historical_reason"] is None, verified

    big, under = shield.render_verified_hero(verified)
    assert "HISTORICAL" not in big, big
    assert "5.0K" in big, big

    strip = shield.render_top_strip(verified, None, "/nonexistent-cache-root", [], None)
    assert "HISTORICAL" not in strip, strip


def test_verified_row_with_differing_fingerprint_renders_historical_with_reason():
    # Calibrated: with the fingerprint comparison in _historical_check
    # short-circuited to always return (False, None) (drift ignored), this
    # goes red, since neither render carries HISTORICAL or a reason for a
    # record whose fingerprint plainly does not match "current-fp"; restored,
    # green.
    exp_mod = _FakeExpMod()
    rows = [{"label": "diet-claude-md", "confidence": "VERIFIED",
             "floor_reduction_tokens": 5000, "timestamp": "2026-08-01T10:00:00+0000",
             "fingerprint_end": "stale-fp-from-last-week", "schema": 2, "treats": None}]
    verified = met.verified_by_label(rows, exp_mod)
    assert verified[0]["historical"] is True, verified
    assert verified[0]["historical_reason"], verified
    assert "moved" in verified[0]["historical_reason"], verified

    big, under = shield.render_verified_hero(verified)
    assert "HISTORICAL" in big, big
    assert "moved" in under, under
    assert "5.0K" in under, under  # the figure stays visible, never hidden

    strip = shield.render_top_strip(verified, None, "/nonexistent-cache-root", [], None)
    assert "HISTORICAL" in strip, strip
    assert "moved" in strip, strip


def test_verified_row_with_no_fingerprint_stays_verified_never_false_historical():
    # Absence of evidence of drift is not evidence of drift: a record with
    # no fingerprint_end at all (a legacy record, or a fixture that predates
    # the guard) must never be guessed into HISTORICAL.
    exp_mod = _FakeExpMod()
    rows = [{"label": "legacy-label", "confidence": "VERIFIED",
             "floor_reduction_tokens": 3000, "timestamp": "2026-08-01T10:00:00+0000"}]
    verified = met.verified_by_label(rows, exp_mod)
    assert verified[0]["historical"] is False, verified
    assert verified[0]["historical_reason"] is None, verified

    big, _ = shield.render_verified_hero(verified)
    assert "HISTORICAL" not in big, big

    # Same guarantee with exp_mod entirely absent (the default), the shape
    # every existing caller in this file already uses.
    verified_no_mod = met.verified_by_label(rows)
    assert verified_no_mod[0]["historical"] is False, verified_no_mod


# --- dashboard legibility: colour, contrast, labels, repetition -------------
# Every check below is about the page a non-technical reader actually sees.
# The first two are accessibility conformance (WCAG 2.2 SC 1.4.1 Use of Color
# and SC 1.4.3 Contrast Minimum), which is why they assert on the stylesheet
# and not only on the markup.

def _plain(html_fragment):
    """Tag-stripped text, to prove a state is distinguishable by WORDS alone,
    with every colour and class thrown away."""
    return re.sub(r"<[^>]+>", "", html_fragment)


def _contrast(hex_a, hex_b):
    """WCAG 2.x relative-luminance contrast ratio between two #rrggbb colours."""
    def lum(h):
        h = h.lstrip("#")
        out = []
        for i in (0, 2, 4):
            c = int(h[i:i + 2], 16) / 255
            out.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
        return 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2]
    la, lb = lum(hex_a), lum(hex_b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _full_page(verified=None, experiment_rows=None):
    profile = _synthetic_profile(switch_share=0.5, floor_share=0.36)
    advise_result = adv.advise(profile, {}, adv.load_strategies())
    sm, sessions = _sm_and_sessions()
    return shield.render(mt, sm, sessions, 30, "stamp", include_sessions=False,
                         verified=verified, profile=profile,
                         advise_result=advise_result,
                         companions_data={"companions": [], "mentions": []},
                         experiment_rows=experiment_rows or [])


def test_hero_regression_never_renders_in_the_success_colour():
    # WCAG 2.2 SC 1.4.1 (Use of Color, Level A). The renderer emitted "big g",
    # "big w" and "big muted", but the only .big rule hardcoded
    # color:var(--good), so a regression, a HISTORICAL caveat and NONE YET all
    # printed in success green. Colour must separate the states, and because
    # colour may not be the ONLY separator, the words must separate them too.
    win_big, win_under = shield.render_verified_hero(
        [{"label": "diet", "floor_reduction": 4200, "historical": False}])
    loss_big, loss_under = shield.render_verified_hero(
        [{"label": "diet", "floor_reduction": -4200, "historical": False}])

    assert 'class="big g"' in win_big, win_big
    assert 'class="big w"' in loss_big, loss_big

    base = re.search(r"\.hero \.big\{([^}]*)\}", shield.CSS)
    assert base and "--good" not in base.group(1), base and base.group(1)
    for cls, token in (("g", "--good"), ("w", "--warn"), ("muted", "--muted")):
        rule = re.search(r"\.hero \.big\.%s\{([^}]*)\}" % cls, shield.CSS)
        assert rule is not None, cls
        assert token in rule.group(1), (cls, rule.group(1))

    # Text alone, no stylesheet at all, must still tell a loss from a win.
    assert "REGRESSION" in _plain(loss_big), loss_big
    assert "REGRESSION" not in _plain(win_big), win_big
    assert "regression" in loss_under.lower(), loss_under
    assert "4.2K" in _plain(loss_big), loss_big  # the figure is never clipped

    # NO DATA is a word, never a number that reads like a saving.
    empty_big, _ = shield.render_verified_hero([])
    assert 'class="big muted"' in empty_big, empty_big
    assert "NONE YET" in _plain(empty_big), empty_big


def test_light_theme_confidence_colours_meet_wcag_aa_contrast():
    # WCAG 2.2 SC 1.4.3 (Contrast Minimum, Level AA): 4.5:1 for normal text.
    # The confidence pills are 9px, far under the 18pt large-text exception,
    # so 4.5:1 is the threshold that applies. Dark mode already passed; both
    # light blocks (the media query and the explicit toggle) are checked so
    # they can never drift apart.
    light = re.search(r':root\[data-theme="light"\]\{([^}]*)\}', shield.CSS)
    media = re.search(r"@media \(prefers-color-scheme: light\)\{\s*:root\{([^}]*)\}",
                      shield.CSS)
    assert light and media
    for block in (light.group(1), media.group(1)):
        tok = dict(re.findall(r"--([a-z0-9]+):(#[0-9a-f]{6})", block))
        for name in ("good", "warn"):
            for bg in ("bg", "panel", "panel2"):
                ratio = _contrast(tok[name], tok[bg])
                assert ratio >= 4.5, (name, bg, tok[name], round(ratio, 2))


def test_observed_pattern_numbers_carry_their_confidence_label():
    # The page's stated invariant is that a number never travels without its
    # label. These three headline figures printed bare.
    html = shield.render_observed_pattern(_synthetic_profile())
    assert html.count('class="cpill"') == 3, html
    assert html.count("MEASURED") == 3, html

    # An absent leaf says NO DATA, never MEASURED over a blank.
    blank = shield.render_observed_pattern({"usage": {}, "behavior": {}})
    assert "MEASURED" not in blank, blank
    assert blank.count("NO DATA") >= 3, blank


def test_label_key_precedes_the_first_pill_and_every_label_has_an_instance():
    html = _full_page()
    legend_at = html.index("What the labels mean")
    first_pill_at = html.index('class="cpill')
    assert legend_at < first_pill_at, (legend_at, first_pill_at)

    # NATIVE was defined in the key and attached to no number on the page. A
    # key entry with no instance teaches a category that does not exist.
    usd = re.search(r'<p class="usdline">(.*?)</p>', html, re.S)
    assert usd is not None
    assert "NATIVE" in usd.group(1), usd.group(1)


def test_each_recommendation_is_shown_once_not_three_times():
    profile = _synthetic_profile(switch_share=0.5, floor_share=0.36)
    result = adv.advise(profile, {}, adv.load_strategies())
    assert result["best"] is not None
    assert len(result["queue"]) >= 2, result["queue"]

    queue_html = shield.render_recommendation_queue(result, 0)
    assert result["best"]["title"] not in queue_html, queue_html
    assert "--decide" not in queue_html, queue_html
    assert result["queue"][1]["title"] in queue_html, queue_html

    # The chips keep their one home, on the Next best move card.
    assert "--decide" in shield.render_next_best_move(result)
    assert _full_page().count("Did it") == 1


def test_queue_emptied_by_the_hero_card_never_claims_a_healthy_profile():
    # Filtering the best card out of the queue must not make a queue of one
    # read as "healthy": that would be a degradation printed as good news.
    strategies = [_mini_strategy("cache.a", "cache", "usage.m1", ">=", 1, "HIGH")]
    result = adv.advise({"usage": {"m1": _leaf(5)}}, {}, strategies)
    assert len(result["queue"]) == 1
    html = shield.render_recommendation_queue(result, 0)
    assert 'class="pain-item"' not in html, html
    assert "healthy" not in html, html
    assert "card above" in html, html

    # A genuinely empty advisor queue still says healthy.
    healthy = adv.advise({"usage": {"m1": _leaf(0)}}, {}, strategies)
    assert healthy["do_nothing"] is True
    assert "healthy" in shield.render_recommendation_queue(healthy, 0)


def test_base_input_units_is_defined_before_it_is_first_used():
    html = _full_page()
    assert "One base-input unit is" in html, "no definition of the invented unit"
    assert html.index("One base-input unit is") < html.index("base-input units"), html


# command_center_state(): the four-state model, docs/plan/2026-08-15-STATE-MODEL.md.
# Every fixture below hands the function the shape its three primitives
# (list_open_experiments, advise, verified_by_label) actually return, never
# the real machine's files, per the memo's "existing primitives only" rule.

def test_state_proving_beats_opportunity():
    open_experiments = [{"label": "diet-claude-md", "started": "2026-08-01T10:00:00",
                          "window_days": 7}]
    advise_result = {"do_nothing": False,
                     "best": {"id": "cache.a", "title": "t", "why_selected": "cache hit is low"},
                     "insufficient": []}
    state, reason = met.command_center_state(open_experiments, advise_result, [], 3)
    assert state == "PROVING", (state, reason)
    assert "diet-claude-md" in reason, reason


def test_state_healthy_when_do_nothing():
    advise_result = {"do_nothing": True, "insufficient": [],
                     "message": "Nothing crossed a trigger threshold, so this profile "
                                "looks healthy right now."}
    state, reason = met.command_center_state([], advise_result, [], 3)
    assert state == "HEALTHY", (state, reason)
    assert "healthy" in reason.lower(), reason


def test_state_unreadable_baseline_still_proving():
    open_experiments = [{"_unreadable": "/some/path.json"}]
    advise_result = {"do_nothing": True, "insufficient": []}
    state, reason = met.command_center_state(open_experiments, advise_result, [], 3)
    assert state == "PROVING", (state, reason)
    assert "/some/path.json" in reason, reason


def test_state_all_triggers_insufficient_is_no_data():
    advise_result = {"do_nothing": True, "insufficient": ["cache.a", "startup.b", "context.c"]}
    state, reason = met.command_center_state([], advise_result, [], 3)
    assert state == "NO DATA", (state, reason)
    assert state != "HEALTHY"


def test_state_historical_verified_does_not_beat_healthy():
    verified = [{"label": "diet-claude-md", "floor_reduction": 5000,
                "historical": True, "historical_reason": "config fingerprint moved"}]
    advise_result = {"do_nothing": True, "insufficient": [],
                     "message": "Nothing crossed a trigger threshold, so this profile "
                                "looks healthy right now."}
    state, reason = met.command_center_state([], advise_result, verified, 3)
    assert state == "HEALTHY", (state, reason)


def _opportunity_beats_verified_fixture():
    advise_result = {"do_nothing": False,
                     "best": {"id": "cache.a", "title": "t", "why_selected": "cache hit is low"},
                     "insufficient": []}
    verified = [{"label": "diet-claude-md", "floor_reduction": 5000, "historical": False}]
    return advise_result, verified


def test_state_opportunity_beats_verified():
    advise_result, verified = _opportunity_beats_verified_fixture()
    state, reason = met.command_center_state([], advise_result, verified, 3)
    assert state == "OPPORTUNITY", (state, reason)


def _unrecognised_format_fixture():
    open_experiments = [{"label": "diet-claude-md", "started": "2026-08-01T10:00:00",
                          "window_days": 7}]
    advise_result = {"do_nothing": True, "insufficient": []}
    verified = [{"label": "diet-claude-md", "floor_reduction": 5000, "historical": False}]
    return open_experiments, advise_result, verified


def test_state_unrecognised_format_beats_proving():
    open_experiments, advise_result, verified = _unrecognised_format_fixture()
    state, reason = met.command_center_state(open_experiments, advise_result, verified, 3,
                                              parse_health="UNRECOGNISED")
    assert state == "NO DATA", (state, reason)


def test_state_parse_health_none_is_unchanged():
    # Same fixture as test_state_opportunity_beats_verified: None must render
    # OPPORTUNITY exactly as omitting the argument does.
    advise_result, verified = _opportunity_beats_verified_fixture()
    state, reason = met.command_center_state([], advise_result, verified, 3, parse_health=None)
    assert state == "OPPORTUNITY", (state, reason)

    # Same fixture as test_state_unrecognised_format_beats_proving, minus the
    # UNRECOGNISED string: None must render PROVING, today's behaviour,
    # unchanged by the new argument's mere presence.
    open_experiments, advise_result2, verified2 = _unrecognised_format_fixture()
    state2, reason2 = met.command_center_state(open_experiments, advise_result2, verified2, 3,
                                                parse_health=None)
    assert state2 == "PROVING", (state2, reason2)


# Verification-review defects (independent review of an unmerged change),
# fixed together: a suppressed strategy hitting `continue` before advisor.py's
# insufficient check let len(insufficient) == strategy_count become
# unreachable after a single suppression, so a completely unmeasured, fully
# suppressed profile rendered HEALTHY instead of NO DATA.

def test_state_suppressed_strategy_still_no_data():
    # The reproduction from the review report, run against the real strategy
    # registry: suppress the first strategy, leave the profile empty (every
    # other strategy's trigger is insufficient). Before the fix this rendered
    # HEALTHY with a reason line naming "NO DATA" twice; it must render the
    # NO DATA state instead.
    strategies = adv.load_strategies()
    treatments = {strategies[0]["id"]: {"decision": "suppressed", "until": "2099-01-01T00:00:00"}}
    res = adv.advise({}, treatments=treatments)
    state, reason = met.command_center_state([], res, [], len(strategies))
    assert state == "NO DATA", (state, reason)


def test_state_every_strategy_suppressed_is_no_data():
    # Denominator 0: advise_result["evaluated"] is 0 because every strategy
    # was suppressed and none reached trigger evaluation at all. This must
    # render NO DATA and say so honestly (suppressed, not insufficient).
    advise_result = {"do_nothing": True, "insufficient": [], "evaluated": 0}
    state, reason = met.command_center_state([], advise_result, [], 5)
    assert state == "NO DATA", (state, reason)
    assert "suppress" in reason.lower(), reason


def test_state_all_suppressed_does_not_hide_a_running_experiment():
    # Same denominator 0 as the test above, but with an open experiment on
    # disk. PROVING must win. Suppressing every strategy is a CONFIGURATION
    # choice and says nothing about whether the meter works, while the open
    # experiment is read from a file rather than computed from the profile, so
    # it is still a fact. Burying a running trial under NO DATA would lose real
    # information and cost the user the stability warning PROVING exists to
    # give. The two MEASUREMENT failures above (unrecognised format, unreadable
    # advisor) do still outrank PROVING, and that asymmetry is the point.
    advise_result = {"do_nothing": True, "insufficient": [], "evaluated": 0}
    open_experiments = [{"label": "diet-claude-md", "window_days": 30}]
    state, reason = met.command_center_state(open_experiments, advise_result, [], 5)
    assert state == "PROVING", (state, reason)
    assert "diet-claude-md" in reason, reason


def test_state_none_advise_result_is_no_data():
    # token_shield.py sets advise_result to None when the advisor fails to
    # load (scripts/token_shield.py:910). The first surface that wires this
    # function up must degrade to NO DATA, not crash with AttributeError.
    state, reason = met.command_center_state([], None, [], 3)
    assert state == "NO DATA", (state, reason)
    assert "advisor" in reason.lower(), reason


def test_state_unreadable_baseline_keeps_the_other_count():
    # _proving_reason returned early on the _unreadable marker before adding
    # "(and N more open)", so a user with one unreadable baseline and other
    # genuinely open experiments was told only about the unreadable one.
    open_experiments = [{"_unreadable": "/some/path.json"},
                         {"label": "a", "started": "2026-08-01T10:00:00", "window_days": 7},
                         {"label": "b", "started": "2026-08-02T10:00:00", "window_days": 7}]
    advise_result = {"do_nothing": True, "insufficient": []}
    state, reason = met.command_center_state(open_experiments, advise_result, [], 3)
    assert state == "PROVING", (state, reason)
    assert "/some/path.json" in reason, reason
    assert "2 more open" in reason, reason


def test_state_healthy_reason_names_the_advisor_message():
    # Mutant that survived: HEALTHY's reason line content was never checked,
    # only that the word "healthy" appears somewhere. Pin the reason to
    # advise_result's own message field verbatim.
    advise_result = {"do_nothing": True, "insufficient": [],
                     "message": "Nothing crossed a trigger threshold, so this profile "
                                "looks healthy right now. Your two strongest metrics: "
                                "cache hit ratio 0.87, startup floor share 0.42."}
    state, reason = met.command_center_state([], advise_result, [], 3)
    assert state == "HEALTHY", (state, reason)
    assert reason == advise_result["message"], reason


def test_state_unrecognised_is_the_only_reason_for_no_data():
    # Mutant that survived: nothing proved parse_health="UNRECOGNISED" is
    # actually load-bearing rather than redundant with an already-firing
    # precondition. Use a fixture that would render a real state (HEALTHY)
    # without it, then show UNRECOGNISED alone forces NO DATA.
    advise_result = {"do_nothing": True, "insufficient": []}
    without_flag_state, _ = met.command_center_state([], advise_result, [], 3)
    assert without_flag_state == "HEALTHY", without_flag_state

    state, reason = met.command_center_state([], advise_result, [], 3, parse_health="UNRECOGNISED")
    assert state == "NO DATA", (state, reason)


# T2.2: the four-state header and the PROVING panel on the dashboard itself
# (docs/plan/2026-08-15-STATE-MODEL.md). command_center_state() is called
# exactly once, inside render(); these tests hand render() the same fixture
# shapes the primitives return and check the rendered HTML, never the state
# priority logic again (that is T2.1's, already covered above).

def test_dashboard_renders_proving_panel():
    exp_mod = met.load_experiment()
    open_experiments = [{
        "label": "diet-claude-md", "started": "2026-08-01T00:00:00+0000",
        "window_days": 7, "treats": exp_mod.CLAUDE_MD_PATH,
        "fingerprint_excluded": [exp_mod.CLAUDE_MD_PATH],
    }]
    profile = _synthetic_profile(switch_share=0.5, floor_share=0.36)
    advise_result = adv.advise(profile, {}, adv.load_strategies())
    sm, sessions = _sm_and_sessions()
    html = shield.render(mt, sm, sessions, 30, "stamp", include_sessions=False,
                         verified=[], profile=profile, advise_result=advise_result,
                         companions_data={"companions": [], "mentions": []},
                         experiment_rows=[], open_experiments=open_experiments,
                         strategy_count=len(adv.load_strategies()), exp_mod=exp_mod,
                         today="2026-08-08")

    # The four-state header, state and reason verbatim from command_center_state.
    band = re.search(r'<div class="cc-band cc-proving">(.*?)</div>', html, re.S)
    assert band, html
    assert "PROVING" in band.group(1), band.group(1)
    assert "diet-claude-md" in band.group(1), band.group(1)

    # The PROVING panel: label, day n of m (2026-08-01 to 2026-08-08 inclusive
    # is day 8 of a 7 day window), and a keep-stable list built from the
    # record's own fingerprint fields. CLAUDE.md is this experiment's own
    # treats/fingerprint_excluded file, so it must be named as the exception,
    # never listed among what must hold still.
    panel = re.search(r'<div class="proving-panel">(.*?)</div>', html, re.S)
    assert panel, html
    body = panel.group(1)
    assert "diet-claude-md" in body, body
    assert "day 8 of 7" not in body, body
    assert "closed" in body.lower(), body
    assert "1 day ago" in body, body
    assert "experiment end" in body, body
    assert "scripts/cli.py" in body, body
    assert "settings.json" in body, body
    assert ".claude.json" in body, body
    assert "installed skills" in body.lower(), body
    keep_section = body.split("Keep this stable")[1]
    assert "CLAUDE.md" not in keep_section, keep_section


def test_proving_panel_last_day_of_window_still_reads_as_in_window():
    # Boundary: 2026-08-01 to 2026-08-07 inclusive is day 7 of a 7 day
    # window, the LAST day still inside it. The panel must still render
    # "day 7 of 7", never the closed-window message: closing happens the
    # day AFTER the window ends, not on its last day.
    exp_mod = met.load_experiment()
    open_experiments = [{
        "label": "diet-claude-md", "started": "2026-08-01T00:00:00+0000",
        "window_days": 7, "treats": exp_mod.CLAUDE_MD_PATH,
        "fingerprint_excluded": [exp_mod.CLAUDE_MD_PATH],
    }]
    profile = _synthetic_profile(switch_share=0.5, floor_share=0.36)
    advise_result = adv.advise(profile, {}, adv.load_strategies())
    sm, sessions = _sm_and_sessions()
    html = shield.render(mt, sm, sessions, 30, "stamp", include_sessions=False,
                         verified=[], profile=profile, advise_result=advise_result,
                         companions_data={"companions": [], "mentions": []},
                         experiment_rows=[], open_experiments=open_experiments,
                         strategy_count=len(adv.load_strategies()), exp_mod=exp_mod,
                         today="2026-08-07")
    panel = re.search(r'<div class="proving-panel">(.*?)</div>', html, re.S)
    assert panel, html
    body = panel.group(1)
    assert "day 7 of 7" in body, body
    assert "closed" not in body.lower(), body


def test_proving_panel_refuses_a_day_count_for_a_future_start_date():
    # A start date AHEAD of today is reachable through clock skew, a restored
    # backup, a hand edited baseline, or a timezone boundary. Without a guard
    # the panel renders "day -28 of 7", which is the same class of impossible
    # looking fraction as "day 8 of 7", just off the other end of the range.
    # The honest answer is NO DATA naming the reason, not the arithmetic.
    exp_mod = met.load_experiment()
    open_experiments = [{
        "label": "diet-claude-md", "started": "2026-09-01T00:00:00+0000",
        "window_days": 7, "treats": exp_mod.CLAUDE_MD_PATH,
        "fingerprint_excluded": [exp_mod.CLAUDE_MD_PATH],
    }]
    profile = _synthetic_profile(switch_share=0.5, floor_share=0.36)
    advise_result = adv.advise(profile, {}, adv.load_strategies())
    sm, sessions = _sm_and_sessions()
    html = shield.render(mt, sm, sessions, 30, "stamp", include_sessions=False,
                         verified=[], profile=profile, advise_result=advise_result,
                         companions_data={"companions": [], "mentions": []},
                         experiment_rows=[], open_experiments=open_experiments,
                         strategy_count=len(adv.load_strategies()), exp_mod=exp_mod,
                         today="2026-08-03")
    panel = re.search(r'<div class="proving-panel">(.*?)</div>', html, re.S)
    assert panel, html
    body = panel.group(1)
    assert "day -" not in body, body
    assert "NO DATA" in body, body
    assert "future" in body.lower(), body


def test_summary_first_line_is_state():
    # The terminal's first line must be the state, read through
    # metrics.command_center_state rather than recomputed in cli.py. A second
    # copy of the priority order in the CLI is exactly the drift the state
    # model exists to prevent, so this pins the WIRING, not the wording.
    import io
    import contextlib
    import cli
    d = tempfile.mkdtemp()
    proj = os.path.join(d, "proj")
    os.makedirs(proj)
    rec = {"type": "assistant", "message": {"usage": {
        "input_tokens": 100, "output_tokens": 50,
        "cache_read_input_tokens": 10, "cache_creation_input_tokens": 5}}}
    with open(os.path.join(proj, "s.jsonl"), "w") as f:
        for _ in range(20):
            f.write(json.dumps(rec) + "\n")
    old_root = cli.ROOT
    cli.ROOT = d
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cli.summary()
    finally:
        cli.ROOT = old_root
    lines = [l for l in buf.getvalue().splitlines() if l.strip()]
    assert lines, "cli.summary() printed nothing to stdout"
    assert lines[0].startswith("STATE: "), lines[0]
    # The state must be one the state function can actually return, never a
    # word invented in the CLI.
    assert any(lines[0].startswith("STATE: " + s)
               for s in ("PROVING", "OPPORTUNITY", "VERIFIED", "HEALTHY", "NO DATA")), lines[0]
    assert "(" in lines[0] and lines[0].rstrip().endswith(")"), lines[0]


def test_proving_panel_handles_unreadable_baseline_without_raising():
    # list_open_experiments fails CLOSED: a corrupt or unreadable baseline
    # file comes back as a marker carrying "_unreadable" and no "label". The
    # panel must name the path, not invent a label, and never raise.
    open_experiments = [{"_unreadable": "/tmp/some-baseline.json"}]
    profile = _synthetic_profile(switch_share=0.5, floor_share=0.36)
    advise_result = adv.advise(profile, {}, adv.load_strategies())
    sm, sessions = _sm_and_sessions()
    html = shield.render(mt, sm, sessions, 30, "stamp", include_sessions=False,
                         verified=[], profile=profile, advise_result=advise_result,
                         companions_data={"companions": [], "mentions": []},
                         experiment_rows=[], open_experiments=open_experiments,
                         strategy_count=len(adv.load_strategies()),
                         exp_mod=met.load_experiment(), today="2026-08-08")
    assert "PROVING" in html, html

    # Isolated to the panel's own fragment: the header's reason line already
    # names the path too (metrics._proving_reason), so checking the whole
    # page would pass even if the panel itself fell back to a guessed label.
    panel = re.search(r'<div class="proving-panel">(.*?)</div>', html, re.S)
    assert panel, html
    body = panel.group(1)
    assert "/tmp/some-baseline.json" in body, body
    assert "(unlabeled)" not in body, body


def test_dashboard_header_renders_every_state():
    # Every surface renders whatever command_center_state returns, including
    # HEALTHY and NO DATA: the header is not conditional on PROVING.
    profile = _synthetic_profile(switch_share=0.1, floor_share=0.05, hit_ratio=0.95)
    advise_result = adv.advise(profile, {}, adv.load_strategies())
    sm, sessions = _sm_and_sessions()
    html = shield.render(mt, sm, sessions, 30, "stamp", include_sessions=False,
                         verified=[], profile=profile, advise_result=advise_result,
                         companions_data={"companions": [], "mentions": []},
                         experiment_rows=[], open_experiments=[],
                         strategy_count=len(adv.load_strategies()), today="2026-08-08")
    assert 'class="cc-band cc-healthy"' in html, html
    assert '<div class="proving-panel">' not in html, html

    no_data_html = shield.render(mt, sm, sessions, 30, "stamp", include_sessions=False,
                                 verified=[], profile=None, advise_result=None,
                                 companions_data={"companions": [], "mentions": []},
                                 experiment_rows=[], open_experiments=[],
                                 strategy_count=0, today="2026-08-08")
    assert 'class="cc-band cc-nodata"' in no_data_html, no_data_html


def test_verified_state_is_visually_and_textually_distinct_from_verified_label():
    # docs/plan/2026-08-15-STATE-MODEL.md's VERIFIED state (a steady state:
    # healthy AND proven) is a different axis from the VERIFIED confidence
    # label (a closed experiment's own evidence). They must never share a
    # colour, and the state word must never appear bare, without a clarifier
    # that names it a state rather than a fresh proof.
    band = shield.render_command_center("VERIFIED", "diet-claude-md: floor reduction +4,200 tokens")
    assert "steady state" in band.lower(), band

    state_color = re.search(r'\.cc-band\.cc-verified \.cc-state\{color:([^;}]+)', shield.CSS)
    ver_pill_color = re.search(r'\.cpill\.ver\{color:([^;]+);', shield.CSS)
    assert state_color and ver_pill_color, shield.CSS
    assert state_color.group(1) != ver_pill_color.group(1), (state_color.group(1),
                                                              ver_pill_color.group(1))


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
