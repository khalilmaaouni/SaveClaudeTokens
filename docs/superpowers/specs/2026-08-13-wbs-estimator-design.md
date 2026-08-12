# WBS cost estimator: design spec

Date: 2026-08-13. Status: DESIGNED, build GATED (MCP wave 2, after wave 1 ships, after the claude-md-diet experiment verdict). This spec fills in the wave 2 bullet from `docs/superpowers/specs/2026-08-12-token-shield-mcp-design.md`: "price a planned piece of work in tokens before running it (inputs: files touched, expected turns, model tier; output: a range with assumptions, ESTIMATED). Ships only with its own calibration story." That boundary is fixed; this spec is everything inside it.

## Goal

Before a session starts a piece of work, answer "roughly how many output tokens will this cost" as a labeled range, so the founder or an orchestrator can pick model tier and subagent fan-out before spending anything. It never claims precision it has not earned, and it never claims a number when the underlying history is too thin to support one.

## Who it serves

The founder, deciding whether a task fits the cheap lane or needs the strongest tier, before dispatching it. Orchestrating agents (brothermode, ultraplan-style planners) that need a cost input to a dispatch decision. Any local MCP client that wants a pre-work estimate the same way it can already call `get_advice` for a post-hoc one. Local only, no accounts, no network, same posture as the rest of the MCP server.

## Inputs and their validation

Three inputs, matching the ratified boundary exactly, nothing added:

- `files_touched` (integer, required, >= 0): count of files the planned work is expected to read or write. 0 is valid (a pure-reasoning task). Negative or non-integer is a validation error, returned before any estimate runs.
- `expected_turns` (integer, required, >= 1): number of assistant turns (tool-call round trips) the planner expects. Must be at least 1; a task with zero turns is not a task.
- `model_tier` (string, required, one of `haiku`, `sonnet`, `opus`, matching the tier names already used in this repo's routing language): which model is expected to run the work.

No other inputs. Adding "task description" or "file sizes" was considered and rejected here: this tool has no code path that reads file contents or task text, so it cannot use them, and accepting them would invite a false impression of sophistication. Rejected inputs are a design decision recorded here, not a TODO.

Validation happens before any lookup. A bad input returns a validation error naming the field and the rule it broke, the same pattern as the experiment guard's refusals. No silent clamping (a `files_touched` of -1 is never treated as 0).

## The estimation model (simple, stated, no learned magic)

No regression, no ML, no hidden weighting. The model is a lookup against the user's own measured history, bucketed by the same three inputs, with an explicit fallback ladder:

1. **Bucket the history.** Every stored actual (see Calibration story) is tagged with the same three inputs it was estimated under: `files_touched` bucketed into `0`, `1-3`, `4-10`, `11+`; `expected_turns` bucketed into `1-3`, `4-10`, `11-25`, `26+`; and `model_tier` as-is. Buckets exist because exact-integer matches on a thin history never hit; coarse buckets do.
2. **Look up the matching bucket.** If the ledger of past estimates-with-actuals (see below) has at least 5 completed matches in that exact bucket, the range is the bucket's own p25 to p75 of actual output tokens, label ESTIMATED, source "bucket history, N=<count>".
3. **Fall back one dimension at a time if the bucket is empty.** Relax `files_touched` to "any" first (turns and tier still matching), then relax `expected_turns` to "any" (files and tier matching), then relax to tier-only. Each relaxation is stated in the assumptions field: "no exact bucket match, widened to tier-only history." Still requires N >= 5 in the widened bucket to produce a number.
4. **Below N=5 anywhere in the ladder: NO DATA.** The tool returns NO DATA explicitly, states the closest bucket size it found and how many, and recommends running `get_profile` or waiting for more completed work in that tier before trusting an estimate. This is the load-bearing rule in the whole spec: a guess dressed as a range is worse than an honest refusal, per `docs/METHODOLOGY.md` section 4 ("an unmeasurable value gets a plausible fill").

No cross-user, cross-machine, or seeded default numbers ship with the tool. A fresh install has zero history and returns NO DATA for every call until the ledger accumulates real completions. This is a deliberate cost: the tool is useless on day one and that is stated in its own docs, not hidden.

## Output shape

A single JSON object, always:

```
{
  "label": "ESTIMATED" | "NO DATA",
  "range": {"low": <int|null>, "high": <int|null>, "unit": "output_tokens"},
  "assumptions": ["<one line per fallback or bucket decision taken>"],
  "sample_size": <int>,
  "bucket": {"files_touched": "<bucket>", "expected_turns": "<bucket>", "model_tier": "<tier>"},
  "source": "wbs_estimator bucket history"
}
```

When `label` is `NO DATA`, `range.low` and `range.high` are `null`, never 0 and never omitted; `assumptions` states which buckets were checked and their sample sizes (e.g. `["files 4-10 x turns 4-10 x sonnet: N=1", "files any x turns 4-10 x sonnet: N=2", "tier-only sonnet: N=3", "below floor of 5 at every level"]`). `range.unit` is always `output_tokens`, matching `measure_tokens.py`'s own units (this tool has no dollar price table for the same reason `measure_tokens.py` doesn't: a hardcoded price goes stale and silently corrupts every later comparison, per `docs/METHODOLOGY.md` section 2).

