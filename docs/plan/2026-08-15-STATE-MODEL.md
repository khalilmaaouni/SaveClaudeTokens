# The four state model, ratified

Task T2.0 of `2026-08-15-LEADERSHIP-WBS.md`. This memo is the keystone of
Window 2: T2.1 implements it in `metrics.py`, T2.2 renders it in
`token_shield.py`, T2.3 prints it in `cli.py`, and T2.4 reviews it against the
five confidence labels. Nothing in E2 may disagree with this file.

The constraint the task set itself, and which this memo keeps: the four states
are defined from EXISTING primitives only. No new store, no new file, no new
threshold. Everything below is computable today from three functions that are
already tested and green on merged main.

## 1. The primitives, read rather than assumed

Each was opened and read on 2026-08-15 before this memo was written. The line
numbers are where they live on `ded1399`.

| Primitive | Where | What it returns |
|---|---|---|
| `advisor.advise(profile, ...)` | `scripts/advisor.py:693` | dict carrying `do_nothing` (bool), `best` (card or None), `insufficient` (list of strategy ids whose trigger could not be evaluated) |
| `experiment.list_open_experiments()` | `scripts/experiment.py:838` | list of raw baseline dicts sorted by start time, `[]` when nothing is open |
| `metrics.verified_by_label(rows, exp_mod)` | `scripts/metrics.py:356` | one row per label, VERIFIED only, each carrying `historical` (bool) and `historical_reason` |

Two properties of these functions decide most of this memo, and neither was
visible from the task description. Both were found by reading the source.

**`list_open_experiments` fails CLOSED.** Its own docstring says so. A baseline
file that cannot be read (permission denied, or truncated mid write by a crash)
does not get skipped. It comes back as a marker dict carrying `_unreadable`
(the file path) and NO `label`, because such a file is indistinguishable from a
genuinely open experiment whose baseline write was interrupted. Any consumer
that treats the returned list as "experiments with labels" will raise a
`KeyError` on that marker or, worse, silently drop it and report nothing open
while an experiment is running.

**`do_nothing` is True in two different worlds.** It means "no strategy crossed
a trigger threshold". That is true when the profile is healthy, and it is
equally true when no trigger could be evaluated at all, because the data to
evaluate it was absent. `advise` reports the difference in `insufficient`, and
`cli.py:1100` already prints `NO DATA on N strategy trigger(s)` from it. The
state model must read that same list or it will report health it never
measured.

## 2. The precondition, which is not a state

Before any state is computed:

> If every strategy trigger is insufficient (`len(insufficient) ==
> len(strategies)`), no state renders. The surface shows NO DATA and names the
> command that produces data.

This is a precondition rather than a fifth state, deliberately. E2's gate is
that the user sees exactly one of four states, and that gate stands: NO DATA is
the absence of a state, not a member of the set, the same way an empty table is
not a row. Adding a fifth state would have been the larger change and it is not
needed.

The reasoning is the project's own ratified invariant, in `CLAUDE.md`: NO DATA
beats a guess, always. HEALTHY computed from zero evaluable triggers is a
guess, and it is the most expensive guess in the product, because it tells a
user with a broken measurement path that they have nothing to fix.

Partial insufficiency (some triggers evaluable, some not) does NOT block a
state. The evaluable ones decide it, and the count of insufficient triggers is
carried in the reason line so the user can see the state rests on partial data.

## 3. The four states

Each is a conjunction of primitive reads. Nothing is recomputed anywhere else:
T2.2 and T2.3 both call the one function T2.1 builds, per the WBS.

**PROVING.** `list_open_experiments()` is non-empty.
Reason line names the label, the day number, and the window length. When the
list holds an `_unreadable` marker, PROVING still renders and the reason names
the FILE PATH instead of a label, saying the baseline could not be read. It
never guesses a label it does not have.

**OPPORTUNITY.** No open experiment, and `do_nothing` is False.
Reason line is the `best` card's own one line summary. `best` is guaranteed
non-None here: `do_nothing` is defined as `best_card is None` at
`advisor.py:751`, so the two can never disagree.

**VERIFIED.** No open experiment, `do_nothing` is True, and at least one row
from `verified_by_label` has `historical` False.
Reason line names the label and its floor reduction. Rows with `historical`
True are excluded and do not contribute, because a HISTORICAL row is evidence
the environment has already invalidated; counting it would let a stale proof
raise the top line state, which is the exact confusion T2.4 exists to catch.

**HEALTHY.** No open experiment, `do_nothing` is True, and no non historical
VERIFIED row exists.
Reason line is `advise`'s own `message` field, which already names the two
strongest metrics. HEALTHY is the floor and always renders when the
precondition passed and nothing above it fired.

