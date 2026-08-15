#!/usr/bin/env python3
"""Self-check for profile.py. No framework, no fixtures.

    python3 scripts/test_profile.py
"""

import json
import os
import statistics
import sys
import tempfile

import profile as pf
import measure_tokens as mt

METRIC_GROUPS = ("usage", "behavior", "instruction", "environment", "pressure", "skipped")

SECRET = "SECRET_CONVERSATION_MARKER_do_not_leak"


def _rec(ts, model="claude-x", effort=None, inp=1, w5=0, w1=0, read=0, out=1,
         sidechain=False, text=None):
    msg = {
        "model": model,
        "usage": {
            "input_tokens": inp,
            "cache_creation": {"ephemeral_5m_input_tokens": w5,
                               "ephemeral_1h_input_tokens": w1},
            "cache_creation_input_tokens": w5 + w1,
            "cache_read_input_tokens": read,
            "output_tokens": out,
        },
    }
    if text is not None:
        msg["content"] = [{"type": "text", "text": text}]
    rec = {"isSidechain": sidechain, "message": msg, "timestamp": ts}
    if effort is not None:
        rec["effort"] = effort
    return json.dumps(rec)


def _write(path, records):
    with open(path, "w") as f:
        f.write("\n".join(records) + "\n")


def _raw_line_bytes(path):
    """Independent recomputation of "total transcript bytes", read straight
    off disk the same way _pressure_scan does (open, iterate lines, skip
    blanks, encode utf-8), without calling any profile.py function. Used so
    the byte-share tests are not just checking a function against itself."""
    total = 0
    with open(path, "r", errors="ignore") as f:
        for line in f:
            if line.strip():
                total += len(line.encode("utf-8", "ignore"))
    return total


def _assistant_line(ts, output_tokens=1, tool_uses=None):
    """One assistant transcript line. tool_uses is a list of
    (tool_id, name, input_dict) tuples, matching the real tool_use block
    shape: {"type": "tool_use", "id", "name", "input", "caller"}."""
    content = [
        {"type": "tool_use", "id": tid, "name": name, "input": inp,
         "caller": {"type": "direct"}}
        for tid, name, inp in (tool_uses or [])
    ]
    msg = {
        "model": "claude-x",
        "content": content,
        "usage": {
            "input_tokens": 1,
            "output_tokens": output_tokens,
            "cache_read_input_tokens": 0,
            "cache_creation": {"ephemeral_5m_input_tokens": 0,
                               "ephemeral_1h_input_tokens": 0},
        },
    }
    return json.dumps({"type": "assistant", "message": msg, "timestamp": ts})


def _user_line(ts, tool_results=None, text=None):
    """One user transcript line. tool_results is a list of
    (tool_use_id, content) pairs, matching {"type": "tool_result",
    "tool_use_id", "content"}. text, if given, becomes a human-typed
    {"type": "text"} block alongside any tool_result blocks."""
    content = [
        {"type": "tool_result", "tool_use_id": tid, "content": c}
        for tid, c in (tool_results or [])
    ]
    if text is not None:
        content.append({"type": "text", "text": text})
    msg = {"role": "user", "content": content}
    return json.dumps({"type": "user", "message": msg, "timestamp": ts})


def test_labels_present_on_every_leaf():
    with tempfile.TemporaryDirectory() as d:
        _write(os.path.join(d, "s.jsonl"), [
            _rec("2026-08-12T10:00:00Z", effort="high", text=SECRET),
            _rec("2026-08-12T10:01:00Z", model="claude-y"),
        ])
        prof = pf.build_profile(root=d, days=30)

    for group in METRIC_GROUPS:
        section = prof[group]
        assert section, f"{group} section is empty"
        for key, leaf in section.items():
            assert set(leaf.keys()) == {"value", "label", "basis"}, (group, key, leaf)
            assert leaf["label"] in ("MEASURED", "SIGNAL", "INFERRED", "NO DATA"), (group, key, leaf)
            if leaf["label"] == "NO DATA":
                assert leaf["value"] is None, (group, key, leaf)
            assert leaf["basis"], (group, key, "basis must not be empty")


def test_no_data_when_source_file_absent():
    with tempfile.TemporaryDirectory() as d:
        m = pf._file_metric(os.path.join(d, "does-not-exist.md"), "test file")
    assert m["label"] == "NO DATA"
    assert m["value"] is None
    assert "does-not-exist.md" in m["basis"]


