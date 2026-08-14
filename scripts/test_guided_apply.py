#!/usr/bin/env python3
"""Calibrated checks for guided_apply.py, the shared apply contract every
wave R producer (optimize.py's CLAUDE.md diet, plugin_prune.py, memory_trim.py)
runs through. Every case here points ex.EXP_DIR/ex.LEDGER at a temp dir and
stubs ex.cmd_start, so nothing here ever touches the real machine's
~/.claude/token-shield/ (which carries a genuinely open experiment on this
machine, claude-md-diet-v2, per wave R's HARD CONSTRAINT 2)."""
import json
import os
import sys
import tempfile

import experiment as ex
import guided_apply as ga


def check(name, cond):
    print(("ok  " if cond else "FAIL ") + name)
    assert cond, name


def _point_exp_at(td):
    saved = (ex.EXP_DIR, ex.LEDGER)
    ex.EXP_DIR = os.path.join(td, "experiments")
    ex.LEDGER = os.path.join(td, "savings.jsonl")
    os.makedirs(ex.EXP_DIR, exist_ok=True)
    return saved


def _restore_exp(saved):
    ex.EXP_DIR, ex.LEDGER = saved


def _seed_open_baseline(label="open-one", end=100.0):
    with open(os.path.join(ex.EXP_DIR, label + ".json"), "w") as f:
        f.write(json.dumps({"label": label, "cohort_end_ts": end,
                            "started": "2026-08-01T00:00:00"}))


def test_apply_refuses_when_an_experiment_is_open():
    with tempfile.TemporaryDirectory() as td:
        saved = _point_exp_at(td)
        _seed_open_baseline()
        called = []
        rc, msg = ga.apply("t", None, lambda: called.append(True),
                           lambda: (True, "ok"))
        check("mutate_fn is never called while an experiment is open", called == [])
        check("apply refuses with rc 2", rc == 2)
        check("the refusal names the open label", "open-one" in msg)
        _restore_exp(saved)


def test_apply_runs_mutate_then_verify_then_opens_experiment_on_success():
    with tempfile.TemporaryDirectory() as td:
        saved = _point_exp_at(td)
        started = []
        real_cmd_start = ex.cmd_start
        ex.cmd_start = lambda label, root, days, now_ts, treats, metric=None: (
            started.append((label, treats)) or 0)
        try:
            called = []
            rc, msg = ga.apply("my-label", "/some/treated/path",
                               lambda: called.append(True), lambda: (True, "ok"))
            check("mutate_fn ran", called == [True])
            check("apply succeeds with rc 0", rc == 0)
            check("cmd_start was called with the exact label and treats passed in",
                  started == [("my-label", "/some/treated/path")])
        finally:
            ex.cmd_start = real_cmd_start
        _restore_exp(saved)


def test_apply_does_not_open_experiment_on_verify_failure():
    with tempfile.TemporaryDirectory() as td:
        saved = _point_exp_at(td)
        started = []
        real_cmd_start = ex.cmd_start
        ex.cmd_start = lambda label, root, days, now_ts, treats, metric=None: (
            started.append((label, treats)) or 0)
        try:
            called = []
            rc, msg = ga.apply("t", None, lambda: called.append(True),
                               lambda: (False, "bad"))
            check("mutate_fn still ran (the write already happened)", called == [True])
            check("verify failure returns rc 1", rc == 1)
            check("no experiment was opened on a verify failure", started == [])
            check("the message carries the verify report", "bad" in msg)
        finally:
            ex.cmd_start = real_cmd_start
        _restore_exp(saved)


def test_backup_file_matches_optimize_cmd_apply_pattern():
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "CLAUDE.md")
        with open(src, "w") as f:
            f.write("original content\n")
        backup = ga.backup_file(src)
        check("backup path follows the '<path>.bak-<stamp>' naming convention",
              backup.startswith(src + ".bak-"))
        with open(backup) as f:
            backed_up = f.read()
        check("the backup's content equals the original", backed_up == "original content\n")
        with open(src) as f:
            check("backup_file does not modify the source itself",
                  f.read() == "original content\n")


if __name__ == "__main__":
    n = 0
    for name in sorted(dir(sys.modules[__name__])):
        if name.startswith("test_"):
            globals()[name]()
            n += 1
    print(f"\n{n} passed")
