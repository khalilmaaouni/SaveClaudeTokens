# Companion first-party verification, 2026-08-13

Goal: before any companion registry entry ships, the roadmap requires the companion's real source, hooks, and modes to be confirmed first-party (docs/ROADMAP.md line 52, quoting the discipline that caught the token-saver identity mixup in docs/CLAIMS.md section D, row D10). This note verifies ponytail, caveman, and token-saver against their actual installed files on this machine (not memory, not the vendor's marketing copy).

Every quote below was read from a file opened during this session, path given beside it.

## ponytail

Installed at: `~/.claude/plugins/cache/claude-community/ponytail/4.9.0`
Registered in `~/.claude/plugins/installed_plugins.json` under key `ponytail@claude-community`, `"version": "4.9.0"`, `"installedAt": "2026-08-12T04:10:15.618Z"`.

Manifest, `~/.claude/plugins/cache/claude-community/ponytail/4.9.0/.claude-plugin/plugin.json`:
```
"name": "ponytail",
"version": "4.9.0",
"description": "Lazy senior dev mode. Forces the simplest, shortest solution that actually works: YAGNI, stdlib first, no unrequested abstractions.",
"author": { "name": "Dietrich Gebert", "url": "https://github.com/DietrichGebert" },
"hooks": "./hooks/claude-codex-hooks.json"
```

Hook footprint, `~/.claude/plugins/cache/claude-community/ponytail/4.9.0/hooks/claude-codex-hooks.json`: 3 events, 3 hook entries.
- `SessionStart`, matcher `"startup|resume|clear|compact"`, runs `hooks/ponytail-activate.js`.
- `SubagentStart`, no matcher, runs `hooks/ponytail-subagent.js`.
- `UserPromptSubmit`, no matcher, runs `hooks/ponytail-mode-tracker.js`.

Modes, `~/.claude/plugins/cache/claude-community/ponytail/4.9.0/hooks/ponytail-config.js`:
```
const DEFAULT_MODE = 'full';
const VALID_MODES = ['off', 'lite', 'full', 'ultra', 'review'];
const RUNTIME_MODES = ['off', 'lite', 'full', 'ultra'];
```
`review` is documented in the same file as session-only, never a valid default (comment: "review is a session-only mode, never a valid default").

Injection behavior, `~/.claude/plugins/cache/claude-community/ponytail/4.9.0/hooks/ponytail-activate.js`. Header names the file as ponytail's SessionStart activation hook for Claude Code (comment uses an em dash there, elided per the no-dash house rule; content otherwise unchanged), then quotes verbatim:
```
// Runs on every session start:
//   1. Writes flag file at $CLAUDE_CONFIG_DIR/.ponytail-active (defaults to ~/.claude; statusline reads this)
//   2. Emits ponytail ruleset as hidden SessionStart context
//   3. Detects missing statusline config and emits setup nudge
```
Subagent injection is corroborated in `README.md` of the same install:
"While active, the ruleset is also injected into every subagent spawned via the Agent tool. To scope that to specific agent types... set the `PONYTAIL_SUBAGENT_MATCHER` env var... Unset means inject into every subagent (the default)."

Always-on token footprint: NO DATA. Searched `README.md` and `docs/*.md` in the installed tree for a stated per-turn or per-session token cost figure (grepped for "footprint", "token cost", "overhead") and found none. The README does carry a relative benchmark ("tokens 78%" of a no-skill baseline on Haiku 4.5) but that is a comparison figure, not an absolute always-on cost.

Capability classification (Token Shield vocabulary: minimal_code, output_compression, tool_output_isolation, deterministic_deduplication; defined at `~/.claude/plugins/cache/token-shield/token-shield/1.7.1/docs/ROADMAP.md` line 37): **minimal_code**. Its own description says it forces "the simplest, shortest solution that actually works," matching the token-shield companions.json entry for ponytail ("smaller diffs, YAGNI ladder"), read from `~/.claude/plugins/cache/token-shield/token-shield/1.7.1/data/companions.json`.

Verdict: CONFIRMED FIRST-PARTY for version, hooks, and modes. Token footprint claim: NO DATA (not stated in any installed file).

## caveman

Installed at: `~/.claude/plugins/cache/claude-community/caveman/0d95a81d35a9`
Registered in `~/.claude/plugins/installed_plugins.json` under key `caveman@claude-community`, `"version": "0d95a81d35a9"` (a git commit sha, not semver), `"installedAt": "2026-07-26T12:07:26.924Z"`.

