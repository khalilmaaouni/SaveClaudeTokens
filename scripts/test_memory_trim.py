#!/usr/bin/env python3
"""Calibrated checks for memory_trim.py. Every case that touches
optimize.review_dir() repoints it at a temp directory first, so no test here
ever writes into the real ~/.token-shield/optimize/ review directory."""
import contextlib
import io
import os
import sys
import tempfile

import memory_trim as mtrim
import optimize


def check(name, cond):
    print(("ok  " if cond else "FAIL ") + name)
    assert cond, name


def _point_review_dir_at(td):
    real = optimize.review_dir
    d = os.path.join(td, "optimize")
    os.makedirs(d, exist_ok=True)
    optimize.review_dir = lambda: d
    return real


def _many_bullets(n):
    return "\n".join(
        f"- [Item {i}](item-{i}.md) - a memory pointer line long enough to count."
        for i in range(n)) + "\n"


def test_propose_trim_within_limit_returns_none_and_cmd_propose_reports_no_data():
    with tempfile.TemporaryDirectory() as td:
        real_review_dir = _point_review_dir_at(td)
        try:
            path = os.path.join(td, "MEMORY.md")
            with open(path, "w") as f:
                f.write(_many_bullets(20))
            check("propose_trim returns None when the file already fits",
                  mtrim.propose_trim(path) is None)

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = mtrim.cmd_propose(path)
            check("cmd_propose exits 0 when there is nothing to trim", rc == 0)
            check("cmd_propose reports NO DATA when there is nothing to trim",
                  "NO DATA" in buf.getvalue())
        finally:
            optimize.review_dir = real_review_dir


def test_propose_trim_moves_bullets_verbatim_never_dropped():
    path_holder = {}
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "MEMORY.md")
        with open(path, "w") as f:
            f.write(_many_bullets(260))
        result = mtrim.propose_trim(path)
        check("propose_trim returns a result when the file exceeds the limit",
              result is not None)
        new_text, archive_text, moved, before, after = result
        check("at least one bullet was moved", len(moved) > 0)
        check("after fits the load limit", after <= 200)
        for bullet in moved:
            check(f"moved bullet appears verbatim in the archive: {bullet[:40]!r}",
                  bullet in archive_text)
            check(f"moved bullet is entirely gone from the new index: {bullet[:40]!r}",
                  bullet not in new_text)


def test_cmd_apply_never_writes_the_source_without_a_prior_propose():
    # Mirrors optimize.py's test_cmd_propose_never_writes_the_source_claude_md:
    # the never-lose-work contract applied to cmd_apply's NO DATA path.
    with tempfile.TemporaryDirectory() as td:
        real_review_dir = _point_review_dir_at(td)
        try:
            src = os.path.join(td, "MEMORY.md")
            original = _many_bullets(260)
            with open(src, "w") as f:
                f.write(original)
            before = open(src, "rb").read()
            rc = mtrim.cmd_apply()
            check("cmd_apply refuses with NO DATA when nothing was proposed", rc == 2)
            after = open(src, "rb").read()
            check("cmd_apply never writes to the source MEMORY.md without a prior propose",
                  before == after)
        finally:
            optimize.review_dir = real_review_dir


if __name__ == "__main__":
    n = 0
    for name in sorted(dir(sys.modules[__name__])):
        if name.startswith("test_"):
            globals()[name]()
            n += 1
    print(f"\n{n} passed")
