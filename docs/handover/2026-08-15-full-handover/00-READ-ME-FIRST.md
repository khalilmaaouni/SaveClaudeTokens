# Read me first

You are picking up **Token Shield**, a Claude Code plugin, from a session that
ended cleanly. Nothing is half done. There is no branch to rescue, no unmerged
work, no failing test.

Read this file, then `01`, then `04`. That is enough to start. Everything else
is reference you can reach for when its situation comes up.

## The one-paragraph version

Token Shield measures where a Claude Code user's tokens go and **proves its own
numbers**. Its whole competitive position is honesty: every figure carries a
confidence label, an unproven number may never borrow a proven one's authority,
and NO DATA always beats a guess. Most of the work in this repository is
defending that property against itself.

## Where things stand, in numbers you can re-derive

| | |
|---|---|
| Branch | `main` at `bafd02a`, clean tree, one branch, one worktree, zero open pull requests |
| Tests | **525 checks green across 23 suites**, exit 0 |
| Plus CI-only | MCP server 13, bench self-check 3, benchmark 93 |
| Python floor | clean over 56 files |
| Version | 1.8.0, and **releasing is gated** (see `05`) |
| Repository | https://github.com/khalilmaaouni/token-shield (public) |
| Local path | `~/SaveClaudeTokens` |

## The three things most likely to trip you up

1. **The documented test command is not the whole suite.** CI runs two more
   steps: the MCP server tests and the bench. A refactor that moves symbols
   passed 525 checks locally and still went red on CI, because `mcp-server/`
   imports the same modules. `03` has the full command.

2. **Clear `__pycache__` before any verifying run.** This repository's practice
   is to prove a test real by putting the defect back and watching it fail.
   Python validates its bytecode cache on modification time and size only, so a
   same-length edit reverted inside one second leaves the *deleted* code
   loaded. It has produced a false failure here and can as easily produce a
   false pass, which is the worst outcome this project has.

3. **A test that is born green proves nothing.** Every fix here ships with a
   test proven red first, by writing the test before the fix or by reinjecting
   the defect afterwards and restoring the file byte identical. This is a
   standing rule, not a preference.

## What to do first

Run the verification in `03`. If it comes back green with those numbers, you
have the same tree the last session left, and you can start on the top item in
`04`.

If it does **not** come back green, stop and report that before anything else.
Something changed outside this repository, and finding out what is the work.
