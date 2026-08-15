# What to do next, in order

Every item names its files, its done-check, and an estimate as a range with a
confidence and its assumption. An item with no done-check is not ready to
start; say so rather than starting it.

Items 1 and 2 are blocked on a decision from Khalil (see `06`). Item 3 is the
best thing to start on if you want to be useful immediately without waiting.

---

## 1. BLOCKED ON A DECISION: sign the fleet records

**Why it matters.** This is the largest open gap in the enterprise story.
Records in an organisation's fleet store are unsigned, so anyone with push
access to that store can forge any machine's record. `docs/FLEET.md` states
this plainly rather than hiding it, which is correct but not a fix.

**Why it is blocked, and do not build around it.** The decided design (a
machine-local key generated at join, public half carried in the record) cannot
be implemented cleanly as it stands:

- **No crypto library is available**, and this repository ships **zero
  dependencies** by design; it installs into other people's Claude Code.
  `cryptography`, `nacl` and `ed25519` are all absent.
- Stdlib gives HMAC, which needs a **shared** secret. Everyone with store
  access would hold it, so it defends against nothing in the actual threat
  model: someone with write access.
- The design puts the public half **in the record**, so an attacker rewriting
  a record rewrites the key with it. It needs pinning at join, which is a
  second decision nobody has taken.

`fleet.py` says in its own comments that a half-signature would be worse than
none. Do not ship one.

**Files when unblocked:** `scripts/fleet.py`, `data/fleet.schema.json`,
`scripts/test_fleet.py`, `scripts/fleet_dashboard.py`, `docs/FLEET.md`.
**Done-check:** a record altered after writing must fail verification on the
reading side, and the dashboard must render it as its own NO DATA row naming
the failure rather than dropping it.
**Estimate:** 6 to 12 hours, low confidence, assuming the dependency question
is settled first. Low because key distribution and trust-on-first-use pinning
are the hard half and neither is designed.

---

## 2. BLOCKED ON BILLING: two-host parity for Bitbucket

There is a standing founder law that every development works on GitHub **and**
Bitbucket Cloud, applying backward to shipped code. This repository has GitHub
Actions only and no `bitbucket-pipelines.yml`.

**Blocked, not merely undone.** The `kmaaouni` Bitbucket workspace is read-only
until a billing change only Khalil can make, so even a written pipeline could
not be observed green, and the law's done-check requires a real run observed
green on both hosts.

State it as BLOCKED with that reason. Do not write the pipeline and call it
done, and do not quietly drop it.

**Estimate:** 2 to 4 hours once unblocked, medium confidence, assuming the
checks stay host-neutral (plain scripts a runner invokes) and the pipeline file
is a thin translation.

---

## 3. START HERE: the competitive field map is wrong about a competitor

**Why it matters.** `docs/` carries a competitive field map asserting that
nobody in this field ships hard budget enforcement. That is false: CodeBurn
ships spend cap guard hooks inside Claude Code. A field map that is wrong about
a competitor is exactly the kind of unearned confidence this project exists
against, and it is ours rather than a third party's.

**Files:** the field map document under `docs/` (grep for the competitor
section), and any place the claim is repeated.
**Done-check:** the corrected row cites a page actually opened, with its date,
and the correction is visible rather than a silent edit. Nothing in the field
map is labelled MEASURED or VERIFIED, because nothing in it was measured here;
keep that property.
**Estimate:** 1 to 2 hours, high confidence. Small, self-contained, and it
removes a false claim.

---

## 4. The live per-task cost counter

Parked earlier with a recommendation attached. Research found two gaps nobody
in this field covers: a hard brake that stops spend at a boundary, and a live
per-task cost counter. The counter was recommended first because it is smaller
and compounds with the measured labels, while the brake collides with the
zero-hooks-by-default promise.

**Done-check:** not yet defined. Define it before starting, or this is not a
plan step.
**Estimate:** unknown until scoped. Do not guess one.

---

## 5. Defect D11, ownership deliberately unassigned

Carried across several sessions with its ownership left open on purpose. Read
`docs/BACKLOG-DEFECTS.md` for what it is before deciding whether to take it.

---

## 6. Housekeeping worth doing when between larger items

- **`token_shield` still owns presentation only, which is correct**, but check
  whether anything has drifted back into it. `scripts/test_architecture.py`
  enforces direction and no-markup-below-layer-2, and it will tell you.
- **The `_harden` helper is duplicated** in `scripts/fleet.py` and
  `scripts/signals.py`, deliberately, because `signals` sits below `fleet` and
  importing upward is refused. If a shared home appears at the right layer,
  they collapse into one. Do not park a shared helper in the wrong layer to
  save six lines.
- **`cli.ROOT` and `cli.EXPERIMENT_DAYS` are aliases of `config` values and
  must stay.** Several tests monkeypatch `cli.ROOT` to point a run at a fixture
  directory. Rewriting cli's internals to read `cfg.ROOT` directly would leave
  those patches silently ineffective, with the tests still passing while
  measuring the real machine.

---

## What is already done, so you do not redo it

All of the following landed and merged on 2026-08-15, each with CI verified on
its own head commit:

- The review round on four previously unreviewed units, which found the
  organisation dashboard's privacy rule was undoable by subtraction.
- `cli.py --version`, and `uninstall` that refuses instead of hanging with no
  terminal attached.
- The architecture layer map plus the check that enforces it.
- Wave 2 in full: the proof ledger's four defects (D18, D19, D8, D21a), three
  weak tests, and the trial's first screen.
- Every silent error handler now states why it is silent, 41 of them.
- `config.py` extracted; the import graph has **no cycles**, where it had four.
- `metrics.py` and `formatting.py` split out of the renderer.
