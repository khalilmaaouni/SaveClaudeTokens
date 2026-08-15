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
    """The fixture must REACH the parser, or this tests nothing.

    It used to be `["{}", '{"no": "usage here"}']`, and neither line ever got
    parsed: trial.py skips any line not containing the exact substring
    `"usage"` (with the closing quote), and `{"no": "usage here"}` has
    `"usage here"`, so the quote falls in the wrong place and the gate drops
    it. Both lines were discarded before any usage handling ran, which made
    this an exact duplicate of test_no_data_when_root_empty above it while
    reading like coverage of a different path.

    The gate is asserted here rather than assumed, so a future change to that
    substring cannot quietly hollow this test out again."""
    parsed_but_empty = '{"message": {"usage": {}}, "timestamp": "2026-08-12T10:00:00Z"}'
    assert '"usage"' in parsed_but_empty, (
        "the fixture must pass trial.py's own line gate, or it is never parsed")

    with tempfile.TemporaryDirectory() as d:
        _write(os.path.join(d, "s.jsonl"), [parsed_but_empty])
        rc, text = _run(d)
    assert rc == 0, rc
    assert "NO DATA" in text

    # Control, so the NO DATA above is known to come from an empty usage
    # object and not from the file being ignored for some other reason: the
    # same shape carrying real counters does NOT say NO DATA.
    with tempfile.TemporaryDirectory() as d:
        _write(os.path.join(d, "s.jsonl"), [_rec(f"2026-08-12T10:0{i}:00Z") for i in range(5)])
        rc2, text2 = _run(d)
    assert rc2 == 0, rc2
    assert "Biggest lever" in text2, (
        "the control fixture produced no reading, so the NO DATA above proves nothing")


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
    # WHAT THIS MISSED, and why the runtime guard below it exists. The list
    # was ('"w")', "'w')", '"w+"', os.makedirs, os.remove, os.unlink,
    # shutil., os.mkdir), which reads as thorough and is not: append mode
    # writes, Path.write_text and write_bytes, os.rename and os.replace, and
    # a plain binary "wb" all write to disk and none of them appear in it. A
    # source scan can only ever catch the spellings someone thought of, which
    # is why it is the cheap first line here and not the proof.
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "trial.py")).read()
    forbidden = ('"w")', "'w')", '"w+"', '"wb"', "'wb'", '"a")', "'a')",
                 '"ab"', '"x")', "write_text", "write_bytes",
                 "os.makedirs", "os.remove", "os.unlink", "os.rename",
                 "os.replace", "os.rmdir", "os.removedirs", "shutil.",
                 "os.mkdir")
    hits = [f for f in forbidden if f in src]
    assert not hits, f"trial.py source contains write/delete calls: {hits}"


def test_the_first_screen_is_readable_by_someone_who_has_never_seen_it():
    """The trial is the FIRST thing a stranger runs, before they have any
    reason to trust this project. Measured on real data before this landed:
    21 seconds of complete silence, then a screen that printed the same
    quantity two ways and led every line with the word that means least.

    Four things, each of which was observed rather than imagined:

    1. `0.365 share of everything read` on line three, and `36% of everything
       a session reads` seven lines later. One number, two formats, and only
       the second is readable. A reader cannot tell they are the same fact.
    2. `3,704 transcripts (265 sessions)` leads with transcripts. A person
       has sessions; transcripts are the files those sessions happen to be
       stored in.
    3. The labels MEASURED, NATIVE and ESTIMATED carry the whole honesty
       claim of this product and appeared with no legend anywhere on screen.
       The module docstring defines them, which nobody reading a terminal
       has open.
    4. Silence. `cli.py summary` already prints a progress line to stderr
       before its scan; the trial, which is the screen that most needs one,
       printed nothing at all. Covered by its own test below.
    """
    with tempfile.TemporaryDirectory() as d:
        _write(os.path.join(d, "s.jsonl"),
               [_rec(f"2026-08-12T10:0{i}:00Z") for i in range(5)])
        _rc, text = _run(d)

    lines = text.splitlines()
    counts = [ln for ln in lines if "sessions" in ln and "MEASURED" in ln]
    assert counts, "no counts line found"
    counts = counts[0]
    assert counts.index("session") < counts.index("transcript"), (
        f"the counts line still leads with transcripts: {counts!r}")

    # One quantity, one format. A bare 0.xxx share must not appear beside a
    # percentage of the same thing.
    assert "share of everything read" not in text, (
        "the startup floor share is still printed as a bare decimal share")
    floor_line = [ln for ln in lines if "startup floor" in ln][0]
    assert "%" in floor_line, f"the floor share is not a percentage: {floor_line!r}"

    # The labels that carry the honesty claim explain themselves on screen.
    assert "MEASURED" in text and "NATIVE" in text and "ESTIMATED" in text
    legend = [ln for ln in lines if "MEASURED" in ln and "ESTIMATED" in ln
              and "NATIVE" in ln]
    assert legend, "the three confidence labels appear with no legend on screen"


