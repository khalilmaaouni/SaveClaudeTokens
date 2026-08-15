#!/usr/bin/env python3
"""Self-check for profile.py. No framework, no fixtures.

    python3 scripts/test_profile.py
"""

import io
import json
import os
import re
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


def _assistant_line(ts, output_tokens=1, tool_uses=None, model="claude-x", input_tokens=1):
    """One assistant transcript line. tool_uses is a list of
    (tool_id, name, input_dict) tuples, matching the real tool_use block
    shape: {"type": "tool_use", "id", "name", "input", "caller"}. model and
    input_tokens default to the original fixed values so every existing
    caller is unaffected; the waste-score attack fixtures below pass both
    explicitly."""
    content = [
        {"type": "tool_use", "id": tid, "name": name, "input": inp,
         "caller": {"type": "direct"}}
        for tid, name, inp in (tool_uses or [])
    ]
    msg = {
        "model": model,
        "content": content,
        "usage": {
            "input_tokens": input_tokens,
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


def _waste_profile(r=0.90, s=0.15, m=0.05, t=1000, v=400, sessions=20, n_messages=20,
                    r_label="MEASURED", s_label="MEASURED", m_label="MEASURED",
                    t_label="MEASURED", v_label="MEASURED", sessions_label="MEASURED"):
    """A minimal profile carrying only the leaves compute_waste_score reads,
    at the real profile.py field names and group nesting (see
    docs/WASTE-SCORE.md's component table, waste-score/2). Defaults sit at
    the no-penalty anchor for every component, and sessions/n_messages
    default comfortably above the sample floor so a test that only cares
    about one component does not also have to think about the floor. t is
    tool_result_avg_bytes (bytes, not a share); v is output_verbosity's
    p90_output_tokens."""
    return {
        "usage": {"cache_hit_ratio_median": _leaf(r, r_label)},
        "instruction": {"startup_floor_share": _leaf(s, s_label)},
        "behavior": {
            "model_switch_volume_share": _leaf(m, m_label),
            "sessions": _leaf(sessions, sessions_label),
        },
        "pressure": {
            "tool_result_avg_bytes": _leaf(t, t_label),
            "output_verbosity": _leaf({"p90_output_tokens": v, "n_assistant_messages": n_messages},
                                       v_label),
        },
    }


def _ws_session(prefix, n_calls=3, input_tokens=1000, output_tokens=500,
                 model="claude-x", switch=False, tool_bytes=None, human_bytes=0):
    """One session (the lines of one transcript file) for the waste-score
    attack reproductions below. Every call in the session carries the SAME
    input_tokens, which is what keeps first_request_share pinned at exactly
    1.0 (first * calls / raw_input collapses to 1.0 whenever every call is
    the same size) regardless of how many calls or sessions the attack adds;
    read stays 0 throughout, which keeps hit_ratio pinned at 0.0 the same
    way. That lets each attack test move exactly one metric and hold the
    other four still, real fixture math throughout, not hand-picked leaves.

    switch=True gives the LAST call a different model, tripping the
    model-switch detector for this session. tool_bytes, given, attaches one
    tool_use to the first call and a matching tool_result of that many
    bytes; human_bytes adds a human-typed text block alongside it. calls
    below 3 are deliberately excluded from measure_tokens's hit_ratio and
    first_request_share aggregation (calls >= 3), which is how the filler
    sessions in attack C stay invisible to components 1 and 2."""
    lines = []
    for i in range(n_calls):
        ts = f"{prefix}T10:{i:02d}:00Z"
        m = "claude-y" if (switch and i == n_calls - 1) else model
        first_call = tool_bytes is not None and i == 0
        tool_uses = [("t1", "Bash", {"cmd": "x"})] if first_call else None
        lines.append(_assistant_line(ts, output_tokens=output_tokens, tool_uses=tool_uses,
                                      model=m, input_tokens=input_tokens))
        if first_call:
            lines.append(_user_line(ts, tool_results=[("t1", "X" * tool_bytes)],
                                     text=("H" * human_bytes if human_bytes else None)))
    return lines


def test_attack_C1A_pasted_human_text_games_v1_structured_input_share():
    # FINDING C1.A (hostile review, fix round 2): padding every user turn
    # with pasted human text lowers structured_input_share (v1's tool_output
    # metric, structured_bytes / (structured_bytes + human_text_bytes)) and
    # therefore RAISES the score, even though pasting more text strictly
    # increases total tokens spent. Reproduced here on real fixtures pushed
    # through the real pipeline (build_profile then compute_waste_score),
    # not hand-picked leaves.
    #
    # Ten sessions, three calls each (the calls >= 3 floor for components 1
    # and 2), one fixed 500-byte tool_result per session so component 4's
    # numerator never moves; only the human-typed text alongside it grows by
    # 8KB per session between the two builds, matching the reviewer's exact
    # manoeuvre.
    def build(human_bytes):
        with tempfile.TemporaryDirectory() as d:
            for i in range(10):
                _write(os.path.join(d, f"s{i}.jsonl"),
                       _ws_session(f"2026-08-{i + 1:02d}", tool_bytes=500, human_bytes=human_bytes))
            return pf.build_profile(root=d, days=30)

    baseline = pf.compute_waste_score(build(100))
    padded = pf.compute_waste_score(build(100 + 8192))
    assert baseline["label"] == "MEASURED", baseline
    assert padded["label"] == "MEASURED", padded
    # THE ACCEPTANCE RULE: no manoeuvre that strictly increases total tokens
    # (pasting 8KB more human text into every turn) may increase the score.
    assert padded["score"] <= baseline["score"], (baseline["score"], padded["score"])


def test_attack_C1B_session_farming_games_v1_model_switch_session_share():
    # FINDING C1.B: padding a machine's session count with cheap, unswitched
    # sessions dilutes model_switch_session_share (a plain count of sessions
    # that switched, over total sessions), so a machine that pays for a
    # fresh startup floor twenty times over scores BETTER than one that pays
    # for it ten times, purely because the extra sessions never switch
    # models. The reviewer's own fixture padded 4 real sessions to 20; the
    # baseline is 10 real sessions here instead of 4, because finding C2 in
    # this same round adds a 10-session floor below which nothing scores at
    # all, and a baseline that cannot score cannot demonstrate a score
    # INCREASE. Ten real sessions (4 of them switching) meets that floor
    # exactly; the manoeuvre padded on top is unchanged: pure session count.
    #
    # Real sessions carry input_tokens=1000/call; the padded, unswitched
    # sessions carry input_tokens=10/call, ten times smaller. Under v1 (a
    # plain session count) that difference does not matter at all, which is
    # exactly the bug; under v2 (weighted by each session's own raw_input,
    # already produced by measure_tokens.read_session) it does.
    def build(n_trivial):
        with tempfile.TemporaryDirectory() as d:
            for i in range(10):
                _write(os.path.join(d, f"real{i}.jsonl"),
                       _ws_session(f"2026-08-{i + 1:02d}", input_tokens=1000, switch=(i < 4),
                                    tool_bytes=500))
            for j in range(n_trivial):
                _write(os.path.join(d, f"trivial{j}.jsonl"),
                       _ws_session(f"2026-08-{(j % 28) + 1:02d}", input_tokens=10, switch=False))
            return pf.build_profile(root=d, days=30)

    baseline = pf.compute_waste_score(build(0))
    padded = pf.compute_waste_score(build(10))
    assert baseline["label"] == "MEASURED", baseline
    assert padded["label"] == "MEASURED", padded
    # THE ACCEPTANCE RULE: ten more (strictly more tokens spent) sessions,
    # none of them switching, may not raise the score.
    assert padded["score"] <= baseline["score"], (baseline["score"], padded["score"])


def test_attack_C1C_filler_messages_game_v1_median_verbosity():
    # FINDING C1.C: appending cheap one-token filler assistant messages
    # drags the MEDIAN output_tokens down, so output_verbosity's v1 penalty
    # falls even though every filler message is pure additional spend. Ten
    # honest sessions (three calls each, 2000 output tokens per call, so the
    # calls >= 3 floor is met and the honest median/p90 both start at 2000)
    # against 60 one-call filler sessions (excluded from components 1 and 2
    # by the calls >= 3 floor, but not from output_verbosity, which counts
    # every scanned assistant message).
    def build(n_filler):
        with tempfile.TemporaryDirectory() as d:
            for i in range(10):
                _write(os.path.join(d, f"honest{i}.jsonl"),
                       _ws_session(f"2026-08-{i + 1:02d}", output_tokens=2000, tool_bytes=500))
            for j in range(n_filler):
                _write(os.path.join(d, f"filler{j}.jsonl"),
                       _ws_session(f"2026-08-{(j % 28) + 1:02d}", n_calls=1, output_tokens=1))
            return pf.build_profile(root=d, days=30)

    baseline = pf.compute_waste_score(build(0))
    padded = pf.compute_waste_score(build(60))
    assert baseline["label"] == "MEASURED", baseline
    assert padded["label"] == "MEASURED", padded
    # THE ACCEPTANCE RULE: sixty more (strictly more tokens spent) filler
    # messages may not raise the score.
    assert padded["score"] <= baseline["score"], (baseline["score"], padded["score"])


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

    # tool_result_avg_bytes (waste-score/2): weight 15, good 2000, bad 20000
    assert pf._linear_penalty(2000, 2000, 20000, 15) == 0
    assert pf._linear_penalty(20000, 2000, 20000, 15) == 15
    assert abs(pf._linear_penalty(11000, 2000, 20000, 15) - 7.5) < 1e-9

    # output_verbosity (waste-score/2, p90 not median): weight 10, good 800, bad 2500
    assert pf._linear_penalty(800, 800, 2500, 10) == 0
    assert pf._linear_penalty(2500, 800, 2500, 10) == 10
    assert abs(pf._linear_penalty(1650, 800, 2500, 10) - 5.0) < 1e-9

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
    # waste-score/2 (FINDING C1.B): model switching is weighted by each
    # session's own token volume, not counted per session, or a machine can
    # dilute a genuine switcher for free by padding on cheap sessions.
    assert by_name["model_switch"]["group"] == "behavior"
    assert by_name["model_switch"]["key"] == "model_switch_volume_share"
    assert by_name["tool_result_avg_bytes"]["weight"] == 15
    assert by_name["tool_result_avg_bytes"]["good"] == 2000
    assert by_name["tool_result_avg_bytes"]["bad"] == 20000
    # waste-score/2 (FINDING C1.A): tool_output reads the average tool_result
    # payload size, not structured_input_share, or pasting more human-typed
    # text raises the score by diluting a share's denominator.
    assert by_name["tool_result_avg_bytes"]["group"] == "pressure"
    assert by_name["tool_result_avg_bytes"]["key"] == "tool_result_avg_bytes"
    assert by_name["output_verbosity"]["weight"] == 10
    assert by_name["output_verbosity"]["good"] == 800
    assert by_name["output_verbosity"]["bad"] == 2500
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
    # The exact worked example published in docs/WASTE-SCORE.md
    # (waste-score/2): r=0.75, s=0.25, m=0.15, t=8000 bytes, v=1500 p90
    # tokens should score 64.6, band WASTEFUL.
    prof = _waste_profile(r=0.75, s=0.25, m=0.15, t=8000, v=1500)
    result = pf.compute_waste_score(prof)
    assert result["label"] == "MEASURED", result
    assert result["score"] == 64.6, result
    assert result["band"] == "WASTEFUL", result
    assert result["version"] == pf.WASTE_SCORE_VERSION


def test_waste_score_perfect_machine_scores_100():
    # Calibrated: mistyping model_switch's weight as 2 instead of 20 in
    # _WASTE_COMPONENTS does not move this test (every penalty is already 0
    # regardless of weight), which is exactly why the worst-case test below
    # is the one that catches a wrong weight.
    prof = _waste_profile(r=1.0, s=0.0, m=0.0, t=0, v=0)
    result = pf.compute_waste_score(prof)
    assert result["label"] == "MEASURED", result
    assert result["score"] == 100.0, result
    assert result["band"] == "LEAN", result


def test_waste_score_worst_case_scores_0():
    # Calibrated: changing model_switch's weight from 20 to 2 in
    # _WASTE_COMPONENTS (a plausible typo) makes this go red: score becomes
    # 100 - (30+25+2+15+10) = 18.0 instead of 0.0, because the weights no
    # longer sum to 100. Restoring weight 20 makes it green again.
    prof = _waste_profile(r=0.0, s=1.0, m=1.0, t=20000, v=3000)
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
    del prof3["pressure"]["tool_result_avg_bytes"]
    result3 = pf.compute_waste_score(prof3)
    assert result3["label"] == "NO DATA", result3
    assert any("tool_result" in reason for reason in result3["missing"]), result3

    # A single failure must not leak a partial score for the other four.
    assert "components" not in result


def test_waste_score_version_present_in_output():
    # Calibrated: dropping the "version" key from the NO-DATA branch's
    # return dict in compute_waste_score makes the second assertion below
    # go red with a KeyError; restoring it makes both green.
    ok = pf.compute_waste_score(_waste_profile())
    assert ok["version"] == "waste-score/2"

    no_data = pf.compute_waste_score(_waste_profile(m_label="NO DATA"))
    assert no_data["version"] == "waste-score/2"


def test_waste_score_sample_floor_no_data_named_with_counts():
    # FINDING C2 (hostile review): a one-session, three-tool-call machine
    # returned MEASURED, 49.9, HEAVY WASTE, the same units as a 229-session
    # baseline. Below the published floor (10 sessions AND 10 assistant
    # messages), the whole result is NO DATA naming the actual shortfall.
    prof = _waste_profile(sessions=1, n_messages=3)
    result = pf.compute_waste_score(prof)
    assert result["label"] == "NO DATA", result
    assert any("session" in reason and "1" in reason for reason in result["missing"]), result
    assert any("assistant message" in reason and "3" in reason for reason in result["missing"]), result

    # Either shortfall alone is enough to refuse the whole score.
    only_thin_sessions = pf.compute_waste_score(_waste_profile(sessions=2))
    assert only_thin_sessions["label"] == "NO DATA", only_thin_sessions
    only_thin_messages = pf.compute_waste_score(_waste_profile(n_messages=4))
    assert only_thin_messages["label"] == "NO DATA", only_thin_messages

    # Ten and ten, the published floor exactly, must NOT be NO DATA.
    at_floor = pf.compute_waste_score(_waste_profile(sessions=10, n_messages=10))
    assert at_floor["label"] == "MEASURED", at_floor


def test_waste_score_nonfinite_input_is_no_data():
    # FINDING M3 (hostile review, plus the founder's own probe): a NaN
    # cache ratio, with every other input healthy, silently failed every
    # comparison in _linear_penalty's clamp and came back as a confident
    # score (70.0, OK, MEASURED) instead of a refusal. Reachability from a
    # real profile is low today, since the upstream divisions that build
    # cache_hit_ratio_median are all guarded against a zero denominator;
    # the guard here is three lines and this repository has already been
    # broken once by exactly this class of silent-comparison bug.
    for bad in (float("nan"), float("inf"), float("-inf")):
        result = pf.compute_waste_score(_waste_profile(r=bad))
        assert result["label"] == "NO DATA", (bad, result)
        assert any("cache_hit_ratio" in reason for reason in result["missing"]), (bad, result)


def test_waste_score_domain_guard_rejects_implausible_share():
    # FINDING C2's second half (hostile review): the reviewer's own fixture
    # produced a startup_floor_share of 1.981, a mathematically impossible
    # "share" that the old clamp silently treated as full penalty. Any
    # component value outside its plausible domain is NO DATA naming the
    # actual value, never a silent clamp to full penalty.
    result = pf.compute_waste_score(_waste_profile(s=1.981))
    assert result["label"] == "NO DATA", result
    assert any("startup_floor" in reason and "1.981" in reason for reason in result["missing"]), result

    # A share below 0 is exactly as implausible as one above 1.
    negative = pf.compute_waste_score(_waste_profile(r=-0.1))
    assert negative["label"] == "NO DATA", negative
    assert any("cache_hit_ratio" in reason for reason in negative["missing"]), negative


def test_waste_score_band_edges_exact_values():
    # FINDING M4 (hostile review's own probe): changing `if score >= floor`
    # to `if score > floor` in pf._waste_band makes a machine scoring
    # exactly 90 read OK instead of LEAN, and the rest of the suite stayed
    # green. Pins every published band edge to its exact value.
    assert pf._waste_band(100.0) == "LEAN"
    assert pf._waste_band(90.0) == "LEAN"
    assert pf._waste_band(89.9) == "OK"
    assert pf._waste_band(70.0) == "OK"
    assert pf._waste_band(69.9) == "WASTEFUL"
    assert pf._waste_band(50.0) == "WASTEFUL"
    assert pf._waste_band(49.9) == "HEAVY WASTE"
    assert pf._waste_band(0.0) == "HEAVY WASTE"


def test_waste_score_doc_tables_match_code_constants():
    # FINDING M4 (hostile review): nothing tied the code to the published
    # document. Parses the component and band tables straight out of
    # docs/WASTE-SCORE.md and asserts they equal the code's own constants,
    # so editing either one alone turns this test red.
    doc_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                             "docs", "WASTE-SCORE.md")
    text = open(doc_path, encoding="utf-8").read()

    # "| 1 | cache_hit_ratio | 30 | 0.90 | 0.50 |"
    comp_rows = re.findall(
        r"^\|\s*\d\s*\|\s*([a-z_]+)\s*\|\s*(\d+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*$",
        text, re.MULTILINE)
    assert len(comp_rows) == 5, comp_rows
    doc_components = {name: (int(w), float(good), float(bad)) for name, w, good, bad in comp_rows}
    for comp in pf._WASTE_COMPONENTS:
        assert comp["name"] in doc_components, (comp["name"], sorted(doc_components))
        w, good, bad = doc_components[comp["name"]]
        assert w == comp["weight"], (comp["name"], "weight", w, comp["weight"])
        assert good == comp["good"], (comp["name"], "good", good, comp["good"])
        assert bad == comp["bad"], (comp["name"], "bad", bad, comp["bad"])
    assert sum(w for w, _, _ in doc_components.values()) == 100, doc_components

    # "| 90 to 100 | LEAN |" / "| below 50 | HEAVY WASTE |"
    threshold_rows = re.findall(
        r"^\|\s*(\d+(?:\.\d+)?)\s+to\s+[\d.]+\s*\|\s*([A-Z ]+?)\s*\|\s*$", text, re.MULTILINE)
    assert len(threshold_rows) == 3, threshold_rows
    doc_bands = sorted(((float(f), n.strip()) for f, n in threshold_rows), reverse=True)
    code_bands = sorted(((float(f), n) for f, n in pf.WASTE_BANDS), reverse=True)
    assert doc_bands == code_bands, (doc_bands, code_bands)

    below_rows = re.findall(r"^\|\s*below\s+(\d+(?:\.\d+)?)\s*\|\s*([A-Z ]+?)\s*\|\s*$",
                             text, re.MULTILINE)
    assert len(below_rows) == 1, below_rows
    below_floor, below_name = below_rows[0]
    assert float(below_floor) == min(f for f, _ in pf.WASTE_BANDS), below_floor
    assert below_name.strip() == "HEAVY WASTE"


def test_waste_score_printed_by_main():
    # FINDING M5 (hostile review): compute_waste_score was dead code,
    # nothing called it. Printed from profile.py's own main(), which
    # cli.py picks up for free since it runs profile.py as a subprocess.
    with tempfile.TemporaryDirectory() as d:
        root = os.path.join(d, "projects")
        os.makedirs(root)
        for i in range(10):
            _write(os.path.join(root, f"s{i}.jsonl"),
                   _ws_session(f"2026-08-{i + 1:02d}", tool_bytes=500))
        out = os.path.join(d, "out", "profile.json")

        argv = sys.argv
        stdout = sys.stdout
        sys.argv = ["profile.py", "--root", root, "--days", "30", "--out", out]
        sys.stdout = captured = io.StringIO()
        try:
            rc = pf.main()
        finally:
            sys.argv = argv
            sys.stdout = stdout
    assert rc == 0, rc
    text = captured.getvalue()
    assert pf.WASTE_SCORE_VERSION in text, text
    assert "waste score" in text.lower(), text


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
