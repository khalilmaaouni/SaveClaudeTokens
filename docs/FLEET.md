# Fleet dashboard

This file is expected to already carry an admin guide to `fleet init`,
`fleet join`, and `fleet leave` (Fleet F2). At the time this section was
written, that guide existed only on the unmerged branch
`origin/build/fleet-f2` and was not yet part of `origin/main`, so this file
did not exist in this worktree. This section was added on its own; whoever
merges Fleet F2 and Fleet F3 together should fold it under the existing
guide rather than keep two separate `docs/FLEET.md` introductions.

## `fleet dashboard`: render the org-wide page

`scripts/fleet_dashboard.py` reads a local checkout of the org's fleet store
(the layout `scripts/fleet.py`'s `push_record()` writes:
`fleet/<org>/<machine-id>/<date>.json`, one record per machine per calendar
day) and renders one self-contained HTML page. This phase does not clone or
pull the store itself; get a local checkout onto disk first (a plain
`git clone` of the org's store, or `fleet pull` in a later phase), then
point `--store-dir` at its root.

```
python3 scripts/fleet_dashboard.py \
  --store-dir /path/to/local/checkout-of-the-fleet-store \
  --org acme \
  --out ~/fleet-dashboard.html
```

The page shows, reusing the single-machine dashboard's own label rules
(`scripts/token_shield.py`'s `esc`, `human`, `pct`, `_cpill`) rather than a
second copy of them:

- **Machines reporting**, one row per record file found. A machine whose
  record is missing, unreadable, malformed, newer-schema, or otherwise
  hostile renders its own row with a named reason instead of a number, and
  never removes or blocks any other machine's row.
- **Token counters by day**, summed across every machine whose record
  loaded cleanly, bucketed by model the same way a single machine's record
  is (today, every counter lands under the bucket key `"unknown"`, per
  `scripts/fleet.py`'s own documented limit: the local telemetry ledger
  carries no true model identity yet).
- **Tokens by team** and **tokens by environment**, the free tags a machine
  sets at `fleet join` time.
- **Experiments, latest per label**, gathered across every machine in the
  org. One row per label, the newest record by timestamp; repeated runs of
  the same label are never added together, and a regression's measured
  delta renders exactly as recorded, negative sign included. Confidence
  values (`VERIFIED`, `NOT_PROVEN` under the current record schema) render
  through the same badge the single-machine dashboard uses.

The renderer is read-only: it never writes into the store, never runs git,
and never sends anything anywhere. Every value on the page came from a
record a machine chose to push; nothing is guessed, and nothing is summed
across confidence labels.
