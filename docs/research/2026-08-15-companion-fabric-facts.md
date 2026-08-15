# Companion Fabric: first party facts, 2026-08-15

Gathered by two read only researchers on 2026-08-15 for the Companion Fabric unit (CF1). Every field below carries the page a researcher actually opened. Where a project's own pages do not state something, the answer is the literal string NO DATA, never an inference.

Source discipline, restated because it is the whole point: only the project's own repository, README, documentation site, manifest or release notes count. Blog posts, listicles and summaries were rejected as sources for every field. This discipline exists because a registry entry was once nearly written from a second hand description of the wrong project entirely (docs/CLAIMS.md section D).

Nothing in this file is a Token Shield measurement. Every percentage below is the vendor's own published claim, recorded as a claim. Nothing here is labelled MEASURED or VERIFIED, because nothing here was measured on this machine.

## RTK (rtk-ai/rtk)

- Repository: https://github.com/rtk-ai/rtk, owner rtk-ai. Its own README warns of a name collision with an unrelated crates.io package called Rust Type Kit.
- What it does, its words: "rtk filters and compresses command outputs before they reach your LLM context." Also "High-performance CLI proxy that cuts up to 90% of the bash output your agent reads."
- Mechanism: a PreToolUse hook rewrites Bash commands to rtk equivalents. Four strategies: smart filtering, grouping, truncation, deduplication. Only Bash calls are rewritten; Read, Grep and Glob are untouched.
- Install, verbatim: `brew install rtk`, then `rtk init -g` to wire it into Claude Code.
- Uninstall, verbatim: `rtk init -g --uninstall`, then `cargo uninstall rtk` or `brew uninstall rtk` depending on how it was installed.
- Hooks: one event, PreToolUse, native binary, Bash calls only.
- MCP server: NO DATA. The README describes a CLI proxy and never mentions an MCP server. No persistent daemon is described; the README states under 10ms overhead per call.
- Environment: no API key. One optional variable, `RTK_TELEMETRY_DISABLED=1`. No base URL override.
- License: Apache 2.0.
- Popularity: 76,156 stars observed 2026-08-15 via the GitHub API. Most recent push 2026-08-14. Latest release tag dev-0.45.1-rc.356, a prerelease channel.
- Published claim: "60-90% on common dev commands". NOTE, AND THIS MATTERS TO US: its README explicitly separates that from billing, saying "That is what RTK measures, and it is not the same as cutting your bill by 90%", and discloses that its token counts are estimated as bytes divided by four with no real tokenizer. It does NOT separate its savings from Anthropic's own prompt caching; caching is not mentioned. So it is more honest than the field average on the bill question, and still silent on the caching question, which is our moat.
- Problem class: tool_output. Every mechanism described treats Bash output, not startup cost, cache health or model verbosity.
- Risks to state before prescribing: it alters what the model sees for Bash calls; it can lose information by design (truncation, deduplication, signatures instead of full bodies), though full output is teed to a local log on failure by default; it is reversible with the commands above; it silently does not cover Read, Grep or Glob, which a user could mistake for full coverage.

VERDICT: PRESCRIBABLE. Complete install and rollback path, permissive license, one hook, and a problem class our tournament already ranks.

## Context Mode (mksglu/context-mode)

