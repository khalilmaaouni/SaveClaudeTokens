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
    # R7/MAJOR: the review file stores only the reviewed NAMES now, never
    # literal argv (a bundle file holding executable commands is exactly what
    # let a tampered file run something other than what was reviewed).
    # cmd_apply_bundle reconstructs disable/enable commands from those names
    # at apply time instead, so this checks the printed commands (what the
    # founder actually reviews before saying yes) and the stored names.
    with tempfile.TemporaryDirectory() as td:
        real_review_dir = _point_review_dir_at(td)
        real_list = pp.list_plugins
        pp.list_plugins = lambda: [{"id": "demo@market", "enabled": True}]
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = pp.cmd_propose_bundle(["demo@market"], "b1")
            out = buf.getvalue()
            check("cmd_propose_bundle returns success", rc == 0)
            path = pp._bundle_path("b1")
            check("the review file was written", os.path.exists(path))
            with open(path) as f:
                bundle = json.load(f)
            check("the review file stores exactly the reviewed names, never argv",
                  bundle["names"] == ["demo@market"]
                  and "disable_commands" not in bundle
                  and "enable_commands" not in bundle)
            check("the printed disable command names the exact plugin id",
                  "claude plugin disable demo@market" in out)
            check("the printed enable command (the revert) is present too",
                  "claude plugin enable demo@market" in out)
        finally:
            pp.list_plugins = real_list
            optimize.review_dir = real_review_dir


def test_cmd_apply_bundle_ignores_tampered_argv_and_rebuilds_from_names():
    # R7/MAJOR, calibrated: a hand-edited bundle file that stores an
    # unrelated (or malicious) command under a legacy "disable_commands" key
    # must never be run. cmd_apply_bundle only ever reads "names" and rebuilds
    # the command itself.
    with tempfile.TemporaryDirectory() as td:
        real_review_dir = _point_review_dir_at(td)
        real_run = pp.subprocess.run
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            class R:
                returncode = 0
                stderr = ""
            return R()

        pp.subprocess.run = fake_run
        try:
            path = pp._bundle_path("tampered")
            with open(path, "w") as f:
                json.dump({"bundle_id": "tampered", "names": ["x@m"],
                          "disable_commands": [["/bin/sh", "-c", "echo PWNED"]],
                          "enable_commands": [["claude", "plugin", "enable", "x@m"]]}, f)
            rc = pp.cmd_apply_bundle("tampered")
            check("cmd_apply_bundle returns success", rc == 0)
            check("only the command rebuilt from names ran, never the stored argv",
                  calls == [["claude", "plugin", "disable", "x@m"]])
        finally:
            pp.subprocess.run = real_run
            optimize.review_dir = real_review_dir


def test_cmd_propose_bundle_refuses_names_that_fail_the_plugin_id_charset():
    # R7/MAJOR: a hyphen-first or shell-metacharacter name is refused before
    # it can ever become a stored bundle, let alone a subprocess argv.
    with tempfile.TemporaryDirectory() as td:
        real_review_dir = _point_review_dir_at(td)
        real_list = pp.list_plugins
        pp.list_plugins = lambda: [{"id": "--all", "enabled": True}]
        try:
            for bad in ["--all", "-a", "a@m; rm -rf /tmp/x", "a\nb@m"]:
                rc = pp.cmd_propose_bundle([bad], "hostile")
                check(f"cmd_propose_bundle refuses {bad!r}", rc == 2)
                check(f"no bundle file was written for {bad!r}",
                      not os.path.exists(pp._bundle_path("hostile")))
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


def test_verify_bundle_reports_not_ok_when_a_plugin_is_absent_entirely():
    # R6/MAJOR, calibrated red-then-green: before the fix, `plugins.get(n,
    # {}).get("enabled")` on a name absent from the plugin list returned None
    # (falsy), so an absent id fell through to "not enabled" -> ok=True. NO
    # DATA is not disabled-confirmed.
    real_list = pp.list_plugins
    pp.list_plugins = lambda: []
    try:
        ok, report = pp.verify_bundle(["ghost@market"])
        check("an id absent from the plugin list is NOT confirmed disabled", not ok)
        check("the report names the absent id", "ghost@market" in report)
    finally:
        pp.list_plugins = real_list

    pp.list_plugins = lambda: [{"id": "other@market", "enabled": True}]
    try:
        ok2, report2 = pp.verify_bundle(["ghost@market"])
        check("still absent when only an unrelated plugin is listed", not ok2)
    finally:
        pp.list_plugins = real_list


if __name__ == "__main__":
    n = 0
    for name in sorted(dir(sys.modules[__name__])):
        if name.startswith("test_"):
            globals()[name]()
            n += 1
    print(f"\n{n} passed")
