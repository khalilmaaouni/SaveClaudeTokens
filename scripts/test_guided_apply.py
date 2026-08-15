#!/usr/bin/env python3
"""Calibrated checks for guided_apply.py, the shared apply contract every
wave R producer (optimize.py's CLAUDE.md diet, plugin_prune.py, memory_trim.py)
runs through. Every case here points ex.EXP_DIR/ex.LEDGER at a temp dir and
stubs ex.cmd_start, so nothing here ever touches the real machine's
~/.claude/token-shield/ (which carries a genuinely open experiment on this
machine, claude-md-diet-v2, per wave R's HARD CONSTRAINT 2). Every case that
touches backup_file/backup_if_exists also points ga.MUTATIONS_LOG (T6.1's
append-only mutation journal) at a temp path, so nothing here ever touches
the real machine's ~/.token-shield/mutations.jsonl either."""
import contextlib
import io
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


def _point_journal_at(td):
    saved = ga.MUTATIONS_LOG
    ga.MUTATIONS_LOG = os.path.join(td, "mutations.jsonl")
    return saved


def _restore_journal(saved):
    ga.MUTATIONS_LOG = saved


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


def test_apply_propagates_mutate_fns_nonzero_rc_and_opens_no_experiment():
    # R1/CRITICAL, calibrated: before the fix, apply() called mutate_fn() and
    # threw away its return value, so a mutate_fn that declined to apply
    # anything (a NO DATA no-op, rc 2) still fell through to verify_fn and,
    # if verify happened to pass (e.g. an already-fitting file "verifies" as
    # fitting), opened an experiment for a change that never happened.
    with tempfile.TemporaryDirectory() as td:
        saved = _point_exp_at(td)
        started = []
        real_cmd_start = ex.cmd_start
        ex.cmd_start = lambda label, root, days, now_ts, treats, metric=None: (
            started.append((label, treats)) or 0)
        try:
            verify_called = []
            rc, msg = ga.apply("t", None, lambda: 2,
                               lambda: (verify_called.append(True), (True, "ok"))[1])
            check("a nonzero mutate_fn rc propagates as apply's own rc", rc == 2)
            check("verify_fn never runs when mutate_fn applied nothing",
                  verify_called == [])
            check("no experiment opened when mutate_fn applied nothing", started == [])
            check("the message says plainly nothing was applied",
                  "nothing was applied" in msg)
        finally:
            ex.cmd_start = real_cmd_start
        _restore_exp(saved)


def test_apply_treats_a_falsy_mutate_rc_as_success():
    # The other half of R1: a mutate_fn that returns None (a bare lambda with
    # no explicit return, exactly what every existing caller of apply() in
    # this test file already passes) or 0 must still be read as "applied",
    # not as a refusal, so the fix does not flip every already-passing case.
    with tempfile.TemporaryDirectory() as td:
        saved = _point_exp_at(td)
        started = []
        real_cmd_start = ex.cmd_start
        ex.cmd_start = lambda label, root, days, now_ts, treats, metric=None: (
            started.append((label, treats)) or 0)
        try:
            rc, msg = ga.apply("t", None, lambda: 0, lambda: (True, "ok"))
            check("an explicit 0 rc from mutate_fn still counts as applied", rc == 0)
            check("an explicit 0 rc still opens the experiment", started == [("t", None)])
        finally:
            ex.cmd_start = real_cmd_start
        _restore_exp(saved)


def test_refuse_if_target_mismatch():
    # R2/R10/CRITICAL, unit test on the shared helper cmd_guided_apply,
    # cmd_guided_apply_output_discipline, and cmd_guided_apply_trim all call
    # before ever touching mutate_fn.
    check("matching paths never refuse",
          ga.refuse_if_target_mismatch("/a/CLAUDE.md", "/a/CLAUDE.md") is None)
    msg = ga.refuse_if_target_mismatch("/a/A-CLAUDE.md", "/a/B-CLAUDE.md")
    check("mismatched paths refuse", msg is not None)
    check("the refusal names the command-line path", "/a/A-CLAUDE.md" in msg)
    check("the refusal names the proposal's stored path", "/a/B-CLAUDE.md" in msg)