def test_the_trial_says_it_is_working_before_it_goes_quiet():
    """Measured at 21 seconds of silence on a real machine, and reported at 36
    on a larger history. A first-time reader with no reason to trust this yet
    watches a blank terminal and concludes it hung.

    The line goes to stderr, not stdout, so anything piping the trial's
    reading stays clean. That is the same choice cli.py summary already made,
    and this is that fix applied to the screen that needed it more."""
    import contextlib as _ctx
    with tempfile.TemporaryDirectory() as d:
        _write(os.path.join(d, "s.jsonl"),
               [_rec(f"2026-08-12T10:0{i}:00Z") for i in range(5)])
        errbuf = io.StringIO()
        outbuf = io.StringIO()
        with _ctx.redirect_stderr(errbuf):
            rc = tr.run(d, 30, out=outbuf)

    assert rc == 0, rc
    progress = errbuf.getvalue()
    assert progress.strip(), "the trial still starts with no sign of life at all"
    assert "read" in progress.lower(), (
        f"the progress line does not say what it is doing: {progress!r}")
    assert "$" not in progress and "MEASURED" not in progress, (
        "the progress line must not carry findings; stdout is where the reading goes")
    assert "MEASURED" in outbuf.getvalue(), "the reading itself must still reach stdout"


def test_no_write_anywhere_on_the_filesystem_not_just_under_its_own_root():
    """The proof the two tests above only gesture at.

    The source scan catches spellings someone listed. The before/after
    snapshot catches writes UNDER THE SANDBOX ROOT only, so a write to
    ~/.token-shield, to a temp directory, or to the repository itself was
    invisible to both, and that is exactly where a real accidental write
    would go: trial.py's whole promise is that a stranger can run it before
    trusting this project with anything.

    So the write primitives themselves are taken away for the duration of
    the run. Reading is untouched, and anything that mutates raises with the
    call named."""
    import builtins
    import shutil as _shutil

    real_open = builtins.open
    attempts = []

    def _read_only_open(file, mode="r", *a, **k):
        if any(ch in mode for ch in "wax+"):
            attempts.append(f"open({file!r}, {mode!r})")
            raise AssertionError(f"trial.py opened {file!r} for writing (mode {mode!r})")
        return real_open(file, mode, *a, **k)

    def _blocked(name):
        def _refuse(*a, **k):
            attempts.append(f"{name}{a[:2]}")
            raise AssertionError(f"trial.py called {name}, which mutates the filesystem")
        return _refuse

    patched = {
        (os, "rename"): _blocked("os.rename"),
        (os, "replace"): _blocked("os.replace"),
        (os, "remove"): _blocked("os.remove"),
        (os, "unlink"): _blocked("os.unlink"),
        (os, "mkdir"): _blocked("os.mkdir"),
        (os, "makedirs"): _blocked("os.makedirs"),
        (os, "rmdir"): _blocked("os.rmdir"),
        (_shutil, "rmtree"): _blocked("shutil.rmtree"),
        (_shutil, "copy"): _blocked("shutil.copy"),
        (_shutil, "move"): _blocked("shutil.move"),
    }
    saved = {(obj, name): getattr(obj, name) for obj, name in patched}

    with tempfile.TemporaryDirectory() as d:
        _write(os.path.join(d, "s.jsonl"),
               [_rec(f"2026-08-12T10:0{i}:00Z") for i in range(5)])
        # The fixture is written BEFORE the primitives are taken away, so the
        # only writer under test is trial.py itself.
        builtins.open = _read_only_open
        for (obj, name), fn in patched.items():
            setattr(obj, name, fn)
        try:
            buf = io.StringIO()
            rc = tr.run(d, 30, out=buf)
        finally:
            builtins.open = real_open
            for (obj, name), fn in saved.items():
                setattr(obj, name, fn)

    assert not attempts, f"trial.py tried to write: {attempts}"
    assert rc == 0, rc
    assert "Biggest lever" in buf.getvalue(), (
        "the run produced no reading, so proving it wrote nothing proves nothing")


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
    # SHARPENED, not loosened. This was `text.count("NATIVE") == 1`, which
    # broke when the screen gained a legend defining the three labels for a
    # first-time reader. What the assertion is actually for is that NATIVE
    # labels exactly ONE figure and is never merged with a MEASURED total, so
    # it now counts label positions rather than occurrences of the word: the
    # legend is prose about the labels, not a labelled number.
    labelled = [ln for ln in text.splitlines() if ln.startswith("NATIVE")]
    assert len(labelled) == 1, f"NATIVE labels {len(labelled)} figures, expected 1"
    legend = [ln for ln in text.splitlines()
              if "MEASURED" in ln and "NATIVE" in ln and "ESTIMATED" in ln]
    assert len(legend) == 1, "the legend defining the labels should appear exactly once"
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