- Repository: https://github.com/mksglu/context-mode, owner mksglu. A second repository, scottconverse/context-mode, is a one star port and must not be used for a registry entry.
- What it does, its words: "the other half of the context problem", covering raw tool output bloat, loss of session state on compaction, the model acting as a data processor rather than a code generator, and output side verbosity.
- Mechanism: context offloading. An MCP server runs tool calls in an isolated subprocess so raw data never enters context and only a result returns. Session continuity comes from a SQLite event log retrieved selectively rather than replayed. Hooks route matching tool calls through the sandbox.
- Install, verbatim: `/plugin marketplace add mksglu/context-mode` then `/plugin install context-mode@context-mode`. MCP only alternative: `claude mcp add context-mode -- npx -y context-mode`.
- Uninstall: **NO DATA for the Claude Code path.** The README gives an upgrade command and a knowledge base purge command, neither of which removes it. The only literal uninstall command in the entire README is for a different client, the Antigravity CLI (`agy plugin uninstall context-mode`). The researcher confirmed this by grepping the full README for uninstall, remove and rollback before reporting the gap, rather than assuming absence.
- Hooks: six events on Claude Code, PreToolUse, PostToolUse, UserPromptSubmit, PreCompact, SessionStart and Stop.
- MCP server: yes, and it is the product. Eleven MCP tools on Claude Code, six sandbox and five meta. Tool execution runs in a sandboxed subprocess.
- Environment: no API key. Three optional variables (`CONTEXT_MODE_DIR`, `CONTEXT_MODE_PLATFORM`, `CONTEXT_MODE_EXTERNAL_MCP_NUDGE_EVERY`). The README states no telemetry, no cloud sync, no account.
- License: Elastic License 2.0, source available, NOT OSI open source. Confirmed by fetching the LICENSE file directly.
- Popularity: 19,865 stars observed 2026-08-15 via the GitHub API. Most recent push 2026-08-14. Latest tagged release v1.0.169 from 2026-06-29, well behind the commit activity.
- Published claim: a benchmark table of raw versus processed bytes per scenario, rolling up to "over a full session: 315 KB of raw output becomes 5.4 KB", the source of its 98 percent headline. It measures bytes of tool output kept out of context, not dollars, and does not separate the figure from Anthropic's own prompt caching, which is never mentioned.
- Problem class: tool_output primarily, since the entire quantified benchmark is per call output size, with a secondary claim on boundaries and startup rent through session continuity across compaction.
- Risks: an MCP server plus six hook events sit in front of nearly every tool call, which is ongoing runtime cost rather than a passive filter; it alters what the model sees, since the model never sees the raw payload; it can lose information, with session data auto deleting without `--continue` and a documented fourteen day cleanup that removes older content databases on startup; and its license carries usage restrictions.

VERDICT: **NOT PRESCRIBABLE TODAY, on our own standing rule.** No confirmed rollback command exists for the Claude Code path. A treatment we cannot reverse is one we will not prescribe, and this is the same rule that blocked two candidates on 2026-08-13 (docs/ROADMAP.md, the RS1 research line). It enters the registry as a MENTION with the reason stated, so a user who already runs it still gets measured honestly.

FLIP CONDITION: the project publishes a literal uninstall command for the Claude Code plugin path, or a maintainer confirms one first party. Then it is re-reviewed for promotion to a curated treatment. This is a documentation gap on their side, not a judgement about the tool's quality, and the registry entry says so in those words.

## Token Optimizer MCP (ooples/token-optimizer-mcp)

- Repository: https://github.com/ooples/token-optimizer-mcp, owner ooples.
- What it does, its words: "Spend less context, keep the conclusions, and audit every claim across 16 coding clients."
- Mechanism: a PreToolUse hook refuses large Read, Grep, Glob, Edit, Write and Bash calls (over roughly 25KB) and redirects them to smart equivalents; re-reads of unchanged files return diffs only; a per project knowledge graph holds prior findings so they are not re-derived.
- Install, verbatim: `/plugin marketplace add ooples/token-optimizer-mcp`, then `/plugin install token-optimizer@token-optimizer`, then `/reload-plugins`.
- Uninstall, verbatim: `npm run uninstall-hooks` to preview, then `npm run uninstall-hooks -- --apply` to execute.
- Hooks: three events, PreToolUse (the router), SessionStart (policy injection), PreCompact.
- MCP server: yes, over stdio, plus the native hooks.
- Environment: no API key. Four optional variables (`TOKEN_OPTIMIZER_MODE`, `TOKEN_OPTIMIZER_LARGE_READ_BYTES`, `TOKEN_OPTIMIZER_CACHE_DIR`, `TOKEN_OPTIMIZER_REDIRECT_LARGE_READS`).
- License: MIT.
- Popularity: 485 stars observed 2026-08-15, 506 commits on master, exact last commit date NO DATA.
- Published claim: "43,491 net verified MCP transport tokens avoided", stated as 54,037 gross minus 10,546 of deliberate expansion. Notable: it publishes a NET figure with its own expansion subtracted, which is the same discipline we apply. It does not separate Anthropic's own cache savings from its own effect.
- Problem class: tool_output primarily, secondarily overbuild through the knowledge graph.
- Risks: a background MCP process plus a gate on every file, search and shell call, so both startup and per call overhead; it refuses or rewrites what the model sees by design; the hooks are removable with the documented script, but the on disk knowledge graph cache is NOT documented as removed by that script, so a residue survives an uninstall.

