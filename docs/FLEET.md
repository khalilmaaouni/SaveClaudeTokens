# Fleet: an admin guide to init, join, and leave

Fleet is the org-wide layer on top of the free, single-machine Token Shield
core. There is no server: an org designates a private git repository it
already owns as the "fleet store", and every machine that joins pushes small
JSON files into it. `scripts/fleet.py` is the only command file; `fleet init`,
`fleet join`, and `fleet leave` are its subcommands. This phase does not ship
`fleet dashboard`; F1 already ships `fleet build` and `fleet push` for a
machine that already has a local fleet config.

## What never leaves a machine

Deliberately absent from every fleet record, by design, not by promise: no
prompts, no file contents, no repo names, no session transcripts, no user
names. What a machine actually pushes, once per push, is:

- token counters (input, output, cache read, cache write), bucketed by day
- labeled experiment results (VERIFIED or NOT_PROVEN) with their fingerprints
- the machine's config fingerprint and installed token-shield version
- the team and environment tags set at join time
- a machine id: a one-way hash of the hostname and the org's own salt, never
  the raw hostname

`fleet init` prints this exact list, in plain words, before it creates or
pushes anything, so an admin sees it before the store exists. `fleet join`
writes it to `~/.token-shield/fleet-config.json` (or wherever `--config`
points), which stays a plain local file the machine's owner can read.

## `fleet init`: create the org profile (admin, once)

```
python3 scripts/fleet.py init <store-git-url> \
  --org acme --salt "a-passphrase-only-your-org-uses" \
  --default-mode balanced
```

Every answer is also a flag, so this runs with no terminal at all (a CI job,
an MDM console, a test). If a flag is missing and the session has a real
terminal, `fleet init` asks for it instead of guessing. `--default-mode` must
be one of `conservative`, `balanced`, or `aggressive`.

What it does, in order:

1. Prints the data-sharing disclosure above.
2. Clones the store.
3. Refuses to continue if `org-profile.json` already exists there, unless
   `--force` is given (a second `fleet init` on an already-initialized store
   is a mistake, not a silent overwrite).
4. Writes `org-profile.json` at the store root: `org`, `salt_fingerprint`,
   `default_mode`, `telemetry: "counters_only"` (the only value F1 through
   F2 ever write), and `push_cadence: "manual"`.
5. Creates the `fleet/` directory the per-machine records will live under.
6. Commits and pushes.

`org-profile.json` never holds the raw salt, only `salt_fingerprint`
(`sha256(salt)`, hex-encoded). A fleet member who can only read the store,
but was never handed the salt directly, cannot recover it from the store
alone. `fleet join` still needs the actual salt (from whatever secret store
the org already uses to distribute the join command); it verifies a
`--salt` against the store's `salt_fingerprint` and refuses a mismatch (see
"fleet join" below), rather than silently registering a phantom machine.

**Honest limit on what this buys.** The salt is not a secret in the sense
that keeps it away from everyone who runs `fleet join`: every machine that
joins must be given the exact same value, so it necessarily reaches every
member who joins a machine, not just the fleet's admins. A member who holds
the salt can still correlate a guessed or known hostname to its
`machine_id` by hashing candidate hostnames themselves; hashing only
protects against two groups: outsiders who never received the salt at all,
and members who can read the store's records but were never handed the
salt directly (a read-only dashboard viewer, for example). Salt-fingerprint
storage closes that second gap; it does not close the first for anyone who
legitimately holds the salt. An org that wants machine ids anonymous even
from its own salt-holding members needs a different mechanism than a
shared org salt (see the design doc's note on a memorable vs. a
pseudonymous, per-org-chosen salt); that mechanism is not built here.

## `fleet join`: register one machine

```
python3 scripts/fleet.py join <store-git-url> \
  --org acme --salt "a-passphrase-only-your-org-uses" \
  --team ios --environment ci
```

`--org` and `--salt` are the exact values `fleet init` used. `--team` and
`--environment` are free tags, but not arbitrary strings: each must match
`^[a-z0-9_-]+$` (lowercase letters, digits, underscore, hyphen only; no
capitals, spaces, or newlines), for example `ios` or `prod-us`. A tag
outside that charset refuses the join loudly, naming the tag and the
allowed characters, rather than silently vanishing from the pushed record
(the record schema's own pattern for `team`/`environment` would otherwise
drop it without a trace). `--hostname` defaults to the machine's own
hostname. `--org` itself must be a single filesystem-safe path component
(`^[a-z0-9][a-z0-9_-]*$`, so no slash and no dot): it becomes part of the
record's path in the store, `fleet/<org>/<machine-id>/<date>.json`, and a
value that could escape that path is refused before anything is written.

Join does four things:

1. Validates `--org`, `--team`, `--environment`, and the day, refusing
   cleanly (before any write) if any fails its pattern.
2. When the store is reachable, reads its `org-profile.json` and refuses if
   `--org` does not match the store's own org, or if `--salt` does not hash
   to the store's `salt_fingerprint`: this is what catches a salt typo
   before it silently creates a phantom `machine_id` for a real machine
   (the org's own salt is verified once, here, rather than trusted blindly
   on every join). An unreachable store skips this check; it never blocks a
   join, the same as every other fleet write in this file.
