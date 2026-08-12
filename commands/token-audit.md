---
name: token-audit
description: Measure real token usage from session transcripts, show waste signals, and compare against a saved baseline.
---

Run the measurement script that ships with this plugin. It reads the `usage`
counters the API returned on every assistant message in the local session
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
   The comparison window must match the baseline's window, or the delta
   measures which sessions fell inside each window rather than any change the
   user made. The script warns when they differ; do not talk past that warning.

Then read the numbers back in plain language, in this order:

- First request median and share. The first request is the startup floor:
  everything loaded before any work happens, plus the opening message. The
  share is how much of the session's total reading that floor accounts for,
  paid again on every call. A high share means pruning the always-loaded set
  is the highest-value action available, ahead of every other lever.
- Cache hit ratio. Above roughly 0.9 means cache discipline is already good
  and habit changes will buy little. Below roughly 0.7 on long sessions means
  something is rebuilding the prefix.
- Cache writes split by TTL. 5 minute writes bill at 1.25x base input and
  1 hour writes at 2x, so a session heavy in 1 hour writes is paying more per
  rebuild. Which TTL applies is set by how the user authenticates, not by a
  preference: a Claude subscription requests 1 hour automatically, an API key
  stays at 5 minutes, and subagents use 5 minutes either way.
- Rewrite ratio and model count per session. A high rewrite ratio is a signal
  to investigate, not proof of anything: ordinary conversation growth writes
  cache too. The model count is the measured cause when it is above 1, since
  each model has its own cache and a switch rebuilds from zero.
- Subagent share of output. Subagents keep exploration out of the parent
  context, which is worth paying for, but a high share alongside many small
  dispatches usually means work went to an agent that a deterministic script
  should have done.

Name the single highest-value action the numbers support, and say what would
have to change for that to stop being the right answer. Where a number is
absent, say NO DATA and why; never fill a gap with a plausible figure. Never
present a ratio as a share of money: this script deliberately carries no model
price table, so it reports relative input units, not dollars.

Load the `token-shield` skill for the playbook behind whichever lever
the numbers point at.