def test_refuse_if_experiment_open_fails_closed_on_unreadable_baseline():
    # R3/CRITICAL, calibrated red-then-green: a baseline file
    # experiment.list_open_experiments() cannot read or parse used to be
    # silently skipped (continue), so a genuinely open experiment whose
    # baseline got truncated mid-write (a crash during json.dump) or whose
    # file mode blocked reading read as "not open" and the apply ran anyway.
    with tempfile.TemporaryDirectory() as td:
        saved = _point_exp_at(td)
        try:
            bad = os.path.join(ex.EXP_DIR, "crashed-mid-write.json")
            with open(bad, "w") as f:
                f.write('{"label": "live-one", "cohort_end')  # truncated, invalid JSON
            called = []
            rc, msg = ga.apply("some-guided-label", None,
                               lambda: called.append("MUTATED") or 0,
                               lambda: (True, "ok"))
            check("a truncated baseline file still refuses (fails closed)", rc == 2)
            check("mutate_fn never ran while an unreadable baseline sat in EXP_DIR",
                  called == [])
            check("the refusal names the unreadable file", bad in msg)

            # A stray non-dict JSON value (e.g. "[]") must not crash either.
            os.remove(bad)
            stray = os.path.join(ex.EXP_DIR, "stray.json")
            with open(stray, "w") as f:
                f.write("[]")
            refusal = ga.refuse_if_experiment_open()
            check("a stray non-dict .json refuses instead of crashing",
                  refusal is not None and stray in refusal)
        finally:
            _restore_exp(saved)


def test_backup_file_matches_optimize_cmd_apply_pattern():
    with tempfile.TemporaryDirectory() as td:
        saved = _point_journal_at(td)
        try:
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
        finally:
            _restore_journal(saved)


def test_journal_line_carries_every_required_field():
    # T6.1: timestamp, target path, pre hash, backup path, producer.
    with tempfile.TemporaryDirectory() as td:
        saved = _point_journal_at(td)
        try:
            target = os.path.join(td, "MEMORY.md")
            with open(target, "w") as f:
                f.write("content\n")
            backup = ga.backup_file(target)
            with open(ga.MUTATIONS_LOG) as f:
                lines = f.readlines()
            check("exactly one line was appended for one mutation", len(lines) == 1)
            record = json.loads(lines[0])
            for field in ("timestamp", "target", "pre_hash", "backup_path", "producer"):
                check(f"journal record carries {field}", field in record)
            check("target names the mutated file", record["target"] == target)
            check("backup_path matches backup_file's own return value",
                  record["backup_path"] == backup)
            check("pre_hash is the hash of the content before the mutation",
                  record["pre_hash"] == ga.sha256_text("content\n"))
            check("producer defaults to 'unknown' outside any apply() call",
                  record["producer"] == "unknown")
        finally:
            _restore_journal(saved)


def test_second_mutation_appends_never_overwrites():
    # T6.1/done-check + DEFECT 1 (T6.1 security review, pre-existing data
    # loss): a second mutation of the SAME target must add a second line and
    # leave the first line, including its backup path and pre hash, exactly
    # as it was, rather than the .sha256-file pattern of one record per
    # target that a later mutation overwrites.
    # This used to fake time.strftime to force two distinct stamps, because
    # backup_file's own stamp only has one-second resolution and two calls
    # inside the same wall-clock second collided on the same backup filename
    # (DEFECT 1: the second backup_file call then silently overwrote the
    # FIRST backup's content on disk, losing the earlier version entirely,
    # while the journal still held two lines pointing at that one surviving
    # file with two different pre_hash values). That faking hid the exact
    # bug it should have caught. No faking now: two real, back-to-back
    # backup_file calls exercise the actual collision path, and
    # unique_backup_path's numeric-suffix fix is what keeps them apart.
    with tempfile.TemporaryDirectory() as td:
        saved = _point_journal_at(td)
        try:
            target = os.path.join(td, "CLAUDE.md")
            with open(target, "w") as f:
                f.write("version one\n")
            backup1 = ga.backup_file(target)
            with open(target, "w") as f:
                f.write("version two\n")
            backup2 = ga.backup_file(target)
            check("the two backups are different files", backup1 != backup2)
            with open(backup1) as f:
                check("the first backup still holds the FIRST version's content "
                      "(not clobbered by the second backup)",
                      f.read() == "version one\n")
            with open(backup2) as f:
                check("the second backup holds the second version's content",
                      f.read() == "version two\n")
            with open(ga.MUTATIONS_LOG) as f:
                lines = [json.loads(l) for l in f if l.strip()]
            check("two mutations of the same target produce two journal lines",
                  len(lines) == 2)
            check("both lines name the same target",
                  lines[0]["target"] == target and lines[1]["target"] == target)
            check("the first line still records the first backup path, untouched",
                  lines[0]["backup_path"] == backup1)
            check("the second line records the second backup path, not the first",
                  lines[1]["backup_path"] == backup2)
            check("the first line's pre_hash is the hash of version one",
                  lines[0]["pre_hash"] == ga.sha256_text("version one\n"))
            check("the second line's pre_hash is the hash of version two",
                  lines[1]["pre_hash"] == ga.sha256_text("version two\n"))
        finally:
            _restore_journal(saved)


