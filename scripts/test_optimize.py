#!/usr/bin/env python3
"""Calibrated checks for optimize.py. The load-bearing one: a hard rule is
never classified movable, even when it also looks like history.
Every case that reaches a real backup (cmd_apply's success path) also points
ga.MUTATIONS_LOG at a temp path first (see _point_journal_at/_restore_journal,
mirrored from test_guided_apply.py), so nothing here ever touches the real
machine's ~/.token-shield/mutations.jsonl."""
import json
import os
import sys
import tempfile

import guided_apply as ga
import optimize as opt


def check(name, cond):
    print(("ok  " if cond else "FAIL ") + name)
    assert cond, name


def _point_review_dir_at(td):
    real = opt.review_dir
    d = os.path.join(td, "optimize")
    os.makedirs(d, exist_ok=True)
    opt.review_dir = lambda: d
    return real


def _point_journal_at(td):
    saved = ga.MUTATIONS_LOG
    ga.MUTATIONS_LOG = os.path.join(td, "mutations.jsonl")
    return saved


def _restore_journal(saved):
    ga.MUTATIONS_LOG = saved


HARD = ("## No attribution\n" + "We NEVER add a Co-Authored-By trailer. " * 30)
HISTORY = ("## Curation decisions\n" + "On 2026-08-09 the postmortem after the "
           "2026-08-08 runaway ratified the plan. " * 30)
HARD_LOOKS_LIKE_HISTORY = ("## Spend postmortem\n" + "After the 2026-08-08 incident we "
                           "set a spend cap. This MUST hold. " * 30)
SHORT = "## Tiny\nOne short line."


def test_hard_rule_section_is_never_movable():
    v, _ = opt.classify(*_split(HARD))
    check("a hard-rule section is HARD, not movable", v == "HARD")


def test_dated_history_is_movable():
    v, _ = opt.classify(*_split(HISTORY))
    check("a long dated-history section is MOVABLE", v == "MOVABLE")


def test_hard_signal_beats_history_signal():
    # The safety-critical case: a section that is dated history but also states a
    # hard rule must be KEPT. The guard wins over the move heuristic.
    v, _ = opt.classify(*_split(HARD_LOOKS_LIKE_HISTORY))
    check("a hard rule wearing history clothing is still HARD", v == "HARD")


def test_short_section_is_kept():
    v, _ = opt.classify(*_split(SHORT))
    check("a short section is KEEP, never moved", v == "KEEP")


def test_propose_keeps_every_hard_section_verbatim():
    text = HARD + "\n" + HISTORY + "\n" + SHORT
    new_text, notes, moved, before, after = opt.propose(text)
    # The hard section's body survives untouched in the new file.
    check("propose keeps the hard section verbatim", "Co-Authored-By trailer" in new_text)
    # The history section moved to notes and left a pointer, not its body.
    check("propose moves the history body to notes", "ratified the plan" in notes)
    check("propose leaves a pointer where history was",
          "Moved to" in new_text and "ratified the plan" not in new_text)
    check("proposed file is not larger than the original", after <= before)
    check("at least the history section moved", any("Curation" in m[0] for m in moved))


def test_cmd_propose_never_writes_the_source_claude_md():
    # The never-lose-work contract: propose is backup-first and propose-only,
    # never a mutation of the file it read. This exercises the real CLI entry
    # point, cmd_propose, the one that actually opens the source path, not the
    # pure propose() function above, which never touches a filesystem path at
    # all and so cannot prove this claim.
    with tempfile.TemporaryDirectory() as d:
        real_review_dir = _point_review_dir_at(d)
        try:
            src = os.path.join(d, "CLAUDE.md")
            original = HARD + "\n" + HISTORY + "\n" + SHORT
            with open(src, "w") as f:
                f.write(original)
            before = open(src, "rb").read()
            rc = opt.cmd_propose(src)
            check("cmd_propose returns success", rc == 0)
            after = open(src, "rb").read()
            check("cmd_propose never writes to the source CLAUDE.md path", before == after)
        finally:
            opt.review_dir = real_review_dir


