# The Token Shield Waste Score (waste-score/1)

## What this number means

The Waste Score is one number from 0 to 100 that says how much measurable
waste a machine's Claude Code usage carries. 100 means no measurable waste
by the five things this score checks. The score is built to be compared
between two different machines: that comparability is the entire reason it
exists, so the formula below is fixed, published, and versioned before any
score is ever shown to anyone.

The version string for this formula is `waste-score/1`. It is printed with
every score the scorer produces, on purpose: if the formula ever changes,
the version string changes too, so a later number can never be silently
compared against an older one.

## The formula, in plain language

Start at 100. For each of five problem areas, look at one number already
measured on the machine, and subtract a penalty based on how bad that
number is. The five penalties are subtracted from 100 to get the final
score. Nothing else is added or subtracted.

```
Score = 100 - (penalty 1 + penalty 2 + penalty 3 + penalty 4 + penalty 5)
```

Each penalty grows in a straight line between two anchor points: a
"no penalty" anchor (this is fine, subtract nothing) and a "full penalty"
anchor (this is as bad as this component gets, subtract the whole weight).
Between those two points, the penalty is a straight-line (linear)
interpolation: half of the way between the two anchors gives half of the
weight as a penalty, a quarter of the way gives a quarter, and so on. Past
either anchor, the penalty stays flat at 0 or at the full weight; it never
goes negative and it never exceeds the component's weight.

## The five components

Each row reads one existing metric out of the profile that
`scripts/profile.py` already builds (the same JSON `usage` / `behavior` /
`instruction` / `pressure` sections the dashboard and the CLI already read).
The scorer never invents a new metric; it only weighs metrics that already
exist.

| # | Problem area | Metric it reads | Weight | No-penalty anchor | Full-penalty anchor |
|---|---|---|---|---|---|
| 1 | Cache health | `usage.cache_hit_ratio_median` (r) | 30 | r is 0.90 or higher | r is 0.50 or lower |
| 2 | Startup rent | `instruction.startup_floor_share` (s) | 25 | s is 0.15 or lower | s is 0.45 or higher |
| 3 | Cache health (model switching) | `behavior.model_switch_session_share` (m) | 20 | m is 0.05 or lower | m is 0.35 or higher |
| 4 | Tool output pressure | `pressure.structured_input_share` (t) | 15 | t is 0.30 or lower | t is 0.70 or higher |
| 5 | Verbosity | `pressure.output_verbosity` median output tokens (v) | 10 | v is 400 or lower | v is 1200 or higher |

The weights add up to 100, which is why a machine that is at or past every
full-penalty anchor scores 0.0, and a machine that is at or better than
every no-penalty anchor scores 100.0.

### Component 1: cache health (hit ratio)

| Cache hit ratio median (r) | Penalty |
|---|---|
| 0.90 or higher | 0 |
| 0.70 (midpoint) | 15 |
| 0.50 or lower | 30 (full) |

Lower cache hit ratio is worse, so this component runs backward from the
other four: the "good" anchor (0.90) is a bigger number than the "bad"
anchor (0.50). The straight-line rule still applies the same way.

### Component 2: startup rent (startup floor share)

| Startup floor share (s) | Penalty |
|---|---|
| 0.15 or lower | 0 |
| 0.30 (midpoint) | 12.5 |
| 0.45 or higher | 25 (full) |

### Component 3: cache health (model switching)

| Model switch session share (m) | Penalty |
|---|---|
| 0.05 or lower | 0 |
| 0.20 (midpoint) | 10 |
| 0.35 or higher | 20 (full) |

### Component 4: tool output pressure (structured input share)

| Structured input share (t) | Penalty |
|---|---|
| 0.30 or lower | 0 |
| 0.50 (midpoint) | 7.5 |
| 0.70 or higher | 15 (full) |

### Component 5: verbosity (median output tokens per assistant message)

| Output verbosity, median tokens (v) | Penalty |
|---|---|
| 400 or lower | 0 |
| 800 (midpoint) | 5 |
| 1200 or higher | 10 (full) |

## Rounding

Every penalty and the running sum are kept as exact floating point numbers
all the way through. Only the final score is rounded, once, to one decimal
place, and it is rounded half up (0.05 rounds to 0.1, never down to 0.0).
Nothing in between is rounded.

## Bands

