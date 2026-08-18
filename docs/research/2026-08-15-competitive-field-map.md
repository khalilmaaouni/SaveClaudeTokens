# Competitive field map, 2026-08-15

Two read-only research passes, run in parallel: one inside the Claude Code ecosystem, one across the wider market (Cursor, Codex, Copilot, Cline, Roo, aider, proxy cost layers, FinOps platforms, compression research). Every row below names the page a researcher actually opened. Star counts and last-push dates in the Claude Code table were cross-checked against the GitHub REST API as a second method; everything else is single-sourced to the page opened and says so.

Nothing here is a Token Shield measurement. These are other people's claims about their own tools, recorded as claims.

## Correction, 2026-08-19: this document was wrong about the field a SECOND time

Same failure class as the correction below, four days later, found by an
overnight pass that re-read the primary source instead of trusting this row.
Full evidence, with verbatim line numbers: [2026-08-19-codeburn-benchmark.md](2026-08-19-codeburn-benchmark.md).

**What it said.** The CodeBurn row in the table below: "No experiment behind any
number and no confidence labelling. `codeburn optimize` estimates a saving;
nothing re-measures whether the fix helped."

**Why that was false, twice over.** CodeBurn README line 195: "once an applied
fix is at least 3 days old, `codeburn act report` compares its estimated savings
against what your sessions actually did... Estimates get checked against
reality, not just claimed." And line 173: "Each one says whether its savings
number is `measured` from provider-counted usage or `estimated`." So they DO
re-measure, and they DO label confidence, on a two label system against our
five. Source fetched 2026-08-19 00:47 JST.

**How the error happened, which is again the part worth keeping.** The row was
written from a CATEGORY, not from a source. CodeBurn was filed as a meter, and
the sweep then reasoned about what meters do rather than re-reading what this
meter does. The correction below warned about exactly this and the warning did
not take, because nothing in the process forces a re-read of a row once it is
written. The surviving honest claim is narrower: CodeBurn re-measures but does
not REFUSE an invalid comparison, and Token Shield does.

## Correction, 2026-08-15 evening: this document was wrong about the field

Kept visible rather than edited away, because a field map that quietly repairs
itself teaches nobody anything.

**What it said.** Threat 4 below read: "Every tool in the Claude Code column,
this one included, only reports and advises. A user who wants a hard stop cannot
get one here today."

**Why that was false.** CodeBurn ships `codeburn guard`, which installs opt-in
hooks into Claude Code and stops a session at a hard cap. The exact wording on
its own README: "Guard installs opt-in hooks into Claude Code that watch session
cost while you work", with a soft cap defaulting to 5 dollars that warns once
in-session, a hard cap defaulting to 15 dollars that "stops the session", and a
checkpoint defaulting to 3 dollars that nudges a fresh session if one ended past
it with no edits and no commits. Source:
https://raw.githubusercontent.com/getagentseal/codeburn/main/README.md, opened
2026-08-15, cross-checked against https://github.com/getagentseal/codeburn, same
date.

**How the error happened, which is the part worth keeping.** The original sweep
enumerated tools by searching for token measurement and reduction. CodeBurn
presents itself as a cost and usage tracker, so it did not surface, and the sweep
then generalised from the tools it had found to the whole field. A search that
finds nothing is evidence about the search, not about the world. The row below
was written from an absence.

**What is still true.** Nothing else found inside Claude Code enforces a budget,
and CodeBurn's own README states its hooks "fail open: a broken guard never
blocks a session", so even the one hard stop in the field is best effort rather
than guaranteed. The gap is narrower than threat 4 claimed and it is not closed.

## Inside Claude Code

