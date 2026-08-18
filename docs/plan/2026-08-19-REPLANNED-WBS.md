# Replanned WBS, 2026-08-19: sequenced for the enterprise turn

Supersedes the sequencing (not the task definitions) in
`2026-08-15-LEADERSHIP-WBS.md`. Written at session close on the founder's
direction of 2026-08-19: enterprise focus, Claude Code only, differentiated by
BrotherSBE and BrotherMode.

The task table in the 2026-08-15 WBS remains authoritative for what each task
IS, which files it owns, and its done-check. What changes here is the ORDER,
and the reason each item earns its place.

## What changed, and why

The old plan sequenced by epic (E1, then E2, then E3). That was right when the
goal was "a complete free product". It is wrong now, because the founder's
direction sorts work by a different question: **does an enterprise buyer touch
this?**

Two consequences:

- **E7 (CSV export) moves UP,** from Window 3 to the first wave. It is the
  chargeback artifact. A finance team receives a labelled CSV or the product is
  not in the evaluation. Under the old plan it was near-last.
- **E5 (silent sensors) moves DOWN.** It is real engineering that improves proof
  quality, but no buyer sees it, and nothing else depends on it.

Everything else keeps its relative order.

## Status at replan

8 of 22 done. E2 and E8 COMPLETE. E1 at 3 of 4. main at `810b898`, clean, suite
green.

## The waves

### Wave 1: the Enterprise door (the only wave that is urgent)

The single argument this product wins on is that an organisation can measure its
Claude Code spend without shipping telemetry to anyone, and hand finance a file
whose every row carries its confidence. Three tasks complete that argument.

| Order | Task | Why it is in wave 1 | Done-check |
|---|---|---|---|
| 1 | **T1.3** MCP org rollup | The org page is reachable from the CLI but not from an agent. Last piece of the front door. | `cd mcp-server && python3 test_mcp_server.py` prints `ok test_get_fleet_summary_respects_min_group` |
| 2 | **T7.1** CSV export with labels | The chargeback artifact. One confidence label per row, no cross-label total anywhere, which is the thing a plain CSV cannot claim. | `cd scripts && python3 test_export.py` prints `ok test_no_cross_label_total_row` and `ok test_every_row_carries_a_label` |
| 3 | **T7.2** `docs/CONNECTORS.md` | Says why CSV is first and attributes OpenTelemetry to Anthropic rather than competing with it. Procurement reads position notes. | `grep -n ATTRIBUTION docs/CONNECTORS.md` |

**Wave 1 done means:** an admin reaches the org view in one command, an agent
can query it under the minimum-group floor, and finance gets a labelled file.

### Wave 2: the first sixty seconds

Nothing in wave 1 matters if nobody gets past install.

| Order | Task | Note | Done-check |
|---|---|---|---|
| 4 | **T4.2** first screen wording | One hero number, one action, plain language, labels intact. | `python3 test_trial.py` exits 0 and `test_install_smoke.py` passes against the new wording |
| 5 | **T3.1** statusline script | **ASK THE FOUNDER FIRST.** Night order FD6 holds it even though it writes no settings. | `python3 test_statusline.py` prints its three named oks |

### Wave 3: reversibility, which is what lets a cautious org say yes

| Order | Task | Note | Done-check |
|---|---|---|---|
| 6 | **T6.2** one command undo | Byte identical restore, verified against the journaled pre hash, journals the undo itself. | `python3 test_guided_apply.py` prints `ok test_undo_restores_byte_identical_and_journals_itself` |
| 7 | **T6.3** undo safety review | Read only, veto rights over T6.2. | `grep -n "CRITICAL FINDINGS: 0"` in the review, or every finding carries a scheduled task id |

### Wave 4: evidence quality (no buyer sees it, so it goes last among the real work)

| Order | Task | Done-check |
|---|---|---|
| 8 | **T5.1** lifecycle sensor | `python3 test_lifecycle_sensor.py` prints `ok test_unknown_event_still_exits_zero`, `ok test_writes_no_stdout` |
| 9 | **T5.2** signals rollup | `python3 test_signals.py` prints `ok test_lifecycle_rollup_counts_manual_and_auto_compacts` |
| 10 | **T5.3** config drift downgrades a verdict | `python3 test_experiment.py` prints `ok test_mid_window_config_change_downgrades_to_not_proven` |
| 11 | **T5.5** version on evidence | `python3 test_experiment.py` prints `ok test_version_drift_names_historical_reason` |
| 12 | **T9.1** selector Lab seed | `python3 bench/test_selector_bench.py` prints `ok test_healthy_profile_returns_do_nothing` |

### Gate

| Order | Task | Done-check |
|---|---|---|
| 13 | **T10.1** integration | The three documented commands, each started from the repo root, never chained, each exit 0, output quoted in the PR |

### Blocked

| Task | Blocker |
|---|---|
| **T3.2** status line wiring | Decision D1, plus night order FD6 |

## Forecast

Ranges with assumptions, never points.

| Wave | Sessions | Confidence | Assumes |
|---|---|---|---|
| Wave 1 | 1 to 2 | High | T1.3 reuses fleet_dashboard's aggregation rather than reimplementing it |
| Wave 2 | 1 | Medium | D1 answered; otherwise T4.2 alone, half a session |
| Wave 3 | 1 to 2 | Medium | The safety review finds nothing critical; a veto adds a session |
| Wave 4 | 2 to 3 | Low | Five tasks touching experiment.py in sequence, one writer at a time |
| Gate | Half | High | No wave reopened |

**All 22 by 2026-08-28: roughly 60/40.** The risk is not the engineering, it is
decisions sitting. Three are open right now and each blocks or reshapes a wave.

## What is deliberately NOT in this plan

- **Git yield correlation** (CodeBurn's `codeburn yield`, splitting spend into
  productive, reverted, abandoned and ambiguous). It is the most interesting
  thing either product does and we have no answer to it. It is a parking lot
  item pending founder decision D3, recorded here so it is not lost.
- **Breadth beyond Claude Code.** Forfeited deliberately per the 2026-08-19
  direction. The developer who wants one dashboard across four coding tools is
  conceded to CodeBurn.
- **Protect Mode hooks.** Still deferred on the flip condition already recorded
  in `docs/ROADMAP.md`.
