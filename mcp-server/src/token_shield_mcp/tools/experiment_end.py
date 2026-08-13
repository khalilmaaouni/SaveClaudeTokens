"""Tool: experiment_end(label). Compares against the pinned baseline;
refusals and NOT_PROVEN reasons returned verbatim in the captured text.
Same fresh-now_ts rule as experiment_start.py.
"""

import time

import cli
import experiment as ex

from token_shield_mcp.wrappers import call_printing


def experiment_end(label: str, root: str = None, days: float = None):
    """Compare the after cohort against label's pinned baseline and append
    one record to the ledger. root/days default the same as
    experiment_start."""
    root = root or cli.ROOT
    days = cli.EXPERIMENT_DAYS if days is None else days
    return call_printing(ex.cmd_end, label, root, days, time.time())
