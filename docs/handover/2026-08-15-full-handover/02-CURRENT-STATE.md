# Current state, and what changed on 2026-08-15

## The tree

| | |
|---|---|
| `main` | `bafd02a` |
| Branches | one local (`main`), one remote (`origin/main`) |
| Worktrees | one |
| Open pull requests | zero |
| Working tree | clean |

## Verified numbers, all run on merged `main` after the last edit

```
check_py311: clean, 56 file(s) parse as Python 3.11
scripts suite:      525 checks green across 23 suites, exit 0
mcp server:         13 passed
bench self-check:   3 passed
benchmark:          ALL PASS (93 checks)
```

## The shape of the code

`scripts/` holds 28 non-test modules in eight declared layers, plus 23 test
suites. The layer map and the rule it enforces are in `docs/ARCHITECTURE.md`
and, more usefully, in `scripts/test_architecture.py`, which is the half that
can refuse a change.

Structural facts as of now, all computed rather than asserted:

- **No import cycles.** There were four, every one running through
  `token_shield`.
- **No upward imports.** `KNOWN_UPWARD` is empty.
- `cli` is a **leaf**: nothing in the repository imports the command line.
- `token_shield` is 941 lines and renders. It was 1,572 and was simultaneously
  the renderer, a metrics module and a file loader.
- `config.py` (layer 0) owns `ROOT`, `EXPERIMENT_DAYS`, `COMPANIONS_PATH`,
  `load_companions`.
- `formatting.py` (layer 0) owns `esc`, `human`, `pct`.
- `metrics.py` (layer 1) owns 607 lines of what the project computes.

## What landed on 2026-08-15

Six pull requests, each merged only after CI passed on its own head commit, each
branch proven an ancestor of `main` before deletion.

**The review round nobody had run.** Four agent-built units had reached a branch
with zero reviewers, because the previous session crossed its spend ceiling and
its review round was cancelled mid flight. The review found one real defect: the
organisation dashboard withheld any figure standing on fewer than five machines
while publishing the org-wide total beside it, so subtracting one published cell
from another returned a single machine's total token volume to within 2.3
percent (27.3M minus 24.2M against a true 3,030,000). Secondary suppression
landed: whatever is withheld must itself stand on at least the minimum group
size.

**Two enterprise paths that could not work.** `cli.py --version` now exists,
read from the plugin manifest so it cannot drift. `uninstall` no longer calls
`sys.stdin.readline()` with no terminal check, which used to block forever under
a management tool; it refuses and deletes nothing without a terminal, and takes
`--yes` for the deliberate path.

**The architecture layer map**, with the check that enforces it, calibrated
three ways.

**Wave 2, in full.** The proof ledger's four defects: an unproven delta printing
in the column a reader takes as proven (D18); a refusal advising the one action
that writes a permanent unproven verdict (D19); a legacy baseline that could
never be closed, which blocked every guided change on a machine indefinitely
(D8); and a non-numeric guard undone by the next subtraction (D21a). Plus three
weak tests and the trial's first screen: 21 seconds of silence, a share printed
two different ways seven lines apart, transcripts leading over sessions, and the
three honesty labels appearing with no legend anywhere on screen.

**Every silent error handler now states why it is silent**, 41 of them. The
external lint reported 23; an AST walk found 41, because that lint's pattern
matches a single exception name and every `except (OSError, ValueError):` was
invisible to it.

**A permission promise that was silently failing.** The `chmod` calls delivering
`0600`/`0700` on the fleet config and signals outbox discarded their failures,
so on a network mount the file kept the umask default while the docstring above
it asserted otherwise, on files holding an organisation's store URL and its
salt.

**`config.py` extracted**, emptying the frozen list and removing all four import
cycles. **`metrics.py` and `formatting.py` split out of the renderer**, with a
new rule that layers 0 and 1 may not emit markup, because direction alone can
never catch a metric and its rendering sharing a file.

## Machine-local files that do not ship

`STATE.md`, `GANTT.html` and `PROJECT.md` are gitignored working files.
`STATE.md` is the running session record and is the most detailed account of
what happened and why. `GANTT.html` is the progress page, published to a stable
artifact link that is republished at every closed loop.

`.sbe/` is gitignored: decision packages written by an external tool, bound to a
commit and regenerated on demand.
