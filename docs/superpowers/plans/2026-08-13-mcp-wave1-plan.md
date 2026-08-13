# Token Shield MCP wave 1: implementation plan (including the Consumption Report)

Date: 2026-08-13. Status: PLAN ONLY, no implementation file exists yet. This document turns the two ratified specs below into steps a future builder session can run without making a single design decision. Every step names its exact paths and ends with a command that proves the step landed.

Ratified specs this plan implements, unchanged:
- `docs/superpowers/specs/2026-08-12-token-shield-mcp-design.md` (the MCP server, wave 1)
- `docs/superpowers/specs/2026-08-13-consumption-report-design.md` (the amendment adding `get_detailed_report`)

## THE GATE (read this before touching anything)

No file under `mcp-server/` and no `scripts/detail_report.py` gets created until the claude-md-diet experiment reaches a verdict in the proof ledger: VERIFIED or an honest NOT_PROVEN. This is the same gate stated in `CLAUDE.md` line 30 and restated at the bottom of both specs. Check the verdict before step 1:

```bash
cd /Users/khalil.maaouni/SaveClaudeTokens && python3 scripts/cli.py experiment report
```

Look for a `claude-md-diet` row with a VERIFIED or NOT_PROVEN count greater than 0. If the row is absent, or shows 0 runs, STOP. Do not create any file listed in this plan. Report the gate as closed and wait.

FOUNDER AMENDMENT 2026-08-13 (explicit decision via question window, after the gate collision was surfaced with the ~30 day verdict timeline): BUILDING is authorized before the verdict. The gate MOVES to the release boundary: no version tag, no release, no plugin publish, and no local plugin update or MCP client registration on this machine until the claude-md-diet experiment reaches VERIFIED or an honest NOT_PROVEN. The experiment itself stays untouched while it runs. Under that amendment this plan's implementation steps MAY run before the verdict; the STOP above now applies only to release steps.

## Scope

In scope: the `mcp-server/` package, all nine wave-1 tools listed in the MCP design spec (including `get_detailed_report`), the new `scripts/detail_report.py` module and its schema v1, the test files for both, one live smoke check, CI wiring, the README install block, and version tagging.

Out of scope, not touched by this plan: the dashboard Habits section described in the Consumption Report spec's "Dashboard" section (it renders the same report object but is a separate dashboard-rendering task, not named in this plan's brief). Wave 2 items (WBS cost estimator, research tools, trend analysis, additional data-source adapters) stay out per both specs.

## Grounding: exact existing functions this plan wraps, never reimplements

Every name below was read directly from the file named, on this date. A builder session must re-grep before use in case the file moved since this plan was written; do not trust this table blindly, it is a snapshot.

| Function | Source file | Shape |
|---|---|---|
| `build_profile(root=None, days=30)` | `scripts/profile.py:204` | pure, returns a dict of `usage`/`behavior`/`instruction`/`environment`/`skipped` metric groups, each leaf `{value, label, basis}` |
| `metric(value, label, basis)` / `no_data(basis)` | `scripts/profile.py:70,74` | pure helpers that build the leaf shape above |
| `collect(root, days)` | `scripts/measure_tokens.py:250` | pure, returns a list of per-session dicts, each carrying `started` (ISO timestamp string or None), `first_request`, `hit_ratio`, `output`, `sub_output`, etc. |
| `summarize(sessions)` | `scripts/measure_tokens.py:262` | pure, aggregates the list from `collect` into one summary dict, or `None` if `sessions` is empty |
| `skip_counts()` | `scripts/measure_tokens.py:98` | pure, returns the module-level skip counters |
| `load_strategies(path=DEFAULT_STRATEGIES)` | `scripts/advisor.py:100` | pure, returns the strategy registry as a list of dicts |
| `advise(profile, treatments=None, strategies=None)` | `scripts/advisor.py:279` | pure, returns `{best, alternatives, companion, queue, do_nothing, advisor_cost_tokens, insufficient, message?}` |
| `load_treatments(path=TREATMENTS_PATH)` | `scripts/advisor.py:343` | reads `~/.token-shield/treatments.json`, never raises |
| `record_decision(strategy_id, decision, days=90, note="", path=TREATMENTS_PATH)` | `scripts/advisor.py:366` | writes treatment memory, returns the record it wrote, raises `ValueError` on an unknown decision |
| `build_report(year, month, root=None)` | `scripts/report.py:287` | pure, returns the monthly report as a markdown string |
| `cmd_start(label, root, days, now_ts, treats)` | `scripts/experiment.py:422` | prints to stdout, returns an int exit code (0 ok, nonzero refusal); writes the baseline snapshot file under `EXP_DIR` |
| `cmd_end(label, root, days, now_ts)` | `scripts/experiment.py:445` | prints to stdout, returns an int exit code; appends one record to `LEDGER` |
| `cmd_report()` | `scripts/experiment.py:490` | prints to stdout, returns an int exit code; read-only summary of the ledger |
| `default_targets(all_memory=False)` | `scripts/context_lint.py:229` | pure, returns `[(path, is_memory_index), ...]` for the files loaded every session |
| `check(path, is_memory_index)` | `scripts/context_lint.py:94` | reads one file, returns `(findings, stats)`, `stats` carries `raw_bytes`, `loaded_bytes`, `loaded_lines` |
| `_verified_by_label()` | `scripts/cli.py:39` | private (leading underscore), reads `experiment.LEDGER`, returns `[(label, floor_reduction), ...]`, latest record per label |
| `savings_breakdown(sm)` | `scripts/token_shield.py` (imported as `ts`, used at `cli.py:88`) | not read during this pass, re-grep the exact signature before use |
| `prescriptions(sm, sessions)` | `scripts/token_shield.py` (imported as `ts`, used at `cli.py:89`) | not read during this pass, re-grep the exact signature before use |
| `check_py311.py` | `scripts/check_py311.py` | the py311 syntax gate; CI runs `--selftest` then the bare check |