def test_follow_on_command_points_at_a_cli_that_actually_exists():
    """The README tells a stranger to clone and run the trial from the
    directory ABOVE the checkout, so a hardcoded "scripts/cli.py" prints a
    command that fails from the only place they could be standing. The
    printed path is resolved from this file's real location instead, so
    whatever it names has to exist on disk from the caller's directory."""
    with tempfile.TemporaryDirectory() as d:
        recs = [_rec(f"2026-08-12T10:{i:02d}:00Z") for i in range(5)]
        _write(os.path.join(d, "s.jsonl"), recs)
        rc, text = _run(d)
    assert rc == 0, rc
    line = [ln for ln in text.splitlines() if "Full plugin" in ln]
    assert len(line) == 1, line
    printed = line[0].split("python3 ", 1)[1].split(" summary", 1)[0]
    assert os.path.isfile(printed), (
        f"trial.py printed 'python3 {printed} summary' but no such file "
        f"exists from the caller's working directory")


def test_the_trials_native_line_discloses_writes_it_could_not_price():
    """The trial is the stranger's first screen, and its NATIVE line is the
    row attributed to Anthropic rather than claimed by this tool.

    A transcript whose usage carries only the FLAT cache_creation counter and
    no nested cache_creation object has an unknown TTL class, so those writes
    cannot be priced (measure_tokens.split_writes puts them in write_unsplit
    and refuses to normalize them). They used to be charged nothing at all,
    which made this headline largest exactly where the evidence was weakest.
    Now they are charged at the most expensive rate AND said out loud.

    Calibrated by reinjection: removing ts.native_note(sv) from the NATIVE
    line in trial.py leaves the number looking identical to a fully priced
    one, and the "no TTL split" assertion fails.
    """
    def _flat(ts_str, inp=100, write=0, read=900, out=50):
        """A record with the flat write counter and NO nested split, which is
        the schema variant this defect lives in."""
        return json.dumps({
            "isSidechain": False,
            "timestamp": ts_str,
            "message": {"model": "claude-x", "usage": {
                "input_tokens": inp,
                "cache_creation_input_tokens": write,
                "cache_read_input_tokens": read,
                "output_tokens": out,
            }},
        })

    with tempfile.TemporaryDirectory() as d:
        _write(os.path.join(d, "flat.jsonl"), [
            _flat(f"2026-08-12T10:0{i}:00Z", inp=90_000, write=2_000_000,
                  read=9_000_000) for i in range(5)
        ])
        rc, text = _run(d)
    assert rc == 0, rc
    native = [ln for ln in text.splitlines() if ln.startswith("NATIVE")]
    assert len(native) == 1, native
    assert "no TTL split" in native[0], native[0]
    assert "lower bound" in native[0], native[0]


