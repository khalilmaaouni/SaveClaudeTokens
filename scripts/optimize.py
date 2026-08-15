#!/usr/bin/env python3
"""
optimize.py: propose a safe, reversible CLAUDE.md diet, then apply it only on
an explicit yes.

The startup floor is the single largest token cost, and CLAUDE.md is the biggest
part of it. This trims that file the way a careful person would: move long dated
history and rationale into a notes file, leave a pointer, and keep every hard
rule exactly where it was.

TWO THINGS MAKE THIS SAFE, both non-negotiable:

1. It never moves a section that reads like a hard rule. Anything mentioning
   NEVER, ALWAYS, MUST, a safety or spend or credential or attribution or
   no-dash rule is kept, untouched. When in doubt it KEEPS. It would rather
   leave weight in than drop a load-bearing line.
2. It never edits your live CLAUDE.md on its own. By default it writes a
   PROPOSAL (the new file, the notes file, and a diff) to a review directory and
   touches nothing. `--apply` is a separate, explicit step, and even then it
   backs the original up first, so a revert is one copy.

The token figures here are ESTIMATED (characters over four). The real saving is
what a session's first-request floor actually drops, which you prove with
experiment mode after you apply, not something this script asserts.

USAGE
  python3 optimize.py                      # propose a diet for ~/.claude/CLAUDE.md
  python3 optimize.py --file PATH          # a different file
  python3 optimize.py --apply              # apply the last proposal, with a backup
  python3 optimize.py --guided-apply       # apply via the guided-apply contract
                                            # (refuses if an experiment is open,
                                            # verifies, auto-opens an experiment)
  python3 optimize.py --propose-output-discipline
                                            # WR+: propose the one static output-
                                            # discipline line for --file
  python3 optimize.py --apply-output-discipline
                                            # apply that proposal via guided apply

WR+, the output-discipline proposal type: a SECOND, unrelated proposal this
script can make, added on top of the CLAUDE.md diet above. It proposes adding
exactly ONE static line (OUTPUT_DISCIPLINE_LINE below) to --file, shown
verbatim before you say yes, applied only under the same backup-and-diff
contract as the diet, and it auto-opens its own experiment on success. This is
a hard cap, not a starting point: one static, hardcoded line, never a
generated list, never a growing set of rules. If a future session wants more
than one line, that is a different, bigger feature, not an extension of this
one; propose it separately instead of growing this constant.
"""

import argparse
import os
import re
import time

import context_lint
import guided_apply

# A section matching ANY of these is a hard rule and is never moved. The list is
# deliberately broad: keeping too much is a nuisance, dropping a rule is a
# failure, so the guard errs hard toward keeping.
HARD_PATTERNS = [
    r"\bNEVER\b", r"\bALWAYS\b", r"\bMUST\b", r"\bdo not\b", r"\bnever\b",
    r"co-?authored|attribution|watermark",
    r"em dash|en dash|\bdashes\b",
    r"spend|ceiling|\bcap(s|ped)?\b|concurren|token.?budget",
    r"credential|api key|password|secret|2fa|token\b",
    r"confirm|irreversible|rm -rf|--force|destructive|delete|overwrite",
    r"safety|safeguard|\bgate(s|d)?\b|permission",
    r"never lose work|persist|checkpoint",
]

# Signals that a section is dated history or rationale, not a live rule.
HISTORY_MARKERS = [
    r"postmortem", r"\bincident\b", r"runaway", r"\bratified\b",
    r"curation decision", r"decision record", r"\bhandover\b",
    r"the \d+ (january|february|march|april|may|june|july|august|september|"
    r"october|november|december)",
]

MOVE_MIN_CHARS = 700   # short sections are never worth moving


def est_tokens(text):
    """Rough token estimate, labeled ESTIMATED everywhere it is shown."""
    return round(len(text) / 4)


def split_sections(text):
    """Split into (heading, body) blocks on top-level '## ' headings. The text
    before the first heading is one preamble block with heading ''."""
    lines = text.split("\n")
    blocks = []
    cur_head = ""
    cur = []
    for ln in lines:
        if ln.startswith("## "):
            blocks.append((cur_head, "\n".join(cur)))
            cur_head = ln
            cur = [ln]
        else:
            cur.append(ln)
    blocks.append((cur_head, "\n".join(cur)))
    return blocks


