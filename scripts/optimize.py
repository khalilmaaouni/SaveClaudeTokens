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
    d = review_dir()
    src_file = os.path.join(d, "source.txt")
    prop = os.path.join(d, "CLAUDE.md.proposed")
    notes = os.path.join(d, "claude-history.md")
    if not (os.path.exists(src_file) and os.path.exists(prop)):
        print("NO DATA: no proposal to apply. Run without --apply first.")
        return 2
    with open(src_file) as f:
        path = f.read().strip()
    if not os.path.exists(path):
        print(f"NO DATA: original {path} is gone; not applying.")
        return 2
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = f"{path}.bak-{stamp}"
    with open(path) as f:
        original = f.read()
    with open(backup, "w") as f:
        f.write(original)
    notes_dest = os.path.join(os.path.dirname(path), "claude-history.md")
    with open(notes) as f:
        notes_text = f.read()
    with open(notes_dest, "w") as f:
        f.write(notes_text)
    with open(prop) as f:
        new_text = f.read()
    with open(path, "w") as f:
        f.write(new_text)
    print(f"applied. original backed up to {backup}")
    print(f"history moved to {notes_dest}")
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
    """The wave R entry point. Reads path's current text (for verify_diet's
    before count), then calls guided_apply.apply(label, treats=path,
    mutate_fn=cmd_apply, verify_fn=lambda: verify_diet(original, path))."""
    if not os.path.exists(path):
        print(f"NO DATA: {path} does not exist.")
        return 2
    with open(path) as f:
        original = f.read()
    label = f"claude-md-diet-guided-{time.strftime('%Y%m%d-%H%M%S')}"
    rc, msg = guided_apply.apply(label, path, cmd_apply,
                                 lambda: verify_diet(original, path))
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
    a = ap.parse_args()
    if a.guided_apply:
        return cmd_guided_apply(a.file)
    if a.apply:
        return cmd_apply()
    return cmd_propose(a.file)


if __name__ == "__main__":
    import sys
    sys.exit(main())
