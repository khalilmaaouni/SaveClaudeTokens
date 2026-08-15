#!/usr/bin/env python3
"""Install smoke test: trial.py against a generated fixture corpus, run the
same way a stranger runs it. No framework, no fixtures.

    python3 scripts/test_install_smoke.py

WHY THIS EXISTS. test_trial.py calls tr.run() in process, which proves the
function's logic but never proves the command line a stranger actually
types: the shebang, argument parsing, importing its sibling modules from a
plain `python3 scripts/trial.py --root ... --days ...` invocation, and the
real wall clock they wait through. This is the one test that runs trial.py
as a subprocess.

Drives bench/generate_corpus.py as a subprocess to build the fixture
corpus; this file never imports or edits that script, only invokes it the
same way a person would from the command line.
"""

import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
GENERATE_CORPUS = os.path.join(REPO_ROOT, "bench", "generate_corpus.py")
TRIAL = os.path.join(HERE, "trial.py")


def test_first_screen_under_60_seconds():
    with tempfile.TemporaryDirectory() as d:
        gen = subprocess.run(
            [sys.executable, GENERATE_CORPUS, "--out", d],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        # Calibrated: pointing GENERATE_CORPUS at a path one directory off
        # (a name that does not exist) makes this go red with the real
        # "No such file or directory" from the subprocess, proving the
        # fixture step is actually load-bearing rather than skipped.
        assert gen.returncode == 0, (
            f"fixture corpus generation failed: {gen.stderr}")

        start = time.monotonic()
        trial = subprocess.run(
            [sys.executable, TRIAL, "--root", d, "--days", "30"],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        elapsed = time.monotonic() - start

    # Calibrated: pointing TRIAL at a path with a typo (trial.py -> trialx.py)
    # makes this go red, since python3 exits 2 on a missing file.
    assert trial.returncode == 0, f"trial.py exited {trial.returncode}: {trial.stderr}"

    # Calibrated: replacing `60` with `0` makes this go red on every run,
    # since any real subprocess launch takes measurable wall clock. This is
    # the actual wall clock around the real trial.py run, not a stand-in.
    assert elapsed < 60, (
        f"trial.py took {elapsed:.1f}s against a fresh fixture corpus, "
        f"over the 60 second install-smoke budget")

    text = trial.stdout
    lines = text.splitlines()
    assert lines, "trial.py printed nothing to stdout"

    # Calibrated: changing "MEASURED" to "MEASURD" makes this go red, since
    # every one of trial.py's five hero branches leads with that exact word.
    assert lines[0].startswith("MEASURED"), (
        f"the hero line does not lead with MEASURED: {lines[0]!r}")

    # Calibrated: changing "Biggest lever:" to "Biggest lever" (dropping the
    # colon trial.py always prints) makes this go red.
    assert "Biggest lever:" in text, "the biggest-lever hero line is missing"

    # Calibrated: changing "Full plugin" to "Full pluginx" makes this go red.
    assert "Full plugin" in text, "the follow-on command line is missing"
    assert "github.com/khalilmaaouni/token-shield" in text, (
        "the follow-on command line lost its repo pointer")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
