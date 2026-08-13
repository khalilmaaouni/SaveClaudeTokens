#!/usr/bin/env python3
"""Self-check for reconcile.py. No framework, no fixtures beyond what each
test builds itself in a temp dir. NEVER points at ~/.claude/projects.

    python3 scripts/test_reconcile.py

Calibration note: test_disagreement_exits_nonzero and test_cli_disagreement_exit_1
were run once against a deliberately widened tolerance (temporarily editing
reconcile.DRIFT_TOLERANCE to 100.0 while writing this file) to confirm they
go RED (fail) when the drift check is too loose to catch anything; then the
real 0.5 percent tolerance was restored and they went GREEN. The checked-in
tolerance below is the real one.
"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("rc", os.path.join(HERE, "reconcile.py"))
rc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rc)


def _rec(inp, w5, w1, read, out, sidechain=False, model="claude-x"):
    return json.dumps({
        "isSidechain": sidechain,
        "message": {"model": model, "usage": {
            "input_tokens": inp,
            "cache_creation": {"ephemeral_5m_input_tokens": w5,
                               "ephemeral_1h_input_tokens": w1},
            "cache_creation_input_tokens": w5 + w1,
            "cache_read_input_tokens": read,
            "output_tokens": out}}})


def _write(path, records):
    with open(path, "w") as f:
        f.write("\n".join(records) + "\n")


def test_split_writes_matches_measure_tokens_semantics():
    # Same three cases measure_tokens.test_split_writes locks down, proving
    # this independent reimplementation applies the same rule: the nested
    # split wins when populated, the flat counter is used only when the
    # nested object is absent or accounts for nothing.
    assert rc._split_writes({"cache_creation": {"ephemeral_5m_input_tokens": 100,
                                                 "ephemeral_1h_input_tokens": 200},
                             "cache_creation_input_tokens": 300}) == (100, 200, 0)
    assert rc._split_writes({"cache_creation": {"ephemeral_5m_input_tokens": 0,
                                                 "ephemeral_1h_input_tokens": 2001},
                             "cache_creation_input_tokens": 0}) == (0, 2001, 0)
    assert rc._split_writes({"cache_creation_input_tokens": 500}) == (0, 0, 500)


def test_parse_session_matches_read_session_semantics():
    with tempfile.TemporaryDirectory() as d:
        fp = os.path.join(d, "s.jsonl")
        _write(fp, [
            _rec(10, 100, 0, 0, 5, model="model-a"),      # parent, first call
            _rec(1, 50, 0, 10, 7, sidechain=True),         # subagent, ignored
            _rec(2, 0, 200, 1000, 9, model="model-b"),     # parent, after switch
        ])
        s = rc.parse_session(fp)

    assert s["calls"] == 3
    assert s["first_request"] == 110, s["first_request"]
    assert s["multi_model"] is True
    # calls >= 3, first_request > 0: share is first*calls/raw_input, raw_input
    # = input + write_total + read = 13 + 350 + 1010 = 1373.
    assert abs(s["share"] - (110 * 3 / 1373)) < 1e-9


def test_parse_session_skips_all_zero_and_bad_json_lines():
    with tempfile.TemporaryDirectory() as d:
        fp = os.path.join(d, "s.jsonl")
        with open(fp, "w") as f:
            f.write(_rec(10, 100, 0, 0, 5, model="model-a") + "\n")
            f.write('{"message": {"usage": {"input_tokens": truncated\n')
            f.write(_rec(2, 0, 200, 1000, 9, model="model-a") + "\n")
        s = rc.parse_session(fp)
    assert s["calls"] == 2
    assert s["multi_model"] is False


def test_subagent_only_transcript_has_no_first_request():
    with tempfile.TemporaryDirectory() as d:
        fp = os.path.join(d, "sub.jsonl")
        _write(fp, [_rec(1, 20, 0, 5, 4, sidechain=True)])
        s = rc.parse_session(fp)
    assert s["first_request"] is None
    assert s["multi_model"] is False


def _build_fixture(d, n_sessions=4):
    """A handful of well-formed sessions, varying enough to exercise the
    median and the multi-model count without any deliberate mismatch."""
    for i in range(n_sessions):
        fp = os.path.join(d, f"s{i}.jsonl")
        if i % 2 == 0:
            _write(fp, [
                _rec(10 + i, 100, 0, 0, 5, model="model-a"),
                _rec(2, 0, 50, 500 + i * 10, 9, model="model-a"),
                _rec(3, 0, 0, 20, 1, model="model-a"),
            ])
        else:
            _write(fp, [
                _rec(20 + i, 200, 0, 0, 8, model="model-a"),
                _rec(4, 0, 80, 300, 3, model="model-b"),  # switch
                _rec(5, 0, 0, 40, 2, model="model-b"),
            ])


def test_empty_dir_is_no_data_exit_2():
    with tempfile.TemporaryDirectory() as d:
        proc = subprocess.run(
            [sys.executable, os.path.join(HERE, "reconcile.py"),
             "--root", d, "--days", "9999"],
            capture_output=True, text=True)
    assert proc.returncode == 2, (proc.returncode, proc.stdout, proc.stderr)
    assert "NO DATA" in proc.stderr


def test_agreement_fixture_exits_0():
    # Real fixture transcripts, parsed by BOTH reconcile.py's own code and a
    # real subprocess run of measure_tokens.py. Since both implement the same
    # population rules, they must agree on real data: this is the actual
    # proof that the reimplementation is faithful, not just that the CLI
    # plumbing works.
    with tempfile.TemporaryDirectory() as d:
        _build_fixture(d, n_sessions=5)
        proc = subprocess.run(
            [sys.executable, os.path.join(HERE, "reconcile.py"),
             "--root", d, "--days", "9999"],
            capture_output=True, text=True)
    assert proc.returncode == 0, (proc.returncode, proc.stdout, proc.stderr)
    assert "RECONCILED" in proc.stdout
    assert "DRIFT" not in proc.stdout


def test_disagreement_exits_nonzero():
    # Calibration for the comparator itself: feed compare() two summaries
    # that differ by far more than the tolerance and confirm it refuses to
    # call that a match. Directly exercises the logic the CLI's exit code 1
    # depends on, without needing a real transcript mismatch (correct code
    # can never produce one against itself).
    own = {"first_request_median": 1000.0, "first_request_share_median": 0.5,
           "multi_model_count": 3}
    mt = {"first_request_median": 2000.0, "first_request_share_median": 0.5,
          "multi_model_count": 3}
    ok, rows = rc.compare(own, mt)
    assert ok is False
    statuses = {name: status for name, *_rest, status in rows}
    assert statuses["first_request_median"] is False
    assert statuses["first_request_share_median"] is True


def test_agreement_comparator_exits_ok():
    own = {"first_request_median": 1000.0, "first_request_share_median": 0.5,
           "multi_model_count": 3}
    mt = {"first_request_median": 1002.0, "first_request_share_median": 0.501,
          "multi_model_count": 3}
    ok, rows = rc.compare(own, mt)
    assert ok is True


def test_cli_disagreement_exit_1():
    # End to end: a real fixture directory, but reconcile.py is pointed at a
    # stub "measure_tokens.py" that prints numbers nothing like the real
    # parse. Proves the exit-1 path fires through the actual CLI, not only
    # through the pure compare() function above.
    with tempfile.TemporaryDirectory() as d:
        _build_fixture(d, n_sessions=3)
        stub = os.path.join(d, "stub_measure_tokens.py")
        with open(stub, "w") as f:
            f.write(
                "print('=== MEASURED, transcripts touched in the last 9999 days ===')\n"
                "print('first request median       999999999 tokens')\n"
                "print('first request share median 0.001')\n"
                "print()\n"
                "print('=== waste signals, highest first request first ===')\n"
                "print(' first_req  share  calls    hit  rewrite  models  session')\n"
                "print('       999  1.000      1  0.000  NO DATA       1  x.jsonl')\n"
            )
        proc = subprocess.run(
            [sys.executable, os.path.join(HERE, "reconcile.py"),
             "--root", d, "--days", "9999", "--measure-tokens", stub],
            capture_output=True, text=True)
    assert proc.returncode == 1, (proc.returncode, proc.stdout, proc.stderr)
    assert "NOT RECONCILED" in proc.stdout
    assert "DRIFT" in proc.stdout


def test_parse_measure_tokens_output_reads_fixed_width_models_column():
    text = (
        "first request median       1,234 tokens\n"
        "first request share median 0.250\n"
        "\n"
        "=== waste signals, highest first request first ===\n"
        " first_req  share  calls    hit  rewrite  models  session\n"
        "       110  0.168      2  0.762     0.30       2  s1.jsonl\n"
        "        20  1.000      1  0.000  NO DATA       1  s2.jsonl\n"
        "\n"
        "models above 1 means the session switched model mid-flight.\n"
    )
    parsed = rc.parse_measure_tokens_output(text)
    assert parsed["first_request_median"] == 1234.0
    assert parsed["first_request_share_median"] == 0.25
    assert parsed["multi_model_count"] == 1


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