def test_idle_gap_bucketing_math():
    # Two gaps under 5 minutes, one in 5-15, one in 15-60, one over 60: five
    # gaps, so each bucket's share is its count divided by 5.
    gaps = [60, 200, 600, 1800, 7200]
    shares = pf._idle_gap_shares(gaps)
    assert shares["under_5m"] == 2 / 5, shares
    assert shares["5m_to_15m"] == 1 / 5, shares
    assert shares["15m_to_60m"] == 1 / 5, shares
    assert shares["over_60m"] == 1 / 5, shares
    assert abs(sum(shares.values()) - 1.0) < 1e-9

    # No gaps at all (e.g. every session had a single timestamped record) is
    # NO DATA, not a fabricated zero.
    assert pf._idle_gap_shares([]) is None


def test_model_switch_detection():
    sessions = [
        {"first_request": 100, "models": 2},  # parent, switched
        {"first_request": 50, "models": 1},   # parent, did not switch
        {"first_request": 0, "models": 5},    # subagent transcript, excluded
    ]
    assert pf._model_switch_share(sessions) == 0.5

    # No parent sessions at all: NO DATA rather than a division by zero or a
    # fabricated 0.0.
    assert pf._model_switch_share([{"first_request": 0, "models": 1}]) is None


def test_profile_json_written_and_valid_and_no_leak():
    with tempfile.TemporaryDirectory() as d:
        root = os.path.join(d, "projects")
        os.makedirs(root)
        _write(os.path.join(root, "s.jsonl"), [
            _rec("2026-08-12T10:00:00Z", effort="max", text=SECRET),
            _rec("2026-08-12T10:20:00Z", model="claude-y", text=SECRET),
        ])
        out = os.path.join(d, "out", "profile.json")

        argv = sys.argv
        sys.argv = ["profile.py", "--root", root, "--days", "30", "--out", out]
        try:
            rc = pf.main()
        finally:
            sys.argv = argv
        assert rc == 0, rc

        assert os.path.isfile(out)
        raw = open(out).read()
        assert SECRET not in raw, "conversation text leaked into profile.json"
        prof = json.loads(raw)
        assert prof["schema"] == 1
        assert prof["window_days"] == 30.0


def test_arbitrary_effort_string_never_reaches_profile_json():
    # Calibrated: reverting _raw_scan to `effort_values.add(eff)` (no
    # effort_bucket call) puts MYSECRETEFFORTSTRING straight into
    # profile.json and this test goes red; with the whitelist, green.
    #
    # The effort field is arbitrary text from outside this tool, so a
    # transcript can carry anything there. profile.json promises counters and
    # byte sizes only, which means an unrecognized value is counted, never
    # copied.
    bogus = "MYSECRETEFFORTSTRING"
    with tempfile.TemporaryDirectory() as d:
        root = os.path.join(d, "projects")
        os.makedirs(root)
        _write(os.path.join(root, "s.jsonl"), [
            _rec("2026-08-12T10:00:00Z", effort=bogus),
            _rec("2026-08-12T10:05:00Z", effort="high"),
            _rec("2026-08-12T10:10:00Z", effort={"nested": bogus}),
        ])
        out = os.path.join(d, "out", "profile.json")

        argv = sys.argv
        sys.argv = ["profile.py", "--root", root, "--days", "30", "--out", out]
        try:
            rc = pf.main()
        finally:
            sys.argv = argv
        assert rc == 0, rc
        raw = open(out).read()

    assert raw.count(bogus) == 0, "raw effort string leaked into profile.json"
    prof = json.loads(raw)
    seen = prof["behavior"]["effort_values_seen"]["value"]
    assert sorted(seen) == ["high", "other"], seen


def test_effort_bucket_whitelist():
    for good in pf.EFFORT_VALUES:
        assert pf.effort_bucket(good) == good
    for bad in ("HIGH", "medium ", "", "sk-secret", 7, None, {"a": 1}, ["low"]):
        assert pf.effort_bucket(bad) == pf.EFFORT_OTHER, bad


def test_tool_result_bytes_helper():
    assert pf._tool_result_bytes("hello") == len("hello".encode("utf-8"))
    assert pf._tool_result_bytes([{"type": "text", "text": "ab"},
                                   {"type": "text", "text": "cd"}]) == 4
    # A block with no usable text contributes 0 rather than raising.
    assert pf._tool_result_bytes([{"type": "image"}]) == 0
    assert pf._tool_result_bytes(None) == 0
    assert pf._tool_result_bytes(7) == 0