VERDICT: PRESCRIBABLE, with the cache residue disclosed in the entry. The behaviour is fully reversible through a documented command, which is our test; leftover cache files are residue to name honestly, not an unreversible change.

## token-saver, project A (ppgranger/token-saver)

This is the project already carried in our registry, and the one installed on this machine (cross checked against its local plugin.json at version 2.7.1).

- Repository: https://github.com/ppgranger/token-saver.
- What it does, its words: "Cut your AI coding costs by 60-99% on CLI output, without losing a single error message."
- Mechanism: 36 content aware processors, local regex and string parsing with no external calls, compressing verbose CLI output (git, docker, npm, terraform, kubectl, pytest and others) while preserving errors, diffs and stack traces.
- Install, verbatim: `/plugin marketplace add ppgranger/token-saver`, then `/plugin install token-saver`.
- Uninstall, verbatim: `python3 install.py --uninstall`.
- Hooks: two events, PreToolUse (rewrites the command to a compressing wrapper) and SessionStart (savings stats and update check).
- MCP server: none. No persistent background process; it runs inline during tool calls.
- License: Apache 2.0, confirmed both on GitHub and in the local plugin manifest.
- Popularity: 136 stars observed 2026-08-15.
- Published claim: 16 before and after scenarios, 76 percent (git diff) to 99.9 percent (npm install) compression, locked to a baselines file under a continuous integration ratchet test. It measures its own CLI output compression only and does not touch or separate Anthropic cache savings.
- Risks: small per call overhead; it alters what the model sees by design, and compression is lossy for whatever it judges to be noise; reversible with the documented command. Machine specific caveat carried from this machine's own rules: the local copy needs a working python3 on 3.13, and its file_content and env processors stay disabled because they would auto approve reads of files including secrets.

VERDICT: PROMOTE from "detect and measure only" to a prescribable treatment, problem class tool_output. The original tier was set while its identity was unverified, which is exactly the ambiguity that has now been settled first party with a documented uninstall. FLIP: a maintainer change removes the uninstall path, or the identity ambiguity resurfaces, in which case it returns to detect and measure only.

## token-saver, project B (ww-w-ai/claude-code-token-saver)

A DIFFERENT project sharing the name. Recorded here so that the collision is documented rather than rediscovered.

- Repository: https://github.com/ww-w-ai/claude-code-token-saver, distributed through https://github.com/ww-w-ai/marketplace.
- Mechanism: detects prompt cache expiry (idle beyond 3,590 seconds) and blocks the resulting full context resend; auto delegates to cheaper subtasks; restores prior session context from transcripts with no model call; injects a trimmed git instruction block at session start.
- Uninstall: NO DATA. No automated uninstall exists. The README says to run `/setup-git-lite revert` before removing the plugin, which reverses one side effect and is not a full uninstall.
- License Apache 2.0, 27 stars observed 2026-08-15.
- Published claim: "45 percent cost reduction measured", 326 dollars a day to 180 dollars a day on one modelled day, and it explicitly does NOT separate Anthropic's native cache savings from its own effect, presenting a combined net figure. THIS IS THE CLEANEST EXAMPLE IN THE FIELD OF THE CONFLATION OUR MOAT ATTACKS: the tool's headline mechanism is preventing a cache expiry, so the number it publishes is substantially Anthropic's caching being credited to the tool.
- Problem class if it were prescribable: cache_health.

