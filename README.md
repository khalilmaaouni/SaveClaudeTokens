# SaveClaudeTokens

Run Claude Code cheaply without losing quality. This plugin ships one skill, `save-claude-tokens`, a playbook Claude loads on demand when the work touches token cost: prompt caching, compaction decisions, model routing, config pruning, or output verbosity.

## Why this exists

Every API call in a Claude Code session resends the whole accumulated context. Most token waste comes from four places:

1. Cache-hostile habits: config edits or model switches mid-session that re-bill the entire preamble (cache writes cost 1.25x to 2x base input, cache reads only 0.1x).
2. A bloated always-loaded context: giant CLAUDE.md files, dozens of unused plugins, MCP servers nobody authenticated, chatty session-start hooks. That weight is paid on every call of every session.
3. Wrong model for the job: mechanical loops running on the strongest tier, or the cheapest tier being trusted to judge its own work.
4. Verbose output: raw log dumps, whole-file reads, uncapped subagent reports. Output is the most expensive token, and it gets re-read as input forever after.

The skill turns each of these into a short set of rules Claude applies automatically, plus a monthly audit ritual and a decision table for /compact versus starting a fresh session.

## Install

```bash
claude plugin marketplace add khalilmaaouni/SaveClaudeTokens
claude plugin install save-claude-tokens@saveclaudetokens
```

That is the whole setup. The skill loads on demand, so it adds one listing line to your sessions and nothing else.

## What is inside

- The cost model in four facts (prefix caching, write and read multipliers, TTL refresh).
- Lever 1: cache-friendly working habits.
- Lever 2: shrinking the always-loaded context, with a copy-paste audit ritual.
- Lever 3: the compact versus fresh session decision rule.
- Lever 4: a model routing table with tier declaration discipline.
- Lever 5: output discipline, including how to use compressors safely.
- Lever 6: durable on-disk memory (works well with an Obsidian vault) so sessions stop re-deriving what past sessions already learned.
- An anti-pattern ledger seeded from real incidents.

## Pairs well with

- caveman (terse narration) and ponytail (minimal generated code) for the output side.
- token-saver (command output compression) for the input side.
- Any note system (Obsidian, plain markdown) for the memory side.

## License

MIT. Author: Khalil Maaouni.
