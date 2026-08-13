"""Tool: get_monthly_report. The month page as structured text (markdown).
Thin wrapper over report.build_report. No default month is stated in the
spec's own tool line, so this mirrors report.py's own CLI default (the
previous calendar month, report._previous_month(), scripts/report.py:64)
rather than inventing a new one.
"""

import report as rpt

from token_shield_mcp.wrappers import call_pure


def get_monthly_report(year: int = None, month: int = None, root: str = None):
    """The monthly report as markdown. year/month default to the previous
    calendar month, matching report.py's own CLI default."""
    if year is None or month is None:
        year, month = rpt._previous_month()
    return call_pure(rpt.build_report, year, month, root=root)
