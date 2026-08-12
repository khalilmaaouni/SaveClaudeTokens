# Consumption Report: design spec

Date: 2026-08-13. Status: DESIGNED, build GATED behind the first experiment verdict (the same ratified gate as v1.8 and the MCP server). Ratified through seven founder question windows this date. This spec AMENDS the MCP server design of 2026-08-12 by adding one tool to its wave 1 surface; everything else in that spec stands unchanged.

## Goal

One versioned JSON report that answers "where do my tokens go, which habits cost me, and what should change", served three ways from one source of truth:

1. An MCP tool, so any MCP client or external app can read it and optimize input and output over time.
2. A Habits section in the existing dashboard, so the user sees their own wastage and patterns on demand.
3. A documented, stable schema, so other apps can build against it without guessing.

## Who it serves

The user, on this machine, wanting to understand habits and wastage. And any local app speaking MCP that wants measured usage data to make better token decisions: model tier choice, subagent fan-out budgets, treatment targeting, cost estimation. Local only, no accounts, no network, no telemetry leaving the machine, same as everything else in this repo.

## The one new module

`scripts/detail_report.py` computes the full report from the same transcript data `profile.py` and `measure_tokens.py` already read. No new data collection, no new hooks, zero always-on cost to the plugin. Companion test file `scripts/test_detail_report.py` in the existing calibrated style.

## Schema v1

Top level: `report_schema` (integer, starts at 1), `generated_at`, `window_days`, `source_label`, five sections, and `daily_series`. Every number in every section is an object `{value, label, source}` where label is one of the standing labels (VERIFIED, MEASURED, INFERRED, ESTIMATED, NATIVE) and source names the script that produced it. Consumers are told in the schema docs: labels never blend, and a sum across labels is a misuse of the data.

Sections:

1. `startup_floor`: first-request median, mean, p90, share of total spend, projected per-session cost, top contributors as reported by `context_lint.py`.
2. `subagents`: output share, call counts, sessions that fan out, fan-out cost per day.
3. `cache`: hit ratio and its trend, rebuild events (MEASURED signals from the profiler), cost per rebuild, 5 minute versus 1 hour write split.
4. `rhythm`: sessions per day, spend by hour of day and weekday, long-session tail cost, compaction events.
5. `habits`: named findings, each carrying four fields: what (the observed pattern), why it matters (the cost, with its label), the action (one concrete step), and confidence (MEASURED or INFERRED, never blank).

`daily_series`: at most `window_days` rows, one per day, each row carrying the per-dimension aggregates for that day. Bounded on purpose: aggregates plus a daily trend give external optimizers the trajectory without shipping thousands of session rows per call. Full per-session export was considered and rejected (founder decision this date): the payload is large and consumers could strip honesty labels from raw rows.

Missing data follows the house rule: the section reports NO DATA verbatim from the underlying script, never a guess, never a silent zero.

## MCP surface (the amendment)

One tool added to the MCP server's wave 1 list:

- `get_detailed_report(window_days=30)`: returns schema v1 as structured JSON, a thin wrapper over `detail_report.py`, output shape matching the script's own, refusals and NO DATA text passed through verbatim.

The MCP server design's rules apply unchanged: no config edits, no new write surface (this tool is read only), every number carries its source label, sources never blended.

## Dashboard

A new Habits section renders the same report object. Influence-only, per the ratified dashboard decision: native caching never appears as bars or dollars, one methodology pointer line. Each habit card follows the existing card grammar: the pattern, its measured cost, the one action, the confidence label.

## How it gets used to save tokens (recorded so the feature has a job, not just a schema)

- Planning time: an agent queries the report before starting work and picks model tier and subagent fan-out from measured waste. The measured subagent output share becomes a budget input instead of a guess.
- The prescribe, measure, verify loop: the habits section names one habit, Experiment Mode proves whether changing it worked. This feeds the companion ecosystem thesis already adopted in the roadmap: Token Shield prescribes and measures, companions treat.
- Companions: ponytail, caveman, and token-saver target their treatments at the dimensions the report says bleed most.
- WBS cost estimator (MCP wave 2): consumes rhythm and startup floor data for calibrated cost ranges.
- Cheap-lane routing: dispatch decisions informed by which work classes waste most on strong tiers.

## Error handling

Same posture as the MCP spec: tool errors carry the script's own message, a missing transcript root returns the profiler's NO DATA, nothing retries silently, nothing degrades to an estimate without the ESTIMATED label.

## Testing

One assert-based test file: schema validated field by field against a seeded sandbox HOME, every section exercised with data present and with data missing (NO DATA asserted verbatim), the label-blend refusal asserted, `daily_series` bound asserted at the window edge. Calibrated by defect reinjection as everywhere in this repo. The py311 gate and the dash, attribution, and secret scans apply.

## The gate, restated

No implementation file is created until the claude-md-diet experiment returns its verdict. VERIFIED opens this build inside MCP wave 1. NOT_PROVEN routes effort to a better experiment first, per the standing law.

## Effort and cost (range, medium confidence)

1 to 2 working days inside the MCP wave 1 build, roughly 80K to 200K output tokens beyond the wave 1 estimate. Assumes the profiler's data structures expose per-day timestamps as they do today.