def test_pressure_tool_output_share_by_tool():
    # Calibrated: swapping the /pa["total_bytes"] divisor for a fixed
    # constant, or having _tool_result_bytes always return 0, makes the
    # asserted share numbers go red; restoring the real division and byte
    # count makes them green again.
    read_content = "A" * 100
    bash_content = "B" * 50
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "s.jsonl")
        _write(path, [
            _assistant_line("2026-08-12T10:00:00Z", tool_uses=[
                ("t1", "Read", {"file_path": "/a"}),
                ("t2", "Bash", {"command": "ls"}),
            ]),
            _user_line("2026-08-12T10:00:01Z", tool_results=[
                ("t1", read_content), ("t2", bash_content),
            ]),
        ])
        expected_total = _raw_line_bytes(path)
        prof = pf.build_profile(root=d, days=30)

    share = prof["pressure"]["tool_output_share_by_tool"]
    assert share["label"] == "MEASURED", share
    assert abs(share["value"]["Read"] - 100 / expected_total) < 1e-9, share
    assert abs(share["value"]["Bash"] - 50 / expected_total) < 1e-9, share


def test_pressure_tool_output_share_no_data_without_tool_results():
    with tempfile.TemporaryDirectory() as d:
        _write(os.path.join(d, "s.jsonl"), [
            _assistant_line("2026-08-12T10:00:00Z"),
        ])
        prof = pf.build_profile(root=d, days=30)
    share = prof["pressure"]["tool_output_share_by_tool"]
    assert share["label"] == "NO DATA"
    assert share["value"] is None


def test_pressure_duplicate_reads_and_commands():
    # Calibrated: changing `count - 1` to `count` in _pressure_scan's
    # duplicate tally (counting every repeated call instead of every call
    # beyond the first) makes these exact-count assertions go red; restoring
    # `count - 1` makes them green.
    with tempfile.TemporaryDirectory() as d:
        _write(os.path.join(d, "s.jsonl"), [
            _assistant_line("2026-08-12T10:00:00Z", tool_uses=[
                ("t1", "Bash", {"command": "ls"}),
                ("t2", "Bash", {"command": "ls"}),      # exact repeat of t1
                ("t3", "Bash", {"command": "pwd"}),     # distinct input
                ("t4", "Read", {"file_path": "/a"}),
                ("t5", "Read", {"file_path": "/a"}),    # exact repeat
                ("t6", "Read", {"file_path": "/a"}),    # exact repeat again
            ]),
        ])
        prof = pf.build_profile(root=d, days=30)

    dup = prof["pressure"]["duplicate_reads"]
    assert dup["label"] == "MEASURED", dup
    assert dup["value"] == {"Bash": 1, "Read": 2}, dup

    cmd = prof["pressure"]["duplicate_commands"]
    assert cmd["label"] == "MEASURED", cmd
    assert cmd["value"] == 1, cmd


def test_pressure_duplicate_reads_measured_zero_not_no_data():
    # Tool calls happened but none repeated: a real, measured 0 / {}, never
    # NO DATA (NO DATA is reserved for "no tool_use blocks at all").
    with tempfile.TemporaryDirectory() as d:
        _write(os.path.join(d, "s.jsonl"), [
            _assistant_line("2026-08-12T10:00:00Z", tool_uses=[
                ("t1", "Bash", {"command": "ls"}),
            ]),
        ])
        prof = pf.build_profile(root=d, days=30)

    dup = prof["pressure"]["duplicate_reads"]
    assert dup["label"] == "MEASURED", dup
    assert dup["value"] == {}, dup

    cmd = prof["pressure"]["duplicate_commands"]
    assert cmd["label"] == "MEASURED", cmd
    assert cmd["value"] == 0, cmd


def test_pressure_duplicate_no_data_without_any_tool_use():
    with tempfile.TemporaryDirectory() as d:
        _write(os.path.join(d, "s.jsonl"), [_assistant_line("2026-08-12T10:00:00Z")])
        prof = pf.build_profile(root=d, days=30)
    dup = prof["pressure"]["duplicate_reads"]
    assert dup["label"] == "NO DATA"
    assert dup["value"] is None
    cmd = prof["pressure"]["duplicate_commands"]
    assert cmd["label"] == "NO DATA"
    assert cmd["value"] is None


