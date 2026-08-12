---
name: advisor
description: Run the deterministic Quick Advisor and present the single best next move to cut tokens, with full drawback disclosure. Triggers include advisor, what should I do, next best move, quick advisor.
---

Run the Quick Advisor and present its best card. Never apply any change on your own; every change needs the user's explicit yes in this conversation.

Steps:

1. Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/profile.py` to refresh the profile snapshot.

2. Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/advisor.py` to rank cards against that profile.

3. Present the result plainly:

   - If it is a "do nothing" result, say so as good news: nothing crossed a trigger threshold, quote the two strongest metrics the advisor named, and stop there. Do-nothing is a valid, celebrated answer, not a non-answer.
   - Otherwise present the whole queue (best card plus up to two alternatives), each with every disclosure field the advisor printed: what it changes, why it was selected (the metric and number that triggered it), expected benefit, evidence label, drawback, quality risk, reversibility, how it is measured, what happens if the user says no, and its source. If a companion card also fired, show it too, labeled companion. Never trim a disclosure field to save space; the full disclosure is the point of this command.
   - State plainly: "Advisor cost: 0 tokens (deterministic)."

4. If the user says to accept, reject, or suppress a card, record that decision and only then, never before the user's explicit word:

   `python3 -c "import sys; sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}/scripts'); import advisor; print(advisor.record_decision('<strategy id>', '<accepted|rejected|suppressed>', note='<one line from the user, or empty>'))"`

   Tell the user what was recorded and where (`~/.token-shield/treatments.json`). A rejected or suppressed card is filtered out of future advice for 90 days by default; an accepted one is stamped with a lineage label so a later experiment can cite the card that caused it.

5. If the user accepted a card that changes a file (CLAUDE.md, settings.json, a hook), do not make that change yourself from this command. Point them at `/token-shield:optimize` for a CLAUDE.md diet, or hand them the exact snippet to paste for anything else, and remind them a config edit needs an experiment (`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/experiment.py start "<label>"`) across the boundary to ever become VERIFIED rather than just recorded as accepted.

If `advisor.py` reports `NO DATA on N strategy trigger(s)`, name which metrics were insufficient rather than silently dropping them; that is real information about what the profile could not measure yet.