def test_unique_backup_path_avoids_collision_on_the_same_stamp():
    # DEFECT 1 core fix, unit-level: unique_backup_path must never return a
    # path that already exists on disk, even when called twice with the
    # IDENTICAL stamp, which is exactly the real-world case (two backups of
    # the same target inside one wall-clock second; time.strftime only has
    # one-second resolution).
    with tempfile.TemporaryDirectory() as td:
        target = os.path.join(td, "CLAUDE.md")
        stamp = "20260101-120000"
        p1 = ga.unique_backup_path(target, stamp)
        check("the first call follows the plain '<path>.bak-<stamp>' shape",
              p1 == target + ".bak-" + stamp)
        with open(p1, "w") as f:
            f.write("already here")
        p2 = ga.unique_backup_path(target, stamp)
        check("a second call with the SAME stamp returns a DIFFERENT path",
              p1 != p2)
        check("the second path is not already on disk", not os.path.exists(p2))
        # And a third call, with p2 also now taken, must keep bumping rather
        # than looping back to a taken path.
        with open(p2, "w") as f:
            f.write("also here")
        p3 = ga.unique_backup_path(target, stamp)
        check("a third call keeps bumping past both taken paths",
              p3 not in (p1, p2) and not os.path.exists(p3))


def test_apply_journals_the_guided_apply_label_as_producer():
    with tempfile.TemporaryDirectory() as td:
        saved_exp = _point_exp_at(td)
        saved_journal = _point_journal_at(td)
        real_cmd_start = ex.cmd_start
        ex.cmd_start = lambda label, root, days, now_ts, treats, metric=None: 0
        try:
            target = os.path.join(td, "CLAUDE.md")
            with open(target, "w") as f:
                f.write("before\n")

            def mutate():
                ga.backup_file(target)
                with open(target, "w") as f:
                    f.write("after\n")
                return 0

            rc, msg = ga.apply("memory-trim-guided-20260101-000000", None,
                               mutate, lambda: (True, "ok"))
            check("apply succeeded", rc == 0)
            with open(ga.MUTATIONS_LOG) as f:
                record = json.loads(f.readline())
            check("the journal record's producer is the guided-apply label",
                  record["producer"] == "memory-trim-guided-20260101-000000")
            check("producer resets to 'unknown' after apply() returns",
                  ga._current_producer == "unknown")
        finally:
            ex.cmd_start = real_cmd_start
            _restore_exp(saved_exp)
            _restore_journal(saved_journal)


def test_corrupt_existing_journal_does_not_lose_new_record_or_crash():
    with tempfile.TemporaryDirectory() as td:
        saved = _point_journal_at(td)
        try:
            with open(ga.MUTATIONS_LOG, "w") as f:
                f.write("not valid json at all\n{also not valid\n")
            target = os.path.join(td, "CLAUDE.md")
            with open(target, "w") as f:
                f.write("content\n")
            backup = ga.backup_file(target)  # must not raise
            check("backup still succeeded despite a corrupt existing journal",
                  os.path.exists(backup))
            with open(ga.MUTATIONS_LOG) as f:
                lines = f.readlines()
            check("the corrupt content is still there, byte for byte",
                  lines[0] == "not valid json at all\n" and lines[1] == "{also not valid\n")
            check("the new record was appended after the corrupt content",
                  len(lines) == 3)
            new_record = json.loads(lines[-1])
            check("the new record parses as valid JSON despite the corrupt prefix",
                  new_record["target"] == target)
        finally:
            _restore_journal(saved)


