# Changelog

All notable changes to this project are recorded here. The format follows
Keep a Changelog. Entries are newest first.

## 1.5.0

- Experiment Mode: a guarded before/after measurement that writes a
  VERIFIED (or NOT_PROVEN) record to a proof ledger.
- Dashboard reworked into three confidence-labeled columns that never
  merge: Verified, Native, Opportunity, each with per-model USD.
- One CLI entry point (`python3 scripts/cli.py`) with four commands: summary,
  dashboard, experiment, prices.
- Every issue card in the dashboard carries a long-term fix, not just the
  number.
- The four confidence labels (VERIFIED, MEASURED, ESTIMATED, NATIVE) are
  now used consistently across every surface.

## 1.4.0

- Renamed the project from SaveClaudeTokens to Token Shield: repo, plugin
  id, skill, and docs all updated together.

## 1.3.x

- Provability pass: a claims register, methodology docs, the Token Shield
  dashboard, and honest attribution that separates Claude Code's own
  caching from what this tool contributes.

## 1.1.0

- Corrected the cache rules against first-party documentation.
- Made the meter honest: the 5 minute versus 1 hour TTL split, parent
  versus subagent sessions kept separate, and refusal to print a false
  delta when a comparison is not valid.

## 1.0.0

- Initial release: the token economy playbook skill plus the measurement
  script.
