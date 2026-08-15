#!/usr/bin/env python3
"""Calibrated checks for memory_trim.py. Every case that touches
optimize.review_dir() repoints it at a temp directory first, so no test here
ever writes into the real ~/.token-shield/optimize/ review directory.
Every case that reaches a real backup (cmd_apply's success path) also points
guided_apply.MUTATIONS_LOG at a temp path first (see
_point_journal_at/_restore_journal, mirrored from test_guided_apply.py), so
nothing here ever touches the real machine's ~/.token-shield/mutations.jsonl."""
import contextlib
import io
import json
import os
import sys
import tempfile

import context_lint
import guided_apply
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


def _point_journal_at(td):
    saved = guided_apply.MUTATIONS_LOG
    guided_apply.MUTATIONS_LOG = os.path.join(td, "mutations.jsonl")
    return saved


def _restore_journal(saved):
    guided_apply.MUTATIONS_LOG = saved


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


def test_cmd_guided_apply_trim_refuses_when_named_file_differs_from_proposal():
    # R2/R10/CRITICAL, mirrors the same fix in optimize.py: the guided apply
    # must refuse, naming both paths, when the file named at apply time is
    # not the file the stored proposal points at.
    with tempfile.TemporaryDirectory() as td:
        real_review_dir = _point_review_dir_at(td)
        try:
            a = os.path.join(td, "A-MEMORY.md")
            b = os.path.join(td, "B-MEMORY.md")
            with open(a, "w") as f:
                f.write(_many_bullets(260))
            with open(b, "w") as f:
                f.write(_many_bullets(5))
            mtrim.cmd_propose(a)
            before_a = open(a, "rb").read()
            before_b = open(b, "rb").read()
            rc = mtrim.cmd_guided_apply_trim(b)
            check("cmd_guided_apply_trim refuses with rc 2 on a target mismatch",
                  rc == 2)
            check("A (the proposal's real target) is never touched",
                  open(a, "rb").read() == before_a)
            check("B (named on the command line) is never touched either",
                  open(b, "rb").read() == before_b)
        finally:
            optimize.review_dir = real_review_dir


def test_propose_trim_keeps_frontmatter_and_comments_in_the_index_never_archived():
    # M4/MAJOR, calibrated red-then-green: propose_trim used to build the new
    # index from context_lint.loaded_content(raw), which strips YAML
    # frontmatter and block HTML comments before propose_trim ever sees the
    # lines. That silently dropped both from the RESULT entirely: gone from
    # the new index, and never archived either (moved[] never contained
    # them, since they never matched BULLET). Trim moves bullet lines only;
    # frontmatter and comments must stay in the index exactly where they were.
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "MEMORY.md")
        front = "---\ntitle: project memory\nowner: khalil\n---\n"
        comment = "<!-- generated by Claude Code, do not hand edit -->\n"
        with open(path, "w") as f:
            f.write(front + comment + _many_bullets(260))
        result = mtrim.propose_trim(path)
        check("propose_trim returns a result when the file exceeds the limit",
              result is not None)
        new_text, archive_text, moved, before, after = result
        check("frontmatter stays in the new index", "title: project memory" in new_text)
        check("frontmatter never leaves the index into the archive",
              "title: project memory" not in archive_text)
        check("the HTML comment stays in the new index",
              "do not hand edit" in new_text)
        check("the HTML comment never leaves the index into the archive",
              "do not hand edit" not in archive_text)


