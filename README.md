# SaveClaudeTokens

Run Claude Code cheaply without losing quality. This plugin ships one skill, `save-claude-tokens`, a playbook Claude loads on demand when the work touches token cost: prompt caching, compaction decisions, model routing, config pruning, or output verbosity.

## Why this exists

Every API call in a Claude Code session resends the whole accumulated context. Most token waste comes from four places:

1. Cache-hostile habits: model switches, effort switches, and toolset changes mid-session that re-bill the entire prefix (cache writes cost 1.25x to 2x base input, cache reads only 0.1x).
2. A bloated always-loaded context: giant CLAUDE.md files, dozens of unused plugins, MCP servers nobody authenticated, chatty session-start hooks. That weight is paid on every call of every session.
3. Wrong model for the job: mechanical loops running on the strongest tier, or the cheapest tier being trusted to judge its own work.
4. Verbose output: raw log dumps, whole-file reads, uncapped subagent reports. Output is the most expensive token, and it gets re-read as input forever after.

The skill turns each of these into a short set of rules Claude applies automatically, plus a monthly audit ritual and a decision table for `/rewind` versus `/recap` versus `/compact` versus a fresh session.

Every behavioral claim in the skill is sourced to first-party documentation and dated, because this area changes. Several rules that circulate as folklore are wrong: editing CLAUDE.md mid-session is cache-safe (it just does not apply until you reload), while changing effort level rebuilds the whole prefix exactly like a model switch.

## Install

```bash
claude plugin marketplace add khalilmaaouni/SaveClaudeTokens
claude plugin install save-claude-tokens@saveclaudetokens
```

That is the whole setup. The skill loads on demand, so it adds one listing line to your sessions and nothing else.

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

## Pairs well with

- caveman (terse narration) and ponytail (minimal generated code) for the output side.
- token-saver (command output compression) for the input side.
- Any note system (Obsidian, plain markdown) for the memory side.

## License

MIT. Author: Khalil Maaouni.
