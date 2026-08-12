# PROJECT.md: SaveClaudeTokens

- Canonical path: ~/SaveClaudeTokens
- Repo remote: https://github.com/khalilmaaouni/SaveClaudeTokens (public, distribution target)
- What it is: a Claude Code plugin (one skill, save-claude-tokens) that encodes the token economy playbook. The repo doubles as its own plugin marketplace.
- Progress page: GANTT.html in this repo; published artifact URL recorded below after first publish.
- Published artifact URL: (filled at first publish)
- Local install: claude plugin marketplace add khalilmaaouni/SaveClaudeTokens; claude plugin install save-claude-tokens@saveclaudetokens
- Commands that matter:
  - Validate structure: claude plugin details save-claude-tokens
  - Dash scan (must return nothing): grep -rnP '[\x{2013}\x{2014}]' ~/SaveClaudeTokens
  - Attribution scan: run the standard gate scan from the github-desktop-push skill; it must return nothing
- Vault space: none yet; proposed to the founder, general session logs carry it meanwhile.
- The machine-local rules this plugin generalizes live in ~/.claude/CLAUDE.md under "SaveClaudeTokens: token economy v2".