def test_cmd_apply_backs_up_and_appends_to_an_existing_memory_archive():
    # M4/MAJOR, calibrated red-then-green: cmd_apply used to overwrite an
    # existing memory-archive.md next to the index with no backup at all,
    # silently destroying whatever an earlier trim had archived. It must
    # back the existing archive up first, then append (never overwrite).
    with tempfile.TemporaryDirectory() as td:
        real_review_dir = _point_review_dir_at(td)
        saved_journal = _point_journal_at(td)
        try:
            path = os.path.join(td, "MEMORY.md")
            archive = os.path.join(td, "memory-archive.md")
            with open(archive, "w") as f:
                f.write("# Earlier archive\n\n- [Old item](old.md) archived last month.\n")
            with open(path, "w") as f:
                f.write(_many_bullets(260))
            mtrim.cmd_propose(path)
            rc = mtrim.cmd_apply()
            check("cmd_apply succeeds", rc == 0)
            check("the earlier archive content survives in place",
                  "Old item" in open(archive).read())
            check("a backup of the earlier archive was written",
                  any(f.startswith("memory-archive.md.bak") for f in os.listdir(td)))
        finally:
            optimize.review_dir = real_review_dir
            _restore_journal(saved_journal)


def test_cmd_apply_journals_creation_when_memory_archive_is_new():
    # DEFECT 3 (T6.1 security review): memory-archive.md gets CREATED (never
    # existed before) on its first write, not backed up. Before the fix,
    # backup_if_exists returned None for a path that did not exist yet and
    # wrote NOTHING to the journal for it, so this creation was invisible; a
    # later one-command undo built on the journal would not know to delete
    # memory-archive.md and would silently leave it behind.
    with tempfile.TemporaryDirectory() as td:
        real_review_dir = _point_review_dir_at(td)
        saved_journal = _point_journal_at(td)
        try:
            path = os.path.join(td, "MEMORY.md")
            archive = os.path.join(td, "memory-archive.md")
            check("sanity: no memory-archive.md exists yet", not os.path.exists(archive))
            with open(path, "w") as f:
                f.write(_many_bullets(260))
            mtrim.cmd_propose(path)
            rc = mtrim.cmd_apply()
            check("cmd_apply succeeds", rc == 0)
            check("memory-archive.md now exists", os.path.exists(archive))
            with open(guided_apply.MUTATIONS_LOG) as f:
                records = [json.loads(l) for l in f if l.strip()]
            archive_records = [r for r in records if r["target"] == archive]
            check("exactly one journal line names the new memory-archive.md",
                  len(archive_records) == 1)
            check("the memory-archive.md line is marked as a creation",
                  archive_records[0].get("created") is True)
            check("the creation line carries no backup path (nothing to back up)",
                  archive_records[0]["backup_path"] is None)
        finally:
            optimize.review_dir = real_review_dir
            _restore_journal(saved_journal)


def test_propose_trim_handles_a_byte_limited_file_with_few_lines():
    # M8/MAJOR, calibrated red-then-green: propose_trim's move count used to
    # be computed from the loaded LINE count alone. A file under the 200-line
    # limit but over the 25KB byte limit (a handful of very long lines)
    # computed need_to_move = 0 and returned None: NO DATA, "already fits",
    # even though context_lint itself says the index is truncated today.
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "big.md")
        # 100 lines, well under the 200-line cap, but each padded past 400
        # bytes so the whole file clears the 25KB byte cap several times over.
        with open(path, "w") as f:
            f.write("\n".join(f"- [Item {i}](i{i}.md) " + "x" * 400
                              for i in range(100)) + "\n")
        with open(path) as f:
            raw = f.read()
        t = context_lint.truncation_report(raw, context_lint.MEMORY_MAX_LINES,
                                           context_lint.MEMORY_MAX_BYTES)
        check("sanity: context_lint agrees this file is truncated today",
              t is not None)
        result = mtrim.propose_trim(path)
        check("propose_trim does not report NO DATA for a byte-limited file",
              result is not None)
        new_text, archive_text, moved, before, after = result
        check("at least one bullet was moved to bring it inside the byte limit",
              len(moved) > 0)
        after_report = context_lint.truncation_report(
            new_text, context_lint.MEMORY_MAX_LINES, context_lint.MEMORY_MAX_BYTES)
        check("the proposed new index actually fits both limits now",
              after_report is None)


if __name__ == "__main__":
    n = 0
    for name in sorted(dir(sys.modules[__name__])):
        if name.startswith("test_"):
            globals()[name]()
            n += 1
    print(f"\n{n} passed")
