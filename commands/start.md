---
name: start
description: One-time onboarding audit for Token Shield. Measures your usage, shows the single best next move, and offers opt-in extras, never editing a file without your explicit yes. Triggers include start, onboard, get started, set up token shield.
---

Run the onboarding audit. This command never edits `settings.json` or `CLAUDE.md` on its own, at any step; every offer below is opt in and needs the user's explicit yes before anything is written.

Steps:

1. **Measure.** Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/profile.py` and read back its 5-line summary plainly: sessions in the window, the first-request floor and its share of everything read, the cache hit ratio median, the share of sessions that switched model mid-flight, and what was skipped while reading. Every number is measured from local transcript counters; say so.

2. **Advise.** Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/advisor.py` and present only the single best card (skip alternatives here, this is onboarding not a full advisor run): what it changes, why it was selected, expected benefit, evidence label, drawback, and reversibility. If the result is "do nothing," say that plainly as a good outcome.

3. **Offer, do not default.** Present each of these as an explicit choice the user answers; take none of them without a clear yes:

   - **Wire the SessionEnd telemetry hook**, so usage accumulates automatically between sessions without paying a model to measure it. If the user says yes, hand them this exact snippet to add to `~/.claude/settings.json` yourself (or add it only after they confirm you should edit that file directly):

     ```json
     {
       "hooks": {
         "SessionEnd": [
           {
             "hooks": [
               {
                 "type": "command",
                 "command": "python3 \"$HOME/.claude/plugins/<install-path>/scripts/session_end_telemetry.py\"",
                 "timeout": 30
               }
             ]
           }
         ]
       }
     }
     ```

     State plainly that this is reversible: delete that `SessionEnd` block from `settings.json` and the hook stops running, with nothing else to undo. It writes no conversation text, file contents, or prompts, only counters, a model count, and the transcript's basename, and it exits 0 even on failure so it can never break a session.

   - **Start a first experiment**, the only honest way to earn a VERIFIED number instead of an estimate. If yes, point them at `/token-shield:stats` for where they stand now, then `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/experiment.py start "<label>"` to pin the baseline before they make one change.

   - **Open the dashboard**, the visual view of the same measured numbers. If yes, run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/cli.py dashboard` and tell them the path it printed.

4. **Close by naming where everything lives.** State plainly:

   - `~/.token-shield/profile.json` (the profile snapshot from step 1)
   - `~/.token-shield/treatments.json` (advisor decisions, once any are recorded)
   - `~/.claude/token-shield/savings.jsonl` (the experiment ledger, once one is started)
   - `~/.claude/settings.json`, one optional `SessionEnd` line, only if they said yes in step 3

   And how to remove all of it with no trace: `claude plugin uninstall token-shield` followed by `python3 ~/.claude/plugins/cache/token-shield/*/scripts/cli.py uninstall` (README, "Uninstall, no trace"). The uninstall script prints what exists before removing anything and asks per item.
