# Finish-the-program plan: Phase 5 closeout, v1.8 wave 2, deep layer, v1.9

Date: 2026-08-13, planned by the orchestrating session at its spend soft stop, for execution by a FRESH session with full budget. Founder order: finish Phase 5, 3g (v1.8 waves and deep layer), 3h (v1.9), planned by Fable, executed by the right subagent and model per task. The founder's gate amendment (PR 18) covers building before the verdict; the release boundary stays gated: no tag, no publish, no local plugin update, no MCP client registration until the claude-md-diet verdict.

## Standing truths the executing session inherits

- Phase 5 cannot be finished by effort. The experiment verdict is time-gated: a same-window close was REFUSED live on 2026-08-13 (windows overlap, exit 2, quoted in the session log), putting the clean close near 2026-09-11. What an EARLY close returns is INFERRED, not run: the suite's calibrated tests "window mismatch downgrades to NOT_PROVEN" and "thin post-change data downgrades to NOT_PROVEN" (scripts/test_experiment.py, green this date) imply a short-window close downgrades honestly; the executing session must not assert the outcome beyond that inference. Phase 5's finishable piece is unit F1 below. Nothing in this plan touches the experiment: no config change, no plugin update, no experiment command beyond read-only checks.
- Every unit: own worktree, own branch, fence written in STATE.md before dispatch, suite green in the worktree before push, the three push gates fail-closed, PR, CI settled, merge by the orchestrator. Workers never push. One suite at a time per tree.
- Every number labeled; NO DATA beats a guess; calibrated tests red to green; no em or en dashes; no AI attribution anywhere.
- Deep-layer law from the ratified advisor plan: the deep advisor runs on Fable, pinned, on demand, its cost printed and subtracted; Fable judges, never executes; the deep selector never invents install commands, never alters labels, never touches files.

## Dispatch table (the founder's right-model-per-task ask, reasons declared)

| Unit | What | Agent | Model | Why this tier |
|---|---|---|---|---|
| F1 | Scorecard first evidence pass | one builder | sonnet | evidence gathering against named tests and numbers; Fable verifies every cell before merge |
| G1 | data/compatibility.json plus hook ownership table | one builder | sonnet | schema plus data work from wave 1 doctor output, mechanically checkable |
| G2 | Overlap suppression plus suppression memory and cooldowns | one builder | sonnet | scoped implementation against existing advisor treatment memory |
| G3 | Deep advisor subagent plus semantic optimizer v2 | one builder | sonnet drafts the harness and prompts; the deep advisor RUNS on Fable at runtime by design | the runtime tier is a ratified product decision, the build itself is scoped wiring |
| H1 | Companion adapter layer (scripts/companions/, one adapter each for ponytail, caveman, token-saver) | one builder | sonnet | adapters mirror the registry contract, evidence already first-party |
| H2 | Mode guidance (conservative, balanced, aggressive) plus guided install and rollback recipes from the curated registry only | one builder | sonnet | recipe rendering from existing data, no judgment calls |
| H3 | Marginal attribution waterfall on the dashboard | one builder | sonnet | display plus math from experiment records; the no-naive-summing rule is testable |
| R | Solid Core wave R build (guided apply) | one builder | sonnet | plan already merged (2026-08-13-solid-core-waveR-plan.md); its experiment interlock is step 1 |
| REVIEW | Adversarial review of G2, G3, H3 (the three judgment-heavy units) | reviewer briefed to REFUTE | opus tier | independent falsification before merge, per house law; Fable triages the findings |
| Verify/merge/judge | every unit | orchestrator | Fable | verification never delegates down |

Sequencing: F1 and G1 first (independent, cheap). G2 after G1 (reads the matrix). G3 after G2 (suppression feeds the selector). H1 after G1; H2 after H1; H3 after G2. R any time (independent). REVIEW after each of G2, G3, H3 lands red-green. Two build lanes maximum in parallel, per the caps.

## Unit specs (files and done-checks)

F1: fill docs/SCORECARD.md cells, each citing a test name, a measured number with its source command, or a shipped surface; the anchors already in the file govern; a cell without evidence stays NOT YET SCORED. Done-check: every scored cell's named evidence exists (grep each cited test name; re-run each cited command); the history section gains its first entry.

G1: data/compatibility.json (pairs over the curated companions plus token-shield itself: shared hook events from doctor output, known-safe or needs-review verdicts with evidence dates, never invented); hook ownership table rendered by scripts/doctor.py (extended, read-only posture unchanged). Tests: scripts/test_doctor.py additions, calibrated. Done-check: python3 scripts/test_doctor.py green; python3 scripts/cli.py doctor prints the ownership section against the live machine.

G2: scripts/advisor.py gains capability-ownership suppression (an active companion owning a capability suppresses Token Shield's duplicate advice card), suppression memory with cooldowns extending the existing treatments store shape. Tests: test_advisor.py additions asserting suppression, expiry, and that suppression NEVER hides a regression warning. Done-check: test_advisor.py green with the new assertions calibrated red to green.

G3: the deep advisor: a pinned Fable-tier subagent invocation path (cli advise --deep), cost printed and subtracted, choosing one treatment from the registry ONLY when deterministic rules cannot decide; semantic optimizer v2 per the deferred blueprint bullet, proposals only, never applies. Files: scripts/deep_advisor.py, prompts under skills/token-shield/, scripts/test_deep_advisor.py (harness tested with a fake model callable, never a live call in tests). Done-check: tests green; one live smoke run printed with its cost, founder-visible, at the founder's explicit yes since it spends Fable tokens.

H1: scripts/companions/ponytail.py, caveman.py, token_saver.py implementing one adapter contract (status, version, modes, activation and rollback commands FROM data/companions.json, never invented). Tests per adapter against fixture registries. Done-check: new tests green; an adapter refuses a registry entry missing evidence fields.

H2: mode guidance rendering in advisor cards (intent phrasing) plus guided install and rollback recipes surfaced through cli advise, sourced from the registry's curated commands only. Done-check: test additions green; a recipe request for an unvetted plugin is refused with the reason printed.

H3: the waterfall on the dashboard: baseline A, plus Core to B, plus companion to C; marginal deltas never summed as naive percentages, interaction declared not separable, a companion version change ends any spanning experiment (wired to the existing fingerprint). Done-check: test_tools.py additions calibrated, including the never-sum assertion.

R: execute docs/superpowers/plans/2026-08-13-solid-core-waveR-plan.md as written; its step 1 interlock (no apply while any experiment is open) is the first commit.

## Budget and closure

Estimates (ranges, medium confidence, priced from tonight's actual unit costs): F1 30k to 60k output; G1 60k to 120k; G2 80k to 150k; G3 120k to 250k; H1 80k to 150k; H2 50k to 100k; H3 80k to 150k; R 150k to 350k; reviews 60k to 150k. Basis note (2026-08-13 audit): the unit costs behind these ranges were not recorded to disk; the ranges stand as estimates with an unrecorded basis until the WBS estimator ledger ships. Total 0.7M to 1.5M: two to four fresh sessions at standard ceilings. The executing session states its ceiling up front, dispatches nothing past 80 percent of it, and hands over with a pack the moment the guard speaks. Close per house law: page republished and delivered, vault log, remaining and unverified stated plainly.
