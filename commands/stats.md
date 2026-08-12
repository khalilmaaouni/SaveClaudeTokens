---
name: stats
description: Show the quick Token Shield summary: verified, native, and opportunity token savings plus your top issue, measured from your own usage counters. Triggers include stats, savings, how much did I save, token summary.
---

Run the Token Shield summary and read it back in plain language.

Step:

Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/cli.py summary`

It reads the API usage counters in the local transcripts and prints three numbers that never merge:

- **VERIFIED**: savings you proved with a real before and after. Reads NONE YET until you run an experiment (`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/cli.py experiment start "my-change"`).
- **NATIVE**: what Claude Code's own caching saved. This is Anthropic's, not this tool's.
- **OPPORTUNITY**: what you can still cut, estimated from your own sessions.

Then name the single top issue and its one-line fix, and stop. Keep it short. Every number is measured or labeled NO DATA, never a guess.

For the full picture, point the user at `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/cli.py dashboard` (the visual), `... prices` (USD API-equivalent), or `/token-audit` (the deep measurement).