| Score range | Band |
|---|---|
| 90 to 100 | LEAN |
| 70 to 89.9 | OK |
| 50 to 69.9 | WASTEFUL |
| below 50 | HEAVY WASTE |

## The all-or-nothing rule, and why it exists

The score is computed only when all five inputs carry the confidence label
MEASURED (see `scripts/profile.py`'s CONFIDENCE LABELS section: MEASURED,
SIGNAL, INFERRED, or NO DATA). If even one of the five inputs is NO DATA,
is missing entirely from the profile, or carries any label other than
MEASURED, the result is NO DATA for the whole score, and the result names
every input that failed and why.

Nothing is ever substituted for a missing input. No zero is filled in for a
missing metric, no partial score is computed over the four inputs that did
happen to be MEASURED, and nothing is guessed. The reason is comparability
itself: a score computed over a varying subset of components is not
comparable between machines, because a good subset score and a bad
five-component score could look identical on the dashboard while meaning
opposite things. A published, comparable number has to be computed the same
way every time it exists, or it is not a fixed measurement at all, and the
honest answer when one of the five underlying metrics is not there is NO
DATA, not a guess dressed up as a number.

## Worked example

Suppose a machine's profile carries these five MEASURED values:

- Cache hit ratio median, r = 0.75
- Startup floor share, s = 0.25
- Model switch session share, m = 0.15
- Structured input share, t = 0.55
- Output verbosity median, v = 650 tokens

Penalty 1 (cache health, weight 30): r = 0.75 sits between the 0.90
no-penalty anchor and the 0.50 full-penalty anchor. Fraction of the way from
good to bad: (0.75 - 0.90) / (0.50 - 0.90) = -0.15 / -0.40 = 0.375.
Penalty = 30 x 0.375 = 11.25.

Penalty 2 (startup rent, weight 25): fraction = (0.25 - 0.15) / (0.45 -
0.15) = 0.10 / 0.30 = 0.3333. Penalty = 25 x 0.3333 = 8.3333.

Penalty 3 (cache health, model switching, weight 20): fraction = (0.15 -
0.05) / (0.35 - 0.05) = 0.10 / 0.30 = 0.3333. Penalty = 20 x 0.3333 =
6.6667.

Penalty 4 (tool output pressure, weight 15): fraction = (0.55 - 0.30) /
(0.70 - 0.30) = 0.25 / 0.40 = 0.625. Penalty = 15 x 0.625 = 9.375.

Penalty 5 (verbosity, weight 10): fraction = (650 - 400) / (1200 - 400) =
250 / 800 = 0.3125. Penalty = 10 x 0.3125 = 3.125.

Sum of penalties = 11.25 + 8.3333 + 6.6667 + 9.375 + 3.125 = 38.75.

Score = 100 - 38.75 = 61.25, rounded half up to one decimal = 61.3.

61.3 falls between 50 and 69.9, so this machine's band is WASTEFUL.

## Honest note: the anchors are a published convention, not a measured optimum

The eight anchor numbers in the five tables above (0.90, 0.50, 0.15, 0.45,
0.05, 0.35, 0.30, 0.70, 400, 1200) were not derived by studying a corpus of
many machines and finding the natural break points between wasteful and
lean usage. No such corpus exists yet. They are a published convention:
round, readable numbers chosen to bracket one real machine's own baseline
so version 1 of the score has somewhere honest to start.

The one piece of real evidence behind them is this repository's own
schema 2 measurement, taken on 2026-08-12 over 229 sessions across 90 days:
cache hit ratio median 0.865, and first-request share median 0.360. Those
two measured numbers sit inside the "some penalty but not the worst"
stretch of components 1 and 2, which is exactly where a normal, not
especially wasteful machine should land. The other three anchors (model
switching, structured input share, output verbosity) do not yet have an
equivalent published baseline behind them; they were rounded to the same
kind of readable numbers by the same convention, not measured the same way.

### The flip condition

When a corpus of many machines' profiles exists, the anchors get re-derived
from that corpus instead of from one machine's convention, and the formula
version increments (`waste-score/2`, and so on). Every score computed under
an earlier formula version is marked HISTORICAL when a newer version
exists, and it is never directly compared against a score computed under
the newer version. Comparing scores across formula versions would silently
compare two different rulers as if they were one, which defeats the entire
purpose of publishing the formula before rendering the score.
