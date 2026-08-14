#!/usr/bin/env python3
"""Calibrated checks for plugin_prune.py. subprocess.run and list_plugins are
always monkeypatched: no test here ever invokes the real `claude` binary, and
optimize.review_dir is repointed at a temp directory so no test here ever
writes into the real ~/.token-shield/optimize/ review directory either."""
import contextlib
import io
import json
import os
import sys
import tempfile

import optimize
import plugin_prune as pp


def check(name, cond):
    print(("ok  " if cond else "FAIL ") + name)
    assert cond, name


def _point_review_dir_at(td):
    real = optimize.review_dir
    d = os.path.join(td, "optimize")
    os.makedirs(d, exist_ok=True)
    optimize.review_dir = lambda: d
    return real


def test_cmd_propose_bundle_writes_the_review_file_with_both_commands():
    with tempfile.TemporaryDirectory() as td:
        real_review_dir = _point_review_dir_at(td)
        real_list = pp.list_plugins
        pp.list_plugins = lambda: [{"id": "demo@market", "enabled": True}]
        try:
            rc = pp.cmd_propose_bundle(["demo@market"], "b1")
            check("cmd_propose_bundle returns success", rc == 0)
            path = pp._bundle_path("b1")
            check("the review file was written", os.path.exists(path))
            with open(path) as f:
                bundle = json.load(f)
            check("the disable command names the exact plugin id",
                  bundle["disable_commands"] ==
                  [["claude", "plugin", "disable", "demo@market"]])
            check("the enable command (the revert) is present too",
                  bundle["enable_commands"] ==
                  [["claude", "plugin", "enable", "demo@market"]])
        finally:
            pp.list_plugins = real_list
            optimize.review_dir = real_review_dir


def test_cmd_apply_bundle_disables_every_named_plugin_and_prints_every_revert():
    with tempfile.TemporaryDirectory() as td:
        real_review_dir = _point_review_dir_at(td)
        real_list = pp.list_plugins
        real_run = pp.subprocess.run
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            class R:
                returncode = 0
                stderr = ""
            return R()

        pp.subprocess.run = fake_run
        pp.list_plugins = lambda: [{"id": "a@m", "enabled": True},
                                   {"id": "b@m", "enabled": True}]
        try:
            pp.cmd_propose_bundle(["a@m", "b@m"], "b2")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = pp.cmd_apply_bundle("b2")
            out = buf.getvalue()
            check("cmd_apply_bundle returns success", rc == 0)
            check("disable ran for every named plugin, in order",
                  calls == [["claude", "plugin", "disable", "a@m"],
                           ["claude", "plugin", "disable", "b@m"]])
            check("every matching enable (revert) command is printed",
                  "claude plugin enable a@m" in out and "claude plugin enable b@m" in out)
        finally:
            pp.subprocess.run = real_run
            pp.list_plugins = real_list
            optimize.review_dir = real_review_dir


def test_verify_bundle_reports_not_ok_when_a_plugin_is_still_enabled():
    real_list = pp.list_plugins
    pp.list_plugins = lambda: [{"id": "a@m", "enabled": False},
                               {"id": "b@m", "enabled": True}]
    try:
        ok, report = pp.verify_bundle(["a@m", "b@m"])
        check("verify_bundle reports ok=False when one named plugin is still enabled",
              not ok)
        check("the report names the still-enabled plugin", "b@m" in report)
        ok2, report2 = pp.verify_bundle(["a@m"])
        check("verify_bundle reports ok=True once every named plugin is disabled", ok2)
    finally:
        pp.list_plugins = real_list


if __name__ == "__main__":
    n = 0
    for name in sorted(dir(sys.modules[__name__])):
        if name.startswith("test_"):
            globals()[name]()
            n += 1
    print(f"\n{n} passed")
