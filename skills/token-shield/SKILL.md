---
name: token-shield
description: Cut Claude Code token spend without cutting quality. This skill should be used when the work involves prompt caching (cache writes, cache hits, TTL, refreshes), deciding between /rewind, /compact, /clear and a fresh session, routing work to the right model tier, pruning plugins and MCP servers that clog the context window, reducing verbose output, or auditing what a session costs. Triggers include tokens, cost, cache, caching, compact, compaction, context full, expensive, spend, budget, token economy, prune plugins.
version: 1.6.0
license: MIT
---

# Token Shield

A playbook for running Claude Code cheaply. The core insight: you pay for the same context over and over. Every API call resends everything the session has accumulated, so the levers are (1) make the resend cheap via caching, (2) make the context small, (3) make the model match the job, and (4) make the output short. In that order of impact.

Rule zero: measure, then act. Every claim below is either sourced to first-party documentation or marked as a habit. Where this playbook cannot verify something, it says so instead of guessing.

## The cost model

Verified against code.claude.com/docs/en/prompt-caching and platform.claude.com/docs/en/build-with-claude/prompt-caching, read 2026-08-12.

1. Caching is a prefix match. The match is exact, so a change anywhere in the prefix recomputes everything after it. There is no per-file or per-segment caching.
2. Requests are ordered so the stable content comes first: system prompt (core instructions, tool definitions, output style), then project context (CLAUDE.md, auto memory, unscoped rules), then the conversation. A change to the conversation layer leaves the two layers above it cached. A change to the system prompt invalidates everything.
3. Cache writes bill at 1.25x base input for the 5 minute TTL and 2x for the 1 hour TTL. Cache reads bill at 0.1x. A session that does not disturb its prefix pays roughly a tenth for everything it re-reads.
4. The TTL resets on every cache hit, so the cache stays warm as long as you keep working. Which TTL you get depends on how you authenticate: on a Claude subscription Claude Code requests the 1 hour TTL automatically, and on an API key or a third-party provider it stays at 5 minutes unless you set `ENABLE_PROMPT_CACHING_1H=1`. A subscription that has gone over its plan limit and is drawing on usage credits drops back to 5 minutes automatically, because 1 hour writes cost more. Subagents use the 5 minute TTL even on a subscription.
5. Two things outside the prompt text are still part of the cache key: the model, and the effort level. Each has its own cache.
6. The cache is effectively scoped to one machine and one directory, because the system prompt embeds the working directory. Two sessions in different directories miss each other's cache, and that includes two worktrees of the same repository. Parallel sessions in the same directory do share it.

## Measure before you optimize

Do not reason about which lever matters most. Measure it. Run `/token-audit`, or the script directly:

```bash
python3 <plugin>/scripts/measure_tokens.py --days 30 --sessions
```

It reads the `usage` counters the API returned on every assistant message in the local transcripts, which are the counters billing is computed from, so its output is measurement rather than estimation. Anything it cannot measure it prints as NO DATA.

Read it this way: a high first request share means Lever 2 dominates and nothing else is worth doing first; a hit ratio below roughly 0.7 on long sessions means Lever 1 has real headroom; a high subagent share means Lever 4 does. Snapshot with `--baseline`, change one thing, then `--compare`. One variable at a time, or the result attributes to nothing.

For a visual read, `scripts/token_shield.py` renders the same measured numbers as a Brave-shields-style HTML dashboard: what caching saved, what it blocked, and the ranked pain points (model switching, the startup floor, mid-session rebuilds) with the fix for each. The full method, telemetry and honesty guarantees are in the repo's `docs/`; every claim carries the check that backs it in `docs/CLAIMS.md`.

Three more scripts round out the toolkit. `scripts/profile.py` builds a deterministic session profile of cache rebuilds, the startup floor, and model switches, each labeled MEASURED or NO DATA (`python3 cli.py profile`). `scripts/advisor.py` ranks the single best next move against that profile, with full drawback disclosure and "do nothing" as a valid answer (`python3 cli.py advise`). `scripts/report.py` writes a monthly report comparing this month's pattern to last month's (`python3 cli.py report --month YYYY-MM`). To remove everything Token Shield wrote to disk, run `python3 cli.py uninstall`: it prints what exists, asks for a typed `YES`, and never touches `settings.json` or `CLAUDE.md`.

Two traps the script now guards, both of which produced a confident wrong number before it did:

- Compare like windows. A 1 day window against a 90 day baseline is not a measurement of your change, it is a measurement of which sessions fell inside each window.
- Do not compare a number across a change to how it is computed. When the metric's population changes, the delta measures your edit to the meter, not your spend.