def test_pressure_output_verbosity():
    # Calibrated: swapping statistics.median for statistics.mean in
    # _output_verbosity makes the median assertion go red (55.0 vs 214.0);
    # restoring median makes it green.
    values = [10, 20, 30, 40, 50, 60, 70, 80, 90, 2000]
    with tempfile.TemporaryDirectory() as d:
        _write(os.path.join(d, "s.jsonl"), [
            _assistant_line(f"2026-08-12T10:00:{i:02d}Z", output_tokens=v)
            for i, v in enumerate(values)
        ])
        prof = pf.build_profile(root=d, days=30)

    v = prof["pressure"]["output_verbosity"]
    assert v["label"] == "MEASURED", v
    assert v["value"]["median_output_tokens"] == statistics.median(values)
    assert v["value"]["p90_output_tokens"] == sorted(values)[9]
    assert v["value"]["over_1000_tokens_share"] == 1 / 10
    assert v["value"]["n_assistant_messages"] == 10


def test_pressure_output_verbosity_p90_needs_ten_samples():
    with tempfile.TemporaryDirectory() as d:
        _write(os.path.join(d, "s.jsonl"), [
            _assistant_line(f"2026-08-12T10:00:{i:02d}Z", output_tokens=1500)
            for i in range(3)
        ])
        prof = pf.build_profile(root=d, days=30)
    v = prof["pressure"]["output_verbosity"]["value"]
    assert v["p90_output_tokens"] is None, v
    assert v["over_1000_tokens_share"] == 1.0, v


def test_pressure_output_verbosity_no_data_without_usage():
    with tempfile.TemporaryDirectory() as d:
        _write(os.path.join(d, "s.jsonl"), [
            json.dumps({"type": "assistant", "message": {"content": []},
                        "timestamp": "2026-08-12T10:00:00Z"}),
        ])
        prof = pf.build_profile(root=d, days=30)
    v = prof["pressure"]["output_verbosity"]
    assert v["label"] == "NO DATA"
    assert v["value"] is None


def test_pressure_structured_input_share():
    # Calibrated: swapping the numerator/denominator (structured_bytes and
    # human_text_bytes) in the structured_input_share formula flips the
    # expected 0.8888... to 0.1111..., so this exact-value assertion goes
    # red; restoring the correct split makes it green.
    with tempfile.TemporaryDirectory() as d:
        _write(os.path.join(d, "s.jsonl"), [
            _user_line("2026-08-12T10:00:00Z",
                       tool_results=[("t1", "X" * 80)], text="human text"),
        ])
        prof = pf.build_profile(root=d, days=30)

    s = prof["pressure"]["structured_input_share"]
    assert s["label"] == "MEASURED", s
    expected = 80 / (80 + len("human text"))
    assert abs(s["value"] - expected) < 1e-9, s


def test_pressure_no_data_on_empty_transcripts():
    with tempfile.TemporaryDirectory() as d:
        _write(os.path.join(d, "s.jsonl"), ["not valid json", "{}"])
        prof = pf.build_profile(root=d, days=30)

    p = prof["pressure"]
    for key in ("tool_output_share_by_tool", "duplicate_reads", "duplicate_commands",
                "output_verbosity", "structured_input_share"):
        assert p[key]["label"] == "NO DATA", (key, p[key])
        assert p[key]["value"] is None, (key, p[key])


def _leaf(value, label="MEASURED"):
    return {"value": value, "label": label, "basis": "test fixture"}


def _waste_profile(r=0.90, s=0.15, m=0.05, t=0.30, v=400,
                    r_label="MEASURED", s_label="MEASURED", m_label="MEASURED",
                    t_label="MEASURED", v_label="MEASURED"):
    """A minimal profile carrying only the five leaves compute_waste_score
    reads, at the real profile.py field names and group nesting (see
    docs/WASTE-SCORE.md's component table). Defaults sit at the no-penalty
    anchor for every component."""
    return {
        "usage": {"cache_hit_ratio_median": _leaf(r, r_label)},
        "instruction": {"startup_floor_share": _leaf(s, s_label)},
        "behavior": {"model_switch_session_share": _leaf(m, m_label)},
        "pressure": {
            "structured_input_share": _leaf(t, t_label),
            "output_verbosity": _leaf({"median_output_tokens": v}, v_label),
        },
    }


