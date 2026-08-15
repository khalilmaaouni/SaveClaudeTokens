# Architecture

What this file is for: where a new piece of work belongs, which direction
dependencies are allowed to point, and what an enterprise deployment actually
consists of. It is enforced by `scripts/test_architecture.py`, which runs in
CI. Where this document and that file disagree, the file wins, because it is
the one that can refuse a change.

Scope note, stated first because it is the honest part: the layer map below
describes 26 modules and about 25,700 lines that today all live flat in
`scripts/`. The layers are real (they are computed from the imports, not
drawn from intent) but they are not yet directories. Turning them into
directories is a mechanical move that buys nothing until the five upward
imports named below are gone, so it is not scheduled ahead of them.

## The one rule

**Imports point down, never up.** A module may import its own layer or any
layer below it. Nothing else.

The reason is not tidiness. Every honesty defect this project has shipped and
then fixed has the same shape: two surfaces onto one number, drifting apart
with nothing able to notice.

- The trial printed `ESTIMATED 218.3M` and the command it recommends printed
  `OPPORTUNITY 230M`, one minute apart on the same machine, because one took
  the largest lever and the other summed overlapping ones.
- The NATIVE headline was largest exactly where the evidence was weakest,
  because one code path charged unsplit cache writes and another did not.
- `cli prices` was fixed to lead with "this is not money you saved" while
  `pricing.py`'s own entry point kept a six-figure total with the caveat five
  lines below it, until this session.
- A regression, a HISTORICAL caveat and a NO DATA placeholder all rendered in
  the same success green, because the only CSS rule matching the hero
  hardcoded the good colour.

A layered graph does not by itself prevent any of those. What it prevents is
the *condition* that makes them cheap to introduce: when the renderer sits
above everything and nothing reaches up into it, there is exactly one place a
label, a caveat, or a colour can be decided, and a second surface has to go
through it rather than around it.

## The layers

Lower number is lower in the stack. The authoritative copy is `LAYERS` in
`scripts/test_architecture.py`.

| L | Name | Modules | What belongs here |
|---|---|---|---|
| 0 | foundation | `measure_tokens`, `context_lint`, `session_end_telemetry`, `check_py311` | Reads raw counters and files on disk. Imports nothing else in this repo, which is what makes it the floor. |
| 1 | metrics | `pricing`, `experiment`, `profile`, `signals` | Turns counters into the quantities the product talks about. No rendering, no advice. |
| 2 | proposal | `guided_apply`, `optimize`, `discover_companions` | Reads metrics and proposes a change. Never renders one. |
| 3 | advice and ecosystem | `companions`, `plugin_prune`, `memory_trim`, `doctor` | Ranks proposals and inspects the installed world. |
| 4 | advisors | `advisor`, `deep_advisor` | The ranked next-move surface renderers consume. |
| 5 | presentation | `token_shield` | Labels, formatting, confidence pills, the CSS, the HTML. |
| 6 | fleet | `fleet` | Many machines, built on the single-machine layers below. |
| 7 | surfaces | `cli`, `trial`, `report`, `detail_report`, `share_card`, `fleet_dashboard`, `reconcile`, `obsidian_export` | One entry point per thing a person or a script can run. |

A module with no layer fails the check. That is deliberate: the cheapest
moment to decide where something belongs is the moment it is created.

### What layer 5 is currently doing wrong

`token_shield` is 1,582 lines and is the presentation layer, but it also
holds `savings_breakdown` (a metric), `COMPANIONS_PATH` and
`load_companions` (foundation-level file access), and the CSS. Nine modules
import it. That is why four of the five upward imports below exist: modules
that only want to read `data/companions.json` have to reach into the
renderer to do it.

Splitting the metric half out of `token_shield` is worth doing and is not
scheduled yet, because the upward imports are the part that actively costs
correctness and they are cheaper to fix.

## The frozen list, and the one change that empties it

Five imports point upward today. They are frozen by name in
`KNOWN_UPWARD`, and the check refuses both a sixth and a stale entry, so the
list can only shrink.

| From | To | Wants |
|---|---|---|
| `advisor` | `token_shield` | `COMPANIONS_PATH`, `load_companions` |
| `doctor` | `token_shield` | `COMPANIONS_PATH`, `load_companions` |
| `discover_companions` | `token_shield` | `COMPANIONS_PATH`, `load_companions` |
| `companions` | `token_shield` | `COMPANIONS_PATH`, `load_companions` |
| `guided_apply` | `cli` | `ROOT`, `EXPERIMENT_DAYS` |