def test_journal_write_failure_does_not_block_the_apply_but_is_reported():
    # The safer-thing choice this task asks for: apply and report, never
    # fail the apply, because by the time _append_mutation runs the backup
    # already exists and the caller is about to overwrite the real target
    # next. A raised exception here would abort a legitimate change over a
    # logging side channel, so the failure is caught and printed instead.
    with tempfile.TemporaryDirectory() as td:
        saved = _point_journal_at(td)
        try:
            blocker = os.path.join(td, "blocker")
            with open(blocker, "w") as f:
                f.write("x")
            ga.MUTATIONS_LOG = os.path.join(blocker, "mutations.jsonl")
            target = os.path.join(td, "CLAUDE.md")
            with open(target, "w") as f:
                f.write("content\n")
            captured = io.StringIO()
            with contextlib.redirect_stderr(captured):
                backup = ga.backup_file(target)
            check("the backup still happened even though the journal write failed",
                  os.path.exists(backup))
            with open(backup) as f:
                check("the backup content is intact", f.read() == "content\n")
            check("the failure was reported to stderr, not silently skipped",
                  "WARNING" in captured.getvalue() and
                  "mutation journal" in captured.getvalue())
        finally:
            _restore_journal(saved)


def test_backup_records_absolute_normalised_target_even_when_input_is_relative():
    # DEFECT 2 (T6.1 security review): the journal used to record whatever
    # path string a caller handed it verbatim. Running --apply with a
    # relative --file (e.g. "CLAUDE.md") journaled a relative target; an undo
    # run later from a different working directory would resolve that
    # relative path against the WRONG directory and hit the wrong file (or no
    # file at all). backup_file/journal_mutation must always record an
    # absolute, normalised path, for both target and backup_path.
    with tempfile.TemporaryDirectory() as td:
        saved = _point_journal_at(td)
        cwd = os.getcwd()
        try:
            os.chdir(td)
            with open("CLAUDE.md", "w") as f:
                f.write("content\n")
            expected_target = os.path.join(os.getcwd(), "CLAUDE.md")
            ga.backup_file("CLAUDE.md")
            with open(ga.MUTATIONS_LOG) as f:
                record = json.loads(f.readline())
            check("the journaled target is an absolute path",
                  os.path.isabs(record["target"]))
            check("the journaled target resolves to the real file, not a "
                  "cwd-relative fragment", record["target"] == expected_target)
            check("the journaled backup_path is also absolute",
                  os.path.isabs(record["backup_path"]))
        finally:
            os.chdir(cwd)
            _restore_journal(saved)


def test_journal_mutation_also_normalises_a_relative_target():
    # DEFECT 2, the journal_mutation() entry point (optimize.cmd_apply's own
    # inline-backup path uses this one, not backup_file), same fix.
    with tempfile.TemporaryDirectory() as td:
        saved = _point_journal_at(td)
        cwd = os.getcwd()
        try:
            os.chdir(td)
            expected_target = os.path.join(os.getcwd(), "CLAUDE.md")
            ga.journal_mutation("CLAUDE.md", "somehash", "CLAUDE.md.bak-x",
                                producer="test")
            with open(ga.MUTATIONS_LOG) as f:
                record = json.loads(f.readline())
            check("journal_mutation also records an absolute target",
                  record["target"] == expected_target)
            check("journal_mutation also records an absolute backup_path",
                  os.path.isabs(record["backup_path"]))
        finally:
            os.chdir(cwd)
            _restore_journal(saved)


def test_backup_if_exists_journals_creation_when_the_file_is_new():
    # DEFECT 3 (T6.1 security review): optimize.py and memory_trim.py call
    # backup_if_exists right before writing claude-history.md /
    # memory-archive.md for the first time. backup_if_exists returned None
    # for a file that did not exist yet and wrote NOTHING to the journal, so
    # an apply that CREATED a file left no record at all; a later undo driven
    # from the journal would not know to delete that file and would silently
    # leave it behind.
    with tempfile.TemporaryDirectory() as td:
        saved = _point_journal_at(td)
        try:
            target = os.path.join(td, "claude-history.md")
            check("sanity: the target does not exist yet", not os.path.exists(target))
            result = ga.backup_if_exists(target)
            check("backup_if_exists still returns None for a brand new file",
                  result is None)
            with open(ga.MUTATIONS_LOG) as f:
                lines = [json.loads(l) for l in f if l.strip()]
            check("a journal line was written even though nothing existed to back up",
                  len(lines) == 1)
            record = lines[0]
            check("the created record names the target", record["target"] == target)
            check("the created record carries no backup path (nothing was backed up)",
                  record["backup_path"] is None)
            check("the created record carries no pre hash (nothing existed to hash)",
                  record["pre_hash"] is None)
            check("the created record is marked as a creation, not a normal mutation",
                  record.get("created") is True)
        finally:
            _restore_journal(saved)


