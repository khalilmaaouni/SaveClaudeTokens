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
4. Writes `org-profile.json` at the store root: `org`, `salt`, `default_mode`,
   `telemetry: "counters_only"` (the only value F1 through F2 ever write),
   and `push_cadence: "manual"`.
5. Creates the `fleet/` directory the per-machine records will live under.
6. Commits and pushes.

The org's salt is not a secret in the cryptographic sense (nobody outside
the org's own store needs it), but every machine that joins must be given
the **exact same value**, or the same hostname hashes to a different
`machine_id` on different machines and the fleet's own records stop lining
up. Keep it in whatever secret store the org already uses to distribute the
join command.

## `fleet join`: register one machine

```
python3 scripts/fleet.py join <store-git-url> \
  --org acme --salt "a-passphrase-only-your-org-uses" \
  --team ios --environment ci
```

`--org` and `--salt` are the exact values `fleet init` used. `--team` and
`--environment` are free tags (any string your org finds useful, for
example `ios` or `staging`); both are optional. `--hostname` defaults to the
machine's own hostname.

Join does two things:

1. Writes the local fleet config (org, salt, hostname, team, environment,
   store) to `~/.token-shield/fleet-config.json`, private to the account
   (the file and its parent directory are both written with restrictive
   permissions).
2. Pushes one small "registration" record for today, even though the
   machine's telemetry ledger is empty on a brand new install, so the
   machine appears in the store immediately rather than waiting for its
   first real day of usage.

**Nothing about join depends on the store being reachable at that moment.**
Step 1 is entirely local. If step 2's push fails for any reason (offline,
no network, store temporarily down), the registration is queued locally
instead, one warning line is printed, and `fleet join` still exits 0. The
machine appears on the dashboard once a later `fleet push` (or the next
`fleet join`) successfully reaches the store; nothing about being offline
blocks the developer from continuing to work.

Running `fleet join` a second time with the same arguments is safe: the
local config is rewritten with the same content, and pushing the same
registration record a second time is a no-op at the git level (nothing
changed, so nothing is committed). It always registers exactly once.

### The MDM one-liner

`scripts/fleet-join.sh` is a small POSIX `sh` wrapper meant for Jamf, or any
MDM that can run a shell script with environment variables set. It requires
`FLEET_STORE`, `FLEET_ORG`, and `FLEET_SALT`; `FLEET_TEAM` and
`FLEET_ENVIRONMENT` are optional. It looks for `fleet.py` next to itself, so
deploy both files to the same directory on the target machine. One line:

```
FLEET_STORE=git@example.com:org/fleet-store.git \
  FLEET_ORG=acme FLEET_SALT="a-passphrase-only-your-org-uses" \
  FLEET_TEAM=ios sh /path/to/fleet-join.sh
```

The script never swallows a failing exit code: a missing required variable,
a missing `python3`, or a failing `fleet.py join` all stop the script and
propagate the same exit code an MDM's own failure reporting expects.

## `fleet leave`: remove this machine's local config

```
python3 scripts/fleet.py leave
```

Deletes the local fleet config file. There is nothing else to undo: `fleet
build` and `fleet push` already refuse (with a NO DATA message) when no
local config exists, so once the config is gone, nothing on the machine
pushes anywhere again. Running `leave` when the machine was never joined is
a harmless no-op, not an error. Uninstalling the plugin entirely leaves no
trace beyond this one file, which `leave` (or a plain `rm`) already removes.

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

## NO DATA beats a guess

A fleet record is never fabricated to look complete. A day with no counters
and no experiment results produces no data-day record at all (F1's `fleet
build` refuses with NO DATA rather than push an all-zero row); the one
exception is `join`'s own registration record, which is honestly a
registration event with zero counters, not a data day pretending to have
some.