def classify(heading, body):
    """Return ('HARD'|'MOVABLE'|'KEEP', reason). Conservative: KEEP unless a
    block is clearly long dated history AND shows no hard-rule signal."""
    blob = (heading + "\n" + body).lower()
    for pat in HARD_PATTERNS:
        if re.search(pat, blob, re.I):
            return "HARD", f"mentions a hard rule ({pat})"
    if len(body) < MOVE_MIN_CHARS:
        return "KEEP", "short"
    hist = sum(1 for pat in HISTORY_MARKERS if re.search(pat, blob, re.I))
    dates = len(re.findall(r"\d{4}-\d{2}-\d{2}", body))
    if hist >= 1 or dates >= 2:
        return "MOVABLE", f"dated history or rationale ({hist} markers, {dates} dates)"
    return "KEEP", "no clear history signal"


def propose(text, notes_rel="claude-history.md"):
    """Return (new_text, notes_text, moved, before_tok, after_tok)."""
    blocks = split_sections(text)
    new_parts = []
    notes_parts = ["# CLAUDE.md history and rationale\n",
                   "Moved out of CLAUDE.md by Token Shield to cut the always-loaded "
                   "startup floor. Every hard rule stayed in CLAUDE.md; this file holds "
                   "the dated history and rationale, kept for the record.\n"]
    moved = []
    for heading, body in blocks:
        verdict, reason = classify(heading, body)
        if verdict == "MOVABLE":
            title = heading[3:].strip() if heading else "(section)"
            saved = est_tokens(body)
            moved.append((title, saved, reason))
            notes_parts.append(body)
            # Keep the heading and leave a one-line pointer, so the map of the
            # file is intact and nothing silently vanishes.
            new_parts.append(f"{heading}\n\nMoved to `{notes_rel}` to save about "
                             f"{saved} estimated tokens. See that file for the detail.")
        else:
            new_parts.append(body)
    new_text = "\n".join(new_parts)
    notes_text = "\n\n".join(notes_parts) + "\n"
    return new_text, notes_text, moved, est_tokens(text), est_tokens(new_text)


def review_dir():
    d = os.path.expanduser("~/.token-shield/optimize")
    os.makedirs(d, exist_ok=True)
    return d


def cmd_propose(path):
    if not os.path.exists(path):
        print(f"NO DATA: {path} does not exist.")
        return 2
    with open(path) as f:
        text = f.read()
    new_text, notes_text, moved, before, after = propose(text)
    d = review_dir()
    with open(os.path.join(d, "CLAUDE.md.proposed"), "w") as f:
        f.write(new_text)
    with open(os.path.join(d, "claude-history.md"), "w") as f:
        f.write(notes_text)
    import difflib
    diff = "".join(difflib.unified_diff(
        text.splitlines(keepends=True), new_text.splitlines(keepends=True),
        fromfile="CLAUDE.md (now)", tofile="CLAUDE.md (proposed)"))
    with open(os.path.join(d, "diff.txt"), "w") as f:
        f.write(diff)
    with open(os.path.join(d, "source.txt"), "w") as f:
        f.write(path)
    with open(os.path.join(d, "source.sha256"), "w") as f:
        f.write(guided_apply.sha256_text(text))
    print(f"=== proposed CLAUDE.md diet for {path} ===")
    print(f"estimated tokens   {before:,} -> {after:,}  "
          f"({before - after:,} fewer, about {(before - after) / before * 100:.0f}%), ESTIMATED")
    if not moved:
        print("nothing safe to move: no long dated-history section without a hard rule.")
    else:
        print(f"{len(moved)} section(s) proposed to move to claude-history.md, hard rules "
              f"all kept:")
        for title, saved, reason in sorted(moved, key=lambda m: -m[1]):
            print(f"  ~{saved:>6,} tok  {title[:52]:52}  ({reason})")
    # The full section-cost map, so you can see where the tokens actually go and
    # direct a deeper diet by hand for the sections the safe classifier keeps.
    smap = [(h[3:].strip() if h else "(preamble)", est_tokens(b), classify(h, b)[0])
            for h, b in split_sections(text)]
    smap = [s for s in smap if s[1] > 0]
    print("\nwhere your CLAUDE.md tokens go (top sections, ESTIMATED):")
    tags = {"HARD": "keep (rule)", "MOVABLE": "movable", "KEEP": "keep"}
    for title, tok, verdict in sorted(smap, key=lambda s: -s[1])[:10]:
        print(f"  ~{tok:>6,} tok  [{tags[verdict]:11}]  {title[:48]}")
    print("  A section marked keep (rule) holds a hard rule and is never auto-moved. "
          "Dieting those is a judgment call, yours; this tool will move exactly the "
          "sections you name, with the same backup and diff.")
    print(f"\nreview:  {os.path.join(d, 'diff.txt')}")
    print(f"apply:   python3 {os.path.basename(__file__)} --apply   (backs the original up first)")
    print("The real saving is proven by experiment mode after you apply, not by this estimate.")
    return 0