def test_waste_score_component_anchors_and_midpoints():
    # Calibrated: changing `penalty = weight * frac` to `weight * frac / 2`
    # in pf._linear_penalty makes the full-penalty and midpoint assertions
    # below go red (e.g. cache_hit_ratio full penalty 15.0 instead of 30.0,
    # midpoint 7.5 instead of 15.0); the no-penalty (0) assertions stay
    # green either way, which is exactly why both anchors are checked.
    # cache_hit_ratio: weight 30, good 0.90, bad 0.50 (runs backward: good > bad)
    assert pf._linear_penalty(0.90, 0.90, 0.50, 30) == 0
    assert pf._linear_penalty(0.50, 0.90, 0.50, 30) == 30
    assert abs(pf._linear_penalty(0.70, 0.90, 0.50, 30) - 15.0) < 1e-9

    # startup_floor: weight 25, good 0.15, bad 0.45
    assert pf._linear_penalty(0.15, 0.15, 0.45, 25) == 0
    assert pf._linear_penalty(0.45, 0.15, 0.45, 25) == 25
    assert abs(pf._linear_penalty(0.30, 0.15, 0.45, 25) - 12.5) < 1e-9

    # model_switch: weight 20, good 0.05, bad 0.35
    assert pf._linear_penalty(0.05, 0.05, 0.35, 20) == 0
    assert pf._linear_penalty(0.35, 0.05, 0.35, 20) == 20
    assert abs(pf._linear_penalty(0.20, 0.05, 0.35, 20) - 10.0) < 1e-9

    # structured_input: weight 15, good 0.30, bad 0.70
    assert pf._linear_penalty(0.30, 0.30, 0.70, 15) == 0
    assert pf._linear_penalty(0.70, 0.30, 0.70, 15) == 15
    assert abs(pf._linear_penalty(0.50, 0.30, 0.70, 15) - 7.5) < 1e-9

    # output_verbosity: weight 10, good 400, bad 1200
    assert pf._linear_penalty(400, 400, 1200, 10) == 0
    assert pf._linear_penalty(1200, 400, 1200, 10) == 10
    assert abs(pf._linear_penalty(800, 400, 1200, 10) - 5.0) < 1e-9

    # Past either anchor the penalty stays flat, it never goes negative and
    # never exceeds the weight.
    assert pf._linear_penalty(1.0, 0.90, 0.50, 30) == 0
    assert pf._linear_penalty(0.0, 0.90, 0.50, 30) == 30


def test_waste_score_anchors_match_published_spec():
    # Ties _WASTE_COMPONENTS (what the scorer actually reads) to the exact
    # numbers docs/WASTE-SCORE.md publishes, so the two can never drift
    # apart silently.
    by_name = {c["name"]: c for c in pf._WASTE_COMPONENTS}
    assert by_name["cache_hit_ratio"]["weight"] == 30
    assert by_name["cache_hit_ratio"]["good"] == 0.90
    assert by_name["cache_hit_ratio"]["bad"] == 0.50
    assert by_name["startup_floor"]["weight"] == 25
    assert by_name["startup_floor"]["good"] == 0.15
    assert by_name["startup_floor"]["bad"] == 0.45
    assert by_name["model_switch"]["weight"] == 20
    assert by_name["model_switch"]["good"] == 0.05
    assert by_name["model_switch"]["bad"] == 0.35
    assert by_name["structured_input"]["weight"] == 15
    assert by_name["structured_input"]["good"] == 0.30
    assert by_name["structured_input"]["bad"] == 0.70
    assert by_name["output_verbosity"]["weight"] == 10
    assert by_name["output_verbosity"]["good"] == 400
    assert by_name["output_verbosity"]["bad"] == 1200
    assert sum(c["weight"] for c in pf._WASTE_COMPONENTS) == 100


def test_waste_score_round_half_up():
    # Calibrated: swapping the floor-based implementation for plain
    # round(x, ndigits) makes pf._round_half_up(61.25, 1) go red (Python's
    # round() uses round-half-to-even and returns 61.2, not 61.3, for this
    # exact binary-representable value); restoring the floor formula makes
    # it green again.
    assert pf._round_half_up(61.25, 1) == 61.3
    assert pf._round_half_up(0.05, 1) == 0.1
    assert pf._round_half_up(100.0, 1) == 100.0
    assert pf._round_half_up(0.0, 1) == 0.0


