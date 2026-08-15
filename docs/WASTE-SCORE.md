# The Token Shield Waste Score (waste-score/2)

## What this number means

The Waste Score is one number from 0 to 100 that says how much measurable
waste a machine's Claude Code usage carries. 100 means no measurable waste
by the five things this score checks. The score is built to be compared
between two different machines: that comparability is the entire reason it
exists, so the formula below is fixed, published, and versioned before any
score is ever shown to anyone.

The version string for this formula is `waste-score/2`. It is printed with
every score the scorer produces, on purpose: if the formula ever changes,
the version string changes too, so a later number can never be silently
compared against an older one. Version 1 of this document was published
before any code read it and never rendered a single score anywhere; version
2 replaced it after a hostile review found three ways to raise the number by
spending MORE tokens, not fewer. See "Version history" below for the full
account, and "How this score can be gamed" for what changed and what did
not.

**Machine-checked**: the two tables below (the five components, and the
bands) are parsed directly out of this document by
`scripts/test_profile.py::test_waste_score_doc_tables_match_code_constants`
and compared against the scorer's own constants in `scripts/profile.py`.
Editing a number in either the table or the code, without touching the
other, turns that test red. This document is not just a description of the
formula; it is one half of the thing that proves the code still matches it.

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
The scorer never invents a new metric; where a metric did not already exist
in a shape that resisted gaming (components 3, 4 and 5 below), a new leaf
was added to profile.py's own pressure or behavior section, built from
counters the parser was already producing.

| # | Component | Weight | Good anchor | Bad anchor |
|---|---|---|---|---|
| 1 | cache_hit_ratio | 30 | 0.90 | 0.50 |
| 2 | startup_floor | 25 | 0.15 | 0.45 |
| 3 | model_switch | 20 | 0.05 | 0.35 |
| 4 | tool_result_avg_bytes | 15 | 2000 | 20000 |
| 5 | output_verbosity | 10 | 800 | 2500 |

The weights add up to 100, which is why a machine that is at or past every
full-penalty anchor scores 0.0, and a machine that is at or better than
every no-penalty anchor scores 100.0.

### Component 1: cache health, cache hit ratio

Metric: `usage.cache_hit_ratio_median` (r), a share between 0 and 1. Lower
is worse, so this component runs backward from the other four: the "good"
anchor (0.90) is a bigger number than the "bad" anchor (0.50). At r = 0.90
or higher the penalty is 0; at r = 0.70 (midpoint) the penalty is 15; at
r = 0.50 or lower the penalty is the full 30.

### Component 2: startup rent, startup floor share

Metric: `instruction.startup_floor_share` (s), a share between 0 and 1. At
s = 0.15 or lower the penalty is 0; at s = 0.30 (midpoint) the penalty is
12.5; at s = 0.45 or higher the penalty is the full 25.

### Component 3: cache health, model switching (weighted by volume)

Metric: `behavior.model_switch_volume_share` (m). At m = 0.05 or lower the
penalty is 0; at m = 0.20 (midpoint) the penalty is 10; at m = 0.35 or
higher the penalty is the full 20.

This is a new leaf, added to profile.py's `behavior` section for
waste-score/2. It answers the same underlying question as the older
`behavior.model_switch_session_share` leaf, which profile.py still
publishes unchanged for anything else that reads it, but weighted by each
session's own token volume (`raw_input`, a number `measure_tokens.py`'s
session reader was already computing) instead of counting every session
equally. See "How this score can be gamed" for why a plain session count
does not survive contact with a hostile reviewer.

### Component 4: tool output pressure, average tool_result size

Metric: `pressure.tool_result_avg_bytes` (t), the average size in bytes of
one tool_result block (total tool_result bytes divided by the count of
tool_result blocks). At t = 2000 bytes or lower the penalty is 0; at
t = 11000 bytes (midpoint) the penalty is 7.5; at t = 20000 bytes or higher
the penalty is the full 15.

This is also a new leaf, added to profile.py's `pressure` section for
waste-score/2, built from two counters the pressure scan already
accumulated for the older `structured_input_share` leaf (which profile.py
still publishes unchanged): the sum of tool_result bytes, and the count of
tool_result blocks. `structured_input_share` itself is gone from the
formula, because its denominator includes human-typed text, which a person
can pad for free. See "How this score can be gamed."

### Component 5: verbosity, the tail of output tokens, not the middle