Two rows above (`savings_breakdown`, `prescriptions`) were named in `cli.py` but this pass did not open `scripts/token_shield.py` to read their exact signatures. Step 5 names this as its first required action: read that file before writing a line of `get_summary`.

## Design decisions this plan makes mechanically, flagged for confirmation

These are not stated verbatim in either spec. Each is the smallest, most reuse-first choice available (ponytail rung 2: reuse what exists), stated plainly here so a reviewer can veto it before the builder session starts.

1. **Two wrapper patterns, chosen by whether the underlying function returns data or prints it.** Pure functions (`build_profile`, `advise`, `build_report`, `load_strategies`, `record_decision`, `load_treatments`) get called directly and their return value serialized to JSON. Print-and-exit-code functions (`cmd_start`, `cmd_end`, `cli.summary`, `cli.dashboard`) get called with `contextlib.redirect_stdout` capturing their text, and the tool returns `{"text": <captured>, "exit_code": <int>}`. This matches the top spec's own words, "output shapes matching the CLI's own," without writing a second copy of any script's logic. A builder disagreeing with this convention should raise it before step 3, since every tool step depends on it.
2. **`get_summary` reuses `cli._verified_by_label` (a private, underscore-prefixed function) plus `ts.savings_breakdown` and `ts.prescriptions` directly, rather than capturing `cli.summary()`'s stdout.** `cli.summary()` mixes computation with `print()` calls that talk about `python3 cli.py ...` invocations, which is CLI-flavored text an MCP client should not have to parse. Confirm this before step 5; the fallback is capturing `cli.summary()`'s stdout verbatim like the other print-and-exit-code tools, which is simpler but noisier for an MCP client.
3. **`detail_report.py`'s per-number objects use the field name `source`, per the Consumption Report spec's schema v1 text ("Every number in every section is an object `{value, label, source}`"), not `basis` like `profile.py`'s existing `metric()` helper.** This is a deliberate naming split: `detail_report.py` gets its own local `metric(value, label, source)` helper rather than reusing `profile.metric()`, because the spec's schema is the contract external MCP clients build against and it names the field `source`. Confirm this before step 12; the alternative is changing the schema wording to `basis` to match the existing helper, which the spec does not currently say.

## Implementation steps

### Step 1: Scaffold the `mcp-server/` package

Create:
- `mcp-server/pyproject.toml` (package name `token-shield-mcp`, depends on the official MCP Python SDK; pin the exact package name and version by running `pip index versions mcp` or reading `https://pypi.org/project/mcp/` at build time, do not guess the pin from memory)
- `mcp-server/src/token_shield_mcp/__init__.py`
- `mcp-server/src/token_shield_mcp/server.py` (stdio transport entry point, empty tool registry for now)
- `mcp-server/README.md` (stub, filled in step 20)

The server imports the existing `scripts/` modules as a library. Add `scripts/` to the importable path (either a relative `sys.path` insert at the top of `server.py`, matching the pattern every existing test file already uses, see `scripts/test_profile.py:10-11`, `import profile as pf` / `import measure_tokens as mt` with no package install step, or a proper package dependency if the builder session decides `scripts/` should become an installable package; that decision is not made by this plan, re-grep `scripts/test_*.py` for the existing convention and mirror it, per the CLAUDE.md rule to mirror the closest sibling).

Estimate: 2 to 4 hours, medium confidence. Assumes the official MCP Python SDK's stdio path needs no more than package install plus one `stdio_server()` call, as both specs assume.

Done check:
```bash
cd /Users/khalil.maaouni/SaveClaudeTokens/mcp-server && python3 -c "import sys; sys.path.insert(0, '../scripts'); import profile, measure_tokens, advisor, report, experiment; print('imports ok')"
```
Must print `imports ok`.

