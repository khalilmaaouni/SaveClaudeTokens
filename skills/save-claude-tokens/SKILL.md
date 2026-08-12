---
name: save-claude-tokens
description: Cut Claude Code token spend without cutting quality. This skill should be used when the work involves prompt caching (cache writes, cache hits, TTL, refreshes), deciding between /compact and a fresh session, routing work to the right model tier, pruning plugins and MCP servers that clog the context window, reducing verbose output, or auditing what a session costs. Triggers include tokens, cost, cache, caching, compact, compaction, context full, expensive, spend, budget, token economy, prune plugins.
version: 1.0.0
license: MIT
---

# Save Claude Tokens

A playbook for running Claude Code cheaply. The core insight: you pay for the same context over and over. Every API call resends everything the session has accumulated, so the levers are (1) make the resend cheap via caching, (2) make the context small, (3) make the model match the job, and (4) make the output short. In that order of impact.

## The cost model in four facts

Verified against the Anthropic prompt caching docs (platform.claude.com/docs/en/build-with-claude/prompt-caching), 2026-08-12:

1. Caching is a prefix match. Any byte change anywhere in the prefix invalidates everything after it. Render order is tools, then system prompt, then messages.
2. Cache writes cost 1.25x base input (5 minute TTL) or 2x (1 hour TTL). Cache reads cost 0.1x. So a cache-friendly session pays roughly a tenth for everything it does not disturb.
3. The TTL refreshes free on every use. A session that keeps moving stays cached. A session that idles past the TTL re-pays the full write on its next turn.
4. Claude Code places cache breakpoints automatically. You cannot place them yourself, but you control the two things that matter: whether the prefix stays stable, and how big it is.

## Lever 1: keep the cache hot (habits, not settings)

- Never edit CLAUDE.md, settings.json, hooks, or MCP config mid-session. Each edit changes the prefix for every later request and re-bills the whole preamble. Config changes happen at session end, then the next session starts clean.
- Never switch models mid-task. Caches are model-scoped; a switch rebuilds from zero. Need a cheaper model for a subtask? Spawn a subagent on that model and keep the main loop where it is.
- Batch independent tool calls into one message. Five parallel calls in one request cost one cache read; five sequential requests cost five.
- For long waits (builds, CI, downloads) use background execution that re-invokes the session when finished. Do not idle past the TTL and then poke the session repeatedly; every poke after expiry is a fresh cache write.
- Keep one task per session. Unrelated context dragged along is pure cost: you pay 0.1x on all of it, every single call.

## Lever 2: shrink the always-loaded context (the biggest win)

Everything loaded at session start (CLAUDE.md, plugin skill listings, MCP tool schemas and instructions, session-start hook output) is paid on every call of every session. Budget it like rent.

- CLAUDE.md carries hard rules only, in terse lines. Details, rationale, history, and playbooks live in skills or notes that load on demand. A rule of thumb: if a paragraph is read once a month, it does not belong in a file read on every call.
- Prune plugins. Each installed plugin adds skill listing lines, and plugins with MCP servers add tool schemas and instruction blocks. Disable anything unused: `claude plugin disable <name>`. Fully reversible with `claude plugin enable <name>`.
- Prune standalone MCP servers the same way. Back up your `~/.claude.json` before removing one so the config is recoverable.
- Keep session-start hooks quiet. Hook stdout enters the context. A hook that prints ten lines when one would do taxes every session it fires in.
- Do not run two skill frameworks that overlap. Pick one, disable the other.
- Audit ritual (monthly, five minutes):

```bash
wc -c ~/.claude/CLAUDE.md                      # bytes / 4 is a rough token estimate
claude plugin list | grep -c '❯'               # installed plugin count
claude mcp list                                 # servers; "Needs authentication" means never used
```

Anything with zero recent use and no planned use gets disabled, and the decision gets one line in your notes so it is not re-litigated.

## Lever 3: compact versus fresh session (the decision rule)

Compaction summarizes history into the context; it costs a large generation, loses detail, and the rewritten context busts the cache anyway. A fresh session costs one prefix write and drops all dead history from every later call. So:

- CHECKPOINT FIRST, ALWAYS: at every good stopping point, write state to disk (a STATE.md, a handover note, a session log): what is finished with its proof, what is in flight, what is not started, open questions.
- FRESH SESSION (the default): when the next chunk of work can be stated from that disk state. Start new, point it at the checkpoint file. Cheaper and cleaner than dragging a summary.
- /compact (the exception): only when you are mid-task and the conversational nuance is not yet on disk, for example deep in a debugging thread whose dead ends matter. Compact once, with focus instructions, then plan the next fresh start.
- /clear: always, between unrelated tasks in the same session.
- Never let auto-compact surprise you. When context passes roughly 70 percent, checkpoint proactively and choose, rather than letting the harness summarize mid-thought.

## Lever 4: route the model to the job

Input and output prices scale steeply with model tier, so a mechanical loop on a frontier model costs several times the same loop on a small one. The routing table:

| Job | Tier |
|---|---|
| Orchestration, architecture, judging, adversarial review, final synthesis, anything user-critical | Strongest available (SOTA) |
| Scoped implementation and search from a precise spec, drafting | Middle tier |
| Mechanical bulk: renames, format sweeps, extraction, inventory greps | Cheapest tier |

- Declare the tier in every subagent brief, with the reason. An unstated tier is a mistake, not a default.
- Never run mechanical loops on the strongest tier, and never let the cheapest tier verify its own work or judge anything. Verification runs on the strong lane.
- Match reasoning effort the same way: low for mechanical stages, medium as the default, high only for the hardest verify and judge stages.
- One deterministic script beats a subagent for one deterministic job. An agent dispatch costs a whole fresh context; a bash or python script costs nothing. Delegate judgment, not loops.

## Lever 5: output discipline

Output tokens cost several times input tokens, and everything you output is re-read as input on every later call. Twice taxed.

- Use a terse output mode for narration and status if one is installed (community examples: caveman compresses working commentary, ponytail makes generated code minimal). Keep full prose only for deliverables a human will reuse.
- Never dump raw logs. Quote the one decisive line. Read files with offset and limit, grep with head limits, tail the build output.
- Cap subagent reports. A subagent that returns its whole transcript re-bills that transcript into the parent forever. A few hundred tokens of findings is the contract.
- Prefer text checks over screenshots when both would answer the question. Images are token-heavy.
- Command-output compressors (for example the token-saver plugin) are a pure win for reading, but never let compressed output stand as evidence where exact text matters. Re-run that one command raw.

## Lever 6: durable memory beats re-derivation

The most expensive token is the one spent re-discovering something a past session already knew.

- Keep decisions, learnings, and project state in on-disk notes (an Obsidian vault, a docs folder, STATE.md files). Sessions read them on demand instead of re-exploring the repo.
- Keep a token-waste ledger: when a session burns tokens on something avoidable (a runaway fleet, a re-read of a huge file, a re-derived decision), append one line: date, what it cost, the rule that prevents it. Review monthly; promote repeat offenders into your CLAUDE.md hard rules.
- Pointer, not payload: the always-loaded file carries one line pointing at the note, never the note itself.

## Anti-pattern ledger (seed entries, all from real incidents)

1. Unbounded subagent fleets. One machine's postmortem found subagents were 74 percent of output tokens in a runaway day. Fix: a per-session token ceiling enforced by a hook, a declared ceiling before any unattended run, and no new dispatches past 80 percent of it.
2. Polling sleeps. A loop that wakes every 30 seconds to check a build pays a full context resend per wake. Fix: background execution with completion callbacks.
3. Cross-project enumeration. Listing every repo, artifact, or resource on the machine to find one project's link. Fix: each project keeps its own PROJECT.md with its links; read that.
4. Sessions started in the home directory. They accumulate a catch-all history no project needs. Fix: one project, one canonical path, sessions start there.
5. Duplicate frameworks. Two skill packs injecting near-identical manifests at every session start. Fix: keep one.
6. Config edits mid-session. Every subsequent call re-paid the preamble. Fix: Lever 1.
7. The verbose hook. A session-start hook printing kilobytes of digest into every session. Fix: Lever 2, keep hooks quiet.

## Machine-local overlay

This skill is generic. Wire it to your machine with a short section in your global CLAUDE.md that states only the hard rules (no config edits mid-session, checkpoint before compact, tier table, prune ritual cadence) and points here for the reasoning. That split is itself the method: rules always loaded, playbook on demand.
