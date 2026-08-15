# Token Shield: the 14 day leadership WBS, three windows

## CORRECTED 2026-08-15 late, after an independent evidence audit

Three corrections, kept visible here rather than edited in silently, following
the precedent set by the field map correction in pull request 83. A plan that
quietly repairs itself teaches nobody anything.

1. **T10.1's done-check was unrunnable as written.** It chained the CLAUDE.md
   full test line and the MCP install in one breath. That line begins
   `python3 scripts/check_py311.py && cd scripts && ...` and never returns, so
   the shell is left in `scripts/`, where `./mcp-server` does not exist. CI
   never hit it because CI runs the two as separate steps from the repository
   root. Fixed in the T10.1 and T10.2 rows below. Method defect: the done-check
   was assembled by concatenating two commands that were each known to work,
   without running the concatenation.

2. **"Zero connectors" and "no export of any kind" were false.**
   `scripts/obsidian_export.py` exists, is registered as a layer 7 module in
   `test_architecture.py`, and writes markdown with an `--out` flag. What is
   genuinely absent is a MACHINE READABLE export: no CSV, no webhook, and no
   `csv` import anywhere under `scripts/` or `mcp-server/`. E7 is unchanged,
   because CSV is still the missing thing. What changes is E1: obsidian_export
   is not routed through `cli.py`, so it is a SIXTH front door, and the epic
   that exists to make five doors into one was counting five.

3. **The count in "three modules each overwrite one hash file" was wrong.** It
   is two modules across three files: `optimize.py` at lines 175 and 369, and
   `memory_trim.py` at line 128. `plugin_prune.py:142` overwrites a bundle
   JSON, not a hash file. E6 is unaffected; the journal is still absent.

Written 2026-08-15 evening. Governs 2026-08-15 through 2026-08-28.
Compresses the founder's 45 day plan (TOKEN_SHIELD_CLAUDE_LEADERSHIP_WBS.md)
into 14 days of parallel agent work. The release gate stays live the whole
time: nothing here tags, releases, publishes, or registers anything. We build
the product that ships the day the claude-md-diet-v2 verdict lands, near
2026-09-13.

## 1. The reordering argument

The founder's plan runs bottom up: five days of truth reset, five of evidence
fabric, five of waste map, five of treatments, five of proof engine, and the
user does not see a screen until days 26 to 30. That order is right for a
product whose engine is unproven. Ours is not: the independent audit of all 29
non-test modules concluded it "reads like a rigorously audited proof engine
with five separate, unfinished front doors." The tournament selector, the
HISTORICAL drift check, the from-scratch reconciler, the org aggregation with
its five machine floor, the guided apply contract: built, tested, green on
merged main (525 checks, exit 0). What is missing is coherence and surface:
the org rollup no command reaches, a PROVING state no screen shows, a live
surface that does not exist, an install minute nobody has scripted, and zero
connectors. So this plan inverts the founder's order: surfaces first (what a
user sees in minute one), coherence second (one front door), fabric third
(sensors, journal, export). Two further reasons the inversion is safe: first,
about a third of the founder's plan re-plans things the audit shows already
built (reconciliation, HISTORICAL, the tournament, rollback previews), and
compressing 45 days into 14 means refusing to rebuild them; second, the
release gate forbids shipping anything until the experiment verdict anyway,
so these 14 days are worth the most when they finish the doors, not when they
deepen an engine that already passed its audit.

## 2. The north star, and the four things a user must be able to do

The loop is MEASURE, DIAGNOSE, TREAT, PROVE, LEARN, and the sentence is:
"I know how you use Claude. I know what is costing you. I know which change
is worth making. I know which plugin is worth running. And I can prove
whether it actually helped you."

By 2026-08-28 a user must be able to do these four things, each testable:

1. **Install in two commands and understand their own usage inside sixty
   seconds.** They type the marketplace add and the install command, run the
   start journey, and the first screen is one hero number, one sentence of
   diagnosis, one recommended action. Timed against a fixture corpus.
2. **Glance down at any moment and see where they stand, for zero tokens.**
   A status line shows context fullness, weekly limit remaining when the
   fields exist, and a PROVING marker when a trial is running. It is the only
   live surface Claude Code allows a plugin, and it costs nothing.
3. **Open one front door and see exactly one of four states.** HEALTHY,
   OPPORTUNITY, PROVING, VERIFIED: one state, one reason, and every other
   view (monthly report, org page, detail, MCP) reachable from it. PROVING,
   invisible anywhere in the product today, gets its screen.
4. **Leave, and undo, freely.** One command exports every number to CSV with
   its confidence label on the row, and one command reverts any change Token
   Shield ever made, byte identical, from an append-only journal.

## 3. The epics

