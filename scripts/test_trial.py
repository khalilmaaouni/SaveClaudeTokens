#!/usr/bin/env python3
"""Self-check for trial.py. No framework, no fixtures.

    python3 scripts/test_trial.py
"""

import contextlib
import io
import json
import os
import sys
import tempfile

import trial as tr
import measure_tokens as mt
import token_shield as ts


def _rec(ts_str, model="claude-x", inp=100, w5=0, w1=0, read=900, out=50,
         sidechain=False):
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
    rec = {"isSidechain": sidechain, "message": msg, "timestamp": ts_str}
    return json.dumps(rec)


def _write(path, lines):
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def _snapshot(root):
    """path -> (size, mtime) for every file under root, so a before/after
    comparison catches any new, deleted, or modified file."""
    snap = {}
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            p = os.path.join(dirpath, name)
            st = os.stat(p)
            snap[p] = (st.st_size, st.st_mtime_ns)
    return snap


def _run(root, days=30):
    buf = io.StringIO()
    rc = tr.run(root, days, out=buf)
    return rc, buf.getvalue()


# --- empty store / NO DATA -------------------------------------------------

def test_no_data_when_root_missing():
    # Calibrated: dropping the `if not os.path.isdir(root)` guard in
    # trial.py makes this go red. Without it, mt.collect() over a
    # nonexistent path silently returns no sessions and run() falls into the
    # "carried no usage counters" branch, which claims the path "exists" when
    # it does not: a dishonest NO DATA message. This test pins the honest,
    # distinct wording the guard produces.
    with tempfile.TemporaryDirectory() as d:
        missing = os.path.join(d, "does-not-exist")
        rc, text = _run(missing)
    assert rc == 0, rc
    assert "NO DATA" in text
    assert missing in text
    assert "Use Claude Code" in text
    assert "no Claude Code transcripts found at" in text
    assert "exists but carried no usage counters" not in text


def test_no_data_when_root_empty():
    with tempfile.TemporaryDirectory() as d:
        rc, text = _run(d)
    assert rc == 0, rc
    assert "NO DATA" in text
    assert "Use Claude Code" in text


def test_no_data_when_transcripts_carry_no_usage():
    with tempfile.TemporaryDirectory() as d:
        _write(os.path.join(d, "s.jsonl"), ["{}", '{"no": "usage here"}'])
        rc, text = _run(d)
    assert rc == 0, rc
    assert "NO DATA" in text


# --- malformed transcript: named skip, never a crash ------------------------

def test_malformed_line_is_skipped_and_reported_not_crashed():
    # Calibrated: removing the `if skip["files"] or skip["lines"]:` block
    # (and its print) in trial.py's non-NO-DATA branch makes this go red,
    # because the printed text then never names the skipped line count even
    # though mt.skip_counts() still reports it.
    with tempfile.TemporaryDirectory() as d:
        good = [_rec(f"2026-08-12T10:0{i}:00Z") for i in range(3)]
        # Contains '"usage"' so read_session tries to json.loads it, and it
        # fails to decode: this is exactly the truncated-write shape
        # measure_tokens.py counts as a skipped line rather than raising.
        broken = '{"message": {"usage": {"input_tokens": '
        _write(os.path.join(d, "s.jsonl"), good + [broken])
        rc, text = _run(d)
    assert rc == 0, rc
    assert "NO DATA" not in text
    assert "skipped 0 unreadable file(s) and 1 unreadable line(s)" in text
    assert "MEASURED" in text


def test_malformed_file_does_not_crash_other_sessions():
    with tempfile.TemporaryDirectory() as d:
        good = [_rec(f"2026-08-12T10:0{i}:00Z") for i in range(5)]
        _write(os.path.join(d, "good.jsonl"), good)
        # A file with no usage-bearing lines at all: read_session returns
        # None for it (calls == 0), and collect() simply excludes it. The
        # good session must still be measured.
        _write(os.path.join(d, "empty.jsonl"), ["not json at all", "{}"])
        rc, text = _run(d)
    assert rc == 0, rc
    assert "NO DATA" not in text
    assert "MEASURED" in text


# --- reads only, never writes ------------------------------------------------

def test_source_has_no_write_or_delete_calls():
    # Calibrated: adding `open(os.path.join(root, "x"), "w")` to trial.py's
    # run() makes this go red immediately, without needing to execute it.
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "trial.py")).read()
    forbidden = ('"w")', "'w')", '"w+"', "os.makedirs", "os.remove",
                 "os.unlink", "shutil.", "os.mkdir")
    hits = [f for f in forbidden if f in src]
    assert not hits, f"trial.py source contains write/delete calls: {hits}"


def test_never_writes_to_disk():
    # Calibrated: temporarily adding `open(os.path.join(root, "touched"),
    # "w").close()` at the top of run() in trial.py makes this go red, since
    # the before/after snapshot of the sandbox root then differs by one file.
    with tempfile.TemporaryDirectory() as d:
        good = [_rec(f"2026-08-12T10:0{i}:00Z") for i in range(5)]
        _write(os.path.join(d, "s.jsonl"), good)
        before = _snapshot(d)
        rc, _text = _run(d)
        after = _snapshot(d)
    assert rc == 0, rc
    assert before == after, "trial.py changed the filesystem under its own root"


def test_main_never_writes_and_returns_zero_on_real_data():
    with tempfile.TemporaryDirectory() as d:
        good = [_rec(f"2026-08-12T10:0{i}:00Z") for i in range(5)]
        _write(os.path.join(d, "s.jsonl"), good)
        before = _snapshot(d)
        argv = sys.argv
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                rc = tr.main(["--root", d, "--days", "30"])
        finally:
            sys.argv = argv
        after = _snapshot(d)
    assert rc == 0, rc
    assert before == after
    assert "Biggest lever" in buf.getvalue()


# --- labels stay separate, never merged or totalled -------------------------

def test_labels_stay_separate_and_no_dollars_shown():
    # Calibrated: replacing the NATIVE line's `ts.human(native)` call with a
    # combined MEASURED+NATIVE total, or adding a "$" figure, makes the
    # dollar-free assertion below go red.
    with tempfile.TemporaryDirectory() as d:
        # enough calls (>=3) and share above 0.30 so first_request_share and
        # prescriptions both come back populated rather than NO DATA.
        recs = [_rec(f"2026-08-12T10:{i:02d}:00Z", inp=5000, w5=0, w1=0,
                     read=100, out=50) for i in range(5)]
        _write(os.path.join(d, "s.jsonl"), recs)
        rc, text = _run(d)
        # The NATIVE figure is the one savings_breakdown computes, never
        # summed with MEASURED totals into a new combined number. Recompute
        # it independently, from the same data, while the sandbox still
        # exists.
        sessions = mt.collect(d, 30)
        sm = mt.summarize(sessions)
        native = ts.savings_breakdown(sm)["saved"]
    assert rc == 0, rc
    assert "$" not in text, "trial.py must never print a dollar figure"
    assert text.count("NATIVE") == 1
    assert text.count("MEASURED") >= 1
    assert ts.human(native) in text


def test_lever_line_present_with_enough_data():
    with tempfile.TemporaryDirectory() as d:
        recs = [_rec(f"2026-08-12T10:{i:02d}:00Z") for i in range(5)]
        _write(os.path.join(d, "s.jsonl"), recs)
        rc, text = _run(d)
    assert rc == 0, rc
    assert "Biggest lever:" in text
    assert "Full plugin" in text
    assert "github.com/khalilmaaouni/token-shield" in text


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
