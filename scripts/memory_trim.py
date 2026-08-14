#!/usr/bin/env python3
"""
memory_trim.py: propose trimming an auto-memory MEMORY.md index back inside
its documented load limit, then apply it only on an explicit yes, proven with
an auto-opened experiment. Mirrors optimize.py's own propose/apply/pointer
shape as closely as the different file format allows: it operates on bullet
lines (context_lint.BULLET) instead of optimize.py's '## ' sections, because
Claude Code's own auto-memory index is a flat list of pointer bullets, not a
rulebook with sections. There is no HARD-rule classification step here either:
the memory index is Claude Code's own auto-generated notes, not hand-written
instructions, so no bullet in it is ever treated as a hard rule to protect.

THRESHOLDS, sourced from context_lint.py (itself sourced to
code.claude.com/docs/en/memory): the first 200 lines or 25KB of MEMORY.md,
whichever comes first, are loaded at the start of every session. Content past
that is silently dropped today; this tool moves that dropped content (and, if
needed, a little more of what is still loaded) into memory-archive.md, keeps
one pointer line in place, and leaves the file within the documented limit.

Two things make this safe, both non-negotiable, mirroring optimize.py:
1. It never edits the live index on its own. `cmd_propose` writes a
   PROPOSAL (the new index, the archive file, and a diff) to a review
   directory and touches nothing live. `apply` is a separate, explicit step
   that backs the original up first, so a revert is one copy.
2. Bullets already past the documented cut point are moved first: they never
   load today anyway, so moving them costs nothing behaviorally. Only if that
   alone is not enough does it move bullets that are still currently loaded,
   working backward from the end of the file.

USAGE
  python3 memory_trim.py                 # propose a trim for this project's auto-memory index
  python3 memory_trim.py --file PATH     # a different MEMORY.md
  python3 memory_trim.py apply           # apply the last proposal, with a backup
"""
import argparse
import difflib
import os
import sys
import time

import context_lint
import guided_apply
import optimize


def propose_trim(path, keep_lines=None):
    """keep_lines defaults to context_lint.MEMORY_MAX_LINES (200). Reads path,
    calls context_lint.truncation_report on its loaded_content to find the
    real cut point (None if the file is already within its limit: nothing to
    propose; returns None). Parses bullet lines via context_lint.BULLET.
    Moves bullets starting from the ones AT OR PAST the reported cut_at_line
    first (they already never load, so moving them costs nothing
    behaviorally), working backward from the end of the file, until the
    remaining index (plus the one pointer line this trim adds) fits within
    keep_lines. Returns (new_text, archive_text, moved, before_lines,
    after_lines), or None when there is nothing to move (either the file
    already fits, or it holds no bullet lines to move)."""
    keep_lines = context_lint.MEMORY_MAX_LINES if keep_lines is None else keep_lines
    with open(path) as f:
        raw = f.read()
    t = context_lint.truncation_report(raw, keep_lines, context_lint.MEMORY_MAX_BYTES)
    if t is None:
        return None

    lines = context_lint.loaded_content(raw).splitlines()
    before_lines = len(lines)
    bullet_idx = [i for i, ln in enumerate(lines) if context_lint.BULLET.match(ln)]

    # +1 accounts for the single pointer line this trim adds once anything
    # moves; a move that removed exactly enough bullets but added no pointer
    # would undercount. Clamped to the bullets actually available: a file
    # with too few bullets to reach the target still moves everything it can.
    need_to_move = max(0, before_lines + 1 - keep_lines)
    to_move = sorted(list(reversed(bullet_idx))[:min(need_to_move, len(bullet_idx))])
    if not to_move:
        return None

    moved = [lines[i] for i in to_move]
    move_set = set(to_move)
    kept_lines = [ln for i, ln in enumerate(lines) if i not in move_set]
    pointer = (f"- {len(moved)} item(s) moved to memory-archive.md to fit the "
              f"{keep_lines}-line load limit. See that file for the detail.")
    new_lines = kept_lines + [pointer]
    new_text = "\n".join(new_lines) + "\n"
    archive_text = ("# Memory index archive\n\n"
                    "Moved out of the auto-memory index by Token Shield to fit its "
                    "documented load limit. Every item here either already fell past "
                    "that limit and was never loading, or was moved to make room for "
                    "one that had; kept here for the record.\n\n" +
                    "\n".join(moved) + "\n")
    return new_text, archive_text, moved, before_lines, len(new_lines)