def test_verify_diet_reports_the_line_count_drop():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "CLAUDE.md")
        before_text = "\n".join(f"line {i}" for i in range(50))
        after_text = "\n".join(f"line {i}" for i in range(10))
        with open(path, "w") as f:
            f.write(after_text)
        ok, report = opt.verify_diet(before_text, path)
        check("verify_diet reports ok when the loaded line count dropped", ok)
        check("verify_diet's report names the before and after line counts",
              "50" in report and "10" in report)

        # A "diet" that did not actually shrink the file must not verify ok:
        # writing the same content back must not read as a successful diet.
        with open(path, "w") as f:
            f.write(before_text)
        ok2, report2 = opt.verify_diet(before_text, path)
        check("verify_diet reports not-ok when the line count did not drop", not ok2)


def test_cmd_guided_apply_refuses_when_experiment_open():
    # The never-lose-work contract, extended to the guided-apply path: a
    # refused apply must never touch the source file at all, mirroring
    # test_cmd_propose_never_writes_the_source_claude_md above but for
    # cmd_guided_apply instead of cmd_propose. cmd_apply is stubbed too (not
    # just the refusal), so that even a regressed guard can never fall
    # through to the real cmd_apply and its real ~/.token-shield/optimize/
    # review directory: the stub marks the source dirty if it ever runs,
    # which the before/after check below would catch exactly like a real
    # unwanted write would.
    real_refuse = ga.refuse_if_experiment_open
    real_cmd_apply = opt.cmd_apply
    ga.refuse_if_experiment_open = lambda: "REFUSED: fixture experiment is open"
    opt.cmd_apply = lambda: (_ for _ in ()).throw(
        AssertionError("cmd_apply must never run while an experiment is open"))
    try:
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "CLAUDE.md")
            original = HARD + "\n" + HISTORY + "\n" + SHORT
            with open(src, "w") as f:
                f.write(original)
            before = open(src, "rb").read()
            rc = opt.cmd_guided_apply(src)
            check("cmd_guided_apply refuses with rc 2", rc == 2)
            after = open(src, "rb").read()
            check("cmd_guided_apply never writes to the source CLAUDE.md when refused",
                  before == after)
    finally:
        ga.refuse_if_experiment_open = real_refuse
        opt.cmd_apply = real_cmd_apply


def test_output_discipline_line_is_a_single_hard_capped_line():
    # WR+'s hard cap: exactly one static line, never a paragraph or list.
    check("OUTPUT_DISCIPLINE_LINE carries no newline",
          "\n" not in opt.OUTPUT_DISCIPLINE_LINE)
    check("OUTPUT_DISCIPLINE_LINE is non-empty", len(opt.OUTPUT_DISCIPLINE_LINE) > 0)


def test_propose_output_discipline_shows_the_line_verbatim_and_is_a_no_op_when_present():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "CLAUDE.md")
        with open(path, "w") as f:
            f.write("# Rules\n- an existing rule\n")
        new_text = opt.propose_output_discipline(path)
        check("propose_output_discipline proposes the line verbatim",
              opt.OUTPUT_DISCIPLINE_LINE in new_text)
        check("propose_output_discipline never writes to path itself",
              "existing rule" in open(path).read()
              and opt.OUTPUT_DISCIPLINE_LINE not in open(path).read())

        # Once the line is already present, proposing again is a no-op.
        with open(path, "w") as f:
            f.write(new_text)
        check("propose_output_discipline returns None once the line is already present",
              opt.propose_output_discipline(path) is None)


