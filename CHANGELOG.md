# Changelog

All notable changes to this project are recorded here. The format follows
Keep a Changelog. Entries are newest first.

## 1.7.0

- Deterministic profiler (profile.py): MEASURED signals (cache rebuilds,
  startup floor, model switches) split from INFERRED patterns (advisor
  recommendations). Every signal is now labeled with its confidence.
- Experiment Mode v2: message-timestamp cohorts and config fingerprints for
  tighter before/after matching. NOT_PROVEN downgrade when data is thin.
  Dashboard no longer sums across confidence labels.
- Quick Advisor (advisor.py + data/strategies.json): ranked action cards with
  full drawback disclosure, treatment memory for learned patterns on your
  machine, and do-nothing as a valid answer. Subagent cost printed per run.
- Companion registry (data/companions.json): curated verified sources for
  tools that pair well with Token Shield (caveman, ponytail, token-saver)
  plus a mentions list.
- Dashboard: Next Best Move card, Observed Pattern section, queue capped at
  3 items, companions panel, experiment history timeline.
- Monthly report (/token-shield:monthly, scripts/report.py): compare your
  pattern to the prior month in one page.
- Onboarding (/token-shield:start, opt-in only): users explicitly opt into
  session-end telemetry hook. No hooks by default.
- Uninstall cleanup (python3 scripts/cli.py uninstall): prints what exists,
  asks before removing, reports verified savings to keep. No trace after.
- Meter honesty: skipped files and lines now counted and reported in meter
  output so you see what the meter actually saw.
- Verification sweep (docs/CLAIMS.md section D): one claim refuted and
  removed (fast-mode transcript observability). Remaining claims re-checked.
- Adversarial review hardening (docs/CLAIMS.md section E): experiment cli
  routing fixed (crashed on both start and end); legacy v1.6 baselines now
  refuse the v2 guards honestly (NOT_PROVEN with reason, never VERIFIED);
  verified savings reported per label with regressions visible, never summed
  across labels or clipped to zero; both cohorts must meet the minimum
  session count; config fingerprint widened to ~/.claude.json and the skills
  tree as a sha256 manifest, with any --treats exclusion printed, never
  silent; half-open cohort and month boundaries; startup floor taken only
  from true session starts; experiment labels HTML-escaped; effort values
  whitelisted before landing in profile.json; a Python 3.11 tokenizer gate
  added to CI; advisor sources rendered as citable pointers into
  docs/CLAIMS.md.

## 1.6.0

- Safe, reversible CLAUDE.md optimizer (scripts/optimize.py and the
  /token-shield:optimize command). It proposes a diet that moves long dated
  history and rationale to a notes file and keeps every hard rule, shows the
  before and after token estimate, the section-cost map, and the diff, and
  applies only on an explicit yes, backing the original up first. It never
  edits CLAUDE.md silently and never on install.
- New /token-shield:stats command: the quick honest summary (verified, native,
  opportunity) plus the top issue.

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