| ID | Title | User value (one sentence) | Gate it must pass | Window |
|---|---|---|---|---|
| E1 | One front door | Every number the product computes is reachable from cli.py and linked from the dashboard, instead of five separate unfinished entrances. | Full suite green; `cli.py fleet dashboard` writes the org page; dashboard links every surface or says NO DATA. | W2, tail in W3 |
| E2 | The four state command center | The user opens the product and sees exactly one of HEALTHY, OPPORTUNITY, PROVING, VERIFIED, including the proof currently running. | Fixture with an open experiment renders PROVING; A6 finds zero critical state and label confusions. | W2 |
| E3 | The status line | A zero token live readout of context, weekly limit, and running proofs sits under every session, always there. | Documented fixture payloads render correctly; absent fields degrade to nothing; never crashes. | W2 |
| E4 | The first sixty seconds | A brand new user gets from two install commands to one honest hero number in under a minute. | Timed smoke on a fixture corpus passes inside 60 seconds; README quickstart commands verified against docs. | W2 |
| E5 | Silent evidence sensors | Once the user opts in, experiments notice config changes, compactions and subagent activity automatically, at zero token cost. | Red then green tests; zero stdout from silent events; a mid window config change downgrades a verdict. | W3 |
| E6 | The journal and one command undo | Any change Token Shield made can be reverted with one command, and the record of every mutation survives forever. | Mutate then undo round trips byte identical; A9 safety review with veto passes. | W3 |
| E7 | The first connector: CSV export | The user hands their numbers to a spreadsheet or FinOps pipeline in one command, labels intact, no cross label totals possible. | Export test proves no total row across labels exists and every row carries a label. | W3 |
| E8 | Competitive honesty close out | Nobody reading our docs is told something false about an alternative tool. | PR 83 merged; corrected threat 4 visible on main. | W1, tonight |
| E9 | Selector Lab seed | The user can trust the one recommended action because the selector is benchmarked against known correct profiles, starting with three. | Healthy profile returns do_nothing; A6 fairness review finds no hand tuned answer leak. | W3 |

Parking lot (could not name user value inside 14 days): everything in
section 8.

## 4. The task table

Notes that apply to every row: every code PR follows branch plus pull
request, founder merges by hand, and the three fail closed scans run over the
whole pushed range before any push. Every fix style change carries a test
calibrated red by reinjecting the defect before going green. NEW files
declare their layer in scripts/test_architecture.py's LAYERS in the same PR,
and NEW test suites are added to .github/workflows/ci.yml and to CLAUDE.md's
documented test line in the same PR. "Files forbidden" lists the contended
files nearest the task; everything not owned is untouchable by default.

### E8 and W1 groundwork

| ID | Task | Owner | Model | Depends on | Files owned | Files forbidden | Deliverable | Done-check |
|---|---|---|---|---|---|---|---|---|
| T8.1 | Close the field map correction: verify the corrected threat 4 and the CodeBurn row (already present in the local tree), run the dash and attribution scans over the PR 83 range, hand to the founder to merge | A0 | opus | none | docs/research/2026-08-15-competitive-field-map.md (verify only, no edit) | everything else | PR 83 merged | `grep -n "CORRECTED 2026-08-15" docs/research/2026-08-15-competitive-field-map.md` prints the threat 4 correction line on main after the merge, exit 0 |
| T2.0 | State model memo: define the four states from existing primitives only (advisor.advise result, experiment.list_open_experiments, the verified rows metrics already computes) with a total priority order so exactly one state can ever render | A2 | opus | none | NEW: docs/plan/2026-08-15-STATE-MODEL.md (docs, no layer) | scripts/ | ratified memo | `grep -c "wins over" docs/plan/2026-08-15-STATE-MODEL.md` prints 3 or more: one explicit tiebreak per pair of simultaneously true states |
| T0.1 | Write the Day 1 task packets for T2.1 and T4.2 in the founder plan's section 19 packet format, standalone briefs a subagent can execute without this conversation | A0 | opus | T2.0 | NEW: docs/plan/packets/ (docs) | scripts/ | two packets | `ls /Users/khalil.maaouni/SaveClaudeTokens/docs/plan/packets/ | wc -l` prints 2 or more |

### E2: the four state command center

| ID | Task | Owner | Model | Depends on | Files owned | Files forbidden | Deliverable | Done-check |
|---|---|---|---|---|---|---|---|---|
| T2.1 | command_center_state() in metrics.py: a pure layer 1 function, no markup, returning one of HEALTHY, OPPORTUNITY, PROVING, VERIFIED plus a one line reason, exactly per the T2.0 order; red tests first by fixture | A3 | sonnet | T2.0 | scripts/metrics.py, scripts/test_tools.py | scripts/token_shield.py, scripts/advisor.py, scripts/cli.py | PR | `cd /Users/khalil.maaouni/SaveClaudeTokens/scripts && python3 test_tools.py` prints ok test_state_proving_beats_opportunity and ok test_state_healthy_when_do_nothing and exits 0, and `python3 test_architecture.py` exits 0 proving no markup entered layer 1 |
| T2.2 | The four state header and the PROVING panel in token_shield.py: open experiment label, day n of m, and a "keep this stable" list built from the experiment record's fingerprint fields | A8 | sonnet | T2.1 | scripts/token_shield.py, scripts/test_tools.py | scripts/metrics.py, scripts/experiment.py, scripts/cli.py | PR | `cd /Users/khalil.maaouni/SaveClaudeTokens/scripts && python3 test_tools.py` prints ok test_dashboard_renders_proving_panel against a fixture with an open experiment, exits 0 |
| T2.3 | The state line in the terminal: cli.py summary prints STATE: <state> (<reason>) as its first line, read through the same metrics function, never recomputed | A8 | sonnet | T2.1, T2.2 merged | scripts/cli.py, scripts/test_tools.py | scripts/metrics.py, scripts/token_shield.py | PR | `cd /Users/khalil.maaouni/SaveClaudeTokens/scripts && python3 test_tools.py` prints ok test_summary_first_line_is_state, exits 0 |
| T2.4 | Adversarial review: try to confuse the four states with the five confidence labels in wording, color, or adjacency, on the rendered fixtures | A6 | opus | T2.2, T2.3 | NEW: docs/plan/reviews/2026-08-20-state-label-review.md | all of scripts/ (read only) | verdict note | `grep -n "CRITICAL FINDINGS: 0" docs/plan/reviews/2026-08-20-state-label-review.md` prints the verdict line, or every finding carries a task ID and the tasks are scheduled before window close |

