# Maintenance: keeping the savings from drifting back

Token savings are not a one-time cleanup. The always-loaded context creeps back
up as you install plugins, grow CLAUDE.md, and add hooks. This is the cadence
that keeps it down, split into what a machine checks and what a human decides.

## Monthly, five minutes

Run the audit and the linter. Both read; neither deletes.

```bash
python3 <plugin>/scripts/measure_tokens.py --days 30           # the number that matters
python3 <plugin>/scripts/context_lint.py                       # where the startup rent went
claude plugin list                                             # what is installed
claude mcp list                                                # servers; "Needs authentication" means never used
```

Read them in this order:

1. **First request median and share** from the audit. If the share is high, the
   always-loaded set is the dominant cost and pruning it beats every other
   lever. This is the number to drive down.
2. **`context_lint` findings.** It flags a CLAUDE.md over the 200 line target,
   duplicated rules, procedures that belong in a skill, rules that could be
   path-scoped, and, for an auto-memory index, exactly which lines fall past the
   documented load limit unread. It exits 0 by default so it never breaks a
   shell chain; `--strict` exits nonzero on a finding for CI.
3. **Plugin and MCP lists.** Anything with zero recent use and no planned use is
   a candidate to disable.

## What the machine decides versus what you decide

- **Automated (safe, reversible, no judgment):** running the audit, running the
  linter, appending to the ledger via the SessionEnd hook, rendering the
  dashboard. None of these change your configuration. They only report.
- **Manual (a judgment call, always reversible):** disabling a plugin
  (`claude plugin disable <name>`, re-enable with `enable`), removing an MCP
  server (back up `~/.claude.json` first), dieting CLAUDE.md, quieting a hook.
  These change what loads, so a human makes the call and records it. For a
  named bundle of plugins, `python3 scripts/cli.py prune propose <id> ... --bundle-id <id>`
  then `prune apply <id>` is the reviewed, guided-apply way to do the same
  disable by hand: it shows the exact commands (and their revert) before you
  say yes, refuses while any experiment is open, and auto-opens one to prove
  the result. It does not replace the manual path above, which stays valid.

The linter never deletes and the audit never changes config on purpose. A
cleanup tool that decided on its own what a rule was worth would eventually
delete something load-bearing. The tools surface evidence; you act on it.

## The promotion and demotion rule for CLAUDE.md

CLAUDE.md is read in full on every session, so every line there pays rent. Keep
it honest with a two-way rule:

- **Promote** a lesson into an always-loaded rule only after the same waste has
  happened twice, the lesson is stable, and it fits in one terse line. A rule
  that pays rent on every call has to be worth more than that rent.
- **Demote** a rule that applies to one subtree (move it to `.claude/rules/`
  with `paths:` frontmatter, so it loads only when a matching file is read), or
  that a linter or hook could enforce, or whose explanation is longer than the
  rule. `context_lint` flags these candidates; you decide.

## When to prune, measured not guessed

Do not prune by plugin count. Prune by measured first-request cost. The audit
tells you the floor before and after a change; the linter tells you where the
floor is coming from. Change one thing, re-measure the same window, keep the
change only if the number moved and quality held. That loop, run monthly, is the
whole of maintenance.

## Verifying a cleanup actually saved

After any prune or diet:

1. Take a fresh baseline (`--baseline`), because a config change that alters the
   always-loaded set may shift the metric; compare only within one schema.
2. Run a few normal sessions so the new floor is represented.
3. Compare the same window against the baseline. The script prints the delta and
   refuses a misleading comparison across mismatched windows or schema versions.
4. If the first-request median dropped and your work still lands first time, the
   cleanup was real. If rework went up, revert it: a token drop paid for in
   rework is not a saving.
