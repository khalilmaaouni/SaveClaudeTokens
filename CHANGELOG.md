# Changelog

All notable changes to this project are recorded here. The format follows
Keep a Changelog. Entries are newest first.

## Unreleased

- Open integration contract v1 (unit I1): any plugin may ship
  token-shield.integration.json in its own root declaring its capabilities,
  modes, and status, version, activation and rollback commands. Discovery
  reads those declarations and labels every field DECLARED, which is not
  and never becomes CURATED: curation still requires first-party human
  verification, and a declaration can never write to data/companions.json.
  A declaration is untrusted third-party input and is treated as such: its
  every field is type-checked, a hostile or malformed declaration is
  refused by name and SKIPPED so discovery of every other plugin continues,
  oversized and deeply nested files are refused rather than raising,
  duplicate JSON keys are refused instead of silently last-wins, and an
  unreadable path yields a refusal row rather than a silent drop. Each row
  carries the cache version it came from, so an uninstalled older version's
  self-claims can never read as current. Nothing downstream consumes
  declarations yet, and the spec says so plainly.

- Companion capability suppression (unit G2): when a companion plugin you
  already run owns a capability, Token Shield stops repeating its own
  duplicate advice card for it. The guard that keeps this safe is a
  per-record metric baseline, not a band: a suppression records the metric
  value it saw, and the card returns whenever the current value is
  materially worse (REGRESSION_MARGIN, 50 percent) in whichever direction
  that strategy's own trigger operator defines as worse. A suppression is
  never silently re-armed once it lapses, sync only ever touches records it
  wrote itself (a user's own decision, accepted included, is untouchable),
  companion state older than STALE_COMPANION_STATE_DAYS (30) suppresses
  nothing, a malformed state file degrades to nothing rather than raising,
  and a strategy whose metric cannot be read right now is not suppressed at
  all, because a guard with no baseline could never lift the suppression.
  Machine suppressions are never reported as the user's own choices on the
  dashboard, and never filed under "what did not work" in the monthly
  report.

- Deep advisor (unit G3): `python3 scripts/cli.py advise --deep`. When the
  deterministic Quick Advisor cannot decide, and only then, one pinned
  Fable-tier call chooses a single treatment from data/strategies.json. It
  judges, never executes: a selection naming anything outside the registry
  is REFUSED with the reason printed, "no confident choice" produces no
  recommendation at all, and the call's cost is printed and subtracted so
  it can never inflate a saving. Deterministic first stays house law:
  without --deep, nothing changes, and with --deep the model is not called
  at all when the rules already decided. The model callable is injected, so
  no test ever makes a live call.

- Update resilience (unit U1): companion discovery now records each
  companion's version, and the doctor renders a VERSION DRIFT section
  comparing the live version against the recorded one. A companion with no
  recorded version is NO DATA, never "no drift". When an experiment is open
  and a companion version changed inside its window, the doctor prints an
  explicit spanning-experiment warning, because a companion moving
  mid-experiment is a confound the result cannot be attributed through.

- Companion adapter layer (scripts/companions/): one read-only contract with
  an adapter each for ponytail, caveman and token-saver. Every fact an
  adapter reports (status, version, modes, activation command, rollback
  command) is read from data/companions.json plus the discovery state;
  a registry entry missing an evidence field is REFUSED with the missing
  field named, never defaulted. No entry currently declares modes, so every
  adapter reports modes as NO DATA with its reason. Adapters never write.
- The Python 3.11 gate now descends into package subdirectories under
  scripts/ (it globbed scripts/*.py only, so scripts/companions/ sat outside
  the gate CI runs before the suite).

- v1.8 wave 1, part 1: companion registry schema v2 (data/companions.json now
  carries tested_version_range, hook_footprint, and last_reviewed per entry,
  hand-verified against this machine's own claude plugin output), native
  companion discovery (scripts/discover_companions.py, every row labeled
  CLAUDE PROJECTED, state written on demand only), and the read-only
  ecosystem doctor (python3 scripts/cli.py doctor: health, 180 day staleness
  threshold, shared hooks reported as facts, never as CONFLICT).

- Token Shield MCP server, wave 1 (`mcp-server/`): an opt-in, separately
  installed MCP server (stdio transport, official MCP Python SDK) wrapping
  the existing scripts as a library. Nine tools (`get_profile`,
  `get_summary`, `get_advice`, `get_monthly_report`, `list_strategies`,
  `record_decision`, `experiment_start`, `experiment_end`,
  `get_detailed_report`) and three resources (the dashboard HTML,
  `docs/METHODOLOGY.md`, `docs/CLAIMS.md`). The plugin itself gains zero
  dependencies, zero hooks, zero always-on cost. Tested against a seeded
  sandbox HOME, both write tools round-tripped, the no-blend rule asserted.
- Consumption Report, schema v1 (`scripts/detail_report.py`): one versioned
  JSON report answering where tokens go, computed from the same transcript
  data `profile.py` and `measure_tokens.py` already read (no new data
  collection). Five sections (startup_floor, subagents, cache, rhythm,
  habits) plus a bounded `daily_series`; every number carries
  `{value, label, source}`, labels never blended. Served as the new
  `get_detailed_report` MCP tool; a dashboard Habits section is out of
  scope for this change. `scripts/test_detail_report.py` added, wired into
  CI, calibrated by defect reinjection.
- Release note: the MCP server and the Consumption Report are implementation
  only in this change. Per the founder's 2026-08-13 gate amendment, no
  version tag, release, or plugin/MCP registration happens until the
  claude-md-diet experiment reaches a verdict; that boundary is unchanged.
- Experiment ledger hardening from a methodology audit (`scripts/experiment.py`):
  every record now names its per-cohort evidence scale (`sessions_before`,
  `sessions_after`, and a p90 `dispersion_before`/`dispersion_after`, None
  when the cohort is too thin for a p90); carries an explicit `direction`
  (saving, regression, or flat) so a regression can never render with the
  same shape as a saving, proven through `token_shield.verified_by_label`'s
  actual output, not just the fixture that feeds it; downgrades to
  NOT_PROVEN when the DOMINANT main-thread model (by session count, ties
  broken lexically) differs between the before and after cohort, the same
  confounder guard already applied to the config fingerprint, with a
  routine minor-version bump on one session no longer enough to trip it;
  downgrades to NOT_PROVEN, never a silent pass, when exactly one cohort
  predates main-thread model tracking entirely; and the thin-data reason
  names which side (before or after) was too thin, matching its sibling
  reasons. Calibrated tests added to `scripts/test_experiment.py` and
  `scripts/test_tools.py`, each proven red before the fix.

## 1.7.1

- Actionable Advisor: every strategy card (data/strategies.json, schema 2)
  gains a "how" field, 2 to 5 concrete steps with a real copy-paste command
  where one applies. advisor.py validates it (non-empty steps, no em or en
  dash); every rendered card on the dashboard gets a "How, exactly" block.
- Decision chips: each card carries a ready-to-copy command row (Did it,
  Not now for 90 days, Never recommend) driving the new
  `python3 scripts/cli.py advise --decide <strategy-id> <done|not-now|never>`,
  which round-trips into the existing treatment memory. The dashboard is
  static HTML, so a chip is its own command, not a button.
- Deterministic alerts band, at the top of the dashboard: fires only on a
  named MEASURED threshold (cache hit ratio median below 0.5, startup floor
  share or model-switch share above 0.5, or the meter itself reporting NO
  DATA), never on healthy data. Each alert names what it is, why it matters,
  the action, and when to act.
- Your routine: a short static section naming what already runs by itself
  monthly and the two commands to run around a config change or an
  experiment.
- Dashboard now shows only what you influence; native caching mechanics
  moved to the methodology doc. The hero is a single "What Token Shield
  verified" card; native caching is one pointer sentence to
  docs/METHODOLOGY.md, no numbers, no bars, no dollars, replacing the old
  three-column hero, the "Where the native saving comes from" bars, and the
  $401,962-style API-equivalent figure that read as hype.
- Guided command flows: `/token-shield:advisor` now shows one best card in
  plain words, asks the decision through the question UI (Do it now guided
  / Explain more first / Not now / Never), and walks accepted steps one at
  a time, handing file edits to their own yes/no question. `/token-shield:start`
  leads with three plain numbers and one hero issue before any opt-in ask,
  and acknowledges already-installed companions first.

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