All five are one cause: four constants and one function that belong in the
foundation are living in a renderer and a surface. **One change removes every
entry**: extract `scripts/config.py` at layer 0 holding `ROOT`,
`EXPERIMENT_DAYS`, `COMPANIONS_PATH` and `load_companions`, and repoint the
five importers at it.

### Decision record: freeze the violations, do not fix them yet

**Criteria, in the order they decided it.** (1) Does the option stop the
problem growing? (2) What is its blast radius measured in call sites and test
suites, not in feeling? (3) Does it leave the codebase honestly described, or
does it leave a document asserting something untrue? (4) Can it be verified by
a command rather than by reading?

**Decision.** Declare the layers, and freeze today's five upward imports by
name in a check that refuses a sixth and refuses a stale entry.

**Rejected alternative 1: extract `scripts/config.py` immediately, in the same
change.** This is the right end state and it is scheduled. Rejected here on
criterion 2: about 35 call sites across six test suites monkeypatch those
symbols through their current owners (`dr.ts.load_companions`,
`adv.ts.COMPANIONS_PATH`), and one test in `test_advisor.py` asserts against
the literal source text `data = ts.load_companions(ts.COMPANIONS_PATH)`. That
is a real refactor with a real blast radius, and it would have landed beside an
unmerged review round in a session whose predecessor overran its token ceiling
by eight percent.

**Rejected alternative 2: move the modules into directories first, and sort
the imports out afterwards.** Superficially the most visible "organise the
architecture" move, and the one most likely to be asked for. Rejected on
criteria 1 and 3: a directory layout is not a dependency rule. Every cycle
would survive the move intact, `advisor` would still reach up into
`token_shield`, and the repository would then LOOK layered while behaving
exactly as before, which is worse than looking flat and being flat. Directories
are cosmetic until the direction is enforced, so they are not scheduled ahead
of the extraction.

**Consequences, including the ones that cost something.** No new upward import
can be added while the old ones are paid down, and that is enforced rather than
asked for. The cost: five violations stay in the codebase and are now WRITTEN
DOWN, which makes them easy to point at and easy to live with. A frozen list is
a standing invitation to leave things frozen. The stale-entry check is the
counterweight, because it forces the list to shrink honestly rather than
quietly outliving its violations, but nothing forces the extraction itself to
happen on any particular day.

**Flip condition.** When a session opens with nothing owed and budget headroom,
the extraction goes first, as its own pull request.

## What the static check cannot see

Named rather than left implicit, because a check whose blind spots are
undocumented reads as more coverage than it has.

- **Subprocess dependencies.** `cli` shells out to nine modules
  (`advisor`, `deep_advisor`, `doctor`, `memory_trim`, `optimize`,
  `plugin_prune`, `profile`, `report`, `token_shield`) rather than importing
  them, and `trial` shells out to `cli`. Those are real dependencies that no
  import graph will ever show. They happen to point downward today; nothing
  enforces that they keep doing so.
- **Two dispatch mechanisms in one file.** `cli` imports four modules
  directly and subprocesses to nine others, with no stated rule for which
  gets which. A command added tomorrow could reasonably use either.
- **Runtime coupling through files.** Modules that share
  `~/.token-shield/` state depend on each other's formats without importing
  anything. The record schemas (`data/fleet.schema.json`,
  `data/signals.schema.json`) are the only thing holding those contracts.
- **Duplication the layer rule actively causes.** `fleet` and `signals` each
  carry their own `_harden(path, mode)`, byte for byte the same idea, because
  `signals` sits below `fleet` and importing upward is exactly what the check
  refuses. That is the rule working, not failing: the honest fix is a
  foundation module, which is the same extraction the frozen list is waiting
  on, and a shared helper parked in the wrong layer would have been the
  dishonest one. Named here so the duplication reads as a decision rather than
  as carelessness.

## Silent failures, and which ones are the design

`tools/sbe_score.py`'s silent-failure lint reports 23 handlers under
`scripts/` that swallow an error. Most of them are this codebase's central
promise working correctly: a ledger line that will not parse, a record that
will not read, a machine directory that will not list, each becomes its own NO
DATA row rather than killing the page or the run for everyone else. Changing
those would be a regression.