Metric: `pressure.output_verbosity`'s `p90_output_tokens` field (v), the
90th percentile of output tokens per assistant message (this field already
existed in profile.py's `_output_verbosity()`, unused until now; it stays
null below 10 samples, which is also why the sample floor below exists). At
v = 800 tokens or lower the penalty is 0; at v = 1650 tokens (midpoint) the
penalty is 5; at v = 2500 tokens or higher the penalty is the full 10.

Version 1 of this formula read `median_output_tokens` instead. See "How
this score can be gamed" for why the middle of the distribution was the
wrong place to read from.

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

The score is computed only when every one of the following holds. Failing
any single one of them makes the WHOLE score NO DATA, naming every input
that failed and why. Nothing is ever substituted for a missing or rejected
input: no zero is filled in, no partial score is computed over whichever
inputs happened to pass, and nothing is guessed.

1. **All five inputs carry the confidence label MEASURED** (see
   `scripts/profile.py`'s CONFIDENCE LABELS section: MEASURED, SIGNAL,
   INFERRED, or NO DATA). A component that is NO DATA, is missing entirely
   from the profile, or carries any label other than MEASURED, fails the
   whole score.
2. **Every input is a finite number.** NaN and positive or negative
   infinity fail every ordinary comparison silently, which used to mean a
   non-finite cache ratio could sail through the penalty clamp and come out
   the other side as a confident, full-penalty score. A plain
   `math.isfinite()` check now runs before any arithmetic touches a value.
3. **Every input falls inside its plausible domain.** A share-type metric
   (cache_hit_ratio, startup_floor, model_switch) must sit between 0.0 and
   1.0; a byte-count or token-count metric (tool_result_avg_bytes,
   output_verbosity) must be zero or positive. A value outside that
   domain, such as a startup_floor_share of 1.981 (a mathematically
   impossible "share," seen on a real small-sample fixture during review),
   is refused by name rather than silently clamped to a full penalty the
   way an out-of-range value used to be.
4. **The sample clears a minimum size.** At least 10 sessions in the
   window, AND at least 10 assistant messages with a measured
   `output_tokens`. A one-session, three-tool-call machine used to come
   back MEASURED with a real-looking score in the same units as a
   229-session baseline; below this floor it is now NO DATA, naming the
   actual session and message counts, not a silent "trust it anyway."

The reason for rule 1, in the founder's own words from the round that
shipped it: a score computed over a varying subset of components is not
comparable between machines, because a good subset score and a bad
five-component score could look identical on the dashboard while meaning
opposite things. Rules 2 through 4 exist for the same underlying reason,
extended to the two other ways a number can lie: a value that is not a
real, finite, in-domain measurement is not a measurement at all, and a
sample too thin to support a median is not a sample a comparable score can
be built on. A published, comparable number has to be computed the same
way, on real and sufficient data, every time it exists, or it is not a
fixed measurement at all.

## Worked example

Suppose a machine's profile carries these five MEASURED values, with a
sample well above the floor:

- Cache hit ratio median, r = 0.75
- Startup floor share, s = 0.25
- Model switch volume share, m = 0.15
- Average tool_result size, t = 8000 bytes
- Output verbosity, p90 = 1500 tokens

Penalty 1 (cache health, weight 30): r = 0.75 sits between the 0.90
no-penalty anchor and the 0.50 full-penalty anchor. Fraction of the way from
good to bad: (0.75 - 0.90) / (0.50 - 0.90) = -0.15 / -0.40 = 0.375.
Penalty = 30 x 0.375 = 11.25.

Penalty 2 (startup rent, weight 25): fraction = (0.25 - 0.15) / (0.45 -
0.15) = 0.10 / 0.30 = 0.3333. Penalty = 25 x 0.3333 = 8.3333.

Penalty 3 (cache health, model switching, weight 20): fraction = (0.15 -
0.05) / (0.35 - 0.05) = 0.10 / 0.30 = 0.3333. Penalty = 20 x 0.3333 =
6.6667.

Penalty 4 (tool output pressure, weight 15): fraction = (8000 - 2000) /
(20000 - 2000) = 6000 / 18000 = 0.3333. Penalty = 15 x 0.3333 = 5.0.

Penalty 5 (verbosity, weight 10): fraction = (1500 - 800) / (2500 - 800) =
700 / 1700 = 0.41176. Penalty = 10 x 0.41176 = 4.1176.

Sum of penalties = 11.25 + 8.3333 + 6.6667 + 5.0 + 4.1176 = 35.3676.

Score = 100 - 35.3676 = 64.6324, rounded half up to one decimal = 64.6.

64.6 falls between 50 and 69.9, so this machine's band is WASTEFUL.

