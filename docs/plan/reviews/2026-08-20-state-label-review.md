# T2.4 adversarial review: can the four states be confused with the five confidence labels?

Read-only review, run 2026-08-19 00:55 JST against the merged T2.1, T2.2 and
T2.3 work. Brief: try to CONFUSE the two axes in wording, colour, or adjacency
on the rendered fixtures, and report rather than fix.

**CRITICAL FINDINGS: 1. MAJOR FINDINGS: 1. MINOR FINDINGS: 1.**

The verdict line is not zero, so per the task's own done-check every finding
below carries a task id and those tasks are scheduled before window close.

## The two axes, for a reader who has not held both in mind at once

- **States** (four, plus a NO DATA case when nothing can be determined) answer
  "what should I do right now". Exactly one ever renders: HEALTHY,
  OPPORTUNITY, PROVING, VERIFIED.
- **Confidence labels** (five) answer "how much should I trust this number":
  VERIFIED, MEASURED, ESTIMATED, NATIVE, RECOMMENDED.

They share the word VERIFIED and nothing else. That overlap was already known
and already guarded. What follows is what the guard does not cover.

## How the colours actually resolve

Read from `scripts/token_shield.py`, both themes, 2026-08-19:

| Variable | Light | Dark | Used by STATE | Used by LABEL |
|---|---|---|---|---|
| `--good` | `#0f7a4e` | `#5ad19a` | HEALTHY | VERIFIED (`.cpill.ver`) |
| `--accent` | `#6a5ad0` | `#8b7be8` | VERIFIED | NATIVE (`.cpill.nat`) |
| `--warn` | `#8a6508` | `#ffcf5c` | OPPORTUNITY | ESTIMATED (`.cpill.est`) |
| `--shield` | `#e2542a` | `#ff6a3d` | PROVING | none |
| `--muted` | `#6b6284` | `#a99fc0` | NO DATA | none |

Three of the five state colours are shared with a confidence label. The
existing guard catches none of those three, because it compares a different
pair.

## CRITICAL 1: the VERIFIED state wears the NATIVE label's colour

`.cc-band.cc-verified .cc-state` and `.cpill.nat` both resolve to `#6a5ad0`
light, `#8b7be8` dark.

**Why this is the worst pairing in the product.** The NATIVE label exists for
exactly one reason, stated as an invariant in `CLAIMS.md` and in the project
instructions: Anthropic's own caching is attributed, never claimed, and never
shown as a Token Shield saving. The VERIFIED state means the opposite: a closed
experiment on this machine proved that Token Shield's own change worked.

A user who has learned "purple means this came from Anthropic, not from the
tool" and then sees a purple VERIFIED banner has been taught, by the product's
own colour language, to read a proven Token Shield result as a native platform
one. The confusion runs in the direction that UNDERSTATES the product, which is
why nobody would notice it in a demo, and it corrupts the one distinction the
labelling system was built to protect.

**Repro.** Render any fixture whose state is VERIFIED beside any panel carrying
a NATIVE pill. Sample the two foregrounds. They are the same value.

**Task:** T2.6, give the VERIFIED state its own colour, distinct from all five
label colours. Scheduled before window close.

## MAJOR 1: the HEALTHY state wears the VERIFIED label's colour

`.cc-band.cc-healthy .cc-state` and `.cpill.ver` both resolve to `#0f7a4e`
light, `#5ad19a` dark.

**Why it matters.** These are the two most flattering readings in the product
and they merge into one green. "Your setup is fine" and "this number is proven"
are different claims with different evidence behind them: HEALTHY is a state
the advisor can return with no experiment on record at all, while the VERIFIED
label requires a closed experiment. A green that means both lets an unproven
healthy verdict borrow the authority of proof.

This is also the collision the existing guard comes closest to catching and
misses. `test_tools.py` asserts that the VERIFIED STATE colour differs from the
VERIFIED PILL colour. Both of those are true and the test passes. It says
nothing about the HEALTHY state, which is where the green actually collides.

**Task:** T2.6, same change.

## MINOR 1: the OPPORTUNITY state wears the ESTIMATED label's colour

Both resolve to `#8a6508` light, `#ffcf5c` dark.

Reported for completeness and ranked minor on purpose: unlike the two above,
this collision is semantically COHERENT. An opportunity is unproven and an
estimate is unproven, so a reader who conflates them arrives at roughly the
right posture. Changing it is optional and may cost more in palette churn than
it returns.

**Task:** T2.6 may leave this one alone; if it does, the decision is recorded
rather than left as an oversight.

## The finding behind the findings, which is the part worth keeping

The guard that exists proves the narrowest true thing in its area. It compares
one pair out of four, passes, and reads as "state and label colours are kept
apart" when what it actually establishes is "these two specific swatches
differ".

This is the vault's `a-test-that-passes-for-the-wrong-reason` class. The
structural fix is not another hand-picked pair: it is one assertion that no
state colour equals ANY label colour, which fails closed as either palette
grows.

**Task:** T2.7, replace the single-pair assertion with a cross-product
assertion over every state colour against every label colour, calibrated red by
reinjecting today's collision before the palette change lands.

## What I could not confuse, recorded so the review is not read as uniformly negative

- **Wording.** `render_command_center` prints the state with a clarifier naming
  it a state; the string "steady state" is asserted by an existing test. The
  bare state word never appears alone, so no state can be read as a fresh proof
  claim on wording alone.
- **Adjacency.** The four-state header renders ABOVE the confidence-label key,
  deliberately and with a comment saying why. The order is right: the state
  answers "what do I do", the key answers "what do these words mean".
- **Arity.** No fixture renders two states at once. The total priority order
  from T2.0 holds on every fixture examined.
- **PROVING and NO DATA.** Both use colours no label uses. Neither can be
  confused with a confidence claim.

## Scope and limits

- Read-only. No file under `scripts/` was modified by this review.
- Colour values were read from the stylesheet, not sampled from a rendered
  screenshot in a browser. A theme override or a user stylesheet could change
  what actually reaches a screen; this review asserts what the product ships.
- Contrast and colour-blind legibility were NOT assessed. Two colours that
  differ by hex can still be indistinguishable to a deuteranopic reader, and
  nothing here tested that. UNVERIFIED, named rather than assumed.
