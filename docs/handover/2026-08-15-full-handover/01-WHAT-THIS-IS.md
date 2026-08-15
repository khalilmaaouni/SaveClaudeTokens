# What this is, and the rules that make it what it is

## The product

A Claude Code plugin that reads the local session transcripts under
`~/.claude/projects`, tells a user where their tokens went, ranks what they
could cut, and lets them **prove** whether a change actually worked.

The repository doubles as its own plugin marketplace. Install:

```
claude plugin marketplace add khalilmaaouni/token-shield
claude plugin install token-shield@token-shield
```

## North star

> The only Claude Code token tool that proves its own numbers: one command a
> non-technical person can read, and a deployment a company can push to a
> thousand machines.

Every backlog item names which half it serves. An item that cannot name one
goes to a parking lot rather than the backlog.

## The confidence labels, which are the whole product

These never merge, never sum across each other, and never appear without their
qualifier:

| Label | Means |
|---|---|
| **VERIFIED** | A closed experiment proved it on this machine |
| **MEASURED** | Counted here, right now, from real transcripts |
| **ESTIMATED** | A projection built from MEASURED numbers |
| **NATIVE** | Anthropic's own behaviour, notably prompt caching. Attributed, never claimed, and never shown in dollars on the dashboard |
| **RECOMMENDED** | A rank. Never evidence |

**NO DATA beats a guess, always.** A fabricated zero claims something was
measured when it was not, and that is the failure this whole design refuses.

## The defect family this project keeps fighting

Nearly every real bug found here has one shape: **two surfaces onto one number,
drifting apart with nothing able to notice.** Concrete instances, all now
fixed:

- The trial printed `ESTIMATED 218.3M` and the command it recommends printed
  `OPPORTUNITY 230M`, one minute apart on the same machine, because one took
  the largest lever and the other summed overlapping ones.
- `cli prices` was fixed to lead with "this is not money you saved" while
  `pricing.py`'s own entry point kept a six-figure total with the caveat five
  lines below it.
- A regression, a HISTORICAL caveat and a NO DATA placeholder all rendered in
  the same success green, because the only CSS rule matching the hero
  hardcoded the good colour.
- The organisation dashboard withheld any figure standing on fewer than five
  machines while publishing the org-wide total beside it, so one subtraction
  returned a single person's token total to within 2.3 percent.
- The proof ledger printed an unproven delta in the column a reader takes as
  the proven result.

The architecture work in this repository exists to make that family harder,
which is why the layer rules are enforced by tests rather than documented.

## Invariants that never merge

- Savings report **per label**; the latest record per label wins; regressions
  show negative; **no cross-label totals anywhere**.
- The plugin registers **zero hooks by default**. Everything is opt-in.
- The command surface is capped at **6 command files**.
- No dollar figure on the dashboard.
- **No AI vendor attribution anywhere**: no `Co-Authored-By` trailer naming any
  model, no generated-with footer, in commits, pull requests, docs or code.
  Sole credited author: Khalil Maaouni.
- **No em dashes or en dashes anywhere.** A test needle that must contain one
  builds it from the codepoint, never the literal byte in source.
