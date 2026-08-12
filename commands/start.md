---
name: start
description: One-time onboarding journey for Token Shield. Measures your usage silently, shows one hero issue and one best first action, guides it step by step, then offers opt-in extras, never editing a file without your explicit yes. Triggers include start, onboard, get started, set up token shield.
---

Run the onboarding journey. This command never edits `settings.json` or `CLAUDE.md` on its own, at any step; every offer below is opt in and needs the user's explicit yes, asked through the question UI, before anything is written.

Steps:

1. **Discover, silently.** Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/profile.py`. Ask nothing yet; this is measurement only.

2. **Where your tokens go, in three numbers.** Read the profile back as exactly three plain numbers, each with a one-phrase meaning, never an encyclopedia of every field:

   - the startup floor and its share ("X tokens before any work happens, Y% of everything a session reads")
   - the cache hit ratio median ("Z% of reads are served from cache")
   - the model-switch share ("W% of sessions ran more than one model")

   Then run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/advisor.py` and name ONE hero issue in one sentence (the best card's title and why it fired) and ONE best first action (what it changes, in one line). Skip alternatives and full disclosure here; this is onboarding, not a full advisor run. If the result is "do nothing," say that plainly as a good outcome and skip to step 6.

3. **Acknowledge what is already installed.** Read `${CLAUDE_PLUGIN_ROOT}/data/companions.json` for its companion ids (ponytail, caveman, token-saver) and check, best-effort, whether each is already active (its plugin cache directory exists; no crawling, no deep search). Name what you found before recommending anything else, for example: "I found ponytail active; I will account for it before recommending anything else." If nothing is detected, say so in one line and move on.

4. **Ask the first-action decision** through the client's native question UI (AskUserQuestion in Claude Code; a client without that UI falls back to one numbered list). Offer exactly these three options:

   - "Do it now, guided (Recommended)"
   - "Explain more"
   - "Skip for now"

   "Do it now, guided" walks the card's `how` steps one at a time exactly as `/token-shield:advisor` does: run safe read-only steps yourself and show the result, hand any file-editing step as an exact snippet behind its own yes/no question, then record the decision with `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/cli.py advise --decide <strategy-id> done`. "Explain more" shows the full disclosure fields (what it changes, why selected, expected benefit, evidence label, drawback, quality risk, reversibility, how measured, if you say no, source) and then re-asks the same three-option question. "Skip for now" moves straight to step 5 without recording a decision.

5. **Offer the three opt-ins, one choice window each.** Ask each of these as its own separate yes/no question; take none of them without a clear yes.

   - **Wire the SessionEnd telemetry hook**, so usage accumulates automatically between sessions without paying a model to measure it. If yes, ask separately whether you should edit `~/.claude/settings.json` directly; if they say yes to that too, add the snippet yourself, otherwise hand it to them to add:

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

6. **Close with the promise.** State plainly what runs by itself and when to come back:

   - Monthly, the dashboard re-renders itself and `/token-shield:monthly` compares it to the prior month.
   - Run `/token-shield:advisor` again after any config change; it always re-measures before it recommends.
   - "Nothing to do" is always reported as good news here, never as a non-answer.

   Then name where everything lives:

   - `~/.token-shield/profile.json` (the profile snapshot from step 1)
   - `~/.token-shield/treatments.json` (advisor decisions, once any are recorded)
   - `~/.claude/token-shield/savings.jsonl` (the experiment ledger, once one is started)
   - `~/.claude/settings.json`, one optional `SessionEnd` line, only if they said yes in step 5

   And how to remove all of it with no trace: `claude plugin uninstall token-shield` followed by `python3 ~/.claude/plugins/cache/token-shield/*/scripts/cli.py uninstall` (README, "Uninstall, no trace"). The uninstall script prints what exists before removing anything and asks per item.
