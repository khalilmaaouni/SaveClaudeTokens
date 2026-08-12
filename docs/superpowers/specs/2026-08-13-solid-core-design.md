# Solid Core: standalone strategy spec

Date: 2026-08-13. Status: DESIGNED, every implementation wave GATED behind the claude-md-diet experiment verdict (the standing gate; the ACT automation level additionally keeps the Protect Mode flip condition: after the first VERIFIED experiment, one guard at a time, cold-cache first). Ratified through five founder question windows this date.

## Goal

Token Shield stands on its own: at least 8.5 on every capability of its own evidence-backed scorecard (reduction, measurement truth, attribution, cache plus startup, personalization, automation) with zero companions installed. The companion ecosystem remains a bonus layer, never the load-bearing wall. Founder directive this date: "the ecosystem is a plus not the whole, we need to be on solid ground across all metrics, nothing under 8.5".

## The yardstick (founder decision: re-derive, never adopt)

External benchmark tables (two received 2026-08-13, single-sourced, UNVERIFIED) are direction, not measurement. The yardstick is docs/SCORECARD.md in this repo: every cell scores only against named evidence (a calibrated test, a measured number from this machine, a shipped surface), is re-scored at every release, and a cell without evidence says NOT YET SCORED rather than carrying a guess. The 8.5 target applies to that scorecard.

## Pillar R: native reduction (guided apply)

Today the tool proposes and advises; it cuts nothing itself. Wave R turns existing proposals into guided applies, each following one contract: backup written first, diff shown, explicit founder yes per change, verification run after, and an experiment record auto-opened so the saving is proven rather than claimed.

- Diet apply: scripts/optimize.py already computes a MOVABLE/HARD/KEEP split and a proposed file; wave R adds the apply step (backup, diff, yes, write, re-lint).
- Plugin prune bundles: context_lint findings become named disable bundles with the exact claude plugin commands, applied one yes at a time, reversible by the same commands.
- Memory index trim: the memory-index truncation finding becomes a guided trim with the same contract.

Explicitly rejected (founder window): apply without asking. Advise-only was rejected as leaving reduction below target.

## Pillar T: native attribution

Every guided apply is auto-attributed: one treatment, one experiment record opened at apply time with the config fingerprint pinned, so the before and after cohort split is exact and the cause is named by the fingerprint diff, not guessed. Single-treatment attribution is core; the multi-treatment waterfall stays in the v1.9 ecosystem layer as the bonus it is.

## Pillar A: the automation ladder (trust posture preserved)

Default install keeps zero hooks, unchanged. /start offers three explicit levels, each behind its own yes, each fully reversed by uninstall-no-trace:

- OBSERVE: the existing opt-in SessionEnd telemetry hook.
- ASSIST: scheduled dashboard and doctor refresh (launchd, like the existing monthly audit), plus session-boundary suggestions; never intervenes inside a session.
- ACT: guards that intervene with a receipt and a one-command rollback. Cold-cache guard first, per the Protect Mode deferral's own flip condition. Each guard lands alone, with its attribution story, never as a bundle.

Explicitly rejected (founder window): automation by default. Stopping at ASSIST was rejected as leaving automation below target; ACT stays inside the flip condition.

## Pillar P: personalization

- Per-project profiles: the profiler learns to split by project slug so advice names the project it came from.
- Habits: the Consumption Report's habits section (spec merged 2026-08-13) feeds habit-based advice.
- Personal thresholds: treatment memory already stores decisions; wave P uses it to tune when advice resurfaces and at what threshold, per user, per machine.
- Per-workflow baselines: session cohorts split by rhythm (short interactive vs long autonomous) so a long overnight run is not scored against interactive baselines.

## Sequencing (all gated on the verdict)

Scorecard ships with this spec (skeleton now, first evidence-backed scoring pass next session). Then, after VERIFIED: R, T, A (OBSERVE and ASSIST), then ACT under its own flip condition, P interleaved where its data sources already exist. Every wave gets its own plan file with steps naming files and done-checks before it starts, per the house order of work. NOT_PROVEN reroutes effort to a better experiment first, unchanged.

## Effort and cost (ranges, medium confidence, priced per wave when planned)

Wave R: 2 to 4 working days, 150K to 350K output tokens. Wave T: 1 to 2 days, 80K to 180K (mostly wiring into experiment.py's existing guards). Wave A observe/assist: 1 to 2 days, 80K to 200K. ACT cold-cache guard: 2 to 3 days including its attribution story, 150K to 300K. Wave P: 2 to 4 days, 150K to 350K. Assumes profiler and experiment data structures hold as shipped in 1.7.1; each wave re-prices at planning time.

## The gate, restated

No implementation file for any wave is created until the claude-md-diet experiment returns its verdict. The ACT level additionally waits for its own flip condition and lands one guard at a time. The scorecard and this spec are the only artifacts that exist before then.