def cmd_propose(path):
    if not os.path.exists(path):
        print(f"NO DATA: {path} does not exist.")
        return 2
    result = propose_trim(path)
    if result is None:
        print(f"NO DATA: {path} already fits its {context_lint.MEMORY_MAX_LINES}-line "
              f"load limit (or holds no bullet lines to move); nothing to trim.")
        return 0
    new_text, archive_text, moved, before, after = result
    d = optimize.review_dir()
    with open(os.path.join(d, "memory-trim.proposed"), "w") as f:
        f.write(new_text)
    with open(os.path.join(d, "memory-archive.md"), "w") as f:
        f.write(archive_text)
    with open(path) as f:
        original = f.read()
    diff = "".join(difflib.unified_diff(
        original.splitlines(keepends=True), new_text.splitlines(keepends=True),
        fromfile="MEMORY.md (now)", tofile="MEMORY.md (proposed)"))
    with open(os.path.join(d, "memory-trim-diff.txt"), "w") as f:
        f.write(diff)
    with open(os.path.join(d, "memory-trim-source.txt"), "w") as f:
        f.write(path)
    print(f"=== proposed memory index trim for {path} ===")
    print(f"loaded lines   {before:,} -> {after:,}")
    print(f"{len(moved)} bullet(s) proposed to move to memory-archive.md")
    print(f"\nreview:  {os.path.join(d, 'memory-trim-diff.txt')}")
    print("apply:   python3 memory_trim.py apply   (backs the original up first)")
    return 0


def cmd_apply():
    """Reads the review files cmd_propose wrote. Backs path up via
    guided_apply.backup_file, writes new_text to path and archive_text to
    memory-archive.md beside it. This IS the mutate_fn passed to
    guided_apply.apply."""
    d = optimize.review_dir()
    src_file = os.path.join(d, "memory-trim-source.txt")
    prop = os.path.join(d, "memory-trim.proposed")
    archive = os.path.join(d, "memory-archive.md")
    if not (os.path.exists(src_file) and os.path.exists(prop)):
        print("NO DATA: no proposal to apply. Run without apply first.")
        return 2
    with open(src_file) as f:
        path = f.read().strip()
    if not os.path.exists(path):
        print(f"NO DATA: original {path} is gone; not applying.")
        return 2
    backup = guided_apply.backup_file(path)
    with open(prop) as f:
        new_text = f.read()
    with open(path, "w") as f:
        f.write(new_text)
    archive_dest = os.path.join(os.path.dirname(path), "memory-archive.md")
    with open(archive) as f:
        archive_text = f.read()
    with open(archive_dest, "w") as f:
        f.write(archive_text)
    print(f"applied. original backed up to {backup}")
    print(f"archive written to {archive_dest}")
    print(f"revert with: cp {backup} {path}")
    return 0


def verify_trim(original_text, path):
    """Re-runs context_lint.check(path, is_memory_index=True) and confirms
    the HIGH truncation finding is gone (or, if the file still does not fit
    because it held too few bullets to reach the target, that dropped_lines
    strictly decreased from original_text's). Returns (ok, report)."""
    before_t = context_lint.truncation_report(
        original_text, context_lint.MEMORY_MAX_LINES, context_lint.MEMORY_MAX_BYTES)
    before_dropped = before_t["dropped_lines"] if before_t else 0
    findings, stats = context_lint.check(path, is_memory_index=True)
    if not stats:
        return False, f"cannot re-read {path} to verify ({findings})"
    if not any(level == "HIGH" for level, _msg in findings):
        return True, f"index now fits its load limit ({stats['loaded_lines']} lines)"
    with open(path) as f:
        after_text = f.read()
    after_t = context_lint.truncation_report(
        after_text, context_lint.MEMORY_MAX_LINES, context_lint.MEMORY_MAX_BYTES)
    after_dropped = after_t["dropped_lines"] if after_t else 0
    ok = after_dropped < before_dropped
    report = f"dropped lines {before_dropped} -> {after_dropped}"
    if not ok:
        report += " (did not improve)"
    return ok, report


def cmd_guided_apply_trim(path):
    """The wave R entry point. Reads path's current text (for verify_trim's
    before count), then calls guided_apply.apply(label, treats=None,
    mutate_fn=cmd_apply, verify_fn=lambda: verify_trim(original, path)).
    treats=None: fingerprint_files() never includes any MEMORY.md path, so a
    memory trim cannot trip the confounder guard at all and needs no
    exclusion."""
    if not os.path.exists(path):
        print(f"NO DATA: {path} does not exist.")
        return 2
    with open(path) as f:
        original = f.read()
    label = f"memory-trim-guided-{time.strftime('%Y%m%d-%H%M%S')}"
    rc, msg = guided_apply.apply(label, None, cmd_apply,
                                 lambda: verify_trim(original, path))
    print(msg)
    return rc


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("action", nargs="?", default="propose", choices=["propose", "apply"])
    ap.add_argument("--file", default=None,
                    help="MEMORY.md path (default: this project's auto-memory index)")
    a = ap.parse_args(argv)
    path = a.file or context_lint.expected_memory_index_path()
    if a.action == "apply":
        return cmd_guided_apply_trim(path)
    return cmd_propose(path)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