def cmd_apply():
    """Returns an int rc: 0 applied, 2 NO DATA/REFUSED and nothing written.
    This IS a guided-apply mutate_fn (see cmd_guided_apply below), so callers
    other than main() must treat a nonzero return as "nothing was applied"."""
    d = review_dir()
    src_file = os.path.join(d, "source.txt")
    prop = os.path.join(d, "CLAUDE.md.proposed")
    notes = os.path.join(d, "claude-history.md")
    hash_file = os.path.join(d, "source.sha256")
    if not (os.path.exists(src_file) and os.path.exists(prop)):
        print("NO DATA: no proposal to apply. Run without --apply first.")
        return 2
    with open(src_file) as f:
        path = f.read().strip()
    if not os.path.exists(path):
        print(f"NO DATA: original {path} is gone; not applying.")
        return 2
    with open(path) as f:
        original = f.read()
    # R8/CRITICAL: refuse a stale proposal. If path changed since this
    # proposal was computed, applying the stored CLAUDE.md.proposed would
    # silently roll back whatever changed in between, and the loaded-line
    # verify would pass anyway (it only checks the count dropped). A missing
    # hash file (a proposal written before this check existed) is treated the
    # same as a mismatch: NO DATA beats a guess about freshness.
    current_hash = guided_apply.sha256_text(original)
    stored_hash = None
    if os.path.exists(hash_file):
        with open(hash_file) as f:
            stored_hash = f.read().strip()
    if stored_hash != current_hash:
        print(f"REFUSED: {path} changed since this proposal was made; applying it "
              f"now would silently roll back whatever changed in between. "
              f"Re-propose against the current file: python3 {os.path.basename(__file__)} "
              f"--file {path}")
        return 2
    # DEFECT 1 (security review, pre-existing data loss): the stamp used to be
    # built here inline (f"{path}.bak-{stamp}"), which only has one-second
    # resolution, so two applies of the same target inside the same
    # wall-clock second collided on the identical backup filename and the
    # second one silently overwrote the first backup on disk. The path CHOICE
    # now goes through guided_apply.unique_backup_path (the same helper
    # backup_file uses), which bumps a numeric suffix until it finds a path
    # that is not already taken. The write itself stays exactly as it was:
    # from 'original', the string already read and verified against
    # current_hash above, never a re-read of path, which would reopen the
    # window between that staleness check and the backup.
    backup = guided_apply.unique_backup_path(path)
    with open(backup, "w") as f:
        f.write(original)
    # T6.1: journal this backup too. This is the flagship mutation (the
    # CLAUDE.md diet itself), and it writes its own backup above instead of
    # calling guided_apply.backup_file, deliberately, so it backs up from the
    # 'original' string already read and verified against current_hash above
    # rather than re-reading the file and reopening that check-then-backup
    # window. journal_mutation reuses the exact hash already computed for
    # that check: no second read, no second hashing helper.
    guided_apply.journal_mutation(path, current_hash, backup)
    notes_dest = os.path.join(os.path.dirname(path), "claude-history.md")
    with open(notes) as f:
        notes_text = f.read()
    # M4: never clobber a hand-written or earlier claude-history.md. Back any
    # existing one up first, then append: earlier content survives in place,
    # not only inside a backup nobody reads.
    history_backup = guided_apply.backup_if_exists(notes_dest)
    with open(notes_dest, "a") as f:
        f.write(notes_text)
    with open(prop) as f:
        new_text = f.read()
    with open(path, "w") as f:
        f.write(new_text)
    print(f"applied. original backed up to {backup}")
    if history_backup:
        print(f"existing history backed up to {history_backup}")
    print(f"history appended to {notes_dest}")
    print(f"revert with: cp {backup} {path}")
    print("Note: a CLAUDE.md edit does not apply until your next /clear, /compact, or "
          "restart. Prove the saving with experiment mode across that boundary.")
    return 0


def verify_diet(original_text, path):
    """Re-runs context_lint.check(path, is_memory_index=False) after an apply
    and confirms the loaded line count actually dropped from original_text's.
    Returns (ok, report)."""
    before_lines = len(context_lint.loaded_content(original_text).splitlines())
    findings, stats = context_lint.check(path, is_memory_index=False)
    if not stats:
        return False, f"cannot re-read {path} to verify ({findings})"
    after_lines = stats["loaded_lines"]
    ok = after_lines < before_lines
    report = f"loaded lines {before_lines} -> {after_lines}"
    if not ok:
        report += " (no drop; nothing safe was moved, so nothing to verify)"
    return ok, report


