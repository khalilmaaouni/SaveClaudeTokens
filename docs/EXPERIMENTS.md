# Experiment Mode

Every other number this tool produces is MEASURED (read from counters,
cause not proven) or ESTIMATED (a transparent projection). Experiment
Mode is the one path that can earn VERIFIED, because it is the only
mode that actually compares a before and an after over the same window.

## How it works

```
python3 scripts/experiment.py start "my-change"
```

Make exactly one change. Work normally for a while, long enough to
build up real sessions on both sides.

```
python3 scripts/experiment.py end "my-change"
```

The same two commands are also available through the CLI:

```
python3 scripts/cli.py experiment start "my-change"
python3 scripts/cli.py experiment end "my-change"
```

`start` marks the boundary and records the state at that point. `end`
measures the sessions since the boundary, compares them against the
sessions before it, and writes the result.

## Why one change at a time

The comparison only means something if the "before" and "after" differ
by the one thing you changed. Two changes in the same window and the
tool cannot tell you which one moved the number, so keep it to one
change per experiment.

## The guardrails that downgrade a result to NOT_PROVEN

A result is written as NOT_PROVEN, not VERIFIED, whenever the
comparison itself is not trustworthy:

- **Schema change.** If the transcript schema changed between the
  before and after windows, the counters are not directly comparable.
- **Window mismatch.** If the before and after windows are not
  comparable (too short, not aligned, overlapping), the comparison is
  refused.
- **Fewer than 3 sessions after the change.** A result from one or two
  sessions is noise, not a measurement, so the tool waits for at least
  three before it will call anything VERIFIED.

Any of these produces NOT_PROVEN instead of a number. This is the same
discipline as NO DATA elsewhere in the tool: refuse to guess rather
than print something that looks like proof and is not.

## Estimated is not verified

A projected or prevented saving, the kind you get from `summary` or
`dashboard` without running an experiment, is ESTIMATED. It is a
transparent, labeled projection, and it is never presented as VERIFIED.
Only a real before, after comparison earns that label.

## The ledger

Every experiment result, VERIFIED or NOT_PROVEN, is appended to
`~/.claude/token-shield/savings.jsonl`. Nothing already written to it
is ever rewritten or deleted, so it stands as the record of every
experiment run so far. The dashboard's Verified column reads from this
file.
