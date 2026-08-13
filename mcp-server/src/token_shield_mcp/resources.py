"""Three MCP resources, per the design spec's Architecture section: the
rendered dashboard HTML, docs/METHODOLOGY.md, docs/CLAIMS.md. Read only.
The dashboard resource never regenerates the file itself (that would be a
silent write outside the two named write tools, record_decision and the
experiment_start/experiment_end pair): a missing dashboard is NO DATA,
naming the command that generates it.
"""

import os

import cli

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.normpath(os.path.join(_HERE, "..", "..", ".."))
METHODOLOGY_PATH = os.path.join(_REPO_ROOT, "docs", "METHODOLOGY.md")
CLAIMS_PATH = os.path.join(_REPO_ROOT, "docs", "CLAIMS.md")


def _read_text(path, what):
    try:
        with open(path, "r") as f:
            return f.read()
    except OSError as e:
        return f"NO DATA: {what} not readable at {path} ({e})"


def dashboard_html() -> str:
    """The rendered Token Shield dashboard, or NO DATA naming the command to
    generate it if it has not been rendered yet."""
    if not os.path.exists(cli.OUT):
        return (f"NO DATA: dashboard not generated yet. Run: "
                f"python3 scripts/cli.py dashboard (expected at {cli.OUT})")
    return _read_text(cli.OUT, "dashboard HTML")


def methodology() -> str:
    return _read_text(METHODOLOGY_PATH, "METHODOLOGY.md")


def claims() -> str:
    return _read_text(CLAIMS_PATH, "CLAIMS.md")