### Step 2: Write the DataSource contract

File: `mcp-server/src/token_shield_mcp/datasource.py`

A small ABC or `typing.Protocol` (Python 3.11 floor, `Protocol` is fine) named `DataSource` with two members: `list_usage_records()` and `source_label`, per the MCP design spec's Architecture section. One implementation, `TranscriptDataSource`, wraps `measure_tokens.collect(root, days)` and sets `source_label = "claude-code-transcripts"`. This is the seam future adapters (Cursor, Codex, deepseek, FCC) plug into; wave 1 ships only this one implementation, do not stub the others.

Estimate: 1 to 2 hours, high confidence, this is a thin pass-through.

Done check:
```bash
cd /Users/khalil.maaouni/SaveClaudeTokens/mcp-server && python3 -c "
import sys; sys.path.insert(0, '../scripts'); sys.path.insert(0, 'src')
from token_shield_mcp.datasource import TranscriptDataSource
ds = TranscriptDataSource()
print(ds.source_label)
"
```
Must print `claude-code-transcripts` (or whatever literal label the builder picks; the point of the check is that the class imports and the attribute exists without a NameError or AttributeError).

### Step 3: Write the wrapper helper module

File: `mcp-server/src/token_shield_mcp/wrappers.py`

Two helpers implementing design decision 1 above:
- `call_pure(fn, *args, **kwargs)`: calls `fn`, returns its value as-is (the MCP tool layer serializes to JSON).
- `call_printing(fn, *args, **kwargs)`: calls `fn` inside `contextlib.redirect_stdout(io.StringIO())`, returns `{"text": captured.getvalue(), "exit_code": result}`.

Estimate: 1 hour, high confidence, this is two functions using only the standard library (`contextlib`, `io`).

Done check:
```bash
cd /Users/khalil.maaouni/SaveClaudeTokens/mcp-server && python3 -c "
import sys; sys.path.insert(0, 'src')
from token_shield_mcp.wrappers import call_pure, call_printing
def p(): print('hello'); return 0
r = call_printing(p)
assert r == {'text': 'hello\n', 'exit_code': 0}, r
print('wrappers ok')
"
```
Must print `wrappers ok`.

### Step 4: Tool `get_profile`

File: `mcp-server/src/token_shield_mcp/tools/get_profile.py` (or a single `tools.py` if the builder session prefers fewer files; either is fine, this plan does not mandate one file per tool)

Calls `call_pure(profile.build_profile, root=None, days=window_days)` where `window_days` is the tool's one optional argument, default 30. Returns the dict as-is. No new logic.

Estimate: 30 minutes, high confidence.

Done check:
```bash
cd /Users/khalil.maaouni/SaveClaudeTokens/mcp-server && python3 -c "
import sys; sys.path.insert(0, '../scripts'); sys.path.insert(0, 'src')
import profile as pf
from token_shield_mcp.wrappers import call_pure
result = call_pure(pf.build_profile, root='/nonexistent-path-for-check', days=30)
assert 'usage' in result and 'behavior' in result, result.keys()
print('get_profile wiring ok')
"
```
Must print `get_profile wiring ok`.

### Step 5: Tool `get_summary`

Before writing this tool, open `scripts/token_shield.py` and read the exact signatures of `savings_breakdown(sm)` and `prescriptions(sm, sessions)` (both are used in `cli.py` but were not read during this planning pass). Copy the exact call shape from what that read shows, do not guess from the `cli.py` call site alone since keyword arguments may differ.

File: `mcp-server/src/token_shield_mcp/tools/get_summary.py`

Per design decision 2, this tool reuses `cli._verified_by_label()`, `token_shield.savings_breakdown(sm)`, and `token_shield.prescriptions(sm, sessions)` directly (the same three calls `cli.summary()` makes internally, read at `scripts/cli.py:77-109`), assembling a structured dict: `{"verified": [...], "native_saved": <int>, "opportunity_estimated": <int>, "top_issue": {...} | None}`. It does not call `cli.summary()` itself, because that function's prints are written for a terminal, not a JSON consumer (see design decision 2 for the fallback if this is rejected).

Estimate: 2 to 3 hours, medium confidence, pending the `token_shield.py` read above.

Done check:
```bash
cd /Users/khalil.maaouni/SaveClaudeTokens/mcp-server && python3 -c "
import sys; sys.path.insert(0, '../scripts'); sys.path.insert(0, 'src')
from token_shield_mcp.tools.get_summary import get_summary
result = get_summary(root='/nonexistent-path-for-check')
assert isinstance(result, dict), result
print('get_summary wiring ok')
"
```
Must print `get_summary wiring ok`, and must not raise on a root that has no transcripts (the NO DATA path has to survive, since the honesty rules say NO DATA beats a guess).

### Step 6: Tool `get_advice`

File: `mcp-server/src/token_shield_mcp/tools/get_advice.py`