3. Writes the local fleet config (org, salt, hostname, team, environment,
   store) to `~/.token-shield/fleet-config.json`, private to the account
   (the file and its parent directory are both written with restrictive
   permissions).
4. Pushes one small "registration" record for today, even though the
   machine's telemetry ledger is empty on a brand new install, so the
   machine appears in the store immediately rather than waiting for its
   first real day of usage.

**Nothing about join depends on the store being reachable at that moment,**
except step 2's mismatch check, which is skipped (not failed) when the
store cannot be reached. Step 3 is entirely local. If step 4's push fails
for any reason (offline, no network, store temporarily down), the
registration is queued locally instead, one warning line is printed, and
`fleet join` still exits 0. The machine appears on the dashboard once a
later `fleet push` (or the next `fleet join`) successfully reaches the
store; nothing about being offline blocks the developer from continuing to
work. A symlink found inside the cloned store or the local queue dir is a
different case: that refuses loudly (exit 2) instead, since silently
falling back to the queue would just move the same attack surface rather
than close it.

Running `fleet join` a second time with the same arguments is safe: the
local config is rewritten with the same content, and pushing the same
registration record a second time is a no-op at the git level (nothing
changed, so nothing is committed). It always registers exactly once.

### The MDM one-liner

`scripts/fleet-join.sh` is a small POSIX `sh` wrapper meant for Jamf, or any
MDM that can run a shell script with environment variables set. It requires
`FLEET_STORE`, `FLEET_ORG`, and `FLEET_SALT`; `FLEET_TEAM`, `FLEET_ENVIRONMENT`,
and `FLEET_HOSTNAME` are optional. It looks for `fleet.py` next to itself, so
deploy both files to the same directory on the target machine. One line:

```
FLEET_STORE=git@example.com:org/fleet-store.git \
  FLEET_ORG=acme FLEET_SALT="a-passphrase-only-your-org-uses" \
  FLEET_TEAM=ios sh /path/to/fleet-join.sh
```

`FLEET_SALT` never reaches `fleet.py join`'s command line: a command-line
argument is world-readable via `/proc/PID/cmdline` on Linux for as long as
the process runs, so the script keeps it in the environment instead and
`fleet.py join` reads it from `FLEET_SALT` there when `--salt` is not given
as a flag. `FLEET_HOSTNAME`, when set, is passed as `--hostname`; when
unset, the script tries `scutil --get ComputerName` (macOS) before falling
back to `fleet.py`'s own hostname default, so a fleet's registrations use a
stable, recognizable name rather than whatever a DHCP lease happened to
assign.

The script never swallows a failing exit code: a missing required variable,
a missing `python3`, or a failing `fleet.py join` all stop the script and
propagate the same exit code an MDM's own failure reporting expects.

## `fleet leave`: remove this machine's local config and queue

```
python3 scripts/fleet.py leave
```

Removes every file this machine's fleet participation ever wrote:
`~/.token-shield/fleet-config.json` (or wherever `--config` points) and the
entire local queue directory, `~/.token-shield/fleet-queue/` (or wherever
`--queue-dir` points), including any records still sitting in it because a
past push never reached the store. Before this fix, leave removed only the
config file: `fleet build` and `fleet push` still refused (with a NO DATA
message) once the config was gone, so pushes did stop, but a record queued
from an earlier offline push survived on disk regardless, which made
"uninstalling leaves no trace" false. Running `leave` when the machine was
never joined is a harmless no-op, not an error (both paths were already
absent). Uninstalling the plugin entirely leaves no trace beyond these two
paths, which `leave` (or a plain `rm -rf` on both) already removes.

Running `join` again after `leave` re-registers the machine exactly as a
first join would.

## The unreachable-store rule, stated once

