---
name: token-audit
description: Measure real token usage from session transcripts, show waste signals, and compare against a saved baseline.
---

Run the measurement script that ships with this plugin. It reads the `usage`
counters Anthropic returned on every assistant message in the local session
transcripts, so its output is measurement, not estimation.

Steps:

1. Run the summary over a sensible window:
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/measure_tokens.py --days 30`

2. Run the waste signals to find the expensive sessions:
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/measure_tokens.py --days 30 --sessions`

3. If the user has a baseline snapshot, compare against it:
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/measure_tokens.py --days 30 --compare <path>`
   If they do not, offer to write one:
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/measure_tokens.py --days 30 --baseline <path>`

Then read the numbers back in plain language, in this order:

- Preamble median. This is what every call in every session pays before any
  work happens. If it is large relative to the useful context, pruning the
  always-loaded set is the highest-value action available, ahead of every
  other lever.
- Cache hit ratio. Above roughly 0.9 means cache discipline is already good
  and habit changes will buy little. Below roughly 0.7 on long sessions
  means something is busting the prefix: look for config edits mid-session,
  model switches, or long idle gaps past the cache TTL.
- Rewrite ratio per session. High values isolate which sessions did the
  busting, so the cause can be found rather than guessed.
- Output share. High means verbosity is the dominant cost, so terser
  narration and capped subagent reports matter more than context size.

Name the single highest-value action the numbers support, and say what would
have to change for that to stop being the right answer. Where a number is
absent, say NO DATA and why; never fill a gap with a plausible figure.

Load the `save-claude-tokens` skill for the playbook behind whichever lever
the numbers point at.