def test_backup_if_exists_still_backs_up_normally_when_the_file_already_exists():
    # The other half of the DEFECT 3 fix must not regress: an existing file
    # still gets a real backup and a normal (non-creation) journal line.
    with tempfile.TemporaryDirectory() as td:
        saved = _point_journal_at(td)
        try:
            target = os.path.join(td, "claude-history.md")
            with open(target, "w") as f:
                f.write("already here\n")
            result = ga.backup_if_exists(target)
            check("an existing file still gets backed up (non-None return)",
                  result is not None)
            check("the backup file exists on disk", os.path.exists(result))
            with open(ga.MUTATIONS_LOG) as f:
                lines = [json.loads(l) for l in f if l.strip()]
            check("exactly one journal line for the existing-file case", len(lines) == 1)
            check("the existing-file case is NOT marked as a creation",
                  lines[0].get("created") is False)
            check("the existing-file case still carries a real backup_path",
                  lines[0]["backup_path"] is not None)
        finally:
            _restore_journal(saved)


def test_nested_apply_restores_the_outer_producer_label():
    # DEFECT 4, second half (T6.1 security review): apply() used to hardcode
    # _current_producer back to the literal "unknown" in its finally clause
    # instead of restoring whatever it was set to before, so an apply() call
    # nested inside code that had already set a producer (an apply nested
    # inside another apply's mutate_fn) lost the outer label the moment the
    # inner one returned.
    with tempfile.TemporaryDirectory() as td:
        saved_exp = _point_exp_at(td)
        saved_journal = _point_journal_at(td)
        real_cmd_start = ex.cmd_start
        ex.cmd_start = lambda label, root, days, now_ts, treats, metric=None: 0
        try:
            with ga.producer_scope("outer-label"):
                check("the outer scope set the producer", ga._current_producer == "outer-label")
                rc, msg = ga.apply("inner-label", None, lambda: 0, lambda: (True, "ok"))
                check("the nested apply succeeded", rc == 0)
                check("producer restores to the OUTER label, not the hardcoded "
                      "'unknown', once the nested apply() returns",
                      ga._current_producer == "outer-label")
            check("producer restores to 'unknown' once the outer scope itself exits",
                  ga._current_producer == "unknown")
        finally:
            ex.cmd_start = real_cmd_start
            _restore_exp(saved_exp)
            _restore_journal(saved_journal)


def test_journal_write_survives_a_non_serialisable_field():
    # DEFECT 5 (T6.1 security review): the journal write used to catch only
    # OSError. json.dumps raises TypeError, not OSError, when a field cannot
    # be serialised (e.g. a set() sneaking in as pre_hash). Before the fix
    # that TypeError propagated uncaught and crashed the caller, well after
    # the real mutation/backup had already happened; it must degrade to the
    # same WARNING-on-stderr path OSError already takes.
    with tempfile.TemporaryDirectory() as td:
        saved = _point_journal_at(td)
        try:
            target = os.path.join(td, "CLAUDE.md")
            captured = io.StringIO()
            with contextlib.redirect_stderr(captured):
                ga.journal_mutation(target, {1, 2, 3}, None, producer="test")
            check("the failure was reported to stderr, not raised",
                  "WARNING" in captured.getvalue() and
                  "mutation journal" in captured.getvalue())
            check("nothing was written to the journal for the failed line",
                  not os.path.exists(ga.MUTATIONS_LOG)
                  or open(ga.MUTATIONS_LOG).read() == "")
        finally:
            _restore_journal(saved)


if __name__ == "__main__":
    n = 0
    for name in sorted(dir(sys.modules[__name__])):
        if name.startswith("test_"):
            globals()[name]()
            n += 1
    print(f"\n{n} passed")