### E3: the status line

| ID | Task | Owner | Model | Depends on | Files owned | Files forbidden | Deliverable | Done-check |
|---|---|---|---|---|---|---|---|---|
| T3.1 | NEW scripts/statusline.py (layer 7) plus its test suite: read the documented stdin JSON, print one line carrying context used percent, weekly limit percent when the rate_limits fields are present, and a PROVING marker when experiment.list_open_experiments is nonempty; absent fields print nothing; malformed stdin prints nothing and exits 0 | A3 | sonnet | T2.1 | NEW: scripts/statusline.py (layer 7), NEW: scripts/test_statusline.py, scripts/test_architecture.py (LAYERS entry), .github/workflows/ci.yml, CLAUDE.md (test line) | scripts/cli.py, scripts/token_shield.py, commands/ | PR | `cd /Users/khalil.maaouni/SaveClaudeTokens/scripts && python3 test_statusline.py` prints ok test_absent_rate_limits_degrade and ok test_open_experiment_prints_proving_marker and ok test_malformed_stdin_exits_zero, exits 0 |
| T3.2 | The wiring step: an opt in question in commands/start.md offering the settings.json statusLine entry (a plugin cannot install one; the script ships under the plugin root and the user adds one line), explicit yes before any edit, instructions only if D1 is unanswered; docs/TELEMETRY.md documents removal | A8 | sonnet | T3.1, D1 | commands/start.md, docs/TELEMETRY.md | scripts/, .claude-plugin/plugin.json | PR | `grep -n "statusLine" /Users/khalil.maaouni/SaveClaudeTokens/commands/start.md` prints the opt in step containing the explicit yes rule |

### E1: one front door

| ID | Task | Owner | Model | Depends on | Files owned | Files forbidden | Deliverable | Done-check |
|---|---|---|---|---|---|---|---|---|
| T1.1 | cli fleet routing: cli.py gains a fleet command (subcommands dashboard, join, record) that subprocesses to fleet_dashboard.py and fleet.py exactly as the existing optimize and prune commands subprocess to theirs; no new fleet behavior, wiring only | A4 | sonnet | T2.3 merged (cli.py free), D2 | scripts/cli.py, scripts/test_tools.py | scripts/fleet.py, scripts/fleet_dashboard.py | PR | `cd /Users/khalil.maaouni/SaveClaudeTokens/scripts && python3 test_tools.py` prints ok test_cli_fleet_dashboard_routes, exits 0 |
| T1.2 | Dashboard cross links: token_shield.py links the monthly report file and the fleet page when each exists on disk, and prints a NO DATA line naming the exact command that produces each when absent | A8 | sonnet | T2.2 merged | scripts/token_shield.py, scripts/test_tools.py | scripts/report.py, scripts/fleet_dashboard.py, scripts/cli.py | PR | `cd /Users/khalil.maaouni/SaveClaudeTokens/scripts && python3 test_tools.py` prints ok test_dashboard_absent_fleet_page_is_no_data, exits 0 |
| T1.3 | MCP org rollup: a new MCP tool get_fleet_summary reading the fleet store read only through fleet_dashboard's aggregation, with the MIN_GROUP_MACHINES floor clamped exactly as render() clamps it, and the withheld remainder rule intact | A4 | sonnet | T1.1 merged, A9 beside | NEW: mcp-server/src/token_shield_mcp/tools/get_fleet_summary.py, mcp-server/src/token_shield_mcp/server.py, mcp-server/test_mcp_server.py | scripts/fleet_dashboard.py | PR | `cd /Users/khalil.maaouni/SaveClaudeTokens/mcp-server && python3 test_mcp_server.py` prints ok test_get_fleet_summary_respects_min_group, exits 0 |
| T1.4 | README front door map: one section naming every surface (dashboard, monthly report, fleet page, MCP, export, status line) and the single command that reaches each | A11 | haiku | T1.1, T1.2 merged | README.md | scripts/ | PR | `grep -n "fleet" /Users/khalil.maaouni/SaveClaudeTokens/README.md` prints the map section naming the cli fleet command |

### E4: the first sixty seconds

| ID | Task | Owner | Model | Depends on | Files owned | Files forbidden | Deliverable | Done-check |
|---|---|---|---|---|---|---|---|---|
| T4.1 | Install smoke: a new test suite that runs trial.py against a generated fixture corpus and asserts the hero lines appear and the run completes inside 60 seconds | A7 | sonnet | none | NEW: scripts/test_install_smoke.py, .github/workflows/ci.yml, CLAUDE.md (test line) | scripts/trial.py | PR | `cd /Users/khalil.maaouni/SaveClaudeTokens/scripts && python3 test_install_smoke.py` prints ok test_first_screen_under_60_seconds, exits 0 |
| T4.2 | First screen wording: trial.py output and start.md step 2 lead with one hero number and one action in plain language, jargon out, every label kept exactly as labeled | A8 | sonnet | none | scripts/trial.py, commands/start.md | scripts/measure_tokens.py, scripts/token_shield.py | PR | `cd /Users/khalil.maaouni/SaveClaudeTokens/scripts && python3 test_trial.py` exits 0 after the wording change, and T4.1's smoke passes against the new wording |
| T4.3 | README quickstart: the exact two install commands (marketplace add, then /plugin install), the zip archive source alternative, and the sixty second script of what the user sees, every command string verified against the current docs by A1 before it is written | A11, facts by A1 | haiku | T4.2 | README.md | scripts/, commands/ | PR | `grep -n "/plugin install" /Users/khalil.maaouni/SaveClaudeTokens/README.md` prints the quickstart install line |

