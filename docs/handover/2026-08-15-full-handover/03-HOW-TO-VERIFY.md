# How to verify, and the trap in doing it the documented way

## The command that actually covers the repository

Run this before you believe anything, and again after your last edit. From the
repository root:

```bash
rm -rf scripts/__pycache__ scripts/companions/__pycache__
python3 scripts/check_py311.py
cd scripts && python3 test_measure_tokens.py && python3 test_reconcile.py && python3 test_tools.py && python3 test_pricing.py && python3 test_experiment.py && python3 test_guided_apply.py && python3 test_optimize.py && python3 test_plugin_prune.py && python3 test_memory_trim.py && python3 test_profile.py && python3 test_advisor.py && python3 test_report.py && python3 test_detail_report.py && python3 test_discover_companions.py && python3 test_doctor.py && python3 test_companions.py && python3 test_deep_advisor.py && python3 test_share_card.py && python3 test_signals.py && python3 test_fleet.py && python3 test_trial.py && python3 test_fleet_dashboard.py && python3 test_architecture.py
```

Expected, as of `bafd02a`: **525 checks green across 23 suites, exit 0**, and
`check_py311: clean, 56 file(s)`.

## The two steps that line does NOT run, and how they bit

CI runs more than the documented command, and `CLAUDE.md` says so. From the
repository root:

```bash
python3 -m pip install ./mcp-server && cd mcp-server && python3 test_mcp_server.py
```

```bash
python3 bench/test_bench.py && python3 bench/generate_corpus.py --out /tmp/bench-corpus && python3 bench/run_benchmark.py --corpus /tmp/bench-corpus
```

Expected: MCP server **13 passed**; bench self-check **3 passed**; benchmark
**ALL PASS (93 checks)**.

**Why this matters, from a real failure in the last session.** A refactor moved
`savings_breakdown` and `prescriptions` out of `token_shield` into a new
`metrics` module. The documented suite came back 525 green. CI went red:
`mcp-server/src/token_shield_mcp/tools/get_summary.py` imports those same
symbols and is not covered by the documented line.

The lesson is not "run more tests". It is that **"the documented suite is
green" is a true statement and not a sufficient safety claim for a change that
moves symbols other packages import.** Ask what else imports what you touched.

If `pip install ./mcp-server` refuses with a PEP 668 externally-managed error,
that is this machine's Python, not your change. There is a virtual environment
at `~/.token-shield/mcp-venv` for MCP dependency work.

## Clear the bytecode cache first. Always.

`rm -rf scripts/__pycache__ scripts/companions/__pycache__` is the first line
of the command above and it is not decoration.

Python validates a cached `.pyc` against the source file's **modification time
and size only**. This repository's practice is to prove a test real by
reinjecting the defect and reverting it. A same-length edit reverted inside one
second is invisible to that check, so the interpreter keeps serving the code
you just deleted.

It has already produced a false failure here: `grep` showed the correct rule on
disk while `import` gave the wrong one, and the `shasum` proof of the restore
was true and did not help, because it proves the **file**, not what Python
**loaded**.

## Calibrating a test, which is required, not optional

A test born green proves nothing. Every fix ships with a test proven red first.
Two acceptable ways:

1. **Write the test before the fix.** Run it, quote the red output, then fix.
2. **Reinject afterwards.** Put the defect back, watch the right check go red
   with a message that names the defect, restore the file, and prove the
   restore with a digest.

Both end with clearing `__pycache__`.

Watch for two traps that both occurred in the last session:

- **A test that goes red for the wrong reason.** One new check crashed with a
  `ValueError` inside its own message-parsing rather than detecting anything.
  It was "red", and it was not calibrated. Read the failure message, not just
  the exit code.
- **A comparison that does not normalise what it does not mean to compare.** A
  calibration script compared two outputs raw, including a temp directory path
  that differs every run, and printed a conclusion directly contradicting its
  own measurement.

## The push gates, all of which must print nothing

Over the whole pushed range, never the net diff, so a secret added and then
deleted is still caught:

```bash
range=origin/main..HEAD
git log -p --text "$range" | grep -naE 'sk[-_][A-Za-z0-9_-]{16,}|gh[oprsu]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|BEGIN [A-Z ]*PRIVATE KEY|[Bb]earer [A-Za-z0-9._+/=-]{16,}'
git log -p --text "$range" | grep -inaE '(password|passwd|api[_-]?key|secret|token)[[:space:]]*[:=][[:space:]]*[^[:space:]]{6,}'
git log --format=%B "$range" | grep -niE 'Co-Authored-By: (Claude|Opus|Sonnet|Haiku|Fable)|noreply@anthropic|Generated with \[Claude Code\]'
git log --format=%B "$range" | perl -CSD -ne 'print if /\x{2014}|\x{2013}/'
git log -p --text "$range" | perl -CSD -ne 'print if /^\+/ && /\x{2014}|\x{2013}/'
```

Use `perl` for the dash scan, not `grep -P`: this machine's BSD grep refuses
`-P` with "invalid option", and **an errored scan prints nothing and reads as
clean**.

## Verifying a push landed

Three ways, because a screenshot and a clean `git status` both prove nothing:

```bash
git fetch origin
git rev-parse HEAD; git rev-parse @{u}; git ls-remote --heads origin <branch>
```

All three must be the same SHA.

## Verifying CI on the right commit

Check the check runs for the **pull request's current head**, not an earlier
commit you happened to verify. In the last session a merge was recommended on
the strength of CI that had passed two commits earlier.

```bash
gh api repos/khalilmaaouni/token-shield/commits/<sha>/check-runs -q '.check_runs[] | "\(.name) \(.status) \(.conclusion)"'
```

And when you add a suite, grep the CI log to confirm it actually ran. This
repository came within one merge of silently dropping a suite from CI.
