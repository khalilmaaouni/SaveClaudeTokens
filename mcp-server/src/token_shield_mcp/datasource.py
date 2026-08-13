"""DataSource contract: the seam future usage-data adapters (Cursor, Codex,
deepseek, FCC) plug into, per the MCP design spec's Architecture section.
Wave 1 ships one implementation only, wrapping the existing Claude Code
transcript reader; the others are not stubbed.

Every source carries its own source_label. by_source() is the only function
in this wave that combines more than one source, and it refuses to blend
them into one figure: it keys the result by source_label instead of summing
across sources. A consumer wanting one number across sources has to make
that choice explicitly; this contract does not make it for them.
"""

from typing import Protocol

import measure_tokens as mt


class DataSource(Protocol):
    source_label: str

    def list_usage_records(self, root=None, days=30):
        ...


class TranscriptDataSource:
    """Wraps measure_tokens.collect(): this machine's Claude Code
    transcripts under ~/.claude/projects (or an explicit root)."""

    source_label = "claude-code-transcripts"

    def list_usage_records(self, root=None, days=30):
        import os
        root = root or os.path.expanduser("~/.claude/projects")
        return mt.collect(root, days)


def by_source(sources, root=None, days=30):
    """Combine multiple DataSource results, keyed by source_label. Never
    flattens two sources into one number."""
    return {s.source_label: s.list_usage_records(root=root, days=days) for s in sources}