The label is never upgraded past what the data supports. A bucket with N=5 does not get called VERIFIED; it is ESTIMATED, full stop, every time, because a range from 5 historical points is still a range, not a proof. Only the calibration report (below) can ever use MEASURED, and only about the estimator's own error, never about a single estimate's accuracy in advance.

## The calibration story

This is the part that makes the tool honest, and it is the majority of this spec by design, per the brief.

### Every estimate is stored

Each call to the estimator writes one row to a local calibration ledger (new file, `~/.claude/wbs-estimate-ledger.jsonl`, same directory convention as `session_end_telemetry.py`'s `~/.claude/token-ledger.jsonl`): `estimated_at`, `estimate_id` (uuid4), the three inputs, the bucket computed, the `label` and `range` returned, and `actual_output` set to `null`. Writing this row is the only side effect of a call; nothing else happens until the work finishes.

### Matching an estimate back to its actual

When the estimated work actually runs and finishes, its real cost is already captured by `session_end_telemetry.py`'s existing per-session ledger row (`~/.claude/token-ledger.jsonl`), which carries `session_id`, `output`, `subagent_output`, and `models` per session, per the field names in that script's `record()` function. The WBS estimator does not duplicate that collection. Instead, a caller (the orchestrator, or the founder by hand) closes the loop explicitly: `record_actual(estimate_id, session_id)`. This tool looks up `session_id` in the token ledger, reads its `output` field (plus `subagent_output` if the estimate's `model_tier` implied fan-out), and writes that sum into the calibration ledger's `actual_output` field for the matching `estimate_id` row.

This is a deliberate manual join, not automatic correlation by timestamp proximity: guessing which session belongs to which estimate from timing alone would silently mismatch on any overlapping work, and a wrong match poisons the calibration data worse than a missing one. `record_actual` is the second and last write tool this feature adds; a call naming an unknown `estimate_id` or `session_id` returns a validation error and writes nothing.

### The estimator publishes its own error distribution

A new read tool, `get_estimator_calibration()`, computes and returns, from every ledger row where `actual_output` is not null: sample size, and for that sample, median absolute percentage error (`abs(actual - midpoint(range)) / actual`), the hit rate (fraction of actuals that landed inside the returned range), and the same breakdown per bucket where a bucket has N >= 5 closed rows. Every number here carries label MEASURED, since it is arithmetic over real matched pairs, not a projection. Below N=5 total closed rows, `get_estimator_calibration()` returns `{"label": "NO DATA", "closed_rows": <n>, "note": "estimator has not accumulated enough completed, matched estimates to report its own error"}`. This mirrors `docs/METHODOLOGY.md`'s own second-pass discipline (section 4, "a single pass is trusted" guard): the estimator's accuracy claim is itself measured and re-derivable, not asserted once and left stale.

### An estimator whose error is unknown reports that

Any surface that shows the estimator's range (the MCP tool response itself, a future dashboard card) shows the calibration sample size alongside the range whenever it is available, and shows nothing about accuracy when `get_estimator_calibration()` is NO DATA. The tool never says "usually accurate" or "typically within X%" unless that X came out of `get_estimator_calibration()` on this machine, this run. No borrowed accuracy claims from another tool, another machine, or from this spec's own reasoning about buckets.

## Error handling

Same posture as the rest of the MCP server (`2026-08-12-token-shield-mcp-design.md`, "Error handling"): validation errors on bad input return before any lookup, naming the field and rule. A missing or unreadable ledger file returns NO DATA, never treated as an empty-but-valid history. A malformed `record_actual` call (unknown id, ledger row already closed) returns a refusal stating why, verbatim, and writes nothing; closing an already-closed row is rejected rather than silently overwritten, so an accidental double-close cannot corrupt the calibration sample. Nothing here retries silently and nothing degrades to a number without its label.

## Testing (repo's calibrated assert style)

One file, `scripts/test_wbs_estimator.py`, no framework, mirroring `scripts/test_measure_tokens.py`'s pattern of importing the module by path and asserting exact tuples/dicts:

- Bucketing: known `files_touched`/`expected_turns` values map to the documented bucket edges (boundary values 0, 1, 3, 4, 10, 11, 25, 26 each asserted, since off-by-one on a bucket edge is the standard way this kind of code silently misclassifies).
- Fallback ladder: a seeded sandbox ledger with N=2 in the exact bucket and N=6 in the tier-only bucket asserts the tool falls back and states so in `assumptions`, not a silent wider match.
- Floor: a seeded ledger with N=4 everywhere asserts NO DATA, not a range from insufficient data (this is the single most important test in the file, mirroring `docs/METHODOLOGY.md`'s "unmeasurable value gets a plausible fill" guard).
- Write path: `record_actual` against a seeded estimate and a seeded token-ledger row asserts the exact `actual_output` value written (sum of `output` plus `subagent_output` when fan-out applies), and a second `record_actual` against the same already-closed `estimate_id` asserts the refusal.
- Calibration report: a seeded ledger of 6 closed rows with known errors asserts the exact median-absolute-percentage-error and hit-rate numbers by hand-computed reference, plus the NO DATA path under 5 closed rows.
- Field-name fidelity: one test asserts the module reads `output` and `subagent_output` (not `output_total` or any other name) from a token-ledger fixture row, so a future rename in `session_end_telemetry.py` breaks this test loudly instead of the estimator silently reading nothing.

The py311 gate and the dash, attribution, and secret scans apply as everywhere in this repo.

## Explicitly out of scope

- No task-description or file-content input, and no code path that reads either, per the inputs section above.
- No dollar pricing; output stays in output-token units, matching the rest of the repo's normalized-cost stance.
- No cross-machine or shared calibration data; the ledger is local to this machine, same as the token ledger it reads from.
- No automatic estimate-to-session matching by timestamp; `record_actual` is a deliberate, named call.
- No learned model, no regression, no weighting scheme; bucketed percentile lookup only.
- No retroactive relabeling of past estimates when the calibration improves; each stored estimate keeps the label and range it was given at estimate time, since a range is a claim about what was known then, not a live-updating figure.
- No UI in this wave; `get_estimator_calibration` and the estimator tool are MCP-only, consumed by the dashboard only if a later spec adds that surface explicitly.

## Effort and cost (range, medium confidence)

1.5 to 3 working days inside MCP wave 2, after wave 1 and the consumption report ship: one day for the estimator tool plus bucketing and validation, half a day for the ledger and `record_actual` join, half to one day for `get_estimator_calibration` and the test file. Roughly 60K to 150K output tokens, one sonnet builder from this spec plus orchestrator verification. Confidence is medium rather than high because the fallback-ladder edge cases (partial bucket relaxation, boundary bucketing) are the kind of thing that tends to need one extra pass once real seeded data is in hand.

## The gate, restated

No `wbs_estimator.py` implementation file is created until MCP wave 1 (including the consumption report amendment) has shipped and the claude-md-diet experiment has returned VERIFIED. Wave 2 items are priced and gated individually when scheduled, per the parent MCP spec; this item additionally requires its own calibration ledger to exist and accumulate real rows before its range output can be trusted, which is a second, feature-internal gate beyond the standing experiment gate: even after the code ships, its output stays labeled ESTIMATED with N stated, and callers are told in the tool's own docs not to trust a range without checking `sample_size` first.
