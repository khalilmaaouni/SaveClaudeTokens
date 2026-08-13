# First-party verification: context-mode and Claude DCP (unit RS1)

Date: 2026-08-13. Executed by a read-only researcher; this document is written by the orchestrator because the researcher cannot write files, which also keeps the registry-edit boundary clean. NO registry entry ships in this unit. This is evidence, not a proposal.

Standing discipline this unit applies (docs/ROADMAP.md): a companion enters data/companions.json only on first-party verification. First-party means the author's own repository, manifest, README or hooks configuration, opened during the check. Anything else is RELAYED and labeled so.

## Verdicts

| Candidate | Verdict | Blocks a curated entry today |
|---|---|---|
| context-mode (mksglu/context-mode) | CONFIRMED FIRST-PARTY | yes: no documented Claude Code uninstall path |
| Claude DCP (exploreborders/claude-dcp) | CONFIRMED FIRST-PARTY | yes: no documented uninstall path at all, plus four months without a commit |

Both projects exist, both are the authors' own repositories, and every field below was read from first-party material tonight. Neither is installed on this machine: `ls ~/.claude/plugins/cache` and `claude plugin list` (79 entries enumerated) contain no matching entry.

## context-mode

- Repository: https://github.com/mksglu/context-mode, author Mert Koseoglu. FIRST-PARTY.
- Manifest: `.claude-plugin/plugin.json`, name `context-mode`, version `1.0.169`, license Elastic-2.0. FIRST-PARTY.
- What it claims, in the author's words: an MCP server that saves 98 percent of the context window with session continuity, sandboxed code execution in 11 languages, an FTS5 knowledge base with BM25 ranking, and automatic state restore across compactions. FIRST-PARTY (plugin.json and README).
- Hooks registered, read from `hooks/hooks.json`: PreToolUse (matchers include Bash, WebFetch, Read, Grep, Agent and several MCP tool names), PostToolUse (broad matcher covering Bash, Read, Write, Edit and others), UserPromptSubmit, PreCompact, SessionStart, Stop. FIRST-PARTY.
- Activation, verbatim from the README install section: `/plugin marketplace add mksglu/context-mode`, then `/plugin install context-mode@context-mode`, then restart or `/reload-plugins`. FIRST-PARTY.
- Rollback or uninstall for Claude Code: NO DATA. The only uninstall line in the README targets a different platform (`agy plugin uninstall context-mode`). A grep of the full README for a Claude Code uninstall string returned zero hits.
- Version and activity: manifest 1.0.169; latest release tag dated 2026-06-29; latest commit to main pushed 2026-08-13, so the tag is stale relative to HEAD. FIRST-PARTY via the GitHub API.
- Savings claim: the README carries a per-scenario byte table (for example a Playwright snapshot at 56.2 KB reduced to 299 B, GitHub issues at 58.9 KB reduced to 1.1 KB) and points at a fuller 21-scenario benchmark document. This is an author-reported measurement. The underlying benchmark document was NOT opened tonight, so its method is UNVERIFIED here. It is a claim with a stated basis, which is more than most, and it is still not independent.

## Claude DCP

- Full name: Claude DCP, Dynamic Context Pruning for Claude Code. Author Christian Hein. FIRST-PARTY.
- Repository: https://github.com/exploreborders/claude-dcp. Manifest `.claude-plugin/plugin.json`, name `claude-dcp`, version `0.2.0`, license MIT. FIRST-PARTY.
- What it claims, in the author's words: it manages conversation context to optimize token usage, runs before native compaction to remove obvious waste, and blocks duplicate tool calls (same tool with the same arguments). FIRST-PARTY (README).
- Hooks registered, read from `hooks/hooks.json`: PreToolUse (`dedup_check.py`, matcher covering Bash, Read, Glob, Grep, WebFetch, Edit, Write and MCP tools), PostToolUse, PostToolUseFailure, PreCompact, PostCompact, UserPromptSubmit (two separate entries), SessionEnd. FIRST-PARTY.
- Activation, verbatim from the README: development mode `claude --plugin-dir /path/to/claude-dcp`; permanent install by copying or symlinking the directory into `~/.claude/plugins/claude-dcp` and adding `claude-dcp` to the `enabledPlugins` array in settings.json. FIRST-PARTY.
- Rollback or uninstall: NO DATA. The README documents none, and a code search for "uninstall" scoped to the repository returned zero results.
- Version and activity: 0.2.0, release tagged 2026-04-09, latest commit to main 2026-04-09. Roughly four months without a commit as of this check. FIRST-PARTY via the GitHub API.
- Savings claim: one hypothetical figure in a comparison table (2.3 KB saved, about 575 tokens estimated), which the author himself disclaims as rough, based on a bytes-per-token approximation rather than real tokenization. There is no benchmark corpus and no before-and-after study. Recorded as an author-disclaimed estimate, never as evidence.

## What this means for the registry, stated plainly

Neither candidate can enter data/companions.json as a curated entry today, and the reason is the same for both: the curated schema requires a rollback path, and neither author documents one for Claude Code. That is a fact about their documentation, not a judgment about their quality.

Three consequences worth recording:

1. The blocker is exactly what unit I1 exists to solve. An open declaration file that a plugin ships itself would let either project state its own capabilities, modes and rollback command, labeled DECLARED rather than CURATED. Curation would still require first-party verification; declaration would let integration scale past hand-checked entries without lowering the evidence bar.
2. Both plugins register hooks on the same broad events Token Shield's compatibility work reasons about (PreToolUse, PostToolUse, UserPromptSubmit, PreCompact, SessionStart or SessionEnd). If either is ever installed beside a companion we already track, the hook-ownership table from unit G1 is what would surface the overlap. Nothing is asserted about a specific pair here: absent a real installation, the honest verdict for any such pair is NO DATA, never known-safe.
3. Claude DCP's four-month gap is precisely the signal unit U1 is built to catch on the other side, when a companion moves under a user who already installed it.

## Reproduction

The researcher's full command list (GitHub API calls for manifests, hooks files, tags, commits and READMEs, two web searches, and the two local plugin-cache checks) is recorded in the session transcript for this unit. Every claim above traces to one of those calls or is marked NO DATA.
