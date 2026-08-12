# Telemetry: what is measured, how it runs over time, and what never leaves

Telemetry here is deterministic and local. It reads counters the API already
wrote and does arithmetic. It never asks a model to measure token spend, because
spending tokens to count tokens is the joke the whole project refuses to be.

## What is measured

Per session, from the `usage` object on every assistant message:

| Field | Meaning |
|---|---|
| `input_tokens` | uncached input on the turn |
| `cache_creation.ephemeral_5m_input_tokens` | cache written at the 5 minute TTL, bills 1.25x |
| `cache_creation.ephemeral_1h_input_tokens` | cache written at the 1 hour TTL, bills 2x |
| `cache_read_input_tokens` | served from cache, bills 0.1x |
| `output_tokens` | generated on the turn |
| `isSidechain` | true on a subagent's own records, so parent and subagent are separable |
| `message.model` | the model on the record, so a mid-session model switch is detectable |

Derived, per session:

- **first_request**: the parent's first call total (input + writes + reads). The
  startup floor every later call also pays.
- **first_request_share**: first_request times call count over total raw tokens.
  How much of the session's reading is the floor being re-paid.
- **hit_ratio**: per-session cache read over total input. Reported as a median
  across sessions, labeled as a median (see the pooled-versus-median note in
  `docs/CLAIMS.md`).
- **normalized_input**: input + 1.25 x write_5m + 2.0 x write_1h + 0.1 x read,
  in base-input units. NO DATA when the TTL split is absent.
- **rewrite_ratio**: writes over reads, a signal to investigate, never proof.
- **subagent share**: how much output came from subagents rather than the main
  thread.

## The metric schema, and why it is versioned

Baselines written by `measure_tokens.py --baseline` carry a `schema` number,
currently 2. Schema 1 counted the first record of every transcript, including
transcripts that are a subagent's own conversation, which read low. Schema 2
counts the 229 real parent sessions separately from the 6,020 subagent
transcripts among them. The two are not comparable, so the compare path refuses
to diff the first-request family across the schema boundary rather than print a
false delta. When the metric changes again, the schema number goes up and the
same refusal protects the next comparison.

## How it runs over time

Two modes, both opt in:

- **On demand.** Run `/token-audit` or `measure_tokens.py` whenever token use,
  context size, or cache behavior becomes material. Nothing runs otherwise.
- **Automatic, if you choose it.** `scripts/session_end_telemetry.py` is a
  SessionEnd hook you wire into your own `~/.claude/settings.json`. On each
  session end it appends one line of counters to a local JSONL ledger
  (`~/.claude/token-ledger.jsonl` by default, or `TOKEN_LEDGER`). Over weeks the
  ledger is a real history you can trend. It is deterministic: no model runs.

The wiring snippet is in the README. The plugin does not register the hook for
you; you paste it, so that installing the plugin never silently starts code.

## What never leaves the machine, and what never enters a file

Privacy is enforced by what the code is capable of writing, not by a promise. A
test asserts the exact key set of a ledger row, so a later edit cannot quietly
widen it (`test_ledger_main_writes_only_allowed_keys`).

- No conversation text, file contents, prompts, or tool output is ever written
  to the ledger or the dashboard. Only counters, a distinct-model count, and the
  transcript basename.
- The transcript basename, never its full path, so a private project name in a
  directory cannot leak.
- Nothing is sent anywhere. There is no network code in any script (grep for
  `socket`, `urllib`, `http`, `smtp` returns nothing).
- The SessionEnd hook prints nothing to stdout and exits 0 even on failure, so
  it can neither inject into a session nor break one
  (`test_telemetry_never_breaks_the_session`).
- The dashboard exports aggregates only. Per-session rows are off unless you
  pass `--include-sessions`, because transcript names identify sessions and a
  synced vault is a different privacy boundary from a local disk.

## The ledger is yours

The ledger and any dashboard note are plain files you own, on your disk. If you
sync them (Obsidian, iCloud, git), that is your decision and your boundary to
manage. The tools default to aggregate, local, and silent; anything beyond that
is a choice you make explicitly.