def test_cmd_apply_output_discipline_never_writes_without_a_prior_propose():
    with tempfile.TemporaryDirectory() as td:
        real_review_dir = _point_review_dir_at(td)
        try:
            src = os.path.join(td, "CLAUDE.md")
            original = "# Rules\n- an existing rule\n"
            with open(src, "w") as f:
                f.write(original)
            before = open(src, "rb").read()
            rc = opt.cmd_apply_output_discipline()
            check("cmd_apply_output_discipline refuses with NO DATA when nothing "
                  "was proposed", rc == 2)
            after = open(src, "rb").read()
            check("cmd_apply_output_discipline never writes to the source without "
                  "a prior propose", before == after)
        finally:
            opt.review_dir = real_review_dir


def test_cmd_guided_apply_output_discipline_refuses_when_experiment_open():
    real_refuse = ga.refuse_if_experiment_open
    real_apply_od = opt.cmd_apply_output_discipline
    ga.refuse_if_experiment_open = lambda: "REFUSED: fixture experiment is open"
    opt.cmd_apply_output_discipline = lambda: (_ for _ in ()).throw(
        AssertionError("cmd_apply_output_discipline must never run while an "
                       "experiment is open"))
    try:
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "CLAUDE.md")
            original = "# Rules\n- an existing rule\n"
            with open(src, "w") as f:
                f.write(original)
            before = open(src, "rb").read()
            rc = opt.cmd_guided_apply_output_discipline(src)
            check("cmd_guided_apply_output_discipline refuses with rc 2", rc == 2)
            after = open(src, "rb").read()
            check("cmd_guided_apply_output_discipline never writes to the source "
                  "when refused", before == after)
    finally:
        ga.refuse_if_experiment_open = real_refuse
        opt.cmd_apply_output_discipline = real_apply_od


def test_cmd_guided_apply_refuses_when_the_named_file_differs_from_the_proposal():
    # R2/R10/CRITICAL, calibrated red-then-green: the mutation used to apply
    # to the file recorded in the PROPOSAL, while verify and --treats used
    # the file named on the command line. Propose against A, apply naming B:
    # A got rewritten (from the stale stored proposal), B was verified and
    # excluded. Neither file should be touched here; the mismatch must
    # refuse before mutate_fn (cmd_apply) ever runs.
    with tempfile.TemporaryDirectory() as td:
        real_review_dir = _point_review_dir_at(td)
        try:
            a = os.path.join(td, "A-CLAUDE.md")
            b = os.path.join(td, "B-CLAUDE.md")
            with open(a, "w") as f:
                f.write(HARD + "\n" + HISTORY + "\n")
            with open(b, "w") as f:
                f.write("# B, a different file entirely\n")
            opt.cmd_propose(a)
            before_a = open(a, "rb").read()
            before_b = open(b, "rb").read()
            rc = opt.cmd_guided_apply(b)
            check("cmd_guided_apply refuses with rc 2 on a target mismatch", rc == 2)
            check("A (the proposal's real target) is never touched",
                  open(a, "rb").read() == before_a)
            check("B (named on the command line) is never touched either",
                  open(b, "rb").read() == before_b)
        finally:
            opt.review_dir = real_review_dir


def test_cmd_apply_refuses_a_stale_proposal_and_keeps_what_changed_since():
    # R8/CRITICAL, calibrated red-then-green: a proposal computed earlier
    # used to apply over a file that changed since propose, silently rolling
    # back whatever was added in between, with verify passing anyway (it
    # only checks the loaded line count dropped). Calibrated to the exact R8
    # shape: propose, then append a new rule directly to the file, then
    # apply must refuse and the new rule must survive untouched.
    with tempfile.TemporaryDirectory() as td:
        real_review_dir = _point_review_dir_at(td)
        try:
            src = os.path.join(td, "CLAUDE.md")
            with open(src, "w") as f:
                f.write(HARD + "\n" + HISTORY + "\n")
            opt.cmd_propose(src)
            with open(src, "a") as f:
                f.write("\n## Spend cap\nNEVER exceed the session token ceiling. "
                        "This rule was added after the proposal was made.\n")
            before = open(src, "rb").read()
            rc = opt.cmd_apply()
            check("cmd_apply refuses a stale proposal instead of applying it",
                  rc == 2)
            check("the file is untouched: the new rule survives byte for byte",
                  open(src, "rb").read() == before)
            check("the new rule text is still there",
                  "NEVER exceed the session token ceiling" in open(src).read())
        finally:
            opt.review_dir = real_review_dir


