#!/usr/bin/env python3
"""server.py: Token Shield MCP server, stdio transport.

  python3 server.py                 # run the stdio server

Wraps the existing scripts/ modules as a library; see
docs/superpowers/specs/2026-08-12-token-shield-mcp-design.md. Every tool is
a thin wrapper over an already-tested script; nothing here reimplements a
metric. The Claude Code plugin gains zero dependencies, zero hooks, zero
always-on cost from this: it is a separate opt-in install (README.md, "MCP
server (optional)").
"""

import os
import sys

# scripts/ is a sibling of mcp-server/, not an installable package. Mirrors
# the relative sys.path insert every scripts/test_*.py file already uses
# (see scripts/test_profile.py:10-11), applied once here at the process
# entry point instead of scripts/ becoming a packaged dependency (that
# packaging decision is explicitly left open by
# docs/superpowers/plans/2026-08-13-mcp-wave1-plan.md step 1).
_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC_DIR = os.path.dirname(_HERE)
_SCRIPTS_DIR = os.path.normpath(os.path.join(_HERE, "..", "..", "..", "scripts"))
for _p in (_SRC_DIR, _SCRIPTS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from mcp.server.fastmcp import FastMCP  # noqa: E402

from token_shield_mcp import resources as res  # noqa: E402
from token_shield_mcp.tools import (  # noqa: E402
    experiment_end,
    experiment_start,
    get_advice,
    get_detailed_report,
    get_monthly_report,
    get_profile,
    get_summary,
    list_strategies,
    record_decision,
)

mcp = FastMCP("token-shield")

mcp.tool()(get_profile.get_profile)
mcp.tool()(get_summary.get_summary)
mcp.tool()(get_advice.get_advice)
mcp.tool()(get_monthly_report.get_monthly_report)
mcp.tool()(list_strategies.list_strategies)
mcp.tool()(record_decision.record_decision)
mcp.tool()(experiment_start.experiment_start)
mcp.tool()(experiment_end.experiment_end)
mcp.tool()(get_detailed_report.get_detailed_report)

mcp.resource("token-shield://dashboard")(res.dashboard_html)
mcp.resource("token-shield://methodology")(res.methodology)
mcp.resource("token-shield://claims")(res.claims)


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