### E5: silent evidence sensors

| ID | Task | Owner | Model | Depends on | Files owned | Files forbidden | Deliverable | Done-check |
|---|---|---|---|---|---|---|---|---|
| T5.1 | NEW scripts/lifecycle_sensor.py (layer 0): one silent script for SessionStart, ConfigChange, PreCompact, PostCompact, SubagentStart, SubagentStop; switches on hook_event_name from the stdin payload, appends one JSON line per event to ~/.token-shield/lifecycle.jsonl, writes nothing to stdout (these events are silent to the model and must stay that way), always exits 0 | A3 | sonnet | none (W3 start) | NEW: scripts/lifecycle_sensor.py (layer 0), NEW: scripts/test_lifecycle_sensor.py, scripts/test_architecture.py (LAYERS entry), .github/workflows/ci.yml, CLAUDE.md (test line) | scripts/session_end_telemetry.py, scripts/signals.py | PR | `cd /Users/khalil.maaouni/SaveClaudeTokens/scripts && python3 test_lifecycle_sensor.py` prints ok test_unknown_event_still_exits_zero and ok test_writes_no_stdout, exits 0 |
| T5.2 | signals.py rolls up the lifecycle log: compaction counts split manual and auto, config changes per day, subagent starts per day; an absent log is a NO DATA row, never a guess | A3 | sonnet | T5.1 merged | scripts/signals.py, scripts/test_signals.py, data/signals.schema.json | scripts/fleet.py, scripts/experiment.py | PR | `cd /Users/khalil.maaouni/SaveClaudeTokens/scripts && python3 test_signals.py` prints ok test_lifecycle_rollup_counts_manual_and_auto_compacts, exits 0 |
| T5.3 | Mid window config drift downgrades a verdict: experiment close consults the lifecycle log when present; a ConfigChange inside the window that the endpoint fingerprint comparison cannot see (changed then reverted) downgrades the verdict to NOT_PROVEN with the drift named in the reason; absent log changes nothing | A2 | opus | T5.1 merged | scripts/experiment.py, scripts/test_experiment.py | scripts/advisor.py, scripts/metrics.py | PR | `cd /Users/khalil.maaouni/SaveClaudeTokens/scripts && python3 test_experiment.py` prints ok test_mid_window_config_change_downgrades_to_not_proven, exits 0 |
| T5.4 | Sensor wiring step in onboarding: one opt in question adds the lifecycle entries to settings.json on an explicit yes, per D3; docs/TELEMETRY.md documents exactly what is written where and how to remove it | A8 | sonnet | T5.1, T5.2 merged, D3 | commands/start.md, docs/TELEMETRY.md | scripts/ | PR | `grep -n "lifecycle_sensor" /Users/khalil.maaouni/SaveClaudeTokens/commands/start.md /Users/khalil.maaouni/SaveClaudeTokens/docs/TELEMETRY.md` prints the opt in step in both files |
| T5.5 | Claude Code version on evidence: capture the installed CLI version (subprocess to the claude binary's version flag; an absent binary records NO DATA) on experiment baselines and closed records; a version difference between start and end becomes a named reason in metrics._historical_check, closing the gap metrics.py line 307 states outright | A3 | sonnet | T5.3 merged (experiment.py free) | scripts/experiment.py, scripts/metrics.py, scripts/test_experiment.py, scripts/test_tools.py | scripts/token_shield.py | PR | `cd /Users/khalil.maaouni/SaveClaudeTokens/scripts && python3 test_experiment.py` prints ok test_version_drift_names_historical_reason, exits 0 |

### E6: the journal and one command undo

| ID | Task | Owner | Model | Depends on | Files owned | Files forbidden | Deliverable | Done-check |
|---|---|---|---|---|---|---|---|---|
| T6.1 | Append only mutation journal: guided_apply appends one line per applied mutation (timestamp, target path, pre hash, backup path, producer) to ~/.token-shield/mutations.jsonl; the per proposal .sha256 files stay, but nothing is ever overwritten again | A4 | sonnet | none (W3 start) | scripts/guided_apply.py, scripts/test_guided_apply.py | scripts/optimize.py, scripts/memory_trim.py, scripts/plugin_prune.py | PR | `cd /Users/khalil.maaouni/SaveClaudeTokens/scripts && python3 test_guided_apply.py` prints ok test_second_mutation_appends_never_overwrites, exits 0 |
| T6.2 | One command undo: cli.py undo restores the newest journaled mutation from its backup, verifies the restored bytes against the journaled pre hash, refuses with a named reason when the backup is missing, and appends the undo itself to the journal | A4 | sonnet | T6.1 | scripts/guided_apply.py, scripts/cli.py, scripts/test_guided_apply.py, scripts/test_tools.py | scripts/experiment.py | PR | `cd /Users/khalil.maaouni/SaveClaudeTokens/scripts && python3 test_guided_apply.py` prints ok test_undo_restores_byte_identical_and_journals_itself, exits 0 |
| T6.3 | Safety review of journal and undo: wrong file restored, journal truncation mid write, undo while an open experiment depends on the mutated state | A9 | opus | T6.2 | NEW: docs/plan/reviews/2026-08-26-undo-safety-review.md | scripts/ (read only) | verdict note, veto right | `grep -n "CRITICAL FINDINGS: 0" docs/plan/reviews/2026-08-26-undo-safety-review.md` prints the verdict line, or the veto stands and T6.2 does not merge |

### E7: the first connector

| ID | Task | Owner | Model | Depends on | Files owned | Files forbidden | Deliverable | Done-check |
|---|---|---|---|---|---|---|---|---|
| T7.1 | NEW scripts/export.py (layer 7): CSV of daily counters and the proof ledger, one confidence label column on every row, no total row across labels anywhere, stdout by default with a --out flag; cli.py export routes to it by the existing subprocess pattern | A4 | sonnet | T6.2 merged (cli.py free), D5 | NEW: scripts/export.py (layer 7), NEW: scripts/test_export.py, scripts/test_architecture.py (LAYERS entry), scripts/cli.py, scripts/test_tools.py, .github/workflows/ci.yml, CLAUDE.md (test line) | scripts/metrics.py, scripts/measure_tokens.py | PR | `cd /Users/khalil.maaouni/SaveClaudeTokens/scripts && python3 test_export.py` prints ok test_no_cross_label_total_row and ok test_every_row_carries_a_label, exits 0 |
| T7.2 | Connector position note: NEW docs/CONNECTORS.md stating why CSV is first and that OpenTelemetry is attributed to Anthropic's own export per docs/ATTRIBUTION.md, with the flip condition for building any push connector | A11, facts by A1 | haiku | T7.1 | NEW: docs/CONNECTORS.md, README.md | scripts/ | PR | `grep -n "ATTRIBUTION" /Users/khalil.maaouni/SaveClaudeTokens/docs/CONNECTORS.md` prints the attribution line |

Why CSV first, decided here rather than surveyed: it is the only connector
buildable under the laws as they stand. Zero dependencies (stdlib csv), zero
network in the single machine path (a webhook or OTel push violates law 5),
universally ingestible by every analytics and FinOps tool the founder named,
and it carries the one thing Anthropic's own OpenTelemetry export does not:
our labels and verdicts. CodeBurn ships CSV export; we ship CSV export with
provenance. OTel remains attributed, not competed with.

### E9: selector Lab seed

| ID | Task | Owner | Model | Depends on | Files owned | Files forbidden | Deliverable | Done-check |
|---|---|---|---|---|---|---|---|---|
| T9.1 | Lab seed: three profile fixtures (healthy, startup context heavy, memory bloat) under a new bench directory, and a new bench suite asserting advisor.advise top 1 on each, with the healthy profile required to return do_nothing | A7 | sonnet | none (W3) | NEW: bench/selector_profiles/ (three JSON fixtures), NEW: bench/test_selector_bench.py, .github/workflows/ci.yml, CLAUDE.md (test line) | scripts/advisor.py | PR | `python3 /Users/khalil.maaouni/SaveClaudeTokens/bench/test_selector_bench.py` prints ok test_healthy_profile_returns_do_nothing, exits 0 |
| T9.2 | Fairness review of the seed: no fixture hand tuned to the selector's known tiebreaks, no answer leak from advisor internals into fixture construction | A6 | opus | T9.1 | NEW: docs/plan/reviews/2026-08-27-lab-seed-review.md | bench/ (read only) | verdict note | `grep -n "CRITICAL FINDINGS: 0" docs/plan/reviews/2026-08-27-lab-seed-review.md` prints the verdict line |

### Integration

| ID | Task | Owner | Model | Depends on | Files owned | Files forbidden | Deliverable | Done-check |
|---|---|---|---|---|---|---|---|---|
| T10.1 | Window 2 integration: the full documented suite plus the MCP suite and the bench run on the integration branch after the last W2 merge; fixes only, each signed off by A0, no redesign | A10 | sonnet | all W2 tasks merged | integration branch only | production files except A0 signed fixes | quoted green run | three SEPARATE commands, each started from the repository root, never chained (see correction 1 at the top of this file): (a) the CLAUDE.md full test line; (b) `cd /Users/khalil.maaouni/SaveClaudeTokens && python3 -m pip install ./mcp-server && cd mcp-server && python3 test_mcp_server.py`; (c) `cd /Users/khalil.maaouni/SaveClaudeTokens && python3 bench/test_bench.py && python3 bench/generate_corpus.py --out /tmp/bench-corpus && python3 bench/run_benchmark.py --corpus /tmp/bench-corpus`. All three exit 0, output quoted in the integration PR |
| T10.2 | Window 3 integration and close out: same commands, plus the close note naming everything UNVERIFIED with its blocker | A10 | sonnet | all W3 tasks merged | integration branch only | production files except A0 signed fixes | quoted green run plus close note | the same three separate commands as T10.1, each exit 0, output quoted; the close note lists each UNVERIFIED item with its blocker |

No task in this table is NEEDS SCOPING. The one that came closest, T5.5, was
scoped by deciding the semantics here: what is captured is the installed CLI
version at check time, labeled as exactly that, because no documented field
exposes the version that ran a past session.

## 5. Window 1: TODAY, 2026-08-15 evening

A partial evening, three items, no production code. Estimates are wall clock
with agents running.

- **T8.1** (A0): PR 83 verification and hand off to the founder for merge.
  The corrected threat 4 text is already in the local tree; the work is the
  three fail closed scans over the pushed range and the founder's click.
  0.5 to 1 hour, high confidence, assumes PR 83's branch matches the local
  file.
- **T2.0** (A2): the state model memo. This is the keystone decision of the
  whole fortnight and it is cheap tonight: four states, every pairwise
  tiebreak written down (the working default: PROVING wins over OPPORTUNITY
  because stability during a trial outranks a new suggestion; VERIFIED renders
  only when no experiment is open and an unacknowledged verdict exists;
  HEALTHY is the floor). 1 to 2 hours, medium confidence, assumes
  advisor.advise and list_open_experiments outputs suffice, which today's
  read of both signatures supports.
- **T0.1** (A0): the two Day 1 task packets, written from the memo. 0.5 to 1
  hour, high confidence.

Nothing else tonight. An evening that ends with the state model ratified and
tomorrow's packets written is a good evening.

## 6. Window 2: THIS WEEK, 2026-08-16 to 2026-08-21

Two writing lanes maximum, named per day. A7 preparing tests beside the lanes
is the founder plan's own allowance (section 9) and its files never overlap a
lane's files on the same day. Reviewers are read only. Estimate for the
window: 11 tasks of 0.5 to 1.5 days each across two lanes, medium confidence,
assuming test_tools.py remains the home of metrics and renderer tests
(confirmed by grep today) and no CI surprises.

- **Aug 16 (Sat).** Lane 1: A3 on T2.1 (metrics state function). Lane 2: A8
  on T4.2 (first screen wording). Beside: A1 verifies the install command
  strings for T4.3 against the docs; A6 reads the T2.0 memo cold. Exit gate:
  T2.1 and T4.2 done-checks green, PRs open.
- **Aug 17 (Sun).** Lane 1: A8 on T2.2 (PROVING panel; token_shield.py).
  Lane 2: A3 on T3.1 (statusline script and suite). Beside: A7 starts T4.1
  (its files are all NEW and disjoint). Exit gate: T3.1 done-check green;
  T2.2 red tests written and turning green.
- **Aug 18 (Mon).** Lane 1: A8 on T2.3 (cli state line; needs T2.2 merged in
  the morning). Lane 2: A7 closes T4.1 (smoke into CI). Beside: A6 begins
  T2.4 on the rendered fixtures. Exit gate: T2.3 and T4.1 done-checks green.
- **Aug 19 (Tue).** Lane 1: A4 on T1.1 (cli fleet routing; cli.py is free
  once T2.3 merged; D2 assumed default). Lane 2: A8 on T3.2 (statusline
  wiring step; D1 assumed default if unanswered). Beside: A9 reads the
  statusline payload boundary (rate limit data stays local, nothing leaves
  disk). Exit gate: T1.1 done-check green.
- **Aug 20 (Wed).** Lane 1: A8 on T1.2 (dashboard cross links). Lane 2: A11
  on T4.3 and T1.4 (README quickstart and front door map, mechanical).
  Beside: A6 delivers the T2.4 verdict. Exit gate: T1.2 green; T2.4 verdict
  line quoted, or its findings scheduled.
- **Aug 21 (Thu).** Integration day, no new features. A10 runs T10.1 on the
  integration branch; A0 reviews the window against this document and
  refreshes the progress page. Exit gate: the full documented suite, the MCP
  suite and the bench all exit 0, output quoted.

## 7. Window 3: NEXT WEEK, 2026-08-22 to 2026-08-28

Same shape. Estimate: 12 tasks of 0.5 to 1.5 days each, medium confidence,
the main assumption being that the lifecycle payloads observed live match the
documented common payload (checked on day one of the window).

- **Aug 22 (Fri).** Lane 1: A3 on T5.1 (lifecycle sensor). Lane 2: A4 on
  T6.1 (mutation journal). Beside: A2 drafts the T5.3 downgrade rule against
  experiment.py's real close path. Exit gate: T5.1 and T6.1 done-checks
  green.
- **Aug 23 (Sat).** Lane 1: A3 on T5.2 (signals rollup). Lane 2: A4 on T6.2
  (cli undo). Beside: A9 starts T6.3. Exit gate: T5.2 green; T6.2 red tests
  written.
- **Aug 24 (Sun).** Lane 1: A2 on T5.3 (mid window drift downgrade, narrow
  write). Lane 2: A4 closes T6.2. Beside: A7 prepares the T9.1 fixture
  shapes on paper against data/strategies.json. Exit gate: T5.3 and T6.2
  done-checks green.
- **Aug 25 (Mon).** Lane 1: A3 on T5.5 (version capture; experiment.py free
  after T5.3 merges). Lane 2: A4 on T7.1 (export connector; cli.py free
  after T6.2 merges). Beside: A9 delivers the T6.3 verdict; veto blocks the
  T6.2 merge if critical. Exit gate: T5.5 green; T6.3 verdict quoted.
- **Aug 26 (Tue).** Lane 1: A8 on T5.4 (sensor wiring step; D3 default if
  silent). Lane 2: A4 closes T7.1 (cli routing, CI, CLAUDE.md line). Beside:
  A7 writes T9.1 (bench files only, disjoint). Exit gate: T7.1 done-check
  green.
- **Aug 27 (Wed).** Lane 1: A4 on T1.3 (MCP fleet tool; A9 beside on the
  five machine floor). Lane 2: A11 on T7.2 (connectors note). Beside: A7
  closes T9.1; A6 runs T9.2 and a window wide adversarial pass. Exit gate:
  T1.3 and T9.1 done-checks green; T9.2 verdict quoted.
- **Aug 28 (Thu).** Close out. A10 runs T10.2; A0 writes the close note
  (everything UNVERIFIED named with its blocker), refreshes the progress
  page, and prepares the handover. No release: the gate holds until the
  claude-md-diet-v2 verdict. Exit gate: both suite commands exit 0, output
  quoted; close note filed.

## 8. What does not fit, and where it went

Cut or deferred from the founder's 45 day plan, each with its reason and its
pull back condition. A compressed plan that pretends everything fits is a lie
with a schedule attached; this one does not fit 31 of the founder's numbered
tasks, and says so.

1. **WBS 1.3 to 1.6, the full fact revalidation cycle** (caching, model,
   effort, MCP, plugin semantics). Cut: data/facts.json already carries 28
   facts with source, date and review interval, and the surface facts were
   re-verified against opened docs pages today. Pull back: any advisor card
   fires on a fact past its review date, or a Claude Code release note
   touches caching or MCP semantics.
2. **WBS 1.8, the stale fact fail CLOSED circuit breaker.** Deferred:
   staleness is fail visible today (doctor prints NEEDS REVIEW, advisor
   prints FACT STALE on the card) and flipping to suppression is a behavior
   change needing A2 and A6 together. Pull back: one wrong recommendation
   traced to a stale fact.
3. **WBS 3.4 to 3.10, the Waste Map signal extensions** (long context, tool
   output, subagent, plugin and MCP pressure). Deferred except what the T5.2
   rollup yields free. Pull back: the Lab seed shows the selector missing a
   dominant class on a real profile.
4. **WBS 5.3 to 5.8, Proof Engine v3** (clean session sufficiency, quality
   panel, the one question user checkpoint, regression verdict rework).
   Deferred entirely: the live claude-md-diet-v2 experiment must run
   untouched, and rewriting the proof engine underneath a running experiment
   is the one way to ruin it. Pull back: the day after its verdict lands.
5. **WBS 6.10, the ten user novice protocol.** Deferred: it needs recruited
   humans, not agents, and the screens it tests are being built this
   fortnight. Pull back: W3 closes green; run it in the gate window before
   release.
6. **WBS 8A in full, the ten plus profile Lab and the 85 percent gate.**
   Only the three profile seed (T9.1) ships. Pull back: mandatory before any
   public leadership claim; the seed exists precisely so the full corpus has
   a proven shape to grow into.
7. **All of Path B, WBS 7B to 12B** (companion curation, Treatment Trial,
   ecosystem tournament). Out entirely: the founder's own plan gates Path B
   on G7A, which is out of reach inside 14 days. Pull back: G7A passes.
8. **WBS 9A.7, the release itself.** Forbidden: the ratified release gate
   holds until the claude-md-diet-v2 experiment reaches VERIFIED or an
   honest NOT_PROVEN, expected near 2026-09-13. These 14 days build the
   product that ships that day.
9. **The proof receipt as a third party verifiable artifact.** Not
   schedulable: unsigned share_card.py is the nearest thing, and real
   signing is undesigned under the zero dependency law (no crypto library,
   and stdlib HMAC means a shared secret). This is a founder decision, not a
   task.
10. **WBS 6.7 and 6.8, the dashboard capacity and cost lenses.** Partially
    deferred: the status line (T3.1) carries the live capacity read, which
    is the honest zero token version. The dashboard lens waits. Pull back:
    the statusline fields prove stable across a Claude Code version bump.
11. **Enterprise expansion of any kind.** Already frozen by the founder's
    plan and stays frozen; T1.1 and T1.3 wire EXISTING fleet code into the
    front door and add nothing to it. Pull back: the individual first gate
    in the founder plan's section 23.

## 9. The critical path

The single chain that decides whether this lands is the single writer chain
through the three most contended files: T2.0 (state model memo) to T2.1
(metrics.py) to T2.2 (token_shield.py) to T2.3 (cli.py) to T1.1 (cli.py) to
T1.2 (token_shield.py) to T10.1, and on through T6.2 (cli.py) to T7.1
(cli.py) to T10.2. Every one of those files allows one writer at a time, so
a slip in any link pushes every later link a full day.

The three likeliest breaks, each with its early warning:

1. **The undocumented transcript format shifts under us.** Our most load
   bearing input has no spec; a Claude Code update can change it without
   notice and every number goes NO DATA at once. Early warning: A10 runs
   reconcile.py each morning of both windows; a nonzero exit or a NO DATA
   spike on a machine that measured fine yesterday is the alarm, and the
   answer is a fixture captured from the new format the same day.
2. **File contention silently serializes the lanes.** Two open tasks both
   naming cli.py or token_shield.py on the same day turns two lanes into
   one and the schedule slips without anyone deciding it. Early warning:
   A0 checks each morning's dispatch against the Files owned column; any
   same day overlap is re-sequenced before dispatch, never during.
3. **The merge queue outruns the founder.** Every task is branch plus PR
   with the founder merging by hand: about 20 PRs in 12 working days, and
   day N+1 tasks depend on day N merges. Early warning: three or more PRs
   open at any morning check means dependent tasks start rebasing instead
   of building; the mitigation is decision D4 tonight.

## 10. Parallelism plan

Genuinely parallel pairs, by construction (disjoint Files owned): T2.1 with
T4.2; T2.2 with T3.1; T2.3 with T4.1; T1.1 with T3.2; T1.2 with T4.3 and
T1.4; T5.1 with T6.1; T5.2 with T6.2; T5.3 with T6.2 close; T5.5 with T7.1;
T5.4 with T7.1 close; T1.3 with T7.2. The barriers: T2.2 waits for T2.1
merged (state must exist before it renders); T2.3, T1.1, T6.2 and T7.1 form
the cli.py single writer queue in that order; T5.5 waits for T5.3 (same
file); T10.1 and T10.2 wait for everything in their windows.

Beside the lanes, never writing production files: A1 (facts), A2 (specs,
except its two narrow writes T5.3), A6 (reviews), A9 (safety), A7 when its
files are all NEW and disjoint (T4.1, T9.1). One writer per file at all
times; a reviewer never reviews its own work; A6 and A9 write only under
docs/plan/reviews/.

Agent count and token budget, all UNMEASURED, ranges with the assumption
named:

- **W1 tonight:** 2 agents beside A0 (A2, plus A0's own packets). Estimated
  60,000 to 150,000 output tokens, low confidence, assuming a memo and two
  packets sized like past review notes.
- **W2:** 4 to 6 agents per day (two writers, one tester beside, one to two
  reviewers). Estimated 150,000 to 400,000 output tokens per day, low
  confidence, assuming each writer task lands in one PR with one revision
  round. The 800,000 per session brake with the 500,000 soft stop binds:
  A0 measures before each dispatch wave and splits a day across sessions
  rather than approaching the brake.
- **W3:** same shape, 4 to 6 agents per day, 150,000 to 400,000 output
  tokens per day, low confidence, same assumption plus one extra review day
  (A9 on T6.3).

Model routing follows the roster: opus never runs a mechanical loop, sonnet
implements from packets, haiku does the mechanical docs, and no cheap tier
verifies anything.

## 11. The decisions this plan is waiting on

Ordered by stakes. Each defaults safely if the founder says nothing.

**D1. Merge cadence.** About 20 pull requests in 12 working days, and every
next day depends on the last one merging; the founder merges by hand and the
queue is the critical path's tightest constraint.
Options: (a) RECOMMENDED: one nightly merge sitting, 15 minutes, all green
PRs in dependency order; (b) merge on ping, whenever a done-check lands; (c)
a standing integration branch A10 maintains, founder merges it to main twice
a week.
Default if silent: (c), because it is the only one that works without the
founder's daily attention, at the price of bigger merges.

**D2. The status line wiring friction.** A plugin cannot install a status
line: the script ships under the plugin root and someone must add one line
to settings.json. This is the always there feeling's single point of
friction, and how hard we push is a taste call.
Options: (a) RECOMMENDED: start.md asks once, and on an explicit yes edits
settings.json itself, mirroring the existing SessionEnd hook offer; (b)
instructions only, the user pastes the line; (c) defer the status line.
Default if silent: (b), the least intrusive; T3.1 builds the script either
way, so upgrading to (a) later is a wording change.

**D3. Fleet in the front door versus the enterprise freeze.** The founder's
plan froze enterprise expansion; the audit calls the org rollup built but
siloed. Wiring existing code into cli.py is coherence, not expansion, but
the founder should own that reading.
Options: (a) RECOMMENDED: wire read only access (T1.1, T1.3), zero new
fleet behavior; (b) keep it siloed until the individual gate passes.
Default if silent: (a), because "five front doors becoming one" was the
founder's own named ask and it takes precedence over a reading of the
freeze.

**D4. Sensor opt in packaging.** T5.4 can offer the six silent lifecycle
events as one yes (one question, six settings.json entries), or a smaller
set (ConfigChange plus the compact pair) that covers the experiment
confounder need with a smaller settings footprint.
Options: (a) RECOMMENDED: all six behind one yes, documented in
docs/TELEMETRY.md; (b) the minimal three, extend later; (c) defer wiring,
ship the script only.
Default if silent: (a): the events are silent, the cost is zero either way,
and one question honors the one opt in principle.

**D5. Connector scope.** T7.1 as specified is CSV to stdout or a file.
JSON output is nearly free to add; a push connector of any kind is not
buildable under the no network law.
Options: (a) RECOMMENDED: CSV only this fortnight; (b) CSV plus JSON.
Default if silent: (a); JSON waits for a named consumer.

**D6. The Window 3 tail.** Aug 27 holds the Lab seed (T9.1, T9.2) and the
MCP fleet tool (T1.3). If the window slips a day, one of them moves out.
Options: (a) RECOMMENDED: the Lab seed survives, T1.3 moves to the gate
window, because the seed feeds the 85 percent leadership gate and the MCP
tool has a cli twin already landed by T1.1; (b) the reverse.
Default if silent: (a).

## Appendix: the founder's five named asks, answered in one line each

- **The install experience:** two commands, then /token-shield:start; the
  sixty second script is T4.2's wording, proven by T4.1's timed smoke, and
  written down in T4.3's README quickstart.
- **The always there feeling:** T3.1's status line, the only zero token live
  surface Claude Code offers a plugin, wired through T3.2 with the friction
  decided in D2.
- **The four state command center:** T2.0 through T2.4; PROVING, invisible
  today, gets its panel in T2.2 and its terminal line in T2.3.
- **Five front doors becoming one:** E1; the org rollup reaches cli.py in
  T1.1, the dashboard links everything in T1.2, MCP parity in T1.3, and the
  map in T1.4.
- **Connectors for analytics and FinOps:** T7.1's labeled CSV export, first
  because it is the only connector legal under the zero dependency and no
  network laws, and the one every FinOps pipeline can ingest tomorrow.