## Lever 1: keep the cache hot

Most cache folklore is wrong in both directions: people fear edits that are free and make switches that cost a full rebuild. The documented list, from the source above.

These rebuild the whole prefix on the next turn:

| Action | Why |
|---|---|
| Switching model with `/model` | Each model has its own cache. Content identical, zero hits. |
| Changing effort with `/effort` | The cache is keyed by effort as well as model. Claude Code confirms first. |
| Turning on fast mode | Adds a request header that is part of the cache key. Costs once per conversation, so turn it on early or not at all. |
| Connecting or disconnecting an MCP server whose tools load into the prefix | Tool definitions sit in the system prompt layer. |
| Enabling or disabling a plugin that provides an MCP server | Same reason. Other plugin components do not do this. |
| Adding or removing a whole-tool deny rule (`Bash`, `WebFetch`, `"*"`) | Removes the tool definition from the system prompt layer. |
| `/compact` | Replaces history with a summary, so the conversation layer no longer shares a prefix. |
| Upgrading Claude Code, and resuming a long session afterwards | New system prompt or tools. Resuming a long old session after an upgrade can be the most expensive request you send. |

These are free, and several are free precisely because they do not apply until a reload:

| Action | Note |
|---|---|
| Editing CLAUDE.md mid-session | Does not invalidate the cache, and does not apply either. The version loaded at session start stays in force until `/clear`, `/compact`, or restart. The exception: nested CLAUDE.md files in subdirectories, and rules with `paths:` frontmatter, load later when Claude first reads a matching file, so editing one of those before it loads does take effect. |
| Editing your MCP config | Does not by itself change the cache. It takes effect on restart, which is when a server connects or disconnects. |
| Enabling or disabling a plugin that ships skills, commands, agents, hooks, LSP servers, monitors or themes | Appended, not prefixed. The next request pays for the new content and still reads everything before it from cache. |
| Changing output style | Cache-safe, and also does not apply until reload. |
| Changing permission mode | Cache-safe, unless the `opusplan` setting makes the toggle a model switch. |
| Invoking a skill or command | Injected as a user message at the point of invocation. |
| Editing a file Claude already read | File contents enter context on read. The edit appends a change notice; it does not rewrite history. |
| `/recap` | Appends a summary as command output rather than replacing history. |
| `/rewind` | Truncates back to a prefix the cache was already built from. |
| Spawning a subagent | It builds its own cache. From the parent's side, the call and result just append. |

So the habits that actually pay:

- Pick model and effort at the top of a session and leave them. Need a cheaper model for a subtask? Spawn a subagent, do not switch the main loop.
- Do config work between sessions, not because an edit costs you (mostly it does not) but because an edit that does not apply is worse than useless: you will believe a rule is active when it is not.
- Batch independent tool calls into one message. Five parallel calls in one request cost one cache read; five sequential requests cost five.
- For long waits use background execution that re-invokes the session when it finishes. Idling past the TTL and then poking the session repeatedly pays a fresh write each time.
- Keep one task per session. Unrelated context is pure rent: you pay 0.1x on all of it, on every call.
- Prefer a fork over a subagent when the work genuinely needs the parent's history, since a fork inherits the parent's prefix and reads its cache.

## Lever 2: shrink the always-loaded context

Everything loaded at session start is paid on every call of every session. Budget it like rent, and measure it as first request tokens rather than counting installed things.

- CLAUDE.md carries hard rules only, in terse lines. Details, rationale, history and playbooks live in skills or notes that load on demand. If a paragraph is read once a month, it does not belong in a file read on every call.
- Prune plugins. Each installed plugin adds listing lines. Disable what you do not use with `claude plugin disable <name>`, reversible with `claude plugin enable <name>`.
- MCP servers need measurement, not a reflex. On supported models Claude Code defers MCP tool definitions behind tool search by default, so only names load upfront and the per-server schema cost largely disappears. Deferral is unavailable or disabled in named cases, including a custom `ANTHROPIC_BASE_URL` gateway, some third-party hosting, and servers or tools marked `alwaysLoad`. Deferral shrinks the schema cost, not the whole cost: observed on one machine, the tool name list and each server's instruction block still arrive at session start. So: check your own first request number before and after, and prune what is expensive, unstable, or unused rather than pruning by server count.
- Keep session-start hooks quiet. Hook stdout enters the context. A hook printing ten lines where one would do taxes every session it fires in.
- Do not run two skill frameworks that overlap. Pick one, disable the other.
- Skill listings have their own budget, and you can spend it deliberately. A skill you want available but not advertised takes `disable-model-invocation: true` in its frontmatter. Skills whose SKILL.md you would rather not edit, such as one checked into a shared repo, can be turned down from settings with `skillOverrides`, whose states are `on`, `name-only`, `user-invocable-only` and `off`; `name-only` lists the skill without its description and frees budget for the rest. Plugin skills are not affected by `skillOverrides`, so manage those through `/plugin`. Each listing entry is capped at 1,536 characters, so a long description is wasted on top of being expensive: put the key use case first.
- Audit ritual, monthly, five minutes:

```bash
python3 <plugin>/scripts/measure_tokens.py --days 30   # the number that matters
python3 <plugin>/scripts/context_lint.py               # where the startup rent goes
claude plugin list                                     # what is installed
claude mcp list                                        # servers; "Needs authentication" means never used
```

`context_lint.py` reports and never edits: duplicated rules, procedures that
belong in a skill, rules that could be path-scoped, and, for an auto-memory
index, exactly which lines fall past the documented load limit (first 200 lines
or 25KB, whichever comes first) and therefore never reach a session at all.
Two things it will tell you that are easy to get backwards: `@path` imports are
expanded at launch, so splitting a file into imports organizes it without
saving a single token, and block-level HTML comments are stripped before
loading, so they are the free place to keep maintainer notes.

Anything with zero recent use and no planned use gets disabled, and the decision gets one line in your notes so it is not re-litigated.

## Lever 3: choose the right session boundary

There are four boundaries and they are not interchangeable. Pick by intent.

- `/rewind` when you went down a path you want to abandon. It truncates to a prefix that is already cached, which is the cheapest way out of a bad thread.
- `/recap` when you only need orientation. It appends a summary and leaves history intact.
- `/compact` at a natural break, when the task continues but the old history is dead weight. While the cache is warm the summarization request reads your prefix from cache, so a mid-session compact costs a fraction of what the context size suggests, and most of its cost is generating the summary. It is most expensive when you resume an old session cold, because then there is no cache to read.
- A fresh session when the next task is unrelated or can be restated from disk. It drops all dead history from every later call.

Checkpoint first, always. At every good stopping point write state to disk (a STATE.md, a handover note, a session log): what is finished with its proof, what is in flight, what is not started, open questions. A checkpoint makes every one of the four boundaries cheap, and makes an unplanned auto-compact survivable.

Run the boundary you chose at a break you chose. Letting auto-compaction fire mid-task hands the timing to the harness.

## Lever 4: route the model to the job

Input and output prices scale steeply with model tier, so a mechanical loop on a frontier model costs several times the same loop on a small one.

| Job | Tier |
|---|---|
| Orchestration, architecture, judging, adversarial review, final synthesis, anything user-critical | Strongest available |
| Scoped implementation and search from a precise spec, drafting | Middle tier |
| Mechanical bulk: renames, format sweeps, extraction, inventory greps | Cheapest tier |

- Declare the tier in every subagent brief, with the reason. An unstated tier is a mistake, not a default.
- Never run mechanical loops on the strongest tier, and never let the cheapest tier verify its own work or judge anything. Verification runs on the strong lane.
- Effort is a real lever but it is not a free one: changing it mid-session rebuilds the cache exactly like a model switch. Choose it at the top of the session, or carry the rebuild deliberately.
- Route by spawning, not switching. A subagent gets its own model and its own context and leaves the parent's cache intact.
- One deterministic script beats a subagent for one deterministic job. An agent dispatch costs a whole fresh context; a bash or python script costs nothing. Delegate judgment, not loops.
- Subagents are not free and not automatically wasteful. They are worth it when they keep a flood of exploration out of the parent context, when the result comes back small, or when parallelism is real. They are waste when dispatched for a task a script would have done. Measure the share: `/token-audit` reports what fraction of your output tokens subagents produced.

## Lever 5: output discipline

Output tokens cost several times input tokens, and everything you output is re-read as input on every later call. Twice taxed.

- Use a terse output mode for narration and status if one is installed. Keep full prose for deliverables a human will reuse.
- Never dump raw logs. Send noisy commands to a file, then read back the exit status, the error lines, and a summary, keeping the full log on disk for exact inspection. That preserves the evidence while keeping it out of context.
- Read files with offset and limit, grep with head limits, tail the build output.
- Cap subagent reports. A subagent that returns its whole transcript re-bills that transcript into the parent forever. A few hundred tokens of findings, evidence and file pointers is the contract.
- Prefer text checks over screenshots when both would answer the question. Images are token-heavy.
- Command-output compressors are a pure win for reading, but never let compressed output stand as evidence where exact text matters. Re-run that one command raw.

