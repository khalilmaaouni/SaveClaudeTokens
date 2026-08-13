# Claims register

Every factual claim this project makes, with the evidence that backs it and a
verdict. The rule is the one the whole project runs on: a claim is trusted in
proportion to how mechanically it can be checked. So each claim below names the
check, not a feeling.

Three kinds of claim, three kinds of proof:

- **DOC** a statement about how Claude Code behaves. Proof: a first-party
  documentation page, fetched and read on the date shown, with the sentence
  quoted. These are re-checkable by opening the URL.
- **MEASURED** a number about token usage. Proof: the API `usage` counters in
  local session transcripts, read by `scripts/measure_tokens.py`, and for the
  headline figures a second derivation by different code with zero drift. Every
  measured number carries its snapshot and the caveat that it was measured on
  one machine.
- **CODE** a statement about what a script in this repo does. Proof: a named
  test in `scripts/test_measure_tokens.py` or `scripts/test_tools.py`, each
  calibrated by reinjecting the defect it guards so a green result means
  something.

Snapshot for every MEASURED number below, unless it says otherwise:
`2026-08-12 15:07:01`, schema 2, a 90 day window, 229 parent sessions among
6,251 transcripts. These totals are snapshot-bound, not stable: a live re-run
one day later, 2026-08-13, read 238 parent sessions among 5,739 transcripts,
median first request 85,587 against 85,021 the day before. A rolling window
churns by whole percents day to day, not a handful, because sessions age out
the trailing edge of the window while new ones are written at the front. This
is why every figure below names its own snapshot instead of standing as a
fixed constant.

---

## A. DOC claims, checked against first-party pages on 2026-08-12

