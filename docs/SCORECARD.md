# Capability scorecard (the yardstick for "nothing under 8.5")

Founder decision 2026-08-13: external benchmark tables are direction, never measurement. This file is the yardstick. Every cell scores ONLY against named evidence in this repo or measured on this machine; a cell without evidence says NOT YET SCORED, never a guess. Re-scored at every release; history kept below.

## Scoring anchors (what a number is allowed to mean)

- 9 to 10: capability proven by calibrated tests AND a measured or verified number from real usage.
- 7 to 8.5: capability shipped and tested; real-usage evidence partial.
- 5 to 6.5: capability exists but is advisory, manual, or unproven on real data.
- Under 5: capability absent or aspirational.
A score may never exceed what its named evidence supports. NO DATA rows stay NOT YET SCORED.

Tie-breaks, so two honest reviewers land on one number: evidence sitting between two bands scores the LOWER band. A cell may reach 8.5 or higher only when it cites BOTH a calibrated test AND a real-usage measured number. Thin-but-present real-usage evidence (fewer than 30 days or fewer than 30 sessions behind the number) caps the cell at 8.0. Ties always break down, never up.

## Current scores (as of v1.7.1, pre-release scoring pass complete)

First evidence-backed scoring pass, wave T merged. Every score below cites a calibrated test (grep-verifiable def), a measured number with its source command (re-run read-only, output quoted), or a shipped surface. The VERIFIED experiment ledger is empty on this machine (no closed experiment: `python3 scripts/cli.py summary` prints "VERIFIED none yet"; no `~/.token-shield/experiments` directory exists), so Actual reduction and Attribution cannot cite real-usage proof of a delivered saving, and both are capped by that absence, not by a feeling.

| Capability | Score | Evidence (required before any number) |
|---|---|---|
| Actual reduction | 6.0 | Calibrated: scripts/test_optimize.py::test_propose_keeps_every_hard_section_verbatim (6/6 passed, exit 0). Shipped: `python3 scripts/optimize.py propose` on a live CLAUDE.md printed "estimated tokens 886 -> 333 (553 fewer, about 62%), ESTIMATED". No real-usage number: `python3 scripts/cli.py summary` prints "VERIFIED none yet. Run: python3 cli.py experiment start" and no `~/.token-shield/experiments` directory exists. Estimate only, capped in the 5 to 6.5 band. |
| Measurement truth | 9.0 | Calibrated: scripts/test_measure_tokens.py (9/9 passed) and scripts/test_pricing.py (7/7 passed), exit 0. Real-usage measured number, independently reconciled: `python3 scripts/reconcile.py --days 30` printed "sessions parsed independently: 3657" and "RECONCILED: every compared field drifts under 0.5 percent" (first_request_median, first_request_share_median, multi_model_count all OK). 3,657 sessions over 30 days is not thin, so the 8.0 real-usage cap does not apply; both a calibrated test and a real-usage number are present. |
| Attribution | 6.0 | Calibrated: scripts/test_tools.py::test_dashboard_attributes_the_saving_to_native_caching and ::test_shield_saving_is_net_of_the_write_premium (both in the 25/25 passed test_tools.py run, exit 0) hold the dashboard to crediting Anthropic's own caching, never a dollar claim. No real-usage proof of a delivered saving to attribute: VERIFIED ledger empty, same evidence as Actual reduction above. Advisory discipline only, capped in the 5 to 6.5 band. |
| Cache plus startup | 8.5 | Calibrated: scripts/test_profile.py::test_idle_gap_bucketing_math and ::test_model_switch_detection (8/8 passed); scripts/test_detail_report.py::test_schema_v1_top_level_and_leaf_shape (6/6 passed), exit 0. Real-usage measured number: `python3 scripts/cli.py profile` printed "sessions in window: 3,657 over 30 days", "cache hit ratio median: 0.911", "first-request floor: 85,587 tokens median, 0.363 share". Not thin (3,657 sessions, 30 days). One band below Measurement truth because cache hit ratio itself is not independently reconciled by reconcile.py (only first_request_median, first_request_share_median, and multi_model_count are). |
| Personalization | 6.5 | Calibrated: scripts/test_advisor.py::test_why_selected_contains_the_profiles_own_number and ::test_record_decision_round_trips_and_expires_correctly (both in the 15/15 passed test_advisor.py run, exit 0). Shipped and running on real data: `python3 scripts/cli.py advise` printed a card citing this machine's own number ("Your model switch session share is 28%"), marked "evidence: ESTIMATED". Real personalization inputs, unproven real-world benefit: top of the 5 to 6.5 advisory band. |
| Automation | 3.0 | Shipped surface, deliberately manual: CLAUDE.md:27 "The plugin registers zero hooks by default; everything is opt-in"; README.md:130 and README.md:266 say the same. scripts/session_end_telemetry.py is the one opt-in hook and only appends measured counters, no action; its docstring states "OPT IN. This plugin does not register this hook for you. Nothing here runs" unless wired by hand. Calibrated: scripts/test_tools.py::test_telemetry_never_breaks_the_session (in the 25/25 passed run) proves the hook is safe, not that it acts. optimize.py --apply and experiment start/end are both user-invoked CLI commands, never autonomous. No autonomous action anywhere: under 5, absent/aspirational band. |

## External benchmarks on record (UNVERIFIED, direction only)

- 2026-08-13, source unnamed, single-sourced: capability table scoring Token Shield across 13 rows (screenshots held by the founder; sub-8 rows mapped to roadmap items in the vault's Open-Items note).
- 2026-08-13, same source: live-products comparison scoring Token Shield 1.6 at reduction 5.5, measurement 9.5, attribution 6.0, cache plus startup 9.0, personalization 2.5, automation 3.5. Recorded verbatim as received; none of these numbers re-derived here.

## History

- 2026-08-13, no release tag yet: pre-release scoring pass, wave T merged. First evidence-backed pass: Actual reduction 6.0, Measurement truth 9.0, Attribution 6.0, Cache plus startup 8.5, Personalization 6.5, Automation 3.0. Full test suite green (exit 0) and `python3 scripts/reconcile.py --days 30` reconciled on 3,657 real sessions; VERIFIED experiment ledger still empty on this machine.