def test_waste_score_worked_example_from_doc():
    # The exact worked example published in docs/WASTE-SCORE.md: r=0.75,
    # s=0.25, m=0.15, t=0.55, v=650 tokens should score 61.3, band WASTEFUL.
    prof = _waste_profile(r=0.75, s=0.25, m=0.15, t=0.55, v=650)
    result = pf.compute_waste_score(prof)
    assert result["label"] == "MEASURED", result
    assert result["score"] == 61.3, result
    assert result["band"] == "WASTEFUL", result
    assert result["version"] == pf.WASTE_SCORE_VERSION


def test_waste_score_perfect_machine_scores_100():
    # Calibrated: mistyping model_switch's weight as 2 instead of 20 in
    # _WASTE_COMPONENTS does not move this test (every penalty is already 0
    # regardless of weight), which is exactly why the worst-case test below
    # is the one that catches a wrong weight.
    prof = _waste_profile(r=1.0, s=0.0, m=0.0, t=0.0, v=0)
    result = pf.compute_waste_score(prof)
    assert result["label"] == "MEASURED", result
    assert result["score"] == 100.0, result
    assert result["band"] == "LEAN", result


def test_waste_score_worst_case_scores_0():
    # Calibrated: changing model_switch's weight from 20 to 2 in
    # _WASTE_COMPONENTS (a plausible typo) makes this go red: score becomes
    # 100 - (30+25+2+15+10) = 18.0 instead of 0.0, because the weights no
    # longer sum to 100. Restoring weight 20 makes it green again.
    prof = _waste_profile(r=0.0, s=1.0, m=1.0, t=1.0, v=3000)
    result = pf.compute_waste_score(prof)
    assert result["label"] == "MEASURED", result
    assert result["score"] == 0.0, result
    assert result["band"] == "HEAVY WASTE", result


def test_waste_score_all_or_nothing_no_data():
    # Calibrated: widening the label check in compute_waste_score from
    # `label != "MEASURED"` to `label not in ("MEASURED", "SIGNAL")` lets a
    # SIGNAL-labeled model_switch leaf through as if it were MEASURED, so
    # the whole-score result silently becomes a number instead of NO DATA.
    # That is exactly the bug this test exists to catch: restoring the
    # exact "MEASURED" check makes it red-to-green.
    #
    # Case 1: one input carries a non-MEASURED label (SIGNAL).
    prof = _waste_profile(m_label="SIGNAL")
    result = pf.compute_waste_score(prof)
    assert result["label"] == "NO DATA", result
    assert result["score"] is None, result
    assert result["band"] is None, result
    assert any("model_switch" in reason for reason in result["missing"]), result

    # Case 2: one input is explicitly NO DATA (value None, label NO DATA).
    prof2 = _waste_profile()
    prof2["usage"]["cache_hit_ratio_median"] = pf.no_data("no usage window")
    result2 = pf.compute_waste_score(prof2)
    assert result2["label"] == "NO DATA", result2
    assert any("cache_hit_ratio" in reason for reason in result2["missing"]), result2

    # Case 3: one input is entirely absent from the profile.
    prof3 = _waste_profile()
    del prof3["pressure"]["structured_input_share"]
    result3 = pf.compute_waste_score(prof3)
    assert result3["label"] == "NO DATA", result3
    assert any("structured_input" in reason for reason in result3["missing"]), result3

    # A single failure must not leak a partial score for the other four.
    assert "components" not in result


def test_waste_score_version_present_in_output():
    # Calibrated: dropping the "version" key from the NO-DATA branch's
    # return dict in compute_waste_score makes the second assertion below
    # go red with a KeyError; restoring it makes both green.
    ok = pf.compute_waste_score(_waste_profile())
    assert ok["version"] == "waste-score/1"

    no_data = pf.compute_waste_score(_waste_profile(m_label="NO DATA"))
    assert no_data["version"] == "waste-score/1"


def test_main_exits_2_on_empty_root():
    with tempfile.TemporaryDirectory() as d:
        empty_root = os.path.join(d, "empty")
        os.makedirs(empty_root)
        argv = sys.argv
        sys.argv = ["profile.py", "--root", empty_root, "--out",
                    os.path.join(d, "profile.json")]
        try:
            rc = pf.main()
        finally:
            sys.argv = argv
    assert rc == 2


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
