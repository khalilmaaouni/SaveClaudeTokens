# Token Shield MCP server: design spec

Date: 2026-08-12. Status: DESIGNED, build GATED behind the first experiment verdict (the same ratified gate as v1.8). Ratified through five founder question windows this date.

## Goal

Answer "where does my token money go, and what should I do next" from ANY MCP client on the user's machine: Claude Desktop, Cursor, Codex-style agents, anything speaking MCP. The advisor journey leaves Claude Code without losing its honesty rules.

## Who it serves day one

Any MCP client on one machine, local only. No accounts, no network, no telemetry leaving the machine. The data it reads is the same data the plugin reads: this machine's Claude Code transcripts and Token Shield's own local records.

## What it exposes (wave 1, the thin mirror)

Tools, each a wrapper over an existing tested script, output shapes matching the CLI's own:

- get_profile: the deterministic usage profile (startup floor, cache behavior, model switches), labels intact.
- get_summary: verified savings per label, top issue, next best move.
- get_advice: the single best card: problem with its measured number, treatment, expected benefit with evidence label, drawback, how steps with commands.
- get_monthly_report: the month page as structured text.
- list_strategies: the full registry with citable sources.
- record_decision(strategy_id, decision): the existing treatment-memory write; echoes exactly what it recorded and when it resurfaces.
- experiment_start(label, treats), experiment_end(label): the existing guarded experiment; refusals and NOT_PROVEN reasons returned verbatim.
- get_detailed_report(window_days): the consumption report, read only; schema and sections in docs/superpowers/specs/2026-08-13-consumption-report-design.md (amendment ratified 2026-08-13).

Resources: the rendered dashboard HTML; docs/METHODOLOGY.md; docs/CLAIMS.md.

Explicitly NOT exposed: config edits of any kind, uninstall, anything touching files outside Token Shield's own store. No silent writes; the two write tools above are the entire write surface.

## Architecture

- New directory mcp-server/ in the token-shield repo: its own small package (pyproject) using the official MCP Python SDK, stdio transport. One config line installs it in any client.
- It imports the existing scripts as a library. The Claude Code plugin gains ZERO dependencies, zero hooks, zero always-on cost from this; the MCP server is a separate opt-in install, per the roadmap decision of this date.
- Data-source interface: a small DataSource contract (list_usage_records, source_label) whose first and only wave-1 implementation wraps the existing transcript reader. Future adapters (Cursor logs, Codex logs, deepseek API usage, FCC proxy counters) implement the same contract. Every number carries its source label; sources are never blended in one figure.

## Honesty rules, inherited unchanged

NATIVE is never claimed or shown as spend. RECOMMENDED is never evidence. NO DATA beats a guess. Verified savings per label, latest record wins, regressions visible, no cross-label totals. Every tool returns the underlying script's own refusal or NO DATA text verbatim; the server never invents a fallback number.

## Error handling

Tool errors surface as MCP tool errors carrying the script's message. A missing transcript root returns the profiler's own NO DATA. A malformed experiment call returns the guard's reason. Nothing retries silently; nothing degrades to an estimate without the ESTIMATED label.

## Testing

One assert-based test file in the existing calibrated style: every tool called against a seeded sandbox HOME, every write tool round-tripped, the no-blend rule asserted with two fake sources. Plus one live smoke against a real MCP client before release. The py311 gate and the dash, attribution, and secret scans apply as everywhere in this repo.

## Distribution

Same repo, released with a token-shield version tag; install documented in README as one client config block. The plugin and the MCP server version together.

## Wave 2, each item gated on evidence

- WBS cost estimator: price a planned piece of work in tokens before running it (inputs: files touched, expected turns, model tier; output: a range with assumptions, ESTIMATED). Ships only with its own calibration story.
- Research tools: query the claims register and companion registry as structured data.
- Trend analysis: month-over-month deltas as structured series.
- Additional data-source adapters (Cursor, Codex, deepseek, FCC), each landing with a verification note on what its counters actually measure.

## Effort and cost (ranges, medium confidence)

Wave 1: 2 to 4 working days after the gate opens; one sonnet builder from this spec plus orchestrator verification; roughly 150K to 400K output tokens. Assumes the MCP SDK stdio path is as documented. Wave 2 items priced individually when scheduled.

## The gate, restated

No mcp-server/ implementation file is created until the claude-md-diet experiment (running since this date) returns its verdict. VERIFIED opens the build; NOT_PROVEN routes effort to a better experiment first, per the standing law.