Every fleet write in this file (`init`'s push, `join`'s registration push,
and F1's own `fleet push`) follows the same rule: a store that cannot be
reached never blocks the machine and never raises. `init` is the one
exception, because there is nothing meaningful to create if the store an
admin is trying to initialize cannot be reached at all; every other command
queues its record locally (`~/.token-shield/fleet-queue/` by default) and
prints exactly one warning line.

Nothing in this repo drains that queue automatically: a record queued
because the store was briefly unreachable sits there until a later `fleet
push` (or the next `fleet join`) happens to succeed against the same store
and day. There is no background retry, no cron, no "drain on next push of a
different day". `fleet leave` removes the queue outright (see above); short
of that, an admin who wants a queued record to actually reach the store
today needs to run `fleet push` again once connectivity returns.

## NO DATA beats a guess

A fleet record is never fabricated to look complete. A day with no counters
and no experiment results produces no data-day record at all (F1's `fleet
build` refuses with NO DATA rather than push an all-zero row); the one
exception is `join`'s own registration record, which is honestly a
registration event with zero counters, not a data day pretending to have
some.

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

### A shared store is untrusted input

A fleet store is written to by every machine in the org, so the reader
treats every file in it as hostile until proven otherwise: ANY failure to
load one file (unreadable, invalid JSON, invalid UTF-8, a stack-exhausting
nesting depth, a bare NaN/Infinity number, a negative or missing counter,
oversized, or a schema this reader does not understand) costs only that one
machine its own NO DATA row naming the reason, never the rest of the page.
Concretely:

- **Size cap.** A record file over 1,000,000 bytes is refused by name
  before it is ever read into memory.
- **Symlinks are refused, not followed.** A symlink anywhere under
  `fleet/<org>/` (a whole machine directory, or one record file) is refused
  rather than followed, so a symlink planted in the store can never make
  the page render content from outside it.
- **`--org` is validated**, the same way `fleet init`/`join`/`push` already
  validate it, before it ever reaches a filesystem path or the page
  `<title>`.
- **A record's filename and its own "date" field must agree.** A
  disagreement is refused as that file's own NO DATA row, so the same
  record can never render under two different dates on the same page, and a
  member cannot park tokens on a future day just by writing a different
  date into the record body.
- **The store path printed on the page is shortened**, the same way
  `fleet.py`'s own warnings are, so a shared org artifact never carries the
  admin's account name.

None of this changes what a healthy record looks like or how it renders;
it only bounds what a hostile or malformed one can do to the page around
it.

## The individual-privacy position, stated as a rule you can audit

This is the section to hand to a works council, a data protection
officer, or anyone who asks what the tool does to people. It is written
as a rule rather than a reassurance, so it can be checked.

**The rule: no Token Shield view produces a per-person performance
number.** An organisation-wide page reports aggregates, and it
suppresses any aggregate backed by fewer than a minimum number of
machines rather than publishing a cell that identifies one person. The
per-machine table exists to answer operational questions (did this
machine report, is its data stale) and not to rank people.

Why the rule is this strict, rather than a matter of taste:

- A tool that measures developer behaviour and aggregates it for an
  administrator is inside employee-monitoring law, not next to it.
- The UK Information Commissioner's Office requires an employer to
  identify a lawful basis, be clear about the purpose, and choose the
  **least intrusive means** that achieves it, collecting no more than
  is needed.
- In Germany, section 87(1) no. 6 of the Works Constitution Act gives
  a works council co-determination over introducing technical systems
  capable of monitoring employee behaviour or performance. That right
  attaches to what a system is CAPABLE of, not to what you intend, so
  a per-person view you never open is still a per-person view.
- New York Civil Rights Law 52-c requires prior written notice to
  employees subject to electronic monitoring, acknowledged in writing.

The design consequence: making the per-person number IMPOSSIBLE is
worth more than a policy saying nobody should look at it. A suppressed
cell says it was suppressed and why, because a silently missing number
reads as a measured zero.

The machine identifier is a salted hash of the hostname, not the
hostname. Be honest with your reviewers about the limit of that: the
raw salt is written to every joined machine, so anyone holding a copy
of the store and the salt can hash candidate hostnames and recover the
mapping. It raises the cost of identifying a machine; it does not make
it impossible. Treat the store as internal data, not as anonymised
data, and say so in your own records.

## Retention and erasure

The question a reviewer always asks, answered plainly, including where
the answer is currently uncomfortable.

**What Claude Code itself keeps.** Session transcripts live locally in
plaintext under `~/.claude/projects/` and expire after 30 days by
default, adjustable with `cleanupPeriodDays`. Token Shield derives its
numbers from those files and never extends their life.

**What the fleet store keeps.** Records accumulate in the org's own git
repository and are kept until an administrator removes them. There is
no automatic expiry, which means the store's retention period is
whatever your organisation writes down. Write it down.

**Removing one machine.** `fleet leave` removes that machine's LOCAL
config and queue. It does not, and cannot, remove anything from the
org store. To erase a machine's data an administrator deletes its
directory in the store:

```bash
git rm -r fleet/<org>/<machine-id>
git commit -m "erase machine records on request"
git push
```

**Read this before you promise anyone erasure.** That deletes the files
from the current tree, and git history still contains every earlier
version of them. A real erasure requires rewriting the store's history
(`git filter-repo` or equivalent) and force pushing, which invalidates
every clone. If your organisation has to honour erasure requests, the
practical options are to keep the store's retention window short and
rebuild it periodically, or to treat the store as a system of record
with a documented retention period from the start. Decide which before
you roll out, not after the first request arrives.

## What an administrator sees that a developer does not, which is nothing

Stated plainly because a reviewer will find it anyway: there is no
access control layer. Push access to the store is read and write access
to the whole store, because a push clones it. Any machine that can push
can read every other machine's records, and can rewrite them.

Records are **not signed**. Anything with write access can forge a
record attributed to another machine, and the dashboard will render it
as truth. Git history attributes each record to the machine that claims
to have written it, which is a trail, not a proof.

If that model does not meet your bar, the shape that does is a
write-only ingestion path: per-machine deploy keys against a repository
developers cannot read, with the aggregation running on the ingestion
side. That is not what ships today, and this section exists so nobody
discovers it during a security review instead of before one.