Manifest, `~/.claude/plugins/cache/claude-community/caveman/0d95a81d35a9/.claude-plugin/plugin.json`:
```
"name": "caveman",
"description": "Ultra-compressed communication mode. Cuts 65% of output tokens (measured) while keeping full technical accuracy by speaking like a caveman.",
"author": { "name": "Julius Brussee", "url": "https://github.com/JuliusBrussee" }
```
This manifest carries no `version` key; the installed_plugins.json commit-sha stands in for a version. A second, unrelated plugin.json exists at `plugins/caveman/.codex-plugin/plugin.json` inside the same checkout (a Codex-platform variant, `"version": "0.1.0"`); that is a different platform target bundled in the same repo, not the Claude Code manifest, and is noted here only so it is not mistaken for the installed version.

Hook footprint, same `.claude-plugin/plugin.json`: 2 events, 2 hook entries.
```
"SessionStart": [{ "hooks": [{ "type": "command", "command": "node \"${CLAUDE_PLUGIN_ROOT}/src/hooks/caveman-activate.js\"", "timeout": 5, "statusMessage": "Loading caveman mode..." }] }],
"UserPromptSubmit": [{ "hooks": [{ "type": "command", "command": "node \"${CLAUDE_PLUGIN_ROOT}/src/hooks/caveman-mode-tracker.js\"", "timeout": 5, "statusMessage": "Tracking caveman mode..." }] }]
```

Modes, `~/.claude/plugins/cache/claude-community/caveman/0d95a81d35a9/src/hooks/caveman-config.js`:
```
const VALID_MODES = [
  'off', 'lite', 'full', 'ultra',
  'wenyan-lite', 'wenyan', 'wenyan-full', 'wenyan-ultra',
```
and further down, `return 'full';` as the default fallback.

Commands shipped, `~/.claude/plugins/cache/claude-community/caveman/0d95a81d35a9/commands/`: `caveman.toml`, `caveman-commit.toml`, `caveman-init.toml`, `caveman-review.toml`, `caveman-stats.toml` (5 commands, each with a matching `.md`). `cavecrew` is not a command in this tree; it is three subagents at `agents/cavecrew-builder.md`, `agents/cavecrew-investigator.md`, `agents/cavecrew-reviewer.md`.

Injection behavior, header comment of `src/hooks/caveman-activate.js`. Header names the file as caveman's SessionStart activation hook for Claude Code (comment uses an em dash there, elided per the no-dash house rule; content otherwise unchanged), then quotes verbatim:
```
// Runs on every session start:
//   1. Writes flag file at $CLAUDE_CONFIG_DIR/.caveman-active (statusline reads this)
//   2. Emits caveman ruleset as hidden SessionStart context
//   3. Detects missing statusline config and emits setup nudge
```

The 65 percent compression figure in the plugin.json description is scoped to one mode only, `src/hooks/caveman-stats.js`:
```
const COMPRESSION = { 'full': 0.65 };
```
with a preceding comment noting only 'full' has measured data; lite and ultra are not benchmarked in that file.