def test_cmd_apply_backs_up_and_appends_to_an_existing_claude_history():
    # M4-adjacent, calibrated red-then-green: cmd_apply used to overwrite an
    # existing claude-history.md next to CLAUDE.md with no backup, silently
    # destroying anything hand-written there. It must back the existing file
    # up first, then append (never overwrite), so earlier content survives
    # both in the backup and in place.
    with tempfile.TemporaryDirectory() as td:
        real_review_dir = _point_review_dir_at(td)
        saved_journal = _point_journal_at(td)
        try:
            src = os.path.join(td, "CLAUDE.md")
            hist = os.path.join(td, "claude-history.md")
            with open(hist, "w") as f:
                f.write("# my own hand written history notes\n")
            with open(src, "w") as f:
                f.write(HARD + "\n" + HISTORY + "\n")
            opt.cmd_propose(src)
            rc = opt.cmd_apply()
            check("cmd_apply succeeds", rc == 0)
            check("the hand-written history survives in place",
                  "hand written history notes" in open(hist).read())
            check("a backup of the earlier history file was written",
                  any(f.startswith("claude-history.md.bak")
                      for f in os.listdir(td)))
        finally:
            opt.review_dir = real_review_dir
            _restore_journal(saved_journal)


def test_cmd_apply_journals_the_primary_claude_md_target():
    # T6.1/defect 2: cmd_apply backs the flagship CLAUDE.md diet target up
    # with its own inline backup (never through guided_apply.backup_file, on
    # purpose, see the comment above that inline backup in optimize.py), so
    # before the fix it produced a backup file but no journal line for path
    # itself, only for its claude-history.md companion via backup_if_exists.
    # A later one-command undo built on the journal would silently never
    # cover the primary target. This must journal path with the same shape
    # backup_file itself writes.
    with tempfile.TemporaryDirectory() as td:
        td = os.path.realpath(td)  # DEFECT A fix: journal now records realpath
        real_review_dir = _point_review_dir_at(td)
        saved_journal = _point_journal_at(td)
        try:
            src = os.path.join(td, "CLAUDE.md")
            original = HARD + "\n" + HISTORY + "\n"
            with open(src, "w") as f:
                f.write(original)
            opt.cmd_propose(src)
            rc = opt.cmd_apply()
            check("cmd_apply succeeds", rc == 0)
            with open(ga.MUTATIONS_LOG) as f:
                records = [json.loads(l) for l in f if l.strip()]
            target_records = [r for r in records if r["target"] == src]
            check("exactly one journal line names the primary CLAUDE.md target",
                  len(target_records) == 1)
            record = target_records[0]
            for field in ("timestamp", "target", "pre_hash", "backup_path", "producer"):
                check(f"the primary target's journal record carries {field}",
                      field in record)
            check("pre_hash is the hash of the original content before the diet applied",
                  record["pre_hash"] == ga.sha256_text(original))
            check("backup_path names a real file on disk",
                  os.path.exists(record["backup_path"]))
        finally:
            opt.review_dir = real_review_dir
            _restore_journal(saved_journal)