Calls `call_pure(profile.build_profile, root=None, days=window_days)`, then `call_pure(advisor.advise, profile=<that result>, treatments=advisor.load_treatments(), strategies=advisor.load_strategies())`. Returns the `advise()` result dict as-is, including the `do_nothing` / `message` path for a healthy profile, and the `insufficient` list.

Estimate: 1 hour, high confidence, this composes two already-pure functions with zero new logic.

Done check:
```bash
cd /Users/khalil.maaouni/SaveClaudeTokens/mcp-server && python3 -c "
import sys; sys.path.insert(0, '../scripts'); sys.path.insert(0, 'src')
import profile as pf, advisor as adv
from token_shield_mcp.wrappers import call_pure
p = call_pure(pf.build_profile, root='/nonexistent-path-for-check', days=30)
result = call_pure(adv.advise, profile=p, treatments=adv.load_treatments(), strategies=adv.load_strategies())
assert 'best' in result and 'queue' in result, result.keys()
print('get_advice wiring ok')
"
```
Must print `get_advice wiring ok`.

### Step 7: Tool `get_monthly_report`

File: `mcp-server/src/token_shield_mcp/tools/get_monthly_report.py`

Calls `call_pure(report.build_report, year, month, root=None)`. Takes `year` and `month` as required tool arguments (the spec's `get_monthly_report` line does not state a default month; `report.py`'s own CLI defaults to `_previous_month(today=None)` at `scripts/report.py:64`, mirror that default here rather than inventing a new one). Returns the markdown string as-is.

Estimate: 1 hour, high confidence.

Done check:
```bash
cd /Users/khalil.maaouni/SaveClaudeTokens/mcp-server && python3 -c "
import sys; sys.path.insert(0, '../scripts'); sys.path.insert(0, 'src')
import report as rpt
from token_shield_mcp.wrappers import call_pure
result = call_pure(rpt.build_report, 2026, 1, root='/nonexistent-path-for-check')
assert isinstance(result, str) and 'Token Shield monthly report' in result, result[:80]
print('get_monthly_report wiring ok')
"
```
Must print `get_monthly_report wiring ok`.

### Step 8: Tool `list_strategies`

File: `mcp-server/src/token_shield_mcp/tools/list_strategies.py`

