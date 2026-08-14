# Token Shield

Save Claude Code tokens. Prove every saving.

[![tests](https://github.com/khalilmaaouni/token-shield/actions/workflows/ci.yml/badge.svg)](https://github.com/khalilmaaouni/token-shield/actions/workflows/ci.yml)

Token Shield continuously finds the cheapest high-quality way for you to use Claude Code, using native capabilities first and specialist plugins only when they prove their value. It measures what Claude Code actually consumed, finds the biggest waste, and proves what you cut with a real before and after. It reads the API usage counters Claude Code already writes to your disk, so the numbers are measured, not guessed. It runs locally and sends nothing anywhere.

- Measures real usage from your own transcripts.
- Keeps three numbers apart and never merges them: what Anthropic's caching already saved (native), what you can still cut (estimated), and what you proved (a verified before and after).
- Shows tokens and API-equivalent dollars, priced per model, or NO PRICE DATA instead of a wrong price.
- Local only. No account, no cloud. No prompt or file content leaves your machine.

## Install

```bash
claude plugin marketplace add khalilmaaouni/token-shield
claude plugin install token-shield@token-shield
```

That is the whole setup. The skill loads on demand, so it adds one listing line to your sessions and nothing else.

Then run `/token-shield:start` once: it measures your usage, names the one thing most worth fixing, and asks before it touches anything.

Or skip the walkthrough and run any command directly:

```bash
python3 scripts/cli.py summary               # /token-shield:stats
python3 scripts/cli.py dashboard             # open the GUI
python3 scripts/cli.py optimize              # /token-shield:optimize
python3 scripts/cli.py experiment start "X"  # /token-shield:token-audit
python3 scripts/cli.py advise                # /token-shield:advisor
python3 scripts/cli.py report                # /token-shield:monthly
```

> Formerly published as `SaveClaudeTokens`. If you installed the old plugin, remove it and re-add: `claude plugin uninstall save-claude-tokens`, then run the two commands above. GitHub redirects the old repository URL, but the plugin and skill ids changed, so a reinstall is needed.

## MCP server (optional)

One config line installs a read-only MCP server over the same data, for any client that speaks MCP (Claude Desktop, Cursor, Codex-style agents):

```json
{
  "mcpServers": {
    "token-shield": {
      "command": "python3",
      "args": ["/path/to/token-shield/mcp-server/src/token_shield_mcp/server.py"]
    }
  }
}
```

It adds nine tools (`get_profile`, `get_summary`, `get_advice`, `get_monthly_report`, `list_strategies`, `record_decision`, `experiment_start`, `experiment_end`, `get_detailed_report`) and three resources (the dashboard HTML, `docs/METHODOLOGY.md`, `docs/CLAIMS.md`), each a thin wrapper over the same scripts the CLI runs. It is a separate opt-in install: the plugin gains zero dependencies, zero hooks, and zero always-on cost from it, and it never touches anything outside Token Shield's own local store.

## Why this exists

Every API call in a Claude Code session resends the whole accumulated context. Most token waste comes from four places:

1. Cache-hostile habits: model switches, effort switches, and toolset changes mid-session that re-bill the entire prefix (cache writes cost 1.25x to 2x base input, cache reads only 0.1x).
2. A bloated always-loaded context: giant CLAUDE.md files, dozens of unused plugins, MCP servers nobody authenticated, chatty session-start hooks. That weight is paid on every call of every session.
3. Wrong model for the job: mechanical loops running on the strongest tier, or the cheapest tier being trusted to judge its own work.
4. Verbose output: raw log dumps, whole-file reads, uncapped subagent reports. Output is the most expensive token, and it gets re-read as input forever after.

The skill turns each of these into a short set of rules Claude applies automatically, plus a monthly audit ritual and a decision table for `/rewind` versus `/recap` versus `/compact` versus a fresh session.

Every behavioral claim in the skill is sourced to first-party documentation and dated, because this area changes. Several rules that circulate as folklore are wrong: editing CLAUDE.md mid-session is cache-safe (it just does not apply until you reload), while changing effort level rebuilds the whole prefix exactly like a model switch.

## What is inside

- The cost model: prefix caching, the three request layers, write and read multipliers, which TTL you get from which authentication, and the two non-text parts of the cache key.
- Lever 1: two tables of what actually rebuilds the cache and what is free, sourced rather than assumed.
- Lever 2: shrinking the always-loaded context, with a copy-paste audit ritual.
- Lever 3: choosing between `/rewind`, `/recap`, `/compact` and a fresh session by intent.
- Lever 4: a model routing table with tier declaration discipline, and where subagents pay for themselves.
- Lever 5: output discipline, including how to keep full evidence on disk and out of context.
- Lever 6: durable on-disk memory (works well with an Obsidian vault) so sessions stop re-deriving what past sessions already learned, with a promotion rule so the always-loaded file does not grow forever.
- An anti-pattern ledger seeded from real incidents.

## Measure, do not guess

The plugin ships a measurement script and a `/token-audit` command. The script
reads the `usage` counters the API returned on every assistant message in your
local session transcripts, which are the counters billing is computed from, so
its output is measurement rather than estimation. It reports:

- **First request cost and share**: the startup floor every later call in the session also pays, and how much of the session's total reading it accounts for.
- **Cache hit ratio**: how much of your context was re-read cheaply.
- **Cache writes split by TTL**: 5 minute and 1 hour writes bill differently (1.25x and 2x), so the split is parsed rather than assumed.
- **Rewrite ratio and model count per session**: signals for which sessions rebuilt their prefix, and a measured cause when the session switched model.
- **Subagent share**: how much of your output came from subagents rather than the main thread.

```bash
python3 scripts/measure_tokens.py --days 30 --sessions
python3 scripts/measure_tokens.py --days 30 --baseline before.json
# change one thing, then:
python3 scripts/measure_tokens.py --days 30 --compare before.json
```

Anything it cannot measure it prints as NO DATA rather than filling the gap
with a plausible number. It warns when you compare two windows of different
length, and it refuses outright to print a delta across a change to how a
metric is computed. Both produce a confident number that means nothing.

Use it to pick the lever before pulling it. On one machine, over 90 days, it
showed a 0.865 median cache hit ratio, which ruled out cache discipline as the
main problem; an 85,021 token median first request with a 0.360 median share,
which put the headroom squarely in the always-loaded set; and 41 percent of all
output tokens coming from subagents, which is a different lever again.

## The Advisor

The advisor profiles your session history and ranks the one best next move to cut tokens. It reads your transcript history and finds patterns: which sessions rebuilt their cache (model switch, effort change), where the startup floor is costing you the most, how much a model downgrade would save versus hurt quality, whether your hook setup is still valid. It offers one ranked action with full drawback disclosure, or do-nothing if the marginal gain is too small. Do-nothing is a valid answer. The advisor remembers treatments (changes you tried and their results) and learns which patterns respond to which fixes on your machine, not on a general baseline.

Every recommendation is backed by experiment-verified savings on your own data, or marked ESTIMATED when it comes from your historic pattern alone. The deterministic profiler costs zero tokens (it is a grep and a sum); the advisor subagent cost is printed so you can decide whether the time is worth the insight.

Every card names concrete "how" steps, 2 to 5 of them, a real copy-paste command where one applies, so drawback disclosure is never the end of the story. Decide what to do with a card in one command:

```bash
python3 scripts/cli.py advise --decide <strategy-id> done       # accepted
python3 scripts/cli.py advise --decide <strategy-id> not-now    # quiet for 90 days
python3 scripts/cli.py advise --decide <strategy-id> never      # does not resurface
```

The dashboard is static HTML, so each card's decision row is that same ready-to-copy command, never a button; each row also names `/token-shield:advisor` for anyone who would rather be walked through it step by step.

Run `/token-shield:advisor` (no args) for the next best move, guided: it shows one card in plain words, asks what to do through the question UI, and walks accepted steps one at a time. Run `/token-shield:start` once for the full onboarding journey, or to opt into the session-end telemetry hook that feeds the advisor.

## Optional tools, all opt in

The plugin registers no hooks and runs nothing on its own. Installing it costs
one skill listing line and one command listing line, and nothing else runs.
These three scripts exist for when you want them, and each does nothing until
you run it.

**`context_lint.py`** measures what you pay at every session start and reports
where the rent is going. It never edits a file.

```bash
python3 scripts/context_lint.py
```

It reads your CLAUDE.md files and this project's auto-memory index, then flags
duplicated rules, multi-step procedures that belong in a skill, rules that name
a path and could be scoped to load only when a matching file is read, and stale
dated entries. It is advisory and exits 0 by default so it never breaks a shell
chain; pass `--strict` to exit nonzero on a finding if you want to gate CI on
it. For the memory index it applies the documented load limit (the
first 200 lines or 25KB, whichever comes first) to the content that actually
loads, with frontmatter and HTML comments stripped the way Claude Code strips
them, and tells you exactly which lines are falling off the end unread.

**Guided apply** (`optimize.py`, `plugin_prune.py`, `memory_trim.py`) proposes
a change, shows the diff, and applies it only on your explicit yes: the
CLAUDE.md diet (`optimize.py --guided-apply`), a named bundle of plugins to
disable (`cli.py prune`), and trimming the auto-memory index back inside its
load limit (`cli.py trim`), plus one hardcoded output-discipline line
(`optimize.py --apply-output-discipline`). Every guided apply refuses outright
while any experiment is open and auto-opens its own experiment on success, so
the saving it claims is always proven, not asserted; see Pillar R of
`docs/superpowers/specs/2026-08-13-solid-core-design.md` for the full
contract.

**`session_end_telemetry.py`** appends one line of counters per session to a
local JSONL ledger, so you accumulate history without paying a model to
measure. It writes no conversation text, no file contents, and no prompts:
only counters, a model count, and the transcript's basename. It sends nothing
anywhere, prints nothing to stdout, and exits 0 even on failure so it can never
break the session it is measuring.

Wire it up yourself in `~/.claude/settings.json`:

```json
{
  "hooks": {
    "SessionEnd": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$HOME/.claude/plugins/<install-path>/scripts/session_end_telemetry.py\"",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

Set `TOKEN_LEDGER` to change where it writes. Default is
`~/.claude/token-ledger.jsonl`.

**`obsidian_export.py`** writes the numbers as a markdown note you can keep in
an Obsidian vault, a docs folder, or anywhere else.

```bash
python3 scripts/obsidian_export.py --out ~/Vault/AI/Claude/TOKEN_DASHBOARD.md --days 30
```

Aggregates only. Per-session rows are off unless you pass `--include-sessions`,
because transcript names identify sessions and a synced vault is a different
privacy boundary from a local disk. Obsidian is a viewer here, never a
dependency.

**`token_shield.py`** renders a Token Shield dashboard as a self-contained HTML
file. The visual language is Brave's shields panel, a shield and a few big
numbers, but the page shows only what you can act on: a deterministic alerts
band up top when a real threshold fires, the VERIFIED number Token Shield
itself proved, and the ranked pain points costing you tokens (model
switching, the startup floor, mid-session rebuilds), each with a "How,
exactly" block and a ready-to-copy decision command. Native caching, the
part Anthropic's own engine does underneath, gets one pointer sentence to
`docs/METHODOLOGY.md`, no numbers, no bars, no dollars, because a page about
what you can influence has no business headlining a mechanic you cannot
touch. NO DATA where a number cannot be measured.

```bash
python3 scripts/token_shield.py --out ~/token-shield.html --days 30
```

Aggregates only, no session identifiers, no paths. Open the HTML locally, or
publish it as a private artifact. This is your dashboard of your own numbers; the
repo ships the generator, never anyone's data.

Both test files run without a framework:

```bash
python3 scripts/test_measure_tokens.py && python3 scripts/test_tools.py
```

## The method, in full

This tool reports savings, so it has to be honest about how it knows them. The
full method, the telemetry, and how it stays correct over time are documented,
not asserted:

- [docs/METHODOLOGY.md](docs/METHODOLOGY.md): measure not estimate, the cost
  model, what "savings" means and how they are checked for real, and the five
  ways a meter drifts into dishonesty with the mechanism that closes each.
- [docs/TELEMETRY.md](docs/TELEMETRY.md): every field measured, the versioned
  metric schema, how it runs over time, and what never leaves the machine.
- [docs/MAINTENANCE.md](docs/MAINTENANCE.md): the monthly cadence, what a machine
  cleans versus what a human decides, and how to verify a cleanup actually saved.
- [docs/CLAIMS.md](docs/CLAIMS.md): every factual and numeric claim this project
  makes, each with the check that backs it. Doc claims quote a first-party page,
  measured numbers carry a snapshot and a second independent derivation, code
  claims name a calibrated test.

The headline numbers are re-derived by a second, independent code path and
checked for zero drift before they are published, and every measured figure
carries the same caveat: it was taken on one machine, so run the tools on yours.

## For skeptics: reproduce our numbers

Do not take a number on this page on faith.

- **Run the measurement on your own machine.** Every measured figure here came from one machine's transcripts, stated as such throughout. `python3 scripts/measure_tokens.py --days 30 --sessions` reads your own usage counters and prints your own numbers, not ours.
- **Check the reproducible benchmark.** A scripted comparison across configurations lives in `bench/`, see bench/README.md for how to run it and how it is scored.
- **Prove your own before and after.** Experiment Mode is the only path to a VERIFIED number in this tool: pin a baseline, make one change, close the window, and it either produces a real verified figure from your data or refuses with NOT_PROVEN rather than guess.

```bash
python3 scripts/cli.py experiment start "my-first-change"
# make one change, then:
python3 scripts/cli.py experiment end "my-first-change"
```

See [docs/EXPERIMENTS.md](docs/EXPERIMENTS.md) for what makes a comparison count and why it sometimes refuses.

## Pairs well with

- caveman (terse narration) and ponytail (minimal generated code) for the output side.
- token-saver (command output compression) for the input side.
- Any note system (Obsidian, plain markdown) for the memory side.

## Uninstall, no trace

The plugin registers no hooks by default. Installing it costs one listing line and nothing else runs until you ask it to.

Token Shield writes to three locations:

- `~/.token-shield/profile.json` (your session profile)
- `~/.token-shield/treatments.json` (advisor treatment memory)
- `~/.token-shield/token-shield.html` (the dashboard, if you ran it)
- `~/.claude/token-shield/savings.jsonl` (experiment ledger, once you start one)
- `~/.claude/settings.json`: one optional `SessionEnd` hook line (only if you ran `/token-shield:start`)

To uninstall with full cleanup:

```bash
claude plugin uninstall token-shield
python3 ~/.claude/plugins/cache/token-shield/*/scripts/cli.py uninstall
```

The uninstall script will print what exists on your machine, ask before removing each item, and print a short exit summary of any verified savings to keep. Removal deletes your local measurement history and is irreversible.

## License

MIT. Author: Khalil Maaouni.
