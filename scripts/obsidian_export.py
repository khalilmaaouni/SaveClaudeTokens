#!/usr/bin/env python3
"""
obsidian_export.py: write a token dashboard as a markdown note.

OPT IN, and local only. It writes one markdown file to a path you name. It has
no network code, and it does not read or copy conversation text: it reads the
same measured counters the audit reads and writes aggregates. Point it at an
Obsidian vault, a docs folder, or anywhere else. Obsidian is a viewer here,
never a dependency.

WHAT IS IN THE NOTE
Aggregate counters, the cache write split, the subagent share, and a plain
reading of which lever the numbers support. Per-session rows are OFF by
default: transcript filenames are session identifiers, and a synced vault is a
different privacy boundary from a local disk. Pass --include-sessions if you
want them and understand where the file is going.

USAGE
  python3 obsidian_export.py --out ~/Vault/AI/Claude/TOKEN_DASHBOARD.md
  python3 obsidian_export.py --out DASH.md --days 30 --include-sessions
"""

import argparse
import importlib.util
import os
import sys
import time


def load_measure():
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location(
        "measure_tokens", os.path.join(here, "measure_tokens.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def lever(sm, mt):
    """Map the shared classification key to note-flavored wording."""
    key = mt.dominant_lever(sm)
    share = sm.get("first_request_share_median")
    hit = sm.get("hit_ratio_median")
    sub = sm.get("subagent_output_share")
    if key == "nodata":
        return ("NO DATA", "Not enough measured sessions to name a lever.")
    if key == "shrink":
        return ("Shrink the always-loaded context",
                f"The startup floor is {share:.0%} of everything read. Pruning what "
                f"loads at session start pays on every call of every session, which "
                f"no other lever does.")
    if key == "cache":
        return ("Keep the cache hot",
                f"A {hit:.2f} median hit ratio means the prefix is being rebuilt. "
                f"Look for model or effort switches, a changed toolset, or idle gaps "
                f"past the cache TTL.")
    if key == "route":
        return ("Route work deliberately",
                f"Subagents produced {sub:.0%} of output tokens. That pays when it "
                f"keeps exploration out of the parent context, and is waste when a "
                f"deterministic script would have done the job.")
    return ("No single dominant lever",
            "The measured signals are all inside their healthy ranges. Spend effort "
            "on the work rather than on the meter.")


def fmt(mt, v):
    return mt.fmt(v)


def render(mt, sm, sessions, days, include_sessions):
    name, why = lever(sm, mt)
    stamp = time.strftime("%Y-%m-%d %H:%M")
    out = [
        "# Token dashboard",
        "",
        f"Measured {stamp} over transcripts touched in the last {days:g} days. ",
        "Every figure below is read from the `usage` counters the API returned, "
        "not estimated. Absent figures read NO DATA.",
        "",
        "## Where the money goes",
        "",
        "| Measure | Value |",
        "| --- | --- |",
        f"| Sessions | {fmt(mt, sm['parent_sessions'])} |",
        f"| Subagent transcripts | {fmt(mt, sm['subagent_transcripts'])} |",
        f"| Assistant calls | {fmt(mt, sm['total_calls'])} |",
        f"| First request median | {fmt(mt, sm['first_request_median'])} tokens |",
        f"| First request p90 | {fmt(mt, sm['first_request_p90'])} tokens |",
        f"| First request share (median) | {fmt(mt, sm['first_request_share_median'])} |",
        f"| Cache hit ratio (median) | {fmt(mt, sm['hit_ratio_median'])} |",
        f"| Cache read | {fmt(mt, sm['read_total'])} |",
        f"| Cache write, 5 minute TTL | {fmt(mt, sm['write_5m_total'])} |",
        f"| Cache write, 1 hour TTL | {fmt(mt, sm['write_1h_total'])} |",
        f"| Normalized input | {fmt(mt, sm['normalized_input_total'])} base-input units |",
        f"| Output | {fmt(mt, sm['output_total'])} |",
        f"| Output from subagents | {fmt(mt, sm['subagent_output_total'])} "
        f"({fmt(mt, sm['subagent_output_share'])}) |",
        "",
        "Normalized input weights writes at 1.25x (5 minute) and 2x (1 hour) and "
        "reads at 0.1x, in base-input units. It is not a dollar figure: no model "
        "price table ships with this tool, because a stale price corrupts every "
        "later comparison.",
        "",
        "## The lever these numbers support",
        "",
        f"**{name}.** {why}",
        "",
    ]
    if include_sessions and sessions:
        out += ["## Heaviest sessions by startup cost", "",
                "| First request | Share | Calls | Hit | Models | Transcript |",
                "| --- | --- | --- | --- | --- | --- |"]
        top = sorted((s for s in sessions if s["first_request"] > 0),
                     key=lambda x: -x["first_request"])[:10]
        for s in top:
            sh = "n/a" if s["first_request_share"] is None else f"{s['first_request_share']:.3f}"
            out.append(f"| {s['first_request']:,} | {sh} | {s['calls']} | "
                       f"{s['hit_ratio']:.3f} | {s['models']} | "
                       f"`{os.path.basename(s['file'])}` |")
        out += ["", "More than one model in a session means it switched mid-flight, "
                    "which rebuilds that session's cache from zero.", ""]
    out += ["---", "", "Written by obsidian_export.py from Token Shield. "
            "Aggregates only: no conversation text, file contents, or tool output "
            "is read into this note."]
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--out", required=True, help="markdown file to write")
    ap.add_argument("--root", default=os.path.expanduser("~/.claude/projects"))
    ap.add_argument("--days", type=float, default=30)
    ap.add_argument("--include-sessions", action="store_true",
                    help="add a per-session table (transcript names identify sessions)")
    a = ap.parse_args()

    if not os.path.isdir(a.root):
        print(f"NO DATA: {a.root} does not exist.", file=sys.stderr)
        return 2

    mt = load_measure()
    sessions = mt.collect(a.root, a.days)
    sm = mt.summarize(sessions)
    if not sm:
        print("NO DATA: no transcripts carried usage counters.", file=sys.stderr)
        return 2

    out = os.path.expanduser(a.out)
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    with open(out, "w") as f:
        f.write(render(mt, sm, sessions, a.days, a.include_sessions))
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
