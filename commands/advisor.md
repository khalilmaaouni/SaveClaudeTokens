---
name: advisor
description: Run the deterministic Quick Advisor, walk the single best next move through guided steps, and record the decision. Triggers include advisor, what should I do, next best move, quick advisor.
---

Run the Quick Advisor and guide the user through its best card, one plain-language step at a time. Never apply any change on your own; every file edit needs the user's explicit yes in this conversation, asked through the question UI, not assumed from an earlier answer.

Steps:

1. Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/profile.py` to refresh the profile snapshot.

2. Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/advisor.py` to rank cards against that profile. Both this and step 1 are deterministic: state plainly, "Advisor cost: 0 tokens (deterministic)."

3. Present ONE card only, in plain words, in 8 lines or fewer:

   - If it is a "do nothing" result, say so as good news: nothing crossed a trigger threshold, quote the two strongest metrics the advisor named, close with the routine line in step 7, and stop there. Do-nothing is a valid, celebrated answer, not a non-answer.
   - Otherwise, name only: the problem, with its measured number (the "why selected" line); what the treatment changes (one sentence from "what it changes"); the expected benefit and its evidence label; the one-line drawback. Do not dump the full disclosure fields or the rest of the queue here; that is what "Explain more first" is for.

4. Ask the decision through the client's native question UI (AskUserQuestion in Claude Code; a client without that UI falls back to one numbered list). Offer exactly these four options, in this order:

   - "Do it now, guided (Recommended)"
   - "Explain more first"
   - "Not now, stay quiet 90 days"
   - "Never recommend this"

5. **Do it now, guided.** Walk the card's `how` steps one at a time, in order:

   - A step with no file-editing command: run it yourself if it is safe and read-only (for example a `profile`, `optimize`, or `experiment` command), and show the result before moving to the next step.
   - A step that edits a file (CLAUDE.md, `settings.json`, a hook, or anything else on disk): never write it silently. Show the exact snippet to add or change, ask a dedicated yes/no question for that one edit, and only write it after a clear yes.

   After the last step, record the decision:

   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/cli.py advise --decide <strategy-id> done`

   Then ask one more choice window: offer to start an experiment across the change (`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/experiment.py start "<label>"`) so the benefit can become a VERIFIED number instead of staying ESTIMATED. If they say yes, tell them the matching `experiment end "<label>"` call closes it out later.

6. **Explain more first.** Show the full disclosure fields for the same card: what it changes, why it was selected, expected benefit, evidence label, drawback, quality risk, reversibility, how it is measured, what happens if the user says no, and its source. Also show up to two alternatives from the queue, each with the same fields. Never trim a disclosure field here; the full disclosure is the point of this branch. Then re-ask the same four-option question window from step 4.

7. **Not now, stay quiet 90 days** or **Never recommend this.** Record the decision and confirm in one quiet line, naming when it resurfaces (or that it will not):

   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/cli.py advise --decide <strategy-id> not-now`  (quiets it for 90 days)
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/cli.py advise --decide <strategy-id> never`  (does not resurface on its own)

8. Close every run, whatever the outcome, with one routine line: "The monthly report compares months by itself; run `/token-shield:advisor` again after any config change."

If `advisor.py` reports `NO DATA on N strategy trigger(s)`, name which metrics were insufficient rather than silently dropping them; that is real information about what the profile could not measure yet.