## 4. The total priority order, and every pairwise tiebreak

> **PROVING, then OPPORTUNITY, then VERIFIED, then HEALTHY.**

Four states make six pairs. Every one is written down, including the three that
cannot both be true, because "cannot happen" is a claim that should be recorded
and checked rather than assumed.

1. **PROVING wins over OPPORTUNITY.** Stability during a trial outranks a new
   suggestion. Acting on a recommendation mid window is the single reliable way
   to ruin a proof, and the product's whole claim is that it can prove things.
   This is the founder's own working default, kept unchanged.
2. **PROVING wins over VERIFIED.** A running proof is the live thing; a past
   verdict is not. Showing a trophy while a trial needs stability inverts the
   urgency.
3. **PROVING wins over HEALTHY.** HEALTHY is the floor and yields to everything.
4. **OPPORTUNITY wins over VERIFIED.** This one departs from a possible reading
   of the founder's plan, and section 5 argues it in full.
5. **OPPORTUNITY wins over HEALTHY.** They are mutually exclusive by
   construction (`do_nothing` is the negation of `best`), so this pair can never
   fire. Recorded so that a future change to `advise` that breaks the
   exclusivity finds a decision already written rather than an accident.
6. **VERIFIED wins over HEALTHY.** Both require `do_nothing` True. VERIFIED is
   strictly more informative: healthy AND something was proven, versus healthy
   with nothing proven. Same facts, more of them.

The order is total, so exactly one state renders. T2.1's tests assert that
directly rather than testing the branches in isolation.

## 5. The decision this memo takes, and the one it cannot

**Taken: OPPORTUNITY outranks VERIFIED.** The alternative reading of the WBS is
that a fresh verdict is news and news should lead. That reading is right about
users and it is not buildable today, for a reason worth stating precisely.

News is perishable, and perishability is not computable from anything on disk.
To render a verdict as news, the product must know whether the user has already
seen it, and there is no acknowledgement store anywhere in the codebase. A
search over `scripts/` and `data/` for any acknowledgement primitive returns
nothing. Without one, "a verdict landed" is indistinguishable from "a verdict
landed five weeks ago and has been on this screen every day since", so VERIFIED
would become sticky: once a user proves anything, the top line says VERIFIED
forever and never shows them the next thing worth doing. That breaks the loop
the product exists to close.

So VERIFIED is defined here as a STEADY STATE, not as news: healthy, and proven.
Steady states must never hide an actionable recommendation, which is why
OPPORTUNITY outranks it.

**Cannot be taken here: whether to build the acknowledgement store.** It is a
new primitive and a new mutation surface, and T2.0's constraint is existing
primitives only. It is recorded as the missing piece rather than smuggled in.

Flip condition, written now so it is not rediscovered later: if an
acknowledgement store is ever built, tiebreak 4 is revisited FIRST, because an
unacknowledged verdict is genuinely news and would then outrank a standing
recommendation. Nothing else in this memo changes when that happens.

## 6. What T2.1 must implement

`command_center_state()` in `scripts/metrics.py`, a pure layer 1 function. No
markup: layers 0 and 1 may not emit markup, and `test_architecture.py` enforces
it.

Returns `(state, reason)` where state is one of the four names or the string
`NO DATA`, and reason is one line of plain text.

The tests the WBS names by title, plus the four this memo adds:

- `test_state_proving_beats_opportunity`: an open experiment and a firing
  recommendation together render PROVING.
- `test_state_healthy_when_do_nothing`: no experiment, `do_nothing` True, no
  verified rows.
- `test_state_unreadable_baseline_still_proving`: a `_unreadable` marker with no
  `label` key renders PROVING and names the path, without raising.
- `test_state_all_triggers_insufficient_is_no_data`: every trigger insufficient
  renders NO DATA, never HEALTHY.
- `test_state_historical_verified_does_not_beat_healthy`: the only VERIFIED row
  carries `historical` True, so HEALTHY renders.
- `test_state_opportunity_beats_verified`: a firing recommendation and a non
  historical verified row together render OPPORTUNITY.

Every one of them is written red first, by fixture, and calibrated by
reinjecting the defect before the fix goes green. A test born green proves
nothing.

## 7. What this memo does not decide

- Wording, colour and adjacency of the four states against the five confidence
  labels. That is T2.4's adversarial review and it may send work back here.
- The PROVING panel's contents beyond the state and its reason. T2.2 owns the
  "keep this stable" list built from the experiment record's fingerprint fields.
- Whether `cli.py` prints the state before or after its existing NO DATA line.
  T2.3 owns that ordering.
