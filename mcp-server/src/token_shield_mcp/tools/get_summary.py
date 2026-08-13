"""Tool: get_summary. Verified savings per label, top issue, next best move.

Per design decision 2 in docs/superpowers/plans/2026-08-13-mcp-wave1-plan.md,
this reuses cli._verified_by_label(), token_shield.savings_breakdown(sm), and
token_shield.prescriptions(sm, sessions) directly -- the same three calls
cli.summary() makes internally, scripts/cli.py:77-109 -- rather than
capturing cli.summary()'s stdout, because that text is written for a
terminal (it talks about `python3 cli.py ...` invocations) and an MCP
client should not have to parse it.
"""

import os

import cli
import measure_tokens as mt
import token_shield as ts


def get_summary(root: str = None, days: float = 30):
    """Verified savings per label (never summed across labels), the native
    caching benefit, the addressable opportunity estimate, and the single
    top issue from this user's own sessions."""
    root = root or cli.ROOT
    if not os.path.isdir(root):
        return {
            "verified": [], "native_saved": None, "opportunity_estimated": None,
            "top_issue": None, "label": "NO DATA",
            "source": f"no Claude Code transcripts found at {root}",
        }
    sessions = mt.collect(root, days)
    sm = mt.summarize(sessions)
    if not sm:
        return {
            "verified": [], "native_saved": None, "opportunity_estimated": None,
            "top_issue": None, "label": "NO DATA",
            "source": "no transcripts carried usage counters yet",
        }
    verified = [{"label": label, "floor_reduction_tokens": fr}
                for label, fr in cli._verified_by_label()]
    native_saved = ts.savings_breakdown(sm)["saved"]
    rx = ts.prescriptions(sm, sessions)
    opportunity = sum(r["saving"] for r in rx)
    top_issue = None
    if rx:
        top = max(rx, key=lambda r: r["saving"])
        top_issue = {"title": top["title"], "fix": top["painkiller"], "saving": top["saving"]}
    return {
        "verified": verified,
        "native_saved": native_saved,
        "opportunity_estimated": opportunity,
        "top_issue": top_issue,
    }
