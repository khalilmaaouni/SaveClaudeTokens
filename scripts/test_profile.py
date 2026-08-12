#!/usr/bin/env python3
"""Self-check for profile.py. No framework, no fixtures.

    python3 scripts/test_profile.py
"""

import json
import os
import sys
import tempfile

import profile as pf
import measure_tokens as mt

METRIC_GROUPS = ("usage", "behavior", "instruction", "environment", "skipped")

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