Capability classification: **output_compression** (of the assistant's own narration, not tool output). Matches the token-shield companions.json entry: "benefit": "compressed narration".

Verdict: CONFIRMED FIRST-PARTY for source, hooks, and modes. The plugin.json carries no semver; installed_plugins.json's commit-sha field is the only local version record, stated here rather than treated as NO DATA since it is a real, quoted field.

## token-saver

Installed at: `~/.claude/plugins/cache/claude-community/token-saver/2.7.1`
Registered in `~/.claude/plugins/installed_plugins.json` under key `token-saver@claude-community`, `"version": "2.7.1"`, `"installedAt": "2026-08-09T23:54:09.496Z"`.

Manifest, `~/.claude/plugins/cache/claude-community/token-saver/2.7.1/.claude-plugin/plugin.json`:
```
"name": "token-saver",
"description": "Automatically compresses verbose CLI output (git, docker, npm, terraform, kubectl, etc.) to save tokens in Claude Code sessions. 32 specialized processors with content-aware compression.",
"version": "2.7.1",
"author": { "name": "ppgranger", "url": "https://github.com/ppgranger" },
"repository": "https://github.com/ppgranger/token-saver",
"license": "Apache-2.0"
```
This confirms Token Shield's own claim D10 in `~/.claude/plugins/cache/token-shield/token-shield/1.7.1/docs/CLAIMS.md`: "the token-saver installed here is `ppgranger/token-saver`, a different project from the blueprint's `ww-w-ai/claude-code-token-saver`." The installed manifest's author and repository fields match ppgranger exactly, matching the resolved identity, not the blueprint's mixup.

Hook footprint, `~/.claude/plugins/cache/claude-community/token-saver/2.7.1/hooks/hooks.json`: 2 events, 2 hook entries.
```
"PreToolUse": [{ "matcher": "Bash", "hooks": [{ "type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/scripts/hook_pretool.py\"", "timeout": 10 }] }],
"SessionStart": [{ "hooks": [{ "type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/scripts/hook_session.py\"", "timeout": 5 }] }]
```

Processors, enabled/disabled state: 32 processors are auto-discovered from `src/processors/`, per the docstring of `~/.claude/plugins/cache/claude-community/token-saver/2.7.1/src/processors/__init__.py`: "Scans all .py modules in this package, finds non-abstract Processor subclasses, instantiates them." The code itself has no per-processor default-disabled list; the shipped default in `~/.claude/plugins/cache/claude-community/token-saver/2.7.1/skills/token-saver-config/SKILL.md` is `disabled_processors (list, default []): processor names ... to turn off entirely`, meaning every processor including file_content and env ships active by default from the vendor.

On this machine that default is overridden. `~/.token-saver/config.json` (a file outside the plugin tree, written locally, not vendor-shipped) reads:
```
{
  "_comment": "Hardening set 2026-08-10. file_content and env are disabled on purpose. Two reasons. (1) token-saver's PreToolUse hook returns permissionDecision allow on every command it wraps, so leaving these on would auto-approve `cat` of any file, including ~/.ssh keys and .env files, without a permission prompt. (2) A compressed or truncated view of a file I am about to edit is a correctness risk, and correctness outranks token saving. Verified 2026-08-10: a 62-line .env piped through wrap.py came back with AWS_SECRET_ACCESS_KEY and ANTHROPIC_API_KEY in clear text, so the documented redaction net did not fire on that path. Re-enable only with a founder decision.",
  "disabled_processors": ["file_content", "env"]
}
```
This directly confirms the CLAUDE.md operating rule that these two processors "stay DISABLED without a founder decision," and it is a locally authored, dated, reasoned override, not a vendor default.

`~/.local/bin/python3` dependency: confirmed present and resolved first in PATH on this machine.
```
$ ls -la ~/.local/bin/python3
lrwxr-xr-x ... /Users/khalil.maaouni/.local/bin/python3 -> /Users/khalil.maaouni/.local/bin/python3.13
$ ~/.local/bin/python3 --version
Python 3.13.14
$ which python3
/Users/khalil.maaouni/.local/bin/python3
```
The hook scripts invoke bare `python3` (see hooks.json above), so this symlink's position in PATH is what makes the hooks run under 3.13. The specific claim that "Apple's 3.9 crashes it" is NOT found in any file inside the token-saver install (searched README.md and CLAUDE.md for "3.13", "3.9", "apple", "crash" and found no hits); that detail is the founder's own operational note about this machine's stock Python, not a token-saver claim, so it is recorded here as NO DATA from the companion's own files, separate from the confirmed dependency on the symlink itself.

Capability classification: **output_compression** (of tool/shell output specifically, not narration). Matches token-shield companions.json: "benefit": "compresses noisy shell output before the model reads it." No processor here does cross-call deduplication or context isolation as their own named strategy, so **deterministic_deduplication** and **tool_output_isolation** are NO DATA for this companion; not found as claims in its own docs.

Verdict: CONFIRMED FIRST-PARTY for source (ppgranger, matching D10), hooks, processor count, and the file_content/env disabled state (local override, quoted and dated). Python 3.9-crash detail: NO DATA in vendor files, machine-level note only.

## Summary

| Companion | Verdict |
|---|---|
| ponytail | CONFIRMED FIRST-PARTY (version, hooks, modes); token footprint NO DATA |
| caveman | CONFIRMED FIRST-PARTY (source, hooks, modes); no semver in manifest, commit-sha stands in |
| token-saver | CONFIRMED FIRST-PARTY (source resolves to ppgranger per D10, hooks, processor config); Apple-3.9-crash detail NO DATA in vendor files |

None of the three needed a correction beyond what docs/CLAIMS.md D10 already recorded for token-saver. No new identity mixup found for ponytail or caveman.
