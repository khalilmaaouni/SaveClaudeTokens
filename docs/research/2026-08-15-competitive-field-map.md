# Competitive field map, 2026-08-15

Two read-only research passes, run in parallel: one inside the Claude Code ecosystem, one across the wider market (Cursor, Codex, Copilot, Cline, Roo, aider, proxy cost layers, FinOps platforms, compression research). Every row below names the page a researcher actually opened. Star counts and last-push dates in the Claude Code table were cross-checked against the GitHub REST API as a second method; everything else is single-sourced to the page opened and says so.

Nothing here is a Token Shield measurement. These are other people's claims about their own tools, recorded as claims.

## Inside Claude Code

| Tool | Surface | Measures, reduces, or displays | Proof posture | Scale |
|---|---|---|---|---|
| [ccusage](https://github.com/ccusage/ccusage) | CLI, reads local transcripts | DISPLAY only | No savings claim of its own | 17,927 stars, pushed 2026-08-14 |
| [RTK](https://github.com/rtk-ai/rtk) | Rust binary wired as a PreToolUse hook | REDUCE, by rewriting shell output before Claude sees it | Claims 60 to 90 percent, and its own docs caveat that this is not the same as cutting a bill by 90 percent | 76,175 stars, pushed 2026-08-13 |
| [context-mode](https://github.com/mksglu/context-mode) | MCP server plus a full hook set | REDUCE, by sandboxing tool output into a searchable local store | Claims 98 percent; a BENCHMARK.md exists but its contents were not visible on the page opened, so the proof is unverified from here | 19,863 stars, pushed 2026-08-14 |
| [token-optimizer-mcp](https://github.com/ooples/token-optimizer-mcp) | MCP server, or a plugin in enforcing mode | MEASURE and REDUCE | Runs its own three-tier confidence system (verified and measured, excluded and collecting, modeled only) and holds numbers back pending a randomized control arm | 485 stars, pushed 2026-08-12 |
| [tamp](https://github.com/sliday/tamp) | Localhost proxy | REDUCE | Claims 52.6 percent fewer input tokens; ships benchmarks and admits they underrepresent real gains, so the proof is self-graded | 89 stars, pushed 2026-07-26 |
| [cccost](https://github.com/badlogic/cccost) | CLI wrapper hooking fetch() | MEASURE only | No savings claim, pure instrumentation | 26 stars, pushed 2025-08-18, stale |
| [claude-md-optimizer](https://github.com/wrsmith108/claude-md-optimizer) | Skill | REDUCE, memory files specifically | States outright that its harness is not yet committed, an honest NOT_PROVEN | 21 stars, pushed 2026-06-25 |
| [tokeneconomics](https://www.claudepluginhub.com/plugins/florianbuetow-tokeneconomics-plugins-tokeneconomics) | Plugin | MEASURE plus advice | No experiment-backed claim visible on the listing (single-sourced, the underlying repo was not reached) | not visible |
| Statusline cost display | Built into Claude Code | DISPLAY only | First-party feature, no claim | not applicable |

## Outside Claude Code, what the wider market does

Cursor ships a per-user dashboard against plan limits. GitHub Copilot exposes org-level usage through a metrics REST API with CSV and PNG export, measured from GitHub's own billing system rather than estimated. OpenAI's Codex CLI shipped no native cost tracking (the feature request closed unshipped), so the space is filled by community transcript parsers. Cline and aider both show cost inline per task as work happens; Roo Code writes a persistent usage ledger to a real file on disk that survives restarts.

The proxy layer is where enforcement lives. LiteLLM tracks spend per key, user, team and model in Postgres and returns 429 when a budget is crossed, which is the only true reduction control found anywhere in this sweep: a block, not a dashboard. Helicone and OpenRouter both surface cache hit rate tied to a dollar figure and decompose a bill into named components. Vantage sells per-developer and per-feature attribution as FinOps for tokens. On the research side, Microsoft's LLMLingua compresses prompts up to 20x with roughly a 1.5 point performance loss, benchmarked and peer reviewed, which is the strongest proof claim in the entire field.

## The five threats, ranked

1. **RTK's mindshare.** At 76k stars and pushed daily, it is the default answer when someone searches for how to reduce Claude Code tokens. Its own honesty about its headline number is closer to this project's ethos than most, which makes it a harder target, not an easier one. Size crowds out rigor.
2. **context-mode's overlap.** 19.9k stars, pushed today, and it occupies the same ground: context reduction plus session memory. It ships a benchmark file. If that benchmark is rigorous, its proof story is stronger than the rest of the field.
3. **token-optimizer-mcp claiming the rigor position first.** It already labels confidence in three tiers and withholds numbers pending a control arm. If it publishes a genuine randomized result before this project's experiment ledger reaches a verdict, the "first rigorously proven" slot is gone.
4. **Enforcement beats reporting.** LiteLLM blocks spend at the boundary. Every tool in the Claude Code column, this one included, only reports and advises. A user who wants a hard stop cannot get one here today.
5. **Live per-task visibility.** Cline and aider catch runaway spend as it happens. A dashboard read after the session is over is a post mortem, not a brake.

## The two gaps nobody covers, which is the moat

**Attribution.** Every reduction tool in the field bundles several mechanisms at once: compression plus caching plus hook rewriting. That means no percentage any of them publishes can be attributed to a single cause. The controlled single-variable experiment this project runs, isolating one lever and publishing a labeled verdict either way, has no equivalent anywhere in this sweep.

**Separating what Anthropic already does from what a tool did.** Not one tool found separates NATIVE prompt-caching savings from tool-attributable savings. Every 60, 90, or 98 percent headline in the tables above conflates the two. That conflation is precisely what this project's label set refuses to do, and it is the least copied differentiator in the field.

## What was deliberately not borrowed

Helicone and OpenRouter both put a dollar figure on cache hit rate. This project already tracks the cache ratio under its NATIVE label and refuses to price it, because that saving is Anthropic's behavior and not the tool's work. That refusal stays. It is a recorded design decision, not a missing feature, and it is worth documenting as a divergence so it is never "fixed" by someone reading the competitive table alone.

## Method and limits

Two sonnet researchers, read-only, dispatched in parallel; both were told to record only what they actually opened and to mark single-sourced facts. The Claude Code pass verified stars and last-push dates against the GitHub API independently of the page scrape. The wider-market pass leaned more on search-engine synthesis, with five pages opened directly; its rows are weaker evidence than the Claude Code rows and should be re-checked before any of them appears in public copy. No claim in this document has been reproduced on this machine. Nothing here is labeled MEASURED or VERIFIED, because nothing here was measured or verified by this project.
