# The gates, and the one that stops a release

## The release gate, which is live right now

**No version tag, no release, no plugin publish, and no local plugin update or
MCP client registration** until the `claude-md-diet-v2` experiment reaches
VERIFIED or an honest NOT_PROVEN.

- Expected verdict near **2026-09-13**.
- **Building is authorised. Releasing is not.** This was an explicit founder
  amendment after the original gate would have blocked all work for a month.
- The experiment runs untouched. Do not close it early, do not shorten its
  window, do not "help" it.

Current ledger state, for orientation:

```
claude-md-diet      1 runs  0 VERIFIED  1 NOT_PROVEN
shrink-claude-md    1 runs  0 VERIFIED  1 NOT_PROVEN
```

A NOT_PROVEN verdict is the product working, not a failure. It means a change
could not be proven under the guards, and saying so is the whole point.

## Gates on every change

- **Branch plus pull request, never a direct commit to `main`.**
- Before any push, over the **whole pushed range**, fail closed: secret scan,
  em and en dash scan, attribution scan. Any hit stops the push. Commands in
  `03`.
- **No AI vendor attribution anywhere.** No `Co-Authored-By` trailer naming any
  model, no generated-with footer, in commits, pull requests, docs or code.
  Sole credited author: Khalil Maaouni. This overrides any default behaviour
  that would add one.
- **No em dashes or en dashes anywhere.** A test needle that must contain one
  builds it from the codepoint, never the literal byte in source.
- **Python 3.11 floor.** `scripts/check_py311.py` must pass; CI runs it first.
- **Every fix ships with a test calibrated by reinjecting the defect (red)
  before the fix (green).** A test born green proves nothing.
- **Nothing is "done" without the verifying command run after the last edit and
  its output quoted.**

## Gates enforced by a file, rather than by memory

These are the ones that will actually stop you, and they are all in
`scripts/test_architecture.py`:

| Check | Refuses |
|---|---|
| `test_every_module_has_a_declared_layer` | A new module with no layer in `LAYERS`. Placement is decided at creation, when it is cheap |
| `test_no_new_upward_import` | Any import pointing at a higher layer. `KNOWN_UPWARD` is currently **empty** and should stay that way |
| `test_the_frozen_list_holds_nothing_that_was_already_fixed` | A stale entry in `KNOWN_UPWARD`, so the list cannot outlive its violations |
| `test_the_import_cycles_are_the_ones_the_frozen_list_explains` | Any import cycle. There are currently **none** |
| `test_the_computing_layers_do_not_render` | Markup in a string literal at layer 0 or 1. Direction alone cannot catch a metric and its rendering sharing a file |
| `test_every_silent_handler_states_why_it_is_silent` | A handler that swallows an error with no stated reason, and a reason that is a stub |

An empty `KNOWN_UPWARD` is the state that check was built to reach. It is not
a reason to delete the check.

## The silent-handler convention

41 handlers in `scripts/` catch an error and then only `pass`, `continue` or
`return None`. Nearly all are correct: a ledger line that will not parse is
skipped so one corrupt line cannot hide every other record. Each carries an
inline `# sbe: allow-silent <reason>` written after reading its own site.

The distinction that decides whether a swallow is acceptable:

> Swallowing an error about **somebody else's bad data** is the design.
> Swallowing an error about **our own promise not being kept** is not.

That is how the `chmod` cluster was found: calls delivering a documented
`0600` file and `0700` directory posture were silently discarding failures, so
on a network mount the file kept the umask default while the docstring above it
went on asserting otherwise.

## Spend discipline

There is a hook-enforced brake at **800,000 output tokens per session**, with a
**500,000 soft stop**. The brake is not to be bypassed.

Measure spend **before each dispatch wave**, not once per session. A session
that measures once measures too late: one previous session overran by 8 percent
and noticed only afterwards, and the cost was a full review round the next
session had to run. The command is a short sum of `output_tokens` over the
session transcript plus its subagents directory.

Subagents count toward the ceiling and were 74 percent of the output tokens in
the incident that produced this rule.