Source key: PC = code.claude.com/docs/en/prompt-caching, MEM =
code.claude.com/docs/en/memory, MCP = code.claude.com/docs/en/mcp, SK =
code.claude.com/docs/en/skills, HK = code.claude.com/docs/en/hooks, PRICE =
platform.claude.com/docs/en/build-with-claude/prompt-caching.

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| A1 | Caching is an exact prefix match; a change anywhere in the prefix recomputes everything after it. | CONFIRMED | PC: "The match is exact, so a change anywhere in the prefix recomputes everything after it." |
| A2 | Requests are layered system prompt, then project context, then conversation, so a conversation change leaves the two above it cached. | CONFIRMED | PC layer table: system prompt / project context / conversation, "A change to the conversation layer leaves the system prompt and project context cached." |
| A3 | Cache writes bill at 1.25x base input for the 5 minute TTL and 2x for the 1 hour TTL; reads at 0.1x. | CONFIRMED | PRICE: "5-minute cache write tokens are 1.25 times", "1-hour cache write tokens are 2 times", "Cache read tokens are 0.1 times". |
| A4 | On a Claude subscription the 1 hour TTL is requested automatically; an API key stays at 5 minutes; subagents use 5 minutes either way. | CONFIRMED | PC: "On a Claude subscription, Claude Code requests the one-hour TTL automatically"; "stays at the cheaper five minutes by default"; "Subagents use the five-minute TTL even on a subscription". |
| A5 | A subscription over its plan limit, drawing on usage credits, drops back to the 5 minute TTL. | CONFIRMED | PC: "Cache writes cost more at the one-hour TTL than at the five-minute TTL, so Claude Code automatically drops to the shorter one." |
| A6 | Both model and effort level are part of the cache key; changing effort mid-session rebuilds the whole prefix. | CONFIRMED, and it refutes a common belief that effort is free | PC: "The cache is keyed by effort level as well as model, so switching with `/effort` means the next request reads the entire conversation history with no cache hits." |
| A7 | Editing a root or user CLAUDE.md mid-session does not invalidate the cache and does not apply until reload. | CONFIRMED | PC: "Editing them mid-session does not invalidate the cache, but the edit also doesn't apply... The new content loads on the next `/clear`, `/compact`, or restart." |
| A8 | Nested CLAUDE.md and rules with `paths:` frontmatter load later and an edit before they load does take effect. | CONFIRMED | PC: "Editing one before it loads does take effect." |
| A9 | Editing MCP config does not itself change the cache; it applies on restart. | CONFIRMED | PC: "Editing your MCP config does not by itself change the cache. The new config takes effect only after a restart". |
| A10 | Enabling or disabling a plugin that ships only skills, commands, agents or hooks is cache-safe; only one providing an MCP server invalidates. | CONFIRMED | PC: "Skills, commands, agents, hooks, LSP servers, monitors, and themes never invalidate the cache"; "The exception is a plugin that provides MCP servers." |
| A11 | MCP tool definitions are deferred behind tool search by default on supported models; deferral is unavailable in named cases. | CONFIRMED | MCP: "Tool search is enabled by default"; PC lists the exceptions (custom `ANTHROPIC_BASE_URL`, some hosting, `alwaysLoad`). |
| A12 | A whole-tool deny rule invalidates the cache. | CONFIRMED | PC: "adding or removing one of these rules mid-session invalidates the cache." |
| A13 | `/rewind` returns to an already-cached prefix; `/recap` appends without replacing history. | CONFIRMED | PC: rewind "truncates your conversation back to an earlier turn... the next request hits the earlier cache entry"; recap "appends the summary as command output". |
| A14 | A warm mid-session `/compact` costs a fraction of what the context size suggests. | CONFIRMED | PC: "a mid-session `/compact` costs a fraction of what the context size suggests and spends most of its time generating the summary." |
| A15 | The cache is scoped per machine and per working directory; two worktrees of one repo miss each other's cache. | CONFIRMED | PC: "two sessions in different directories build different prefixes and miss each other's cache. That includes worktrees of the same repository." |
| A16 | The auto-memory index loads the first 200 lines or 25KB, whichever comes first; content past that is dropped. | CONFIRMED | MEM: "The first 200 lines of MEMORY.md, or the first 25KB, whichever comes first, are loaded at the start of every conversation." |
| A17 | CLAUDE.md targets under 200 lines and loads in full regardless of length. | CONFIRMED | MEM: "target under 200 lines per CLAUDE.md file"; "This limit applies only to MEMORY.md. CLAUDE.md files are loaded in full regardless of length". |
| A18 | Block-level HTML comments are stripped before the index is loaded; `@path` imports expand at launch. | CONFIRMED | MEM: comments "are stripped before the index is loaded"; imports "are expanded and loaded into context at launch". |
| A19 | `disable-model-invocation: true` stops a skill loading until invoked; `skillOverrides` has four states and does not affect plugin skills. | CONFIRMED | SK: "Set to `true` to prevent Claude from automatically loading this skill"; the four `skillOverrides` states; "Plugin skills are not affected by `skillOverrides`." |
| A20 | A SessionEnd hook event exists and its input includes the transcript path. | CONFIRMED | HK: `SessionEnd` event; common input includes `transcript_path` ("Path to conversation JSON"). |

