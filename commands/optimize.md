---
name: optimize
description: Propose a safe, reversible CLAUDE.md diet that cuts the always-loaded startup floor. It keeps every hard rule, backs up before it changes anything, and applies only on your explicit yes. Triggers include optimize claude.md, diet claude.md, shrink startup context, reduce token consumption.
---

Propose a CLAUDE.md diet, show it, and apply it only if the user says yes. Never edit CLAUDE.md silently, and never on install.

Steps:

1. Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/optimize.py`

   It reads the user's CLAUDE.md (default `~/.claude/CLAUDE.md`), estimates its token cost, and writes a PROPOSAL to `~/.token-shield/optimize/` without touching the live file. It moves only long dated history and rationale into a notes file, leaves a pointer, and keeps every section that carries a hard rule (anything mentioning NEVER, ALWAYS, MUST, or a safety, spend, credential, or attribution rule). When in doubt it keeps.

2. Read the output back plainly: the before and after token estimate (labeled ESTIMATED), the sections it proposes to move, and the section-cost map showing where the tokens go. Be honest if the safe automatic cut is small: on a CLAUDE.md that interleaves rules and history, most sections carry a rule and are kept, so the deeper diet is a judgment call the user makes.

3. Show the diff at `~/.token-shield/optimize/diff.txt` so the user sees exactly what would change.

4. Apply ONLY if the user explicitly confirms. On yes, run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/optimize.py --apply`. It backs the original up to a timestamped `.bak` file first, so a revert is one copy. Tell the user the revert command it prints.

5. Remind them: a CLAUDE.md edit does not take effect until the next `/clear`, `/compact`, or restart, and the real saving is proven by running an experiment across that boundary (`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/cli.py experiment start "claude-md-diet"`), not by the estimate.

If the user wants a deeper diet of a section the tool kept (because it holds a rule), help them do it by hand: keep the rule lines, move the history and rationale, and use the same backup and experiment steps.