def cmd_guided_apply(path):
    """The wave R entry point. Checks the open-experiment interlock FIRST,
    the same gate guided_apply.apply itself leads with, so "an experiment is
    already open" always wins and is always named correctly, regardless of
    any stale proposal sitting in the review directory. R2/R10/CRITICAL:
    only once that is clear, refuses outright, naming both paths, when path
    (named at apply time) does not match the stored proposal's own target
    (source.txt), so a guided apply can never mutate one file while
    verifying and excluding a different one. The mismatch check is only run
    when a proposal actually exists; a missing proposal falls through to
    cmd_apply's own NO DATA path (propagated by guided_apply.apply). Reads
    path's current text (for verify_diet's before count), then calls
    guided_apply.apply(label, treats=path, mutate_fn=cmd_apply,
    verify_fn=lambda: verify_diet(original, path))."""
    if not os.path.exists(path):
        print(f"NO DATA: {path} does not exist.")
        return 2
    refusal = guided_apply.refuse_if_experiment_open()
    if refusal:
        print(refusal)
        return 2
    src_file = os.path.join(review_dir(), "source.txt")
    if os.path.exists(src_file):
        with open(src_file) as f:
            stored_path = f.read().strip()
        mismatch = guided_apply.refuse_if_target_mismatch(path, stored_path)
        if mismatch:
            print(mismatch)
            return 2
    with open(path) as f:
        original = f.read()
    label = f"claude-md-diet-guided-{time.strftime('%Y%m%d-%H%M%S')}"
    rc, msg = guided_apply.apply(label, path, cmd_apply,
                                 lambda: verify_diet(original, path))
    print(msg)
    return rc


# WR+: one static line, a hard cap, never a generated or growing list. This
# constant is the entire proposal every output-discipline call makes; nothing
# in this module reads it from a file, builds it from findings, or appends to
# it. Changing what it says is a deliberate one-line edit to this constant,
# not a feature this tool grows on its own.
OUTPUT_DISCIPLINE_LINE = (
    "Report results in the fewest words that carry every fact: no restating "
    "the request, no narrating steps already shown, no filler adjectives.")


def propose_output_discipline(path):
    """WR+. Reads path, returns the proposed new text with
    OUTPUT_DISCIPLINE_LINE appended, or None when the line is already present
    (nothing to propose). Pure with respect to path: never writes."""
    with open(path) as f:
        text = f.read()
    if OUTPUT_DISCIPLINE_LINE in text:
        return None
    return text.rstrip("\n") + "\n\n" + OUTPUT_DISCIPLINE_LINE + "\n"


def cmd_propose_output_discipline(path):
    """WR+. Writes the proposal to review_dir() under output-discipline-
    specific filenames (never optimize's own CLAUDE.md.proposed/diff.txt, so
    the two proposal types never collide in the same review directory), shows
    the one line verbatim, and never touches path."""
    if not os.path.exists(path):
        print(f"NO DATA: {path} does not exist.")
        return 2
    new_text = propose_output_discipline(path)
    if new_text is None:
        print(f"NO DATA: {path} already carries the output-discipline line; "
              f"nothing to propose.")
        return 0
    with open(path) as f:
        original = f.read()
    d = review_dir()
    with open(os.path.join(d, "output-discipline.proposed"), "w") as f:
        f.write(new_text)
    import difflib
    diff = "".join(difflib.unified_diff(
        original.splitlines(keepends=True), new_text.splitlines(keepends=True),
        fromfile="CLAUDE.md (now)", tofile="CLAUDE.md (proposed)"))
    with open(os.path.join(d, "output-discipline-diff.txt"), "w") as f:
        f.write(diff)
    with open(os.path.join(d, "output-discipline-source.txt"), "w") as f:
        f.write(path)
    with open(os.path.join(d, "output-discipline-source.sha256"), "w") as f:
        f.write(guided_apply.sha256_text(original))
    print(f"=== proposed output-discipline line for {path} ===")
    print("This ONE line, shown verbatim, is the whole proposal (a hard cap; "
          "this tool never proposes more than one line):")
    print(f"  {OUTPUT_DISCIPLINE_LINE}")
    print(f"\nreview: {os.path.join(d, 'output-discipline-diff.txt')}")
    print("apply:  python3 optimize.py --apply-output-discipline")
    return 0