def test_cmd_apply_journals_creation_when_claude_history_is_new():
    # DEFECT 3 (T6.1 security review): claude-history.md gets CREATED (never
    # existed before) on its first write, not backed up. Before the fix,
    # backup_if_exists returned None for a path that did not exist yet and
    # wrote NOTHING to the journal for it, so this creation was invisible; a
    # later one-command undo built on the journal would not know to delete
    # claude-history.md and would silently leave it behind.
    with tempfile.TemporaryDirectory() as td:
        td = os.path.realpath(td)  # DEFECT A fix: journal now records realpath
        real_review_dir = _point_review_dir_at(td)
        saved_journal = _point_journal_at(td)
        try:
            src = os.path.join(td, "CLAUDE.md")
            hist = os.path.join(td, "claude-history.md")
            check("sanity: no claude-history.md exists yet", not os.path.exists(hist))
            with open(src, "w") as f:
                f.write(HARD + "\n" + HISTORY + "\n")
            opt.cmd_propose(src)
            rc = opt.cmd_apply()
            check("cmd_apply succeeds", rc == 0)
            check("claude-history.md now exists", os.path.exists(hist))
            with open(ga.MUTATIONS_LOG) as f:
                records = [json.loads(l) for l in f if l.strip()]
            hist_records = [r for r in records if r["target"] == hist]
            check("exactly one journal line names the new claude-history.md",
                  len(hist_records) == 1)
            check("the claude-history.md line is marked as a creation",
                  hist_records[0].get("created") is True)
            check("the creation line carries no backup path (nothing to back up)",
                  hist_records[0]["backup_path"] is None)
        finally:
            opt.review_dir = real_review_dir
            _restore_journal(saved_journal)


def test_direct_apply_route_records_a_named_producer_not_unknown():
    # DEFECT 4 (T6.1 security review): the plain `--apply` CLI flag (main's
    # a.apply branch) calls cmd_apply() directly, never through
    # guided_apply.apply(), which is the only place that used to set
    # _current_producer. That left it at its module default "unknown", so
    # every journal line written by a hand-run --apply recorded producer:
    # "unknown", exactly the path a person actually runs by hand.
    with tempfile.TemporaryDirectory() as td:
        td = os.path.realpath(td)  # DEFECT A fix: journal now records realpath
        real_review_dir = _point_review_dir_at(td)
        saved_journal = _point_journal_at(td)
        real_argv = sys.argv
        try:
            src = os.path.join(td, "CLAUDE.md")
            with open(src, "w") as f:
                f.write(HARD + "\n" + HISTORY + "\n")
            opt.cmd_propose(src)
            sys.argv = ["optimize.py", "--file", src, "--apply"]
            rc = opt.main()
            check("main()'s --apply route succeeds", rc == 0)
            with open(ga.MUTATIONS_LOG) as f:
                records = [json.loads(l) for l in f if l.strip()]
            target_records = [r for r in records if r["target"] == src]
            check("exactly one journal line names the primary target",
                  len(target_records) == 1)
            check("the direct --apply route records a real producer, not 'unknown'",
                  target_records[0]["producer"] != "unknown")
            check("the producer names this as a claude-md-diet apply",
                  "claude-md-diet" in target_records[0]["producer"])
        finally:
            opt.review_dir = real_review_dir
            _restore_journal(saved_journal)
            sys.argv = real_argv


def _split(section_text):
    blocks = opt.split_sections(section_text)
    # the section is the last block (after any preamble)
    heading, body = blocks[-1]
    return heading, body


if __name__ == "__main__":
    import sys
    # The real review dir must be byte-for-byte untouched by this suite: every
    # test that reaches a CLI entry point points review_dir at a temp dir. This
    # guard is what turns a future unisolated test into a red run instead of
    # silent droppings in the user's real store.
    real_dir = opt.review_dir()
    before_listing = sorted(os.listdir(real_dir)) if os.path.isdir(real_dir) else None
    n = 0
    for name in sorted(dir(sys.modules[__name__])):
        if name.startswith("test_"):
            globals()[name]()
            n += 1
    after_listing = sorted(os.listdir(real_dir)) if os.path.isdir(real_dir) else None
    assert before_listing == after_listing, (
        "the suite wrote the real review dir %s: before %r, after %r"
        % (real_dir, before_listing, after_listing))
    print(f"\n{n} passed")