## Honest note: the anchors are a published convention, not a measured optimum

The ten anchor numbers in the table above were not derived by studying a
corpus of many machines and finding the natural break points between
wasteful and lean usage. No such corpus exists yet. Most of them are a
published convention: round, readable numbers chosen to bracket one real
machine's own baseline so this formula has somewhere honest to start.

The cache and startup anchors (0.90, 0.50, 0.15, 0.45) are informed by this
repository's own schema 2 measurement, taken on 2026-08-12 over 229
sessions across 90 days: cache hit ratio median 0.865, and first-request
share median 0.360. Those two measured numbers sit inside the "some penalty
but not the worst" stretch of components 1 and 2, which is where a normal,
not especially wasteful machine should land.

The output_verbosity anchors (800, 2500) carry one more piece of real
evidence added in waste-score/2: this same machine's p90 output tokens
measured 1,884 on the same window, which is why the full-penalty anchor was
set comfortably above it (2500) rather than at some smaller round number
that a normal machine would already be pinned against.

The model_switch and tool_result_avg_bytes anchors (0.05, 0.35, 2000,
20000) do not yet have an equivalent published baseline behind them; they
are rounded to the same kind of readable numbers by the same convention,
not measured the same way, and that gap is named here rather than hidden.

### The flip condition

When a corpus of many machines' profiles exists, the anchors get re-derived
from that corpus instead of from one machine's convention, and the formula
version increments again (`waste-score/3`, and so on). Every score computed
under an earlier formula version is marked HISTORICAL when a newer version
exists, and it is never directly compared against a score computed under
the newer version. Comparing scores across formula versions would silently
compare two different rulers as if they were one, which defeats the entire
purpose of publishing the formula before rendering the score.

## How this score can be gamed

Publishing this section is a deliberate decision, not an oversight: a score
that will not name its own weak points is not one worth trusting, and this
is the same posture that makes the MEASURED / SIGNAL / INFERRED / NO DATA
labels elsewhere in this repository worth anything. Nothing below is
softened, and nothing is claimed closed unless a calibrated test in
`scripts/test_profile.py` proves it on a real fixture pushed through the
real pipeline (`build_profile` then `compute_waste_score`, not hand-picked
leaves).

The founder's acceptance rule for this formula: **no manoeuvre that
strictly increases total tokens spent may increase the score.** A hostile
review of waste-score/1 found three manoeuvres that broke this rule.

**Attack A: paste more human text (structured_input_share).** Under
waste-score/1, component 4 read `structured_input_share`, tool_result bytes
divided by (tool_result bytes plus human-typed text bytes). Pasting more
human text into every turn grows the denominator without touching the
numerator, so the share falls and the penalty falls with it, even though
pasting more text strictly increases total tokens spent. Reproduced on a
real fixture (`test_attack_C1A_pasted_human_text_games_v1_structured_input_share`):
ten sessions, adding 8KB of human text per session moved the score from
28.8 to 43.8, a 15-point gain from pure waste.

*Resisted in waste-score/2, closed by the reviewer's own test:* component 4
now reads `tool_result_avg_bytes`, which is built only from tool_result
bytes and the tool_result count. Human-typed text never enters that
formula at all, so it cannot move this component in either direction. The
same fixture, replayed after the fix, moves the score by exactly 0.0.

**Attack B: farm cheap sessions (model_switch_session_share).** Under
waste-score/1, component 3 read a plain count: switched sessions divided by
total sessions. Every session counted the same regardless of size, so
padding a machine's history with many small, unswitched sessions diluted a
genuine switcher's share for free. Reproduced on a real fixture
(`test_attack_C1B_session_farming_games_v1_model_switch_session_share`): 10
real sessions (4 switching), padded with 10 more trivial unswitched
sessions, moved the score from 8.8 to 18.8, a 10-point gain from padding
alone.

*Resisted, not fully closed, in waste-score/2:* component 3 now weights
each session by its own `raw_input` token volume instead of counting it as
one. The same fixture, replayed after the fix, moves the score by exactly
0.0, because ten sessions at one-hundredth the size of the real ones
contribute almost nothing to the weighted total (0.4 to 0.396, both still
in the full-penalty zone). This is resistance, not elimination: enough
REAL padding volume, comparable in size to the genuine sessions, would
still dilute the number, but the cost now scales with actual tokens spent
rather than with a free session count, which is the property the founder's
acceptance rule asks for.

