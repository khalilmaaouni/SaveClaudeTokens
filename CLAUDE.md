# Token Shield: working rules for Claude sessions in this repo

## What this is
A Claude Code plugin that measures where tokens go and proves its own numbers. The repo doubles as its own plugin marketplace. Public at github.com/khalilmaaouni/token-shield. Sole credited author: Khalil Maaouni.

## Commands (documented, never guessed)
- Full test suite, from repo root (CI, .github/workflows/ci.yml, runs more than this line: it also runs `python3 scripts/check_py311.py --selftest` before check_py311.py, then the bench self-check and benchmark (`python3 bench/test_bench.py && python3 bench/generate_corpus.py --out /tmp/bench-corpus && python3 bench/run_benchmark.py --corpus /tmp/bench-corpus`), then `python3 -m pip install ./mcp-server` and `cd mcp-server && python3 test_mcp_server.py` after this line):
  `python3 scripts/check_py311.py && cd scripts && python3 test_measure_tokens.py && python3 test_reconcile.py && python3 test_tools.py && python3 test_pricing.py && python3 test_experiment.py && python3 test_guided_apply.py && python3 test_optimize.py && python3 test_plugin_prune.py && python3 test_memory_trim.py && python3 test_profile.py && python3 test_advisor.py && python3 test_report.py && python3 test_detail_report.py && python3 test_discover_companions.py && python3 test_doctor.py && python3 test_companions.py && python3 test_deep_advisor.py && python3 test_share_card.py && python3 test_signals.py && python3 test_fleet.py && python3 test_trial.py && python3 test_install_smoke.py && python3 test_fleet_dashboard.py && python3 test_architecture.py`
- MCP server tests locally: `cd mcp-server && python3 test_mcp_server.py` (13 passed, exit 0). Do NOT prefix it with `python3 -m pip install ./mcp-server` locally, corrected 2026-08-16: that exits 1 on this machine because the system Python is externally managed (PEP 668), so the `&&` chain stops before the test runs. The install is not a precondition anyway, since `test_mcp_server.py` puts `src/` and `scripts/` on `sys.path` at lines 21 and 22 and imports from the source tree whether or not a package is installed. CI keeps its own install step and that is correct there: on a clean runner it also proves the package builds. Bench tests locally, from repo root: `python3 bench/generate_corpus.py --out /tmp/bench-corpus && python3 bench/run_benchmark.py --corpus /tmp/bench-corpus` (kit self-check: `python3 bench/test_bench.py`).
- Dashboard: `python3 scripts/cli.py dashboard` (writes ~/.token-shield/token-shield.html)
- Profiler: `python3 scripts/cli.py profile`; advisor: `python3 scripts/cli.py advise`
- Experiments: `python3 scripts/cli.py experiment start|end "<label>"`

## Gates, all of them
- Branch plus pull request, never a direct commit to main.
- Before any push, over the WHOLE pushed range, fail closed: secret scan, em and en dash scan, attribution scan. Any hit stops the push.
- No AI vendor attribution anywhere: no Co-Authored-By trailer, no generated-with footer, in commits, PRs, docs, or code.
- No em or en dashes anywhere. Test needles that must contain a dash character build it from the codepoint (a Python unicode escape for U+2013 or U+2014 inside a normal string literal), never the literal byte in source.
- Python 3.11 floor: scripts/check_py311.py must pass; CI runs it before the tests.
- Every fix ships with a test calibrated by reinjecting the defect (red) before the fix (green). A test born green proves nothing.
- Nothing is "done" without the verifying command run after the last edit and its output quoted.

## Invariants that never merge
- Confidence labels stay separate: VERIFIED (a closed experiment proved it), MEASURED (counted on this machine), ESTIMATED (a projection), NATIVE (Anthropic's own behavior, notably caching: attributed, never claimed, never in dollars on the dashboard), RECOMMENDED (a rank, never evidence).
- Savings report per label; the latest record per label wins; regressions show negative; no cross-label totals anywhere.
- NO DATA beats a guess, always.
- The plugin registers zero hooks by default; everything is opt-in.
- Command surface is capped at 6 command files.

## The ratified gate
Version 1.8 (deep advisor subagent, semantic optimizer, ecosystem waves in docs/ROADMAP.md) does not start until one real experiment reaches VERIFIED or an honest NOT_PROVEN in the proof ledger. Do not create v1.8 files before that record exists.

FOUNDER AMENDMENT 2026-08-13 (explicit decision via question window, after the gate collision was surfaced with the ~30 day verdict timeline): BUILDING is authorized before the verdict. The gate MOVES to the release boundary: no version tag, no release, no plugin publish, and no local plugin update or MCP client registration on this machine until the claude-md-diet experiment reaches VERIFIED or an honest NOT_PROVEN. The experiment itself stays untouched while it runs.

## Machine-local files
STATE.md, GANTT.html, PROJECT.md are gitignored working files for the founder's machine; they never ship in the plugin.