## B. MEASURED numbers, snapshot 2026-08-12 15:07:01, one machine

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| B1 | The `usage.cache_creation` object carries both `ephemeral_5m_input_tokens` and `ephemeral_1h_input_tokens`, present on every record. | CONFIRMED | probe over 11,760 records in a 7 day window: nested object present 11,760 / 11,760. |
| B2 | The flat `cache_creation_input_tokens` can read 0 while the nested fields carry real writes. | CONFIRMED | same probe: 8 of 11,760 records had flat 0 and nested sum 2,001. This is why the parser prefers the nested object. |
| B3 | 90 day median first request is 85,021 tokens; p90 is 100,606. | CONFIRMED, zero drift | `measure_tokens.py --days 90` and an independent second derivation (different code, same transcripts) both returned 85,021 and 100,606. |
| B4 | The startup floor is about 36 percent of everything a session reads (median first-request share 0.360). | CONFIRMED | `measure_tokens.py` per-session share, median over sessions with 3+ calls. |
| B5 | Subagents produced about 41 percent of all output tokens (share 0.406). | CONFIRMED, zero drift | both derivations returned 0.406 and the same subagent output total 118,123,824. |
| B6 | The per-session median cache hit ratio is 0.865. | CONFIRMED, and note the distinction below | `measure_tokens.py` median of per-session ratios. |
| B7 | The earlier "41,890 preamble" figure measured the wrong population. | CONFIRMED | over the same 90 day window, the schema-1 method (first record of every transcript) saw 6,249 transcripts with a 41,898 median; schema 2 saw the 229 real sessions among them with an 85,021 median. Same machine, same counters. The metric changed, not the spend. |
| B8 | 65 sessions switched model mid-flight, 28 percent of the 229 active parent sessions, each rebuilding its cache from zero. | CONFIRMED, zero drift on the count | `measure_tokens.py` per-session model count and an independent derivation that reads transcripts directly (not through `measure_tokens`) both returned exactly 65 switched sessions. The denominator is the code's own `len(parent)` = 229 active sessions, so the share is 65/229 = 28 percent. Model switching is a PROVEN pain point because each model has its own cache (claim A6). |
| B9 | Caching's net saving in the 90 day window is about 74.6 billion base-input token-units. | CONFIRMED, and stated net | reads of 84.8B billed 8.5B at 0.1x instead of 84.8B uncached, a gross read saving of 76.3B (0.9 x reads). Caching also pays a write premium of 1.7B (0.25 x the 5 minute writes plus 1.0 x the 1 hour writes). The dashboard headline is the NET, 76.3B minus 1.7B = 74.6B, not the gross read figure dressed up as net. A relative figure in base-input units, not dollars. |
| B10 | The 74.6B saving is Claude Code's native automatic caching, NOT produced by this tool. | CONFIRMED, and this is the load-bearing honesty of the whole dashboard | Claude Code "manages prompt caching automatically" (code.claude.com/docs/en/prompt-caching); the cache reads that generate B9 happen by default whether or not Token Shield is installed. The dashboard attributes the number to Anthropic's caching in the hero itself and does not claim it. The tool's own attributable value is separate: the pain-point prescriptions (what following its rules saves ON TOP of native caching) and the visibility of the number. Presenting the native saving as the plugin's own would be the exact overclaim this project exists to avoid. |

### The two hit-ratio statistics, stated precisely

B6 is the **median of per-session hit ratios** (0.865). The **pooled** ratio,
total cache read over total input across everything, is 0.966 on the same
snapshot. Both are correct and they answer different questions: the pooled
number is dominated by a few very long sessions with high reuse, the median
weights every session equally. This project reports the median, because the
question it serves is "how does a typical session do", and it labels it as a
median rather than letting it be read as the pooled figure. A number that does
not say which statistic it is, is not yet a scientific number.

## C. CODE claims, proven by calibrated tests

| # | Claim | Verdict | Test |
|---|---|---|---|
| C1 | Normalized cost is NO DATA when the TTL split is unknown, never an assumed 5 minute price. | CONFIRMED | `test_unsplit_writes_give_no_data_not_a_guess`, `test_split_writes` |
| C2 | The startup floor is the parent's first call, never a subagent's. | CONFIRMED | `test_read_session`, `test_subagent_transcript_is_not_a_session` |
| C3 | A subagent-only transcript is counted as a subagent transcript, not a session, but its tokens stay in the totals. | CONFIRMED | `test_subagent_transcript_is_not_a_session` |
| C4 | The meter refuses to print a first-request delta across the schema change, and warns on a window mismatch. | CONFIRMED | `test_legacy_baseline_keys_still_readable`, plus the `--compare` schema and window guards |
| C5 | A ratio delta is formatted as a ratio, and a percent against a zero baseline is NO DATA, not +0.0%. | CONFIRMED | `test_delta_formatting` |
| C6 | `context_lint` derives the project slug by replacing every non-alphanumeric with a dash, matching the real directory names. | CONFIRMED | `test_project_slug_replaces_every_non_alphanumeric` |
| C7 | `context_lint` measures the loaded content (frontmatter and block comments stripped), strips block comments only, and counts CRLF terminators in the byte cut. | CONFIRMED | `test_loaded_content_matches_what_claude_code_loads`, `test_memory_index_truncation_is_reported_where_it_actually_cuts` |
| C8 | The telemetry ledger row carries counters only, never conversation text, and keeps the transcript basename not its full path. | CONFIRMED | `test_ledger_row_carries_counters_and_nothing_else`, `test_ledger_main_writes_only_allowed_keys` |
| C9 | The telemetry hook exits 0 and prints nothing to stdout on hostile input, so it can never break the session it measures. | CONFIRMED | `test_telemetry_never_breaks_the_session` |
| C10 | The dashboard export writes aggregates only, no session-identifying text. | CONFIRMED | `test_lever_naming_follows_the_measurement`, and the export omits per-session rows unless asked |

