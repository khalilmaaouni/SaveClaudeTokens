#!/usr/bin/env python3
"""Calibrated checks for optimize.py. The load-bearing one: a hard rule is
never classified movable, even when it also looks like history."""
import os
import tempfile

import optimize as opt


def check(name, cond):
    print(("ok  " if cond else "FAIL ") + name)
    assert cond, name


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
        src = os.path.join(d, "CLAUDE.md")
        original = HARD + "\n" + HISTORY + "\n" + SHORT
        with open(src, "w") as f:
            f.write(original)
        before = open(src, "rb").read()
        rc = opt.cmd_propose(src)
        check("cmd_propose returns success", rc == 0)
        after = open(src, "rb").read()
        check("cmd_propose never writes to the source CLAUDE.md path", before == after)


def _split(section_text):
    blocks = opt.split_sections(section_text)
    # the section is the last block (after any preamble)
    heading, body = blocks[-1]
    return heading, body


if __name__ == "__main__":
    import sys
    n = 0
    for name in sorted(dir(sys.modules[__name__])):
        if name.startswith("test_"):
            globals()[name]()
            n += 1
    print(f"\n{n} passed")