## Lever 6: durable memory beats re-derivation

The most expensive token is the one spent re-discovering something a past session already knew.

- Keep decisions, learnings and project state in on-disk notes. Sessions read them on demand instead of re-exploring the repo.
- Pointer, not payload: the always-loaded file carries one line pointing at the note, never the note itself.
- Keep a token-waste ledger: when a session burns tokens on something avoidable, append one line with the date, what it cost, and the rule that prevents it. If you want the numeric half of that ledger kept for you, wire the plugin's opt-in `session_end_telemetry.py` into a SessionEnd hook: it appends counters per session and never spends a model token to do it. Measuring token spend by asking a language model to measure it is a joke that bills.
- Promote a ledger line into an always-loaded rule only after the same waste happens twice, the lesson is stable, and it is short enough to state in one line. A rule in CLAUDE.md pays rent on every call of every session, so it has to be worth more than that. Demote in the other direction: rules that apply to one subtree, or that a linter or hook could enforce, do not belong there.

## Anti-pattern ledger

1. Unbounded subagent fleets. One machine's postmortem found subagents were 74 percent of output tokens in a runaway day; a later measurement over 90 days on the same machine put them at 41 percent of all output tokens. Fix: a per-session token ceiling, a declared ceiling before any unattended run, and no new dispatches past 80 percent of it.
2. Polling sleeps. A loop that wakes every 30 seconds to check a build pays a full context resend per wake. Fix: background execution with completion callbacks.
3. Cross-project enumeration. Listing every repo, artifact or resource on the machine to find one project's link. Fix: each project keeps its own PROJECT.md with its links; read that.
4. Sessions started in the home directory. They accumulate a catch-all history no project needs, and because the cache is scoped to the working directory they also miss the cache the project's own directory built. Fix: one project, one canonical path.
5. Duplicate frameworks. Two skill packs injecting near-identical manifests at every session start. Fix: keep one.
6. Believing a mid-session config edit took effect. A root or user CLAUDE.md edit is cache-safe and inert until reload, which is worse than costly: you act as though a rule is live when it is not. Nested and path-scoped rules that have not loaded yet behave the opposite way, which makes guessing unreliable. Fix: change config between sessions.
7. The verbose hook. A session-start hook printing kilobytes of digest into every session. Fix: Lever 2, keep hooks quiet.
8. Optimizing tokens without a denominator. A change that cuts tokens 30 percent and doubles rework is not an optimization. The number worth improving is tokens per accepted result, so record whether the work landed first time, not just what it cost.
9. A ceiling with no sanctioned way to raise it. A brake that cannot be adjusted is a wall, and a wall in front of work someone has authorized gets removed rather than respected: the ceiling goes to zero, or the guard gets switched off, and then it protects nothing at all. The same reasoning already governs the repeat-command breaker, which deliberately lets ordinary debugging through, because a gate that fires on normal work gets switched off and a switched-off gate saves nothing. Fix, in three parts: the owner's explicit budget is an exception and is honored in the same turn rather than escalated back to them; honor it by RAISING the number in that project's entry, never by suspending the guard, so the brake stays mechanical at whatever figure was named; and require every raise to carry a future expiry, enforced by the guard itself, so an exception cannot outlive the work it was given for. Without the third part the first two are how "raised for this sprint" becomes "raised forever", which is the failure mode the ceiling existed to prevent.

## The sibling bill: cloud metered usage

Token discipline has a sibling trap: a cloud provider's metered-usage chart that looks like an invoice and is not one. On 2026-08-16 a GitHub Free account showed $864.61 of August "metered usage"; the verified truth was billed $0.00, because the chart plots the gross list-price value of free-tier compute and discounts it all. Before treating any usage chart as a bill, read in this order: the billing Overview's "next payment due" card, the payment history, one day's hover tooltip (gross versus billed versus discount), then the budgets page. Preventive posture for a free account: no payment method on file, a $0 stop-usage budget per product, CI disabled or manual-trigger only, and since pushing is free, checkpoint pushes continue while verification runs locally. Audit drift with `python3 scripts/github_cost_guard.py` (NO-DATA is never a pass). Full walkthrough: docs/CLOUD-COST-SHIELD.md.

## Machine-local overlay

This skill is generic. Wire it to your machine with a short section in your global CLAUDE.md that states only the hard rules (pick model and effort at session start, checkpoint before any boundary, the tier table, the prune cadence) and points here for the reasoning. That split is itself the method: rules always loaded, playbook on demand.