## D. Advisor sweep claims, checked 2026-08-12 before the v1.7 build

Source key: SET = code.claude.com/docs/en/settings, IM =
code.claude.com/docs/en/interactive-mode, SA = code.claude.com/docs/en/sub-agents,
HK and MCP as above. Verified by a read-only sweep, each quote from an opened
first-party page, then spot-checked by the orchestrator against local files.

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| D1 | An `InstructionsLoaded` hook event fires at session start and when instruction files load lazily. | CONFIRMED | HK: "Fires at session start and when files are lazily loaded during a session." |
| D2 | `includeGitInstructions: false` removes the built-in commit and PR workflow instructions. | CONFIRMED | SET: "Default: true... Set to false to remove both." |
| D3 | `claudeMdExcludes` skips named CLAUDE.md files when loading memory. | CONFIRMED | SET: "Glob patterns or absolute paths of CLAUDE.md files to skip when loading memory." |
| D4 | `skillOverrides` can hide or collapse a skill per name. | CONFIRMED | SET: "Per-skill visibility overrides keyed by skill name." |
| D5 | `MAX_MCP_OUTPUT_TOKENS` caps MCP tool output size. | CONFIRMED | MCP: "adjust the maximum allowed MCP output tokens using the MAX_MCP_OUTPUT_TOKENS environment variable." |
| D6 | Tool search is on by default and `ENABLE_TOOL_SEARCH` controls it. | CONFIRMED | MCP: "Tool search is enabled by default... Control tool search behavior with the ENABLE_TOOL_SEARCH environment variable." |
| D7 | `/btw` asks a question without adding to conversation history. | CONFIRMED | IM: "Use /btw to ask a question about your current work without adding to the conversation history." |
| D8 | Effort changes are observable in transcripts; fast-mode state is not. | SPLIT: effort CONFIRMED, fast-mode REFUTED | Top-level `"effort":"xhigh"` appears 79 times in one real transcript; a `fastMode` counter field appears in none (the one literal hit is conversation text, not a field). Fast-mode detection is CUT from the profiler. |
| D9 | Agent frontmatter supports `model`, `effort`, and `maxTurns`. | CONFIRMED | SA: "`maxTurns`... Maximum number of agentic turns"; "`effort`... Options: low, medium, high, xhigh, max." |
| D10 | The blueprint's companion repos exist as named, but the token-saver installed here is `ppgranger/token-saver`, a different project from the blueprint's `ww-w-ai/claude-code-token-saver`. | CONFIRMED with correction | `gh api repos/<owner>/<repo>` resolved each blueprint repo; local `~/.claude/plugins/cache/claude-community/token-saver` manifest names ppgranger. The registry keys token-saver to ppgranger and lists claude-code-token-saver separately, mention-only. |

Consequences applied to the build: fast-mode signals are excluded everywhere;
`data/companions.json` uses the installed, verified sources; every strategy that
cites D1 to D9 names the row it stands on.

## E. Review-driven scope decisions, 2026-08-12 adversarial review

| Row | Decision | Reason |
|-----|----------|--------|
| E1 | The experiment fingerprint hashes the user CLAUDE.md, `~/.claude/settings.json`, `~/.claude.json`, and the `~/.claude/skills` tree, as a sorted per-file manifest of sha256 lines. Project-level CLAUDE.md files stay OUT of fingerprint scope. | The experiment is machine-level and the working directory can change between start and end, so hashing one project's CLAUDE.md would make the fingerprint depend on where the command was typed. The gap is recorded here rather than hidden: a project CLAUDE.md edit during an experiment window is a confounder the fingerprint will not catch. |
| E2 | When `--treats` names a file inside fingerprint scope, the exclusion is recorded in the experiment record and printed at close, never applied silently. | The reviewer proved a treated `settings.json` blinds the guard to every other change in that file; visibility is the affordable fix, structural key-level hashing is deferred. |

## The standing caveat on every measured number

Every MEASURED figure here was taken on one machine's transcripts. They are
defaults for illustration, not universal constants. The honest use of this repo
is to run `measure_tokens.py` on your own machine and read your own numbers. The
method is portable; the specific figures are not. This is stated wherever a
number appears, not only here.