def cmd_apply_output_discipline():
    """WR+. Reads the review files cmd_propose_output_discipline wrote, backs
    the original up via guided_apply.backup_file, writes the proposed text.
    This IS the mutate_fn passed to guided_apply.apply, so it returns an int
    rc: 0 applied, 2 NO DATA/REFUSED and nothing written.
    R8/CRITICAL: refuses when path changed since this proposal was made (same
    staleness guard as cmd_apply's, see there for why)."""
    d = review_dir()
    src_file = os.path.join(d, "output-discipline-source.txt")
    prop = os.path.join(d, "output-discipline.proposed")
    hash_file = os.path.join(d, "output-discipline-source.sha256")
    if not (os.path.exists(src_file) and os.path.exists(prop)):
        print("NO DATA: no output-discipline proposal to apply. Run without "
              "--apply-output-discipline first.")
        return 2
    with open(src_file) as f:
        path = f.read().strip()
    if not os.path.exists(path):
        print(f"NO DATA: original {path} is gone; not applying.")
        return 2
    with open(path) as f:
        current = f.read()
    current_hash = guided_apply.sha256_text(current)
    stored_hash = None
    if os.path.exists(hash_file):
        with open(hash_file) as f:
            stored_hash = f.read().strip()
    if stored_hash != current_hash:
        print(f"REFUSED: {path} changed since this proposal was made; applying it "
              f"now would silently roll back whatever changed in between. "
              f"Re-propose against the current file: python3 optimize.py "
              f"--propose-output-discipline --file {path}")
        return 2
    backup = guided_apply.backup_file(path)
    with open(prop) as f:
        new_text = f.read()
    with open(path, "w") as f:
        f.write(new_text)
    print(f"applied. original backed up to {backup}")
    print(f"revert with: cp {backup} {path}")
    return 0


def verify_output_discipline(path):
    """WR+. Confirms OUTPUT_DISCIPLINE_LINE is present in path after an
    apply. Returns (ok, report)."""
    with open(path) as f:
        text = f.read()
    ok = OUTPUT_DISCIPLINE_LINE in text
    return ok, ("the line is present" if ok else "the line is missing after apply")


def cmd_guided_apply_output_discipline(path):
    """WR+ entry point. Composes with guided_apply.apply exactly like
    cmd_guided_apply above: treats=path (this proposal edits path itself, so
    the same --treats exclusion applies), label
    output-discipline-guided-<timestamp>, a separate label from both the diet
    guided apply and a plain --apply run, so the three never collide.
    Checks the open-experiment interlock FIRST (see cmd_guided_apply above
    for why), then the R2/R10/CRITICAL file-target-mismatch refusal, checked
    against output-discipline-source.txt."""
    refusal = guided_apply.refuse_if_experiment_open()
    if refusal:
        print(refusal)
        return 2
    d = review_dir()
    src_file = os.path.join(d, "output-discipline-source.txt")
    if os.path.exists(src_file):
        with open(src_file) as f:
            stored_path = f.read().strip()
        mismatch = guided_apply.refuse_if_target_mismatch(path, stored_path)
        if mismatch:
            print(mismatch)
            return 2
    label = f"output-discipline-guided-{time.strftime('%Y%m%d-%H%M%S')}"
    rc, msg = guided_apply.apply(label, path, cmd_apply_output_discipline,
                                 lambda: verify_output_discipline(path))
    print(msg)
    return rc


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--file", default=os.path.expanduser("~/.claude/CLAUDE.md"))
    ap.add_argument("--apply", action="store_true",
                    help="apply the last proposal, backing up the original first")
    ap.add_argument("--guided-apply", action="store_true",
                    help="apply the last proposal via wave R's guided-apply contract: "
                         "refuses if any experiment is open, verifies the diet actually "
                         "dropped loaded lines, and auto-opens one experiment to prove it")
    ap.add_argument("--propose-output-discipline", action="store_true",
                    help="WR+: propose the one static output-discipline line for --file")
    ap.add_argument("--apply-output-discipline", action="store_true",
                    help="WR+: apply the proposed output-discipline line via guided apply")
    a = ap.parse_args()
    if a.propose_output_discipline:
        return cmd_propose_output_discipline(a.file)
    if a.apply_output_discipline:
        return cmd_guided_apply_output_discipline(a.file)
    if a.guided_apply:
        return cmd_guided_apply(a.file)
    if a.apply:
        # DEFECT 4: the plain --apply route never went through guided_apply's
        # apply() (that is cmd_guided_apply's job, see --guided-apply above),
        # so _current_producer stayed at its module-default "unknown" and
        # every journal line for a hand-run --apply recorded producer:
        # "unknown", the exact path a person actually runs by hand. Wrap it
        # in the same producer_scope guided_apply.apply() uses internally.
        with guided_apply.producer_scope("claude-md-diet-apply"):
            return cmd_apply()
    return cmd_propose(a.file)


if __name__ == "__main__":
    import sys
    sys.exit(main())
