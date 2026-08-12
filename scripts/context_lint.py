#!/usr/bin/env python3
"""
context_lint.py: find recurring context rent before it is charged.

Everything in CLAUDE.md and in the auto-memory index is read at the start of
every session, so a line that is rarely useful is still paid for constantly.
This script measures those files and reports what it finds. It never edits or
deletes anything: the judgment of what a rule is worth is yours.

THRESHOLDS AND WHERE THEY COME FROM
Sourced to code.claude.com/docs/en/memory, read 2026-08-12:
  - CLAUDE.md: "target under 200 lines per CLAUDE.md file", and CLAUDE.md
    files are loaded in full regardless of length.
  - MEMORY.md: "The first 200 lines of MEMORY.md, or the first 25KB,
    whichever comes first, are loaded at the start of every conversation."
    Content past that is silently dropped, so this script shows you exactly
    what is falling off the end.
  - YAML frontmatter and block-level HTML comments are stripped before the
    content is loaded, so they do not count. That also makes an HTML comment
    the free place to keep maintainer notes.
  - Imports with @path are "expanded and loaded into context at launch", so
    splitting a file into imports organizes it without saving anything.

Anything this script cannot measure it says so about, rather than guessing.
Heuristic findings are labeled HEURISTIC and are prompts to look, not verdicts.

USAGE
  python3 context_lint.py                       # user CLAUDE.md, project CLAUDE.md, auto memory
  python3 context_lint.py FILE [FILE ...]       # specific files
  python3 context_lint.py --memory-index PATH   # treat PATH as a MEMORY.md index
"""

import argparse
import os
import re
import sys

CLAUDE_MD_TARGET_LINES = 200      # documented target, not a hard limit
MEMORY_MAX_LINES = 200            # documented hard load limit
MEMORY_MAX_BYTES = 25 * 1024      # documented hard load limit

FRONTMATTER = re.compile(r"\A---\r?\n.*?\r?\n---\r?\n", re.DOTALL)
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
IMPORT = re.compile(r"(?<![`\w])@([~./][^\s`]*)")
DATE = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
BULLET = re.compile(r"^\s*[-*+]\s+(.*\S)\s*$")
NUMBERED = re.compile(r"^\s*\d+[.)]\s+\S")
PATHISH = re.compile(r"(\*\*/|\S+/\S+\.\w{1,5}\b|\B\*\.\w{1,5}\b|\.\w{1,5}/)")


def loaded_content(text):
    """What Claude Code actually loads: frontmatter and block comments stripped."""
    return HTML_COMMENT.sub("", FRONTMATTER.sub("", text))


def normalize(line):
    """Collapse a bullet to its comparable core, for duplicate detection."""
    line = re.sub(r"[`*_]", "", line.lower())
    line = re.sub(r"[^a-z0-9 ]+", " ", line)
    return " ".join(line.split())


def truncation_report(text, max_lines, max_bytes):
    """Where a hard-limited index gets cut, measured on the loaded content."""
    body = loaded_content(text)
    lines = body.splitlines()
    by_line = len(lines) > max_lines
    encoded = body.encode("utf-8")
    by_bytes = len(encoded) > max_bytes
    if not (by_line or by_bytes):
        return None
    # Whichever limit bites first wins.
    cut_line = max_lines if by_line else len(lines)
    if by_bytes:
        kept, used = 0, 0
        for ln in lines:
            size = len(ln.encode("utf-8")) + 1
            if used + size > max_bytes:
                break
            used += size
            kept += 1
        cut_line = min(cut_line, kept)
    return {"cut_at_line": cut_line, "total_lines": len(lines),
            "dropped_lines": len(lines) - cut_line, "loaded_bytes": len(encoded),
            "reason": "byte limit" if by_bytes and cut_line != max_lines else "line limit"}


