"""Tool: get_detailed_report(window_days=30). The consumption report, read
only. Thin wrapper over detail_report.build_detail_report; adds zero to the
write surface, per both specs' explicit statement.
"""

import detail_report as dr

from token_shield_mcp.wrappers import call_pure


def get_detailed_report(window_days: float = 30, root: str = None):
    """Schema v1: report_schema, generated_at, window_days, source_label,
    startup_floor, subagents, cache, rhythm, habits, daily_series."""
    return call_pure(dr.build_detail_report, root=root, window_days=window_days)