| Tool | Surface | Measures, reduces, or displays | Proof posture | Scale |
|---|---|---|---|---|
| [CodeBurn](https://github.com/getagentseal/codeburn) | CLI and full-screen TUI, macOS menu bar app, GNOME top-bar extension, desktop app for three platforms, localhost web dashboard, MCP server, and opt-in Claude Code hooks | MEASURE, DISPLAY and ENFORCE. The only hard budget stop found anywhere inside Claude Code | CORRECTED 2026-08-19, see the correction at the top: re-measures via `codeburn act report` at 3 days and labels findings `measured` or `estimated` (two labels to our five). The surviving gap is REFUSAL, not measurement: nothing declines the comparison when the window is invalid. Turn classification is disputed in public by a user who saw 1 planning turn detected in 30 days Turn classification is disputed in public by a user who saw 1 planning turn detected in 30 days | 9,391 stars, 745 forks, 57 open issues, created 2026-04-13; 9,147 npm downloads in the week of 2026-08-03; version 0.9.20; MIT (GitHub and npm registry APIs, queried 2026-08-15) |
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

## The six threats, ranked

Five when this was written. The sixth is CodeBurn's surface, added with the
correction above.

1. **RTK's mindshare.** At 76k stars and pushed daily, it is the default answer when someone searches for how to reduce Claude Code tokens. Its own honesty about its headline number is closer to this project's ethos than most, which makes it a harder target, not an easier one. Size crowds out rigor.
2. **context-mode's overlap.** 19.9k stars, pushed today, and it occupies the same ground: context reduction plus session memory. It ships a benchmark file. If that benchmark is rigorous, its proof story is stronger than the rest of the field.
3. **token-optimizer-mcp claiming the rigor position first.** It already labels confidence in three tiers and withholds numbers pending a control arm. If it publishes a genuine randomized result before this project's experiment ledger reaches a verdict, the "first rigorously proven" slot is gone.
4. **Enforcement beats reporting, and it has now arrived inside Claude Code.** CORRECTED 2026-08-15, see the correction note at the top: this threat previously claimed no tool in the Claude Code column ships a hard stop. CodeBurn does, through opt-in hooks with a soft cap, a hard cap that stops the session, and a checkpoint nudge. LiteLLM still does it harder at the proxy boundary with a 429. Token Shield reports and advises and does not stop anything, which is a deliberate consequence of registering zero hooks by default, not an oversight. The honest residual gap: CodeBurn's guard fails open by its own README, so nobody in this field ships a guaranteed stop, only a best-effort one.
5. **Surface and reach.** CodeBurn puts the day's number in a macOS menu bar next to the clock, ships a TUI, a desktop app and a localhost web dashboard, and trials with a single `npx codeburn` that installs nothing. Token Shield renders one HTML file a user has to go and open. On being seen and being tried, we are behind, and no amount of rigor compensates for a tool nobody has open (source: https://codeburn.app/, opened 2026-08-15).
6. **Live per-task visibility.** Cline and aider catch runaway spend as it happens. A dashboard read after the session is over is a post mortem, not a brake.

## The two gaps nobody covers, which is the moat

**Attribution.** Every reduction tool in the field bundles several mechanisms at once: compression plus caching plus hook rewriting. That means no percentage any of them publishes can be attributed to a single cause. The controlled single-variable experiment this project runs, isolating one lever and publishing a labeled verdict either way, has no equivalent anywhere in this sweep.

**Separating what Anthropic already does from what a tool did.** Not one tool found separates NATIVE prompt-caching savings from tool-attributable savings. Every 60, 90, or 98 percent headline in the tables above conflates the two. That conflation is precisely what this project's label set refuses to do, and it is the least copied differentiator in the field.

**The loop nobody closes, confirmed by the correction.** CodeBurn was the field's
best case for a counter-example, because it both finds waste (`codeburn optimize`)
and enforces a budget (`codeburn guard`). It still does not close the loop: the
sources record no mechanism that applies a fix and then re-measures whether that
fix helped, and no confidence label on any number it prints. So the sequence
measure, diagnose, treat, prove, learn remains unoccupied by anyone in this
sweep, including the tool that beats us on every surface. That is the position
worth holding.

**No org rollup and no FinOps pipe anywhere in the Claude Code column.** CodeBurn
has local device pairing across a user's own machines and a preview cloud sync
behind OIDC, and no team dashboard, no webhook, no Slack, no OpenTelemetry, no
warehouse export (source: https://github.com/getagentseal/codeburn, opened
2026-08-15). Everything in this column is a single-developer tool. Anthropic's
own OpenTelemetry export and organisation analytics occupy the counting half of
that ground, which `docs/ATTRIBUTION.md` already records; the labelled,
per-experiment proof half is unoccupied.

## What was deliberately not borrowed

Helicone and OpenRouter both put a dollar figure on cache hit rate. This project already tracks the cache ratio under its NATIVE label and refuses to price it, because that saving is Anthropic's behavior and not the tool's work. That refusal stays. It is a recorded design decision, not a missing feature, and it is worth documenting as a divergence so it is never "fixed" by someone reading the competitive table alone.

## Method and limits

Two sonnet researchers, read-only, dispatched in parallel; both were told to record only what they actually opened and to mark single-sourced facts. The Claude Code pass verified stars and last-push dates against the GitHub API independently of the page scrape. The wider-market pass leaned more on search-engine synthesis, with five pages opened directly; its rows are weaker evidence than the Claude Code rows and should be re-checked before any of them appears in public copy. No claim in this document has been reproduced on this machine. Nothing here is labeled MEASURED or VERIFIED, because nothing here was measured or verified by this project.

**The correction pass, 2026-08-15 evening.** One further read-only researcher,
briefed on a single tool rather than on a field, opened the marketing site, the
GitHub repository, the raw README, the npm registry record and an independent
Hacker News thread, and cross-checked the guard wording across three of those
before it was recorded here. Star, fork, issue and download counts came from the
GitHub and npm APIs rather than from a page.

**The method defect this exposed, which applies to the next sweep too.** The
original passes enumerated by CAPABILITY (who measures tokens, who reduces
them). A tool that presents itself under a different capability, in this case
cost and usage tracking, never entered the candidate set, and the sweep then drew
a conclusion about the whole field from the set it had. The fix is not to search
harder. It is to name, before the sweep, the adjacent categories a competitor
could be filed under (cost tracking, FinOps, observability, usage analytics,
budget control) and to enumerate each, and to refuse any sentence of the form
"nobody does X" unless the search that would have found an X is named beside it.