Calls `call_pure(advisor.load_strategies)`. Returns the list of strategy dicts as-is, each already carrying a `source` field the spec calls "citable sources" (see `advisor.py:150 format_source`, applied inside `_card`, not inside `load_strategies` itself; confirm whether `list_strategies` should run each entry through `format_source` too, since raw `load_strategies()` output carries the unformatted `source` field from `data/strategies.json`, not the citable rendering `_card` produces. This is a third naming/shape question, smaller than the two flagged above: default to calling `format_source` on each entry's `source` field before returning, since the spec explicitly says "with citable sources.")

Estimate: 1 hour, high confidence.

Done check:
```bash
cd /Users/khalil.maaouni/SaveClaudeTokens/mcp-server && python3 -c "
import sys; sys.path.insert(0, '../scripts'); sys.path.insert(0, 'src')
import advisor as adv
from token_shield_mcp.wrappers import call_pure
result = call_pure(adv.load_strategies)
assert isinstance(result, list) and len(result) > 0, result
print('list_strategies wiring ok, ' + str(len(result)) + ' strategies')
"
```
Must print `list_strategies wiring ok, N strategies` with N greater than 0.

### Step 9: Tool `record_decision`

File: `mcp-server/src/token_shield_mcp/tools/record_decision.py`

The one write tool besides the experiment pair. Calls `call_pure(advisor.record_decision, strategy_id, decision, days=90, note="", path=advisor.TREATMENTS_PATH)`, letting the `ValueError` on an unknown decision propagate up to the error-passthrough layer (step 15) rather than being caught here. Per the spec: "echoes exactly what it recorded and when it resurfaces," so the tool returns `record_decision`'s own return value (the record dict, which carries `until` for rejected/suppressed or `lineage` for accepted) unmodified.

Estimate: 1 hour, high confidence.

Done check:
```bash
cd /Users/khalil.maaouni/SaveClaudeTokens/mcp-server && python3 -c "
import sys, tempfile, os
sys.path.insert(0, '../scripts'); sys.path.insert(0, 'src')
import advisor as adv
from token_shield_mcp.wrappers import call_pure
with tempfile.TemporaryDirectory() as d:
    path = os.path.join(d, 'treatments.json')
    rec = call_pure(adv.record_decision, 'test-strategy', 'not-now', days=90, note='', path=path)
    assert rec['decision'] == 'not-now' and 'until' in rec, rec
    print('record_decision wiring ok')
"
```
Must print `record_decision wiring ok`.

### Step 10: Tool `experiment_start`

File: `mcp-server/src/token_shield_mcp/tools/experiment_start.py`

Calls `call_printing(experiment.cmd_start, label, root, days, now_ts, treats)`. `root` defaults to `~/.claude/projects` (matches `cli.py`'s `ROOT` constant), `days` defaults to 30 (matches `cli.py`'s `EXPERIMENT_DAYS` constant), `now_ts` is always `time.time()` read fresh at call time, never a cached value, `treats` is an optional tool argument passed through unchanged. Returns `{"text": ..., "exit_code": ...}` per the wrapper convention; the refusal and NOT_PROVEN text lives inside `text`, verbatim, satisfying "refusals ... returned verbatim."

Estimate: 1 to 2 hours, medium confidence (the sandbox test in step 16 needs a seeded HOME so `cmd_start` writes its baseline snapshot somewhere disposable).

Done check:
```bash
cd /Users/khalil.maaouni/SaveClaudeTokens/mcp-server && python3 -c "
import sys, os, time, tempfile
sys.path.insert(0, '../scripts'); sys.path.insert(0, 'src')
with tempfile.TemporaryDirectory() as home:
    os.environ['HOME'] = home
    import importlib
    import experiment as ex
    importlib.reload(ex)
    from token_shield_mcp.wrappers import call_printing
    result = call_printing(ex.cmd_start, 'wave1-check', '/nonexistent-path-for-check', 30, time.time(), None)
    assert 'text' in result and 'exit_code' in result, result
    print('experiment_start wiring ok')
"
```
Must print `experiment_start wiring ok`. Note the `importlib.reload` line: `experiment.py`'s `STORE`/`EXP_DIR`/`LEDGER` constants are built from `os.path.expanduser("~/...")` at import time (see `scripts/experiment.py:51-53`), so a test that sets `HOME` after the module is already imported gets the wrong path unless the module is reloaded (or the process is started fresh with `HOME` set first). Carry this same care into the seeded-sandbox test file in step 16.

### Step 11: Tool `experiment_end`

File: `mcp-server/src/token_shield_mcp/tools/experiment_end.py`

Calls `call_printing(experiment.cmd_end, label, root, days, now_ts)`, same defaults and same fresh-`now_ts` rule as step 10. Returns the same `{"text", "exit_code"}` shape.

Estimate: 1 hour, high confidence, this is the same pattern as step 10 with one fewer argument.

Done check:
```bash
cd /Users/khalil.maaouni/SaveClaudeTokens/mcp-server && python3 -c "
import sys, os, time, tempfile, importlib
sys.path.insert(0, '../scripts'); sys.path.insert(0, 'src')
with tempfile.TemporaryDirectory() as home:
    os.environ['HOME'] = home
    import experiment as ex
    importlib.reload(ex)
    from token_shield_mcp.wrappers import call_printing
    result = call_printing(ex.cmd_end, 'no-such-label', '/nonexistent-path-for-check', 30, time.time())
    assert result['exit_code'] == 2 and 'NO DATA' in result['text'], result
    print('experiment_end wiring ok, NO DATA refusal passed through verbatim')
"
```
Must print `experiment_end wiring ok, NO DATA refusal passed through verbatim`. This exercises the real refusal path (`cmd_end` prints `NO DATA: no baseline named '...'` at `scripts/experiment.py:449` and returns 2 when no baseline file exists), proving the passthrough carries the exact wording rather than a paraphrase.

### Step 12: New module `scripts/detail_report.py`, schema v1

GATED. Do not create this file before the gate check at the top of this plan passes.

File: `scripts/detail_report.py`

Per design decision 3, this module defines its own `metric(value, label, source)` helper (field name `source`, not `basis`), matching the Consumption Report spec's schema wording exactly. The module's one public entry point, name it `build_detail_report(root=None, window_days=30)`, is a pure function of disk state (mirror `report.build_report`'s own doc comment style at `scripts/report.py:287-289`: "Pure function of disk state: no printing, no writing, so it stays directly testable"). It composes, never reimplements:

- `measure_tokens.collect(root, days=window_days)` for the raw per-session list (each session dict carries `started`, an ISO timestamp, per `scripts/measure_tokens.py:225`; this is the per-day timestamp source both specs assume exists, confirmed present during this planning pass).
- `measure_tokens.summarize(sessions)` for the aggregate totals feeding `startup_floor`, `subagents`, and `cache`.
- `profile.build_profile(root, days=window_days)` for cross-checking the same MEASURED figures the profiler already computes (share of total spend, model-switch behavior), rather than recomputing them a second way.
- `context_lint.default_targets(all_memory=False)` plus `context_lint.check(path, is_memory_index)` for each returned path, ranking by `stats["loaded_bytes"]`, for `startup_floor.top_contributors` (see the Consumption Report spec's section 1 line, "top contributors as reported by `context_lint.py`," confirmed against `context_lint.py`'s exact function names during this pass; `check()` and `default_targets()` are the only two functions in that file able to produce this).
- New aggregation logic (genuinely new, not a reuse of an existing function) that buckets `collect()`'s per-session `started` timestamps by calendar day and by hour-of-day/weekday, for the `rhythm` section and for `daily_series`. This is the one part of this module with no existing counterpart anywhere in `scripts/`; write it as a small private helper, e.g. `_bucket_by_day(sessions)`, and skip any session whose `started` is `None` (subagent-only transcripts never set it, per `scripts/measure_tokens.py:213-215`) rather than crashing on it or silently zero-filling it into day one.

Five sections plus `daily_series`, per the spec's schema v1 list (`startup_floor`, `subagents`, `cache`, `rhythm`, `habits`), each leaf `{value, label, source}`, missing data reported as `no_data(...)` (this module's own local version, same shape, never a guessed number). `daily_series` bounded at `window_days` rows exactly, per the spec's "Bounded on purpose" paragraph; a builder must not let it exceed that even when more days of data exist in a wider scan.

The `habits` section (named findings, each with `what`/`why_it_matters`/`action`/`confidence`) is the one section requiring judgment calls about what counts as a "habit." This plan does not enumerate the exact habit rules (that is itself a design decision the spec leaves open); flag any concrete habit-detection heuristic the builder invents back to a review pass before it ships, since a wrong heuristic here is exactly the "guess dressed as a finding" the house rules forbid.

Estimate: 1 to 2 working days, medium confidence, per the Consumption Report spec's own effort line ("1 to 2 working days inside the MCP wave 1 build ... Assumes the profiler's data structures expose per-day timestamps as they do today"), confirmed true during this planning pass.

Done check:
```bash
cd /Users/khalil.maaouni/SaveClaudeTokens && python3 -c "
import sys; sys.path.insert(0, 'scripts')
import detail_report as dr
result = dr.build_detail_report(root='/nonexistent-path-for-check', window_days=30)
for key in ('report_schema', 'generated_at', 'window_days', 'source_label',
            'startup_floor', 'subagents', 'cache', 'rhythm', 'habits', 'daily_series'):
    assert key in result, f'missing {key}'
assert result['report_schema'] == 1, result['report_schema']
assert len(result['daily_series']) <= 30, len(result['daily_series'])
print('detail_report schema v1 ok')
"
```
Must print `detail_report schema v1 ok`.

### Step 13: Tool `get_detailed_report`

GATED, same as step 12.

File: `mcp-server/src/token_shield_mcp/tools/get_detailed_report.py`

Calls `call_pure(detail_report.build_detail_report, root=None, window_days=window_days)`, `window_days` default 30 per the spec's own signature line, `get_detailed_report(window_days=30)`. Returns the schema v1 dict as-is; read-only, no new write surface, per both specs' explicit statement that this tool adds zero to the write surface.

Estimate: 30 minutes, high confidence, this is the thinnest wrapper in the set.

Done check:
```bash
cd /Users/khalil.maaouni/SaveClaudeTokens/mcp-server && python3 -c "
import sys; sys.path.insert(0, '../scripts'); sys.path.insert(0, 'src')
import detail_report as dr
from token_shield_mcp.wrappers import call_pure
result = call_pure(dr.build_detail_report, root='/nonexistent-path-for-check', window_days=30)
assert result['report_schema'] == 1
print('get_detailed_report wiring ok')
"
```
Must print `get_detailed_report wiring ok`.

### Step 14: Resources

File: `mcp-server/src/token_shield_mcp/resources.py`

Three MCP resources, per the design spec's Architecture section: the rendered dashboard HTML (the file `cli.py`'s `OUT` constant points at, `~/.token-shield/token-shield.html`, generated by `token_shield.py`, read as bytes if present, NO DATA-style refusal if absent, never auto-generated by the resource read itself since that would be a silent write outside the two named write tools), `docs/METHODOLOGY.md`, and `docs/CLAIMS.md` (both confirmed present in the repo during this pass, read as plain text).