**Attack C: append filler messages (median output_verbosity).** Under
waste-score/1, component 5 read the median of output_tokens per assistant
message. Appending many small, low-token filler messages drags the median
down, even though every filler message is additional real spend. Reproduced
on a real fixture (`test_attack_C1C_filler_messages_game_v1_median_verbosity`):
10 honest sessions (30 messages at 2000 output tokens each), padded with 60
one-token filler messages, moved the score from 20.0 to 30.0, a 10-point
gain from filler alone.

*Resisted at this fixture's ratio, not fully closed in general, in
waste-score/2:* component 5 now reads p90 instead of the median. The same
fixture, replayed after the fix, moves the score by exactly 0.0, because
p90 sits in the top 10% of the sample and the honest messages still fill
that whole band (30 honest messages out of 90 total sit at positions 60-89
of a 90-message sorted list; the 90th-percentile index, 81, falls inside
that untouched honest band). This resistance has a named, quantifiable
edge: p90 only stays untouched by filler while the filler count stays under
roughly 9 times the honest message count (below that ratio, the top 10% of
the sample is still majority-honest; above it, filler starts to occupy the
90th-percentile position too). A flood large enough to cross that ratio
would still drag p90 down, and running that many extra real messages is
itself real, measurable spend, same as attack B's residual risk.

**A farm that remains open, named rather than hidden: the tiny-tool-call
flood against component 4.** `tool_result_avg_bytes` is a plain average
(total tool_result bytes divided by tool_result count). Running many extra
tool calls with a near-zero-byte result (repeating a cheap command like
`pwd` many times) pulls the average down and lowers this component's
penalty, even though each extra call is a real additional tool round-trip
with its own JSON and conversation overhead that this average does not see.
This is not closed in waste-score/2. `pressure.duplicate_reads` and
`pressure.duplicate_commands` already count exactly this kind of repeated,
low-value call, but neither is wired into the waste score yet; doing so is
left for a future formula version rather than folded into this fix round
unannounced. Cost to a user who wanted to run this farm for real: they
would have to execute genuinely many extra tool calls inside their own real
Claude Code sessions, spending real tokens on real API calls to move a
locally-computed number, which is an unusual thing to want badly enough to
pay for, but it is possible, and it is named here rather than hidden.

## Version history

**waste-score/1** (initial publication): the five-component formula, the
all-or-nothing MEASURED rule, and the published bands, ratified before any
code implemented it (docs/WASTE-SCORE.md was committed before
`compute_waste_score` was written, in a separate commit, and `git log`
proves the order). Never wired into any output; no score under this version
was ever rendered anywhere.

**waste-score/2** (this document, fix round 2, hostile review): version
bump because the formula itself changed, not just the code around it.
Changes:

- Component 3 (`model_switch`) reads a new leaf,
  `behavior.model_switch_volume_share`, weighted by each session's own
  token volume, instead of `behavior.model_switch_session_share`, a plain
  session count. Weight (20), good anchor (0.05) and bad anchor (0.35) are
  unchanged.
- Component 4 reads a new leaf, `pressure.tool_result_avg_bytes` (average
  bytes per tool_result block), instead of `pressure.structured_input_share`
  (a share whose denominator includes human-typed text). Weight (15) is
  unchanged; the anchors moved from a 0.30-0.70 share to a 2000-20000 byte
  range, because the metric itself changed units.
- Component 5 (`output_verbosity`) reads `p90_output_tokens` instead of
  `median_output_tokens` from the same leaf. Weight (10) is unchanged; the
  anchors moved from 400-1200 to 800-2500, informed by this machine's own
  measured p90 of 1,884 tokens.
- Added: the sample floor (10 sessions AND 10 assistant messages), the
  finite-number guard, and the plausible-domain guard, all described under
  "The all-or-nothing rule" above.
- Added: this document is now machine-checked against the code's own
  constants by a parsing test (see "Machine-checked" at the top).

Because nothing under waste-score/1 was ever rendered, nothing real is
invalidated by this change. Had a waste-score/1 number ever been shown to a
user, it would now be marked HISTORICAL and never compared against a
waste-score/2 number, per the flip condition above; that rule exists
starting now, for whichever version comes after this one.

### A design decision recorded here, as asked

Component 3 could have been dropped instead of fixed, with its 20 points
redistributed (cache 40, startup 30, tool output 20, verbosity 10). It was
kept, weighted by volume, because the data needed to do that safely
(`raw_input`, a per-session token-volume total) was already being produced
by `measure_tokens.py`'s existing session reader; no new parsing pass was
written to save it. If a future review finds that `raw_input`-weighting is
itself gameable in a way this document has not named, dropping the
component and redistributing its weight remains the documented fallback.