def check(path, is_memory_index):
    """Return (findings, stats) for one file. findings are (level, message)."""
    try:
        with open(path, "r", errors="replace") as f:
            raw = f.read()
    except OSError as e:
        return [("ERROR", f"cannot read: {e}")], None

    body = loaded_content(raw)
    lines = body.splitlines()
    stats = {"raw_bytes": len(raw.encode("utf-8")),
             "loaded_bytes": len(body.encode("utf-8")),
             "loaded_lines": len(lines)}
    out = []

    free = stats["raw_bytes"] - stats["loaded_bytes"]
    if free > 0:
        out.append(("OK", f"{free:,} bytes are frontmatter or HTML comments, "
                          f"stripped before loading and therefore free"))

    if is_memory_index:
        t = truncation_report(raw, MEMORY_MAX_LINES, MEMORY_MAX_BYTES)
        if t:
            out.append(("HIGH", f"index exceeds its documented load limit "
                                f"({MEMORY_MAX_LINES} lines or "
                                f"{MEMORY_MAX_BYTES // 1024}KB). It is cut at line "
                                f"{t['cut_at_line']} of {t['total_lines']} by the "
                                f"{t['reason']}, so {t['dropped_lines']} lines never "
                                f"reach any session. Move detail into topic files, "
                                f"which load on demand."))
        else:
            out.append(("OK", f"index fits its load limit "
                              f"({stats['loaded_lines']} lines, "
                              f"{stats['loaded_bytes']:,} bytes loaded)"))
    else:
        if stats["loaded_lines"] > CLAUDE_MD_TARGET_LINES:
            out.append(("MEDIUM", f"{stats['loaded_lines']} loaded lines against a "
                                  f"documented target of under {CLAUDE_MD_TARGET_LINES}. "
                                  f"This file loads in full on every session, so the "
                                  f"whole of it is recurring rent."))

    # Imports do not reduce context: they are expanded at launch.
    imports = IMPORT.findall(body)
    if imports:
        shown = ", ".join(sorted(set(imports))[:5])
        out.append(("INFO", f"{len(set(imports))} @import(s) load at launch and are "
                            f"paid for like inline text, so splitting does not save "
                            f"context: {shown}"))

    # Exact duplicate rules, which cost twice and can contradict each other.
    seen = {}
    dupes = []
    for i, ln in enumerate(lines, 1):
        m = BULLET.match(ln)
        if not m:
            continue
        key = normalize(m.group(1))
        if len(key) < 25:
            continue
        if key in seen:
            dupes.append((seen[key], i, m.group(1)[:60]))
        else:
            seen[key] = i
    for first, second, text in dupes[:5]:
        out.append(("MEDIUM", f"duplicate rule, lines {first} and {second}: {text}"))
    if len(dupes) > 5:
        out.append(("MEDIUM", f"and {len(dupes) - 5} more duplicate rules"))

    # A run of numbered steps is a procedure, and a procedure belongs in a
    # skill, which loads on demand instead of every session.
    run = start = 0
    procedures = []
    for i, ln in enumerate(lines, 1):
        if NUMBERED.match(ln):
            if run == 0:
                start = i
            run += 1
        else:
            if run >= 4:
                procedures.append((start, run))
            run = 0
    if run >= 4:
        procedures.append((start, run))
    for start, run in procedures[:3]:
        out.append(("HEURISTIC", f"a {run} step procedure at line {start}. Procedures "
                                 f"belong in a skill, which loads only when used."))

    # Rules that name a path or an extension usually apply to one subtree, and
    # a path-scoped rule loads only when a matching file is read. This applies
    # to instructions you write, not to an index of notes Claude wrote.
    scoped = [] if is_memory_index else [i for i, ln in enumerate(lines, 1)
                                         if BULLET.match(ln) and PATHISH.search(ln)]
    if len(scoped) >= 3:
        out.append(("HEURISTIC", f"{len(scoped)} rules name a path or an extension "
                                 f"(first at line {scoped[0]}). Those may belong in "
                                 f".claude/rules/ with paths: frontmatter, so they "
                                 f"load only when a matching file is read."))

    # Dated entries go stale, and a stale rule is rent on a fact that moved.
    dated = DATE.findall(body)
    if dated:
        oldest = min(dated)
        out.append(("INFO", f"{len(dated)} dated marker(s), oldest {'-'.join(oldest)}. "
                            f"Dated entries are worth re-reading: a rule about a "
                            f"tool's behavior can outlive the behavior."))
    return out, stats


def project_memory_index(cwd=None):
    """The auto-memory index for THIS project only.

    Auto memory lives at ~/.claude/projects/<project>/memory/, where <project>
    is the working directory path with separators replaced by dashes. Scanning
    every project's memory instead would read other projects' notes to answer a
    question about this one, which is both noisy and nobody's business here.
    """
    cwd = os.path.abspath(cwd or os.getcwd())
    slug = cwd.replace(os.sep, "-")
    path = os.path.expanduser(os.path.join("~/.claude/projects", slug, "memory", "MEMORY.md"))
    return path if os.path.isfile(path) else None


def all_memory_indexes():
    root = os.path.expanduser("~/.claude/projects")
    found = []
    if os.path.isdir(root):
        for dirpath, _dirs, files in os.walk(root):
            if os.path.basename(dirpath) == "memory" and "MEMORY.md" in files:
                found.append(os.path.join(dirpath, "MEMORY.md"))
    return sorted(found)


def default_targets(all_memory=False):
    """The files that are actually read every session, where they exist."""
    out = []
    user = os.path.expanduser("~/.claude/CLAUDE.md")
    if os.path.isfile(user):
        out.append((user, False))
    for p in ("CLAUDE.md", os.path.join(".claude", "CLAUDE.md"), "CLAUDE.local.md"):
        if os.path.isfile(p):
            out.append((os.path.abspath(p), False))
    if all_memory:
        out += [(p, True) for p in all_memory_indexes()]
    else:
        mem = project_memory_index()
        if mem:
            out.append((mem, True))
    return out


def main():
    ap = argparse.ArgumentParser(description="Report recurring context rent. Never edits.")
    ap.add_argument("files", nargs="*", help="files to check (default: the usual ones)")
    ap.add_argument("--memory-index", action="append", default=[],
                    help="treat this path as an auto-memory MEMORY.md index")
    ap.add_argument("--all-memory", action="store_true",
                    help="check every project's memory index, not just this project's")
    a = ap.parse_args()

    targets = [(os.path.abspath(f), False) for f in a.files]
    targets += [(os.path.abspath(f), True) for f in a.memory_index]
    if not targets:
        targets = default_targets(a.all_memory)
    if not targets:
        print("NO DATA: no CLAUDE.md or auto-memory index found to check.")
        return 0

    worst = 0
    for path, is_mem in targets:
        findings, stats = check(path, is_mem)
        kind = "auto-memory index" if is_mem else "always-loaded instructions"
        print(f"\n=== {path}  ({kind}) ===")
        if stats:
            print(f"    {stats['loaded_lines']:,} lines and "
                  f"{stats['loaded_bytes']:,} bytes load into every session")
        for level, msg in findings:
            if level in ("HIGH", "ERROR"):
                worst = max(worst, 2)
            elif level == "MEDIUM":
                worst = max(worst, 1)
            print(f"  [{level}] {msg}")

    print("\nNothing above was changed. Every finding is a question about whether a "
          "line earns what it costs on every call of every session; HEURISTIC ones "
          "are prompts to look, not verdicts.")
    return worst


if __name__ == "__main__":
    sys.exit(main())