Estimate: 1 hour, high confidence.

Done check:
```bash
cd /Users/khalil.maaouni/SaveClaudeTokens && test -f docs/METHODOLOGY.md && test -f docs/CLAIMS.md && echo "resource source files present"
```
Must print `resource source files present`.

### Step 15: Error passthrough rules

File: `mcp-server/src/token_shield_mcp/errors.py`

One small module implementing the rule stated identically in both specs: tool errors surface as MCP tool errors carrying the underlying script's own message; nothing retries silently; nothing degrades to an estimate without the ESTIMATED label. Concretely: any exception raised inside a `call_pure` or `call_printing` invocation (for example `record_decision`'s `ValueError` on an unknown decision string) propagates to the MCP SDK's own error-reporting path unmodified, no `except Exception: return {"error": "something went wrong"}` catch-all anywhere in this package. A `call_printing` result with a nonzero `exit_code` is NOT raised as an error (a refusal or a NO DATA text is not an exception, per both specs, it is data the client reads), only a Python exception becomes an MCP tool error.

Estimate: 1 to 2 hours, high confidence for the rule itself, medium for the exact MCP SDK error-surface mechanism (depends on the SDK's own API, confirm the exact call at build time against the installed package, do not guess it now).

Done check:
```bash
cd /Users/khalil.maaouni/SaveClaudeTokens/mcp-server && python3 -c "
import sys; sys.path.insert(0, '../scripts'); sys.path.insert(0, 'src')
import advisor as adv
from token_shield_mcp.wrappers import call_pure
try:
    call_pure(adv.record_decision, 'x', 'not-a-real-decision', path='/tmp/does-not-matter.json')
    raise SystemExit('expected ValueError, none raised')
except ValueError as e:
    assert 'not-a-real-decision' in str(e), e
    print('error passthrough ok: ' + str(e)[:60])
"
```
Must print a line starting with `error passthrough ok:`.

### Step 16: Test file, MCP server

File: `mcp-server/test_mcp_server.py`

One assert-based test file in the existing calibrated style (no framework, no fixtures, mirror `scripts/test_profile.py`'s and `scripts/test_experiment.py`'s own top-of-file docstring and `_rec()`-style synthetic-record helpers). It must exercise, at minimum:

- Every one of the nine tools, called against a seeded sandbox `HOME` (a `tempfile.TemporaryDirectory()` with `HOME` set before any `scripts/` module carrying a module-level `os.path.expanduser("~/...")` constant is imported or reloaded, per the note in step 10).
- Both write tools (`record_decision`, and the `experiment_start`/`experiment_end` pair) round-tripped: write, then read the same file back and assert the written value matches.
- The no-blend rule, asserted with two fake `DataSource` implementations carrying different `source_label` values, proving the server never merges their numbers into one figure (this is the one assertion this plan cannot pre-write, since it depends on the exact tool surface that reads multiple sources, which wave 1 does not yet have beyond the single `TranscriptDataSource`; if wave 1 truly ships only one DataSource implementation, this assertion instead proves the contract itself refuses a second source without an explicit label, not that two real sources coexist without blending).

Estimate: 3 to 5 hours, medium confidence, this is the largest single test file in the set.

Done check:
```bash
cd /Users/khalil.maaouni/SaveClaudeTokens/mcp-server && python3 test_mcp_server.py
```
Must exit 0 with no assertion failure printed.

### Step 17: Test file, detail_report

GATED, same as step 12.

File: `scripts/test_detail_report.py`

Per the Consumption Report spec's Testing section: schema validated field by field against a seeded sandbox HOME, every section exercised with data present and with data missing (NO DATA asserted verbatim, not just "is falsy"), the label-blend refusal asserted, `daily_series` bound asserted at the window edge (feed it more than `window_days` worth of synthetic sessions and assert the returned list is still exactly `window_days` long or fewer, never more). Calibrated by defect reinjection, per the repo-wide rule in `CLAUDE.md` line 19: write the test red against the pre-fix `detail_report.py` first if a defect is found during step 12's build, then green after the fix, and say so in the commit that lands it.

Estimate: 3 to 4 hours, medium confidence.

Done check:
```bash
cd /Users/khalil.maaouni/SaveClaudeTokens/scripts && python3 test_detail_report.py
```
Must exit 0 with no assertion failure printed.

### Step 18: Live smoke test against a real MCP client

Per both specs: one live smoke test before release, in addition to the assert-based files above. This step is manual, not scriptable into a single done-check the way the others are; a builder session runs the `mcp-server/` package against a real MCP client (Claude Desktop, or any MCP Inspector-style tool) pointed at the stdio entry point built in step 1, calls each of the nine tools once with real (or realistically seeded) data, and confirms each response matches its schema. Record the transcript of that session (screenshots or copied tool-call/response pairs) as the evidence this step ran, since there is no automated proof otherwise.

Estimate: 1 to 2 hours, low confidence (depends entirely on how straightforward the chosen MCP client's config UI is, unmeasured until tried).

Done check: no single command; the record of the manual session (tool calls in, responses out, for all nine tools) is the evidence. State explicitly in the closing report which client was used.

### Step 19: CI wiring

File: `.github/workflows/ci.yml`

The existing job runs, verbatim, from `.github/workflows/ci.yml:14-19` today:
```
python3 scripts/check_py311.py --selftest && python3 scripts/check_py311.py
```
and
```
cd scripts && python3 test_measure_tokens.py && python3 test_tools.py && python3 test_pricing.py && python3 test_experiment.py && python3 test_optimize.py && python3 test_profile.py && python3 test_advisor.py && python3 test_report.py
```
Add `test_detail_report.py` to that same `cd scripts && ...` chain (making it eight test files, per this plan's brief line naming "the eight test files": the seven already listed plus `test_detail_report.py`). Add one new CI step running `mcp-server/test_mcp_server.py`, with its own `cd mcp-server && python3 test_mcp_server.py` line (or fold it into a step that first installs `mcp-server`'s dependencies via its `pyproject.toml`, since that test file imports the MCP SDK where the top-level `check_py311`/`scripts` tests do not).

Estimate: 1 hour, high confidence, this is editing one YAML file.

Done check:
```bash
cd /Users/khalil.maaouni/SaveClaudeTokens && grep -c "test_detail_report.py" .github/workflows/ci.yml && grep -c "test_mcp_server.py" .github/workflows/ci.yml
```
Both greps must return a count of at least 1.

### Step 20: README install block

File: `README.md`

Add one new section, sibling to the existing `## Install` section (`README.md:15-22`), naming it `## MCP server (optional)` or similar, containing the one-config-line install the design spec promises ("One config line installs it in any client"). Mirror the existing `## Install` section's terse, command-first style: a fenced code block with the exact client config JSON (server name, command, args pointing at the `mcp-server/` stdio entry point), then one sentence saying what it adds (the nine tools plus the three resources) and one sentence on scope (local only, opt-in, zero cost to the plugin's default footprint, per the design spec's Architecture paragraph).

Estimate: 1 hour, high confidence.

Done check:
```bash
cd /Users/khalil.maaouni/SaveClaudeTokens && grep -n "MCP server" README.md
```
Must return at least one match.

### Step 21: Version tagging with the plugin

Files: `.claude-plugin/plugin.json`, `CHANGELOG.md`, `mcp-server/pyproject.toml`

Per the design spec's Distribution section: "The plugin and the MCP server version together." Bump `.claude-plugin/plugin.json`'s `"version"` field (currently `1.7.1`, confirmed this date) to the next version implementing this wave, set `mcp-server/pyproject.toml`'s own version field to match, and add one new `CHANGELOG.md` entry at the top (mirroring the existing `## 1.7.1` entry's bullet style at `CHANGELOG.md:6-20`) naming the MCP server, the nine tools, and the Consumption Report schema v1 as what shipped. Do not invent the next version number here; that is a decision for the builder session to make against the repo's own versioning convention at the time (check whether recent bumps are patch, minor, or major and match the pattern, do not guess semver rules never confirmed against this repo's actual history).