One cluster was genuinely wrong and is fixed: the `chmod` calls that deliver
the `0600` file and `0700` directory posture on the fleet config and the
signals outbox were wrapped in `except OSError: pass`. Swallowing an error
about somebody else's bad data is the design. Swallowing an error about OUR OWN
promise not being kept is not, and the docstrings above those calls went on
asserting a posture the code had silently failed to achieve, on files holding
an organisation's store URL and its salt. They now warn on stderr, naming the
path and the mode, and still never raise, because refusing to save a config
over a permission that could not be tightened would lose the user's work.

**Open, and not claimed as green:** the remaining 23 sites have no
`# sbe: allow-silent <reason>` marker, so the lint FAILs as a gate. The correct
disposition is one visible, reasoned marker per site, read individually rather
than pasted, which is its own unit of work and not yet done.

## Deploying to an organisation

The enterprise story is three separable pieces, and they are separable on
purpose: an organisation can adopt the first without the second and the
second without the third.

### 1. One machine, no network

The default, and the only mode that needs no decision from anyone. Everything
reads local transcripts under `~/.claude/projects` and writes local state
under `~/.token-shield/`. There is no network call in the single-machine
path, no account, and no identifier that leaves the disk. The plugin
registers zero hooks until somebody opts in.

Deployment surface an administrator needs, all of it now present:

- `cli.py --version` reports the installed build, read from
  `.claude-plugin/plugin.json` so it cannot drift from what the marketplace
  installed.
- `cli.py uninstall --yes` removes local data without a prompt. Without a
  terminal and without the flag it refuses and deletes nothing, rather than
  blocking a fleet-wide push forever waiting for a person to type `YES`.
- Exit codes are meaningful: `0` success, `1` a refusal the caller asked for,
  `2` NO DATA or a bad invocation.

### 2. Opt-in telemetry, still local

A `SessionEnd` hook the user installs deliberately (`/token-shield:start`)
writes a per-day counter rollup to disk. `signals.py` summarises it. Nothing
is transmitted. This exists so the fleet layer has something honest to read,
not as a precondition for it.

### 3. The fleet store, many machines

`fleet.py` writes one whitelisted record per machine per day into a git
repository the organisation owns, and `fleet_dashboard.py` renders the org
view read-only. The record shape is frozen in `data/fleet.schema.json` with
`additionalProperties: false` everywhere, and is built by walking that schema
and copying only what it names, never by taking a larger object and deleting
the bad parts.

Four properties an administrator or a works council will ask about, each with
its current honest answer:

- **What is in a record.** Counters, a date, a machine id, optional team and
  environment tags, and experiment outcomes. No prompts, no file contents, no
  repository names, no session transcripts, no user names.
- **Whether it can measure a person.** Not as published. One machine is one
  person in most organisations, so no per-machine token count and no
  per-machine experiment result appears on the org page at all; the machine
  table carries operational health only. Aggregates are published only when
  at least five distinct machines stand behind them, and as of this session
  the withheld remainder must also stand on five, because publishing a
  five-machine group next to a six-machine total handed back the sixth
  machine by subtraction.
- **Who can write to it.** Anyone with push access to the store, which is
  read *and* write access to every record in it. Records are unsigned and
  therefore forgeable by anyone holding that access. This is the largest open
  gap in the enterprise story and it is stated in `docs/FLEET.md` rather than
  glossed.
- **How a record is erased.** Deleting the file removes it from the working
  tree; git history still holds it, so real erasure means rewriting history.
  Said plainly because the comfortable half of that answer is not the true
  one.

### What Anthropic already ships, and why that matters here

Claude Code already has an organisation-wide analytics dashboard, an
OpenTelemetry export carrying `claude_code.token.usage` and
`claude_code.cost.usd`, and managed settings that can allowlist plugin
marketplaces. Token Shield attributes that rather than competing with it: the
thing it adds is the proof layer (a labelled, calibrated, per-experiment
claim), not another token counter. `docs/ATTRIBUTION.md` holds the full
position and its flip condition.

## Adding something new

1. Decide its layer before writing it. `test_architecture.py` refuses a
   module with no declared layer, which is the check firing at the cheapest
   possible moment.
2. If it needs something from a higher layer, that is the signal the thing it
   needs is in the wrong place. Move the thing down; do not add an upward
   import and a frozen entry.
3. A new surface goes at layer 7 and reaches its numbers through layer 5, so
   the labels and caveats it prints are the same ones every other surface
   prints. Two doors onto one figure is the defect family this whole file
   exists to make harder.