VERDICT: NOT PRESCRIBABLE. No documented uninstall, only a partial revert, so it fails the same reversibility rule as Context Mode. It enters as a mention whose main job is to disambiguate the name.

## ccusage (ryoppippi/ccusage)

- Repository: https://github.com/ryoppippi/ccusage, canonical per its own site https://ccusage.com/.
- What it is: "A fast local CLI for tracking tokens and estimated costs" across Claude Code and roughly fifteen other agents.
- Mechanism: reads the local usage logs each agent already writes, computes token and cost breakdowns by day, week, month, session and five hour billing block. No network calls to run a report.
- Install, verbatim: `npx ccusage@latest`. Uninstall: NO DATA.
- MCP server: none. No persistent background process.
- License MIT, 17.9k stars observed 2026-08-15.
- Published savings or accuracy figures: none found first party. It claims no savings, which is consistent with being a meter.

CLASSIFICATION: METER, not a treatment. It reports and never intervenes.
THE MEASUREMENT IDEA WORTH COPYING: it separates cache creation tokens from cache read tokens in its reports rather than lumping everything cached together. It stops short of isolating Anthropic's cache saving as its own figure, which is the step we already take and it does not.

## CodeBurn (getagentseal/codeburn)

Name caveat: no first party source for a project literally spelled "CodeBurn" was found. getagentseal/codeburn, lowercase, is the closest match and is reported as such, not as a confirmed identity.

- What it is: "Free, local tool to track AI coding token usage and cost across 40 tools and agents", by model, project and task.
- Mechanism: reads local session files, prices against daily refreshed pricing data, classifies usage into thirteen task categories. A separate `optimize` command scans for waste patterns (re-read files, low edit to read ratio, unused MCP servers, bloated configs) and can apply reversible journaled fixes with `optimize --apply`.
- Install, verbatim: `npm install -g codeburn`, or run through `npx codeburn`. Uninstall: NO DATA first party.
- Hooks: guard hooks install into Claude Code's settings.json to enforce spend caps (5 dollars soft, 15 dollars hard by default) and to warn on high waste sessions. Exact event names: NO DATA.
- MCP server: yes, through `codeburn mcp`, plus an optional dashboard and a macOS menubar widget.
- License MIT, 9.4k stars observed 2026-08-15.
- Published savings figures: none. Its README claims only to surface waste.

CLASSIFICATION: METER primarily. The optional `optimize --apply` is a narrow treatment edge, opt in and secondary.
TWO IDEAS WORTH COPYING: per task category classification (thirteen categories) with a one shot success rate, which ties cost to outcome rather than volume and is the same idea as cost per successful task; and a spend cap enforced through guard hooks.
MATERIAL CORRECTION TO OUR OWN FIELD MAP: our field map recorded that every Claude Code tool only reports and that hard budget enforcement exists only in proxy tools. That is now WRONG as written. CodeBurn ships spend cap guard hooks inside Claude Code. The parked question about a hard budget brake should be re-opened with this evidence, and the field map line corrected rather than left standing.

## Summary of verdicts

| Tool | Class | Prescribable | Reason |
|---|---|---|---|
| RTK | treatment, tool_output | YES | full documented rollback, Apache 2.0, one hook |
| Token Optimizer MCP | treatment, tool_output | YES, with disclosed cache residue | documented uninstall script for the hooks |
| token-saver (ppgranger) | treatment, tool_output | YES, promoted from detect only | identity settled first party, documented uninstall |
| Context Mode | treatment, tool_output | NO | no uninstall command for the Claude Code path |
| claude-code-token-saver (ww-w-ai) | treatment, cache_health | NO | no uninstall, only a partial revert |
| ccusage | meter | not applicable | a meter is never a treatment |
| CodeBurn (codeburn) | meter | not applicable | a meter is never a treatment |

