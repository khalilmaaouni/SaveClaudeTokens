#!/usr/bin/env python3
"""
config.py: the paths and constants every layer above this one reads.

WHY THIS FILE EXISTS
--------------------
Four constants and one function used to live in the wrong place, and five
modules had to reach UPWARD to get at them: `advisor`, `doctor`,
`discover_companions` and the `companions` package all imported the RENDERER
(`token_shield`) purely to read `data/companions.json`, and `guided_apply`
imported the COMMAND LINE (`cli`) purely to read two numbers. Those were the
five entries in `scripts/test_architecture.py`'s frozen list, and they were
all one cause: things that belong at the bottom of the stack were living at
the top of it.

Nothing in this module imports anything else in this repository, which is
what makes it the floor. docs/ARCHITECTURE.md states the rule it exists to
satisfy: imports point down, never up.

WHAT BELONGS HERE, AND WHAT DOES NOT
------------------------------------
Here: a path this project reads or writes, a constant more than one module
must agree on, and the smallest possible loader for a file that several
layers need before any of them can do anything.

NOT here: anything that computes a metric, decides a verdict, or renders. A
module that starts collecting behaviour because "everyone imports it anyway"
is how the renderer became a god module in the first place, which is the
mistake this file was extracted to undo. If something here grows a decision,
it has outgrown this file.
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

# Where Claude Code keeps the session transcripts every measurement in this
# project is read from. The one input path the whole tool depends on.
ROOT = os.path.expanduser("~/.claude/projects")

# Window length, in days, that BOTH cohorts of an experiment must share. A
# before cohort measured over 30 days and an after cohort measured over 7
# hold different sessions, so comparing them measures the window as much as
# the treatment; experiment.build_record downgrades on any mismatch. Shared
# rather than re-declared so the command line and the guided apply path
# cannot drift into opening experiments the ledger will refuse.
EXPERIMENT_DAYS = 30

# The curated companion registry. Read by the advisor, the doctor, the
# discovery pass and the companions package, none of which should have to
# know anything about the renderer to find it.
COMPANIONS_PATH = os.path.join(HERE, "..", "data", "companions.json")


def load_companions(path):
    """data/companions.json, or None if missing or corrupt. Never raises.

    None means NO DATA to every caller, and each one says so in its own
    words rather than falling back to a default registry: a companion this
    project cannot read about is one it must not prescribe."""
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None  # sbe: allow-silent an unreadable registry is NO DATA at every caller, which each one states, rather than a default registry that would let this project prescribe a companion it cannot read about