def test_the_trial_agrees_with_the_command_it_recommends_about_the_headline():
    """The trial's last line sends a stranger straight to `cli.py summary`, so
    the two screens they see inside one minute must name the same "how much you
    could still cut" figure. Both build it from the same prescriptions over the
    same data.

    They diverged: trial.py took the largest lever while cli.py summed every
    lever, so on real data here the trial said 218.3M and the very next command
    said 230M, in the same words. Summing overlapping levers double counts the
    same startup floor, so the largest lever is the honest reduction and both
    sides take it.

    The fixture deliberately produces MORE THAN ONE prescription, because with
    a single lever max and sum are equal and the contract cannot fail. Its
    token counts are large so that both surfaces land in millions: cli.py
    rounds to whole millions, so a fixture whose levers are thousands apart
    would round both sides to the same "0M" and pass while broken.

    Tolerance is half a million token-units, which is cli.py's own rounding.
    Any gap wider than the coarser format can explain is a real disagreement.
    """
    import cli

    # The magnitude is large on purpose. cli.py rounds to whole millions, so
    # the two levers have to differ by several million before the gap survives
    # that rounding; a fixture whose levers differ by thousands passes while
    # broken. Session count stays at five because the startup floor lever is
    # triggered by the median SHARE, so adding sessions removes the second
    # lever instead of enlarging it.
    big = 30_000_000
    with tempfile.TemporaryDirectory() as d:
        # Session one switches model mid-session, which is its own lever.
        _write(os.path.join(d, "switch.jsonl"), [
            _rec("2026-08-12T10:00:00Z", model="claude-a", inp=big, read=200),
            _rec("2026-08-12T10:05:00Z", model="claude-b", inp=400, read=big),
            _rec("2026-08-12T10:09:00Z", model="claude-b", inp=400, read=big),
        ])
        # Four more single-model sessions, each paying a large startup floor,
        # so a second lever is detected alongside the switch.
        for i in range(4):
            _write(os.path.join(d, f"s{i}.jsonl"), [
                _rec(f"2026-08-12T1{i}:00:00Z", inp=big, read=200, out=3_000_000),
                _rec(f"2026-08-12T1{i}:06:00Z", inp=400, read=big, out=3_000_000),
            ])

        sm = mt.summarize(mt.collect(d, 30))
        rx = ts.prescriptions(sm, mt.collect(d, 30))
        assert len(rx) > 1, (
            "fixture produced only one lever, so this contract cannot fail and "
            "the test would prove nothing")

        _, trial_text = _run(d)

        buf = io.StringIO()
        real_root = cli.ROOT
        cli.ROOT = d
        try:
            with contextlib.redirect_stdout(buf):
                cli.summary(30)
        finally:
            cli.ROOT = real_root
        cli_text = buf.getvalue()

    scale = {"K": 1e3, "M": 1e6, "B": 1e9}

    def _headline(text, marker):
        """The number each surface prints, normalised out of its own unit
        suffix so a K/M/B difference can never be read as agreement."""
        # startswith, not `in`: a headline is a line the label OPENS. Matching
        # anywhere also caught the legend that defines the three labels for a
        # first-time reader, which mentions every marker and carries no figure.
        # startswith after strip, not `in`: a headline is a line the label
        # OPENS (cli indents its own by two spaces, the trial does not).
        # Matching anywhere also caught the legend that defines the three
        # labels for a first-time reader, which mentions every marker and
        # carries no figure of its own.
        line = [ln for ln in text.splitlines() if ln.strip().startswith(marker)]
        assert len(line) == 1, (marker, line)
        blob = line[0].split(marker, 1)[1].strip().split(" ", 1)[0]
        assert blob[-1] in scale, (marker, blob)
        return float(blob[:-1]) * scale[blob[-1]]

    trial_v = _headline(trial_text, "ESTIMATED")
    cli_v = _headline(cli_text, "OPPORTUNITY")
    assert abs(trial_v - cli_v) <= 500_000, (
        f"the trial says {trial_v:,.0f} and the command it recommends says "
        f"{cli_v:,.0f} for the same data, in the same words")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
