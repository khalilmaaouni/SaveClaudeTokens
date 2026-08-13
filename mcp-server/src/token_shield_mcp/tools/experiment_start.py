"""Tool: experiment_start(label, treats). Pins a before baseline for the
guarded before/after experiment; refusals and NOT_PROVEN reasons returned
verbatim in the captured text, per the wrapper convention in wrappers.py.
`now_ts` is always time.time() read fresh at call time, never a cached
value, per the plan's step 10 note.
"""

import time

import cli
import experiment as ex

from token_shield_mcp.wrappers import call_printing


def experiment_start(label: str, root: str = None, days: float = None, treats: str = None):
    """Pin a baseline snapshot for label. root defaults to cli.ROOT
    (~/.claude/projects), days defaults to cli.EXPERIMENT_DAYS (30)."""
    root = root or cli.ROOT
    days = cli.EXPERIMENT_DAYS if days is None else days
    return call_printing(ex.cmd_start, label, root, days, time.time(), treats)