Estimate: 1 hour, high confidence for the mechanical edits, the version number choice itself is the one open call.

Done check:
```bash
cd /Users/khalil.maaouni/SaveClaudeTokens && python3 -c "
import json
p = json.load(open('.claude-plugin/plugin.json'))
print(p['version'])
" && head -5 CHANGELOG.md
```
Must print a version number different from `1.7.1`, and the `CHANGELOG.md` head must show a new top entry above the `## 1.7.1` line.

## Total effort roll-up

Wave 1 minus the Consumption Report (steps 1 to 11, 14 to 16, 18 to 21): roughly 2 to 4 working days, medium confidence, per the MCP design spec's own line, confirmed unchanged during this pass.

Consumption Report addition (steps 12, 13, 17): roughly 1 to 2 working days, medium confidence, per that spec's own line, confirmed the profiler's per-day timestamp assumption holds.

Combined: 3 to 6 working days after the gate opens. This range carries the same assumption both specs state: the MCP Python SDK's stdio path works as documented, unverified in this planning pass since no implementation file was created to test it.

## Ambiguities flagged for review before a builder session starts (not resolved by this plan)

1. The wrapper-pattern split (pure-call versus stdout-capture) in design decision 1: not stated explicitly in either spec, inferred as the smallest-diff reading of "output shapes matching the CLI's own."
2. `get_summary`'s exact data source in design decision 2: reusing a private, underscore-prefixed function (`cli._verified_by_label`) across a package boundary is a minor layering smell; the fallback (stdout-capturing `cli.summary()`) is uglier for a JSON client but avoids reaching into another module's private name.
3. The `metric()` field name split (`source` in `detail_report.py` versus `basis` in `profile.py`) in design decision 3: the two modules will describe the same kind of fact with two different field names unless someone later renames one to match the other.
4. Whether `list_strategies` should run each entry through `advisor.format_source` before returning (step 8): the spec says "with citable sources," `format_source` is the only function in the repo that renders a citable source string, but `load_strategies()` itself does not call it.
5. `scripts/token_shield.py`'s `savings_breakdown` and `prescriptions` signatures were not read during this planning pass; step 5 names this explicitly as its required first action, not a gap silently left for the builder to discover mid-implementation.
6. The `habits` section's actual detection heuristics (step 12): the spec names the shape (`what`/`why_it_matters`/`action`/`confidence`) but not the rules that decide when a pattern counts as a habit worth surfacing. This is real, unresolved design work, not a naming choice.
