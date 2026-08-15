#!/usr/bin/env python3
"""Install smoke test: trial.py against a generated fixture corpus, run the
same way a stranger runs it. No framework, no fixtures.

    python3 scripts/test_install_smoke.py

WHY THIS EXISTS. test_trial.py calls tr.run() in process, which proves the
function's logic but never proves the command line a stranger actually
types: argument parsing, importing its sibling modules from a plain
`python3 scripts/trial.py --root ... --days ...` invocation, the real wall
clock they wait through, and the promise at trial.py line 12 that it writes
nothing anywhere. That last one cannot be proven in process without
monkeypatching the very thing under test. This is the one test that runs
trial.py as a subprocess.

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

# The first screen budget from the plan. One constant, used both as the
# subprocess timeout and as the assertion bound, so the two cannot drift
# apart into a budget that is enforced in one place and not the other.
BUDGET_SECONDS = 60
# The fixture build is setup, not the thing under budget. It gets its own
# ceiling only so a wedged generator fails this suite instead of hanging
# the CI job forever.
GENERATE_CEILING_SECONDS = 120


def test_first_screen_under_60_seconds():
    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as home:
        try:
            gen = subprocess.run(
                [sys.executable, GENERATE_CORPUS, "--out", d],
                capture_output=True, text=True, cwd=REPO_ROOT,
                timeout=GENERATE_CEILING_SECONDS,
            )
        except subprocess.TimeoutExpired:
            raise AssertionError(
                f"the fixture corpus generator did not finish within "
                f"{GENERATE_CEILING_SECONDS} seconds")
        # Calibrated: pointing GENERATE_CORPUS at a path one directory off
        # (a name that does not exist) makes this go red with the real
        # "No such file or directory" from the subprocess, proving the
        # fixture step is actually load-bearing rather than skipped.
        assert gen.returncode == 0, (
            f"fixture corpus generation failed: {gen.stderr}")

        # HOME is redirected at an empty temporary directory for two
        # reasons. It stops the developer's real ~/.claude and
        # ~/.token-shield from leaking into a run that is supposed to see
        # only its fixture, and it turns trial.py's own headline promise
        # (line 12, "it writes nothing anywhere") into something this suite
        # can actually check, which no in-process test can do without
        # monkeypatching the thing under test.
        env = dict(os.environ, HOME=home)
        corpus_before = sorted(os.listdir(d))

        start = time.monotonic()
        try:
            trial = subprocess.run(
                [sys.executable, TRIAL, "--root", d, "--days", "30"],
                capture_output=True, text=True, cwd=REPO_ROOT,
                env=env, timeout=BUDGET_SECONDS,
            )
        except subprocess.TimeoutExpired:
            # Without this the budget below is unenforceable: a wedged
            # trial.py is exactly the failure a 60 second budget exists to
            # catch, and an untimed subprocess.run would block CI for hours
            # rather than going red, because `elapsed` is only computed
            # once the process has already exited.
            raise AssertionError(
                f"trial.py did not finish within the {BUDGET_SECONDS} second "
                "install smoke budget, so the first screen is over budget")
        elapsed = time.monotonic() - start

        wrote_into_home = sorted(os.listdir(home))
        corpus_after = sorted(os.listdir(d))

    # Calibrated: pointing TRIAL at a path with a typo (trial.py -> trialx.py)
    # makes this go red, since python3 exits 2 on a missing file.
    assert trial.returncode == 0, f"trial.py exited {trial.returncode}: {trial.stderr}"

    # Calibrated: replacing BUDGET_SECONDS with 0 makes this go red on every
    # run, since any real subprocess launch takes measurable wall clock. This
    # is the actual wall clock around the real trial.py run, not a stand-in.
    # It is the slow-but-finishing half of the budget; the timeout above is
    # the never-finishing half. Neither one covers the other.
    assert elapsed < BUDGET_SECONDS, (
        f"trial.py took {elapsed:.1f}s against a fresh fixture corpus, "
        f"over the {BUDGET_SECONDS} second install-smoke budget")

    # trial.py line 12 promises it writes nothing anywhere. This checks the
    # part of that promise a user would actually notice: with HOME pointed at
    # an empty directory, any dotfile, cache or config trial.py drops under the
    # home directory lands here where it can be seen.
    #
    # Scope, stated rather than implied, because the promise is broader than
    # the check. This does NOT prove trial.py writes nothing anywhere. Two
    # writes escape it by construction: the interpreter's own bytecode cache
    # under scripts/__pycache__, which Python creates on import and trial.py
    # does not control, and any write to an absolute path outside both HOME and
    # the corpus. Closing those would need a filesystem sandbox, which is a
    # larger tool than this budget guard deserves.
    #
    # Calibrated: adding a single
    # open(os.path.join(os.path.expanduser("~"), ".probe"), "w") to trial.py
    # makes this go red naming .probe, then reverted.
    assert wrote_into_home == [], (
        f"trial.py writes nothing anywhere, but it created {wrote_into_home} "
        f"under HOME")
    assert corpus_after == corpus_before, (
        f"trial.py modified the corpus it was pointed at: "
        f"{corpus_before} became {corpus_after}")

    text = trial.stdout
    lines = text.splitlines()
    assert lines, "trial.py printed nothing to stdout"

    # This one is deliberately weak and is documented as weak rather than
    # dressed up. All five of trial.py's hero branches lead with MEASURED, so
    # this cannot tell them apart; what it does catch is the two NO DATA early
    # returns above the hero block (trial.py lines 57 and 74), which is the
    # real regression: a first screen that degraded to NO DATA against a
    # corpus that plainly has usage in it. test_trial.py line 575 carries the
    # stronger in-process version that also checks the number itself.
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
