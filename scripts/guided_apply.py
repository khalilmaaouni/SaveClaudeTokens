#!/usr/bin/env python3
"""
guided_apply.py: the shared contract every wave R guided apply runs through.

Three producers (optimize.py's CLAUDE.md diet, plugin_prune.py, memory_trim.py)
each propose a change of their own shape, in their own review directory, using
their own backup logic. This module carries only the two things all three
actually share:

1. The open-experiment refusal gate. No apply may run while any experiment is
   open, because an apply changes the config fingerprint and would force that
   open experiment's later verdict to NOT_PROVEN. `refuse_if_experiment_open`
   checks this via `experiment.list_open_experiments`, never by guessing.
2. The "run the mutation, verify it, auto-open one experiment" tail. Every
   guided apply calls `mutate_fn()` BEFORE `experiment.cmd_start(...)`, so the
   pinned baseline fingerprint already reflects the change and the experiment
   never trips its own confounder guard. On a verify failure the change is
   left in place (already written by mutate_fn) and NO experiment opens, so a
   bad state never produces a ledger record about itself; the founder reverts
   by hand from the printed backup path.

This module has no stdin confirmation prompt. The "propose it, show the diff,
ask yes, apply" ceremony runs as chat turns driven by a command file
(commands/optimize.md), the same two-invocation split optimize.py's own
propose/--apply already uses: a founder or agent only calls `apply()` here
after the yes was already given in chat.
"""
import contextlib
import hashlib
import json
import os
import sys
import time

import experiment as ex
import config as cfg  # ROOT, EXPERIMENT_DAYS: read from the foundation, never re-declared

# T6.1: the append-only mutation journal. One line per applied mutation
# (timestamp, target path, pre hash, backup path, producer), written by
# backup_file/backup_if_exists/journal_mutation below, which are the shared
# points every producer's mutate_fn already calls to back a target up before
# overwriting it. A module-level path, same seam as ex.EXP_DIR/ex.LEDGER (see
# test_guided_apply.py's _point_exp_at), so a test can redirect it without
# ever touching the founder's real ~/.token-shield/mutations.jsonl.
# ANY test that can reach backup_file, backup_if_exists, or journal_mutation
# (directly or through a producer's cmd_apply/cmd_guided_apply) MUST redirect
# this path first. Use the _point_journal_at/_restore_journal helper pattern
# from test_guided_apply.py, mirrored into every other test file that needs
# it; do not invent a second pattern.
MUTATIONS_LOG = os.path.expanduser("~/.token-shield/mutations.jsonl")

# Which guided-apply run is currently mutating something, set by apply()
# around its call to mutate_fn(). backup_file() reads this to fill the
# journal's "producer" field. The apply() label already names its producer
# module (e.g. "memory-trim-guided-<stamp>", "plugin-prune-<id>-guided-
# <stamp>"), so reusing it needs no new argument threaded through
# optimize.py/memory_trim.py/plugin_prune.py, none of which this task may
# edit. "unknown" when backup_file runs outside any apply() call.
_current_producer = "unknown"


@contextlib.contextmanager
def producer_scope(label):
    """Security-review fix (DEFECT 4): sets _current_producer to label for the
    duration of the `with` block, then restores whatever it was BEFORE the
    block ran, rather than hardcoding it back to "unknown". apply() below used
    to reset to the literal "unknown" in its finally clause, which meant a
    nested apply (an apply() call made from inside another apply()'s
    mutate_fn) clobbered the outer label instead of just borrowing it for its
    own inner mutation. Any direct, non-guided call into backup_file (e.g.
    optimize.py's plain --apply, which never goes through apply() at all and
    used to record "unknown" as its producer) should also open its own scope
    here instead of poking _current_producer by hand."""
    global _current_producer
    previous = _current_producer
    _current_producer = label
    try:
        yield
    finally:
        _current_producer = previous


def refuse_if_experiment_open():
    """None if clear to apply, else a REFUSED string naming every open label
    and the exact command to close each one, matching the refusal wording
    style experiment.py's own cmd_end overlap refusal already uses.

    experiment.list_open_experiments() fails CLOSED: a baseline file it could
    not read or parse comes back as a marker dict carrying "_unreadable"
    instead of being silently skipped, because a file that cannot be read
    might be a genuinely open experiment whose write got interrupted. Those
    markers get their own line here, naming the file rather than a label,
    since there is no command that can close a baseline nobody can read."""
    open_now = ex.list_open_experiments()
    if not open_now:
        return None
    lines = ["REFUSED: an experiment is already open. Applying now would change "
             "the config that experiment is measuring and would force its "
             "verdict to NOT_PROVEN when it later closes."]
    for baseline in open_now:
        unreadable = baseline.get("_unreadable")
        if unreadable:
            lines.append(f'  - {unreadable} is unreadable or unparseable; cannot '
                         f'confirm whether it is an open experiment. Fix or remove '
                         f'that file by hand before applying.')
            continue
        label = baseline.get("label")
        started = baseline.get("started")
        lines.append(f'  - "{label}" started {started}. Close it first: '
                     f'python3 experiment.py end "{label}"')
    return "\n".join(lines)


def refuse_if_target_mismatch(cli_path, stored_path):
    """None if cli_path and stored_path resolve to the same file, else a
    REFUSED string naming both. A guided apply's mutate_fn always mutates the
    file the STORED proposal points at, never the path handed to it, so a
    caller naming a different file at apply time must be refused before
    anything runs, rather than silently mutate one file while verifying and
    excluding another."""
    a = os.path.abspath(os.path.expanduser(cli_path))
    b = os.path.abspath(os.path.expanduser(stored_path))
    if a == b:
        return None
    return (f"REFUSED: the file named at apply time does not match the proposal's "
            f"stored target. Named at apply: {cli_path}. Proposal target: "
            f"{stored_path}. Re-propose against {cli_path}, or apply naming "
            f"{stored_path}.")


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _abs(path):
    """None-safe os.path.abspath(os.path.expanduser(...)). DEFECT 2: the
    journal used to record whatever string a caller passed in verbatim, so an
    --apply run against a relative --file (e.g. "CLAUDE.md") journaled a
    relative target. An undo run later from a different working directory
    would then resolve that relative path against the WRONG directory. Every
    path written to the journal goes through this first."""
    if not path:
        return path
    return os.path.abspath(os.path.expanduser(path))


def unique_backup_path(path, stamp=None):
    """Returns a '<path>.bak-<stamp>' backup path guaranteed not to already
    exist. DEFECT 1 (security review, pre-existing data loss): time.strftime's
    stamp only has one-second resolution, so two backups of the same target
    inside the same wall-clock second used to collide on the identical
    filename, and the second backup_file call silently overwrote the first
    backup on disk, losing the earlier version entirely (the journal still
    held two lines with that same backup_path but two different pre_hash
    values, one of them describing bytes that no longer existed anywhere).
    When the plain stamped path is already taken, a numeric suffix is added
    and bumped until a free path is found. Shared by backup_file below AND by
    optimize.cmd_apply's own inline backup (which must keep writing from its
    already-read, already-verified 'original' string rather than re-reading
    the file through here, so only the PATH CHOICE is shared, not the read)."""
    stamp = stamp or time.strftime("%Y%m%d-%H%M%S")
    candidate = f"{path}.bak-{stamp}"
    n = 2
    while os.path.exists(candidate):
        candidate = f"{path}.bak-{stamp}-{n}"
        n += 1
    return candidate


def _append_mutation(target_path, pre_hash, backup_path, producer, created=False):
    """Appends one JSON line to MUTATIONS_LOG. Append-only: opens in 'a' mode
    and never reads, seeks, rewrites, or truncates the file, so a second
    mutation of the same target adds a second line and leaves every earlier
    line, corrupt or not, exactly as it was; nothing here ever parses what is
    already in the file, which is also why a corrupt or unreadable existing
    journal cannot lose or block the new record.

    target_path and backup_path are normalised to absolute paths before being
    written (DEFECT 2, see _abs above); backup_path may be None (see created
    below) and stays None rather than being turned into an absolute path.

    created=True marks a line where the mutation CREATED target_path (it did
    not exist before), rather than backing up and overwriting an existing
    one. DEFECT 3: backup_if_exists used to return None and write NOTHING to
    the journal when the target did not exist yet, so an apply that created a
    file (claude-history.md, memory-archive.md on their first write) left no
    trace at all; a later undo built on the journal would not know to delete
    it and would silently leave it behind. A created line always carries
    pre_hash=None and backup_path=None (there was nothing to hash or back up)
    plus created=True, so it is never mistaken for a normal mutation line.

    A journal-write failure (missing/unwritable ~/.token-shield, full disk,
    permissions, or a field that json.dumps cannot serialise) is caught and
    reported loudly on stderr, never raised and never silent: the backup this
    line would describe has already been written by the time this runs, and
    the caller is about to overwrite the real target next, so raising here
    would abort a legitimate apply over a logging side channel. Losing one
    history line is recoverable (the per-proposal .sha256 file and the backup
    path printed to the user still exist); losing or blocking the founder's
    actual change would not be."""
    record = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "target": _abs(target_path),
        "pre_hash": pre_hash,
        "backup_path": _abs(backup_path),
        "producer": producer or "unknown",
        "created": bool(created),
    }
    try:
        journal_dir = os.path.dirname(MUTATIONS_LOG)
        if journal_dir:
            os.makedirs(journal_dir, exist_ok=True)
        with open(MUTATIONS_LOG, "a") as f:
            f.write(json.dumps(record) + "\n")
    except (OSError, TypeError) as e:
        # OSError: journal file/dir unwritable. TypeError: json.dumps choked
        # on a field it cannot serialise (DEFECT 5: this used to catch only
        # OSError, so a non-serialisable field crashed the apply outright,
        # well after the real mutation had already happened).
        print(f"WARNING: mutation journal not written to {MUTATIONS_LOG} ({e}). "
              f"The mutation of {target_path} itself still applied; only this "
              f"history line is missing. Backup remains at {backup_path}.",
              file=sys.stderr)


def journal_mutation(target_path, pre_hash, backup_path, producer=None, created=False):
    """Public entry point to append one line to the mutation journal, for a
    caller that writes its own backup instead of going through backup_file
    (see optimize.cmd_apply, which backs the flagship CLAUDE.md diet target
    up from the 'original' string it already read and hashed for its own
    staleness check, deliberately not re-reading the file through
    backup_file, which would reopen the window between that check and the
    backup). Defers to _append_mutation, the single journal writer backup_file
    itself also calls, so there is exactly one place that writes
    MUTATIONS_LOG and the journal line's shape can never drift between the
    two paths. producer defaults to whatever apply() has set as the current
    producer (see _current_producer above), same default backup_file uses."""
    _append_mutation(target_path, pre_hash, backup_path, producer or _current_producer,
                     created=created)


def backup_file(path):
    """Mirrors optimize.cmd_apply's own backup: a unique_backup_path stamp,
    '<path>.bak-<stamp>' (or a numeric-suffixed variant when that collides,
    see unique_backup_path/DEFECT 1), full read then full write. Returns the
    backup path.
    Also appends one line to the mutation journal (see _append_mutation):
    this is the one place every producer's mutate_fn already calls to back a
    target up, so it is also the one place that already has the pre-mutation
    content in hand to hash, with no second hashing helper or second backup
    mechanism needed."""
    backup = unique_backup_path(path)
    with open(path) as f:
        original = f.read()
    with open(backup, "w") as f:
        f.write(original)
    _append_mutation(path, sha256_text(original), backup, _current_producer)
    return backup


def backup_if_exists(path):
    """Like backup_file, but a no-op on disk (returns None, backs up nothing)
    when path does not exist yet. Used before an archive/history file gets
    written to, so a pre-existing archive is never silently overwritten, and
    a first-ever write (nothing there to back up) is not an error.
    DEFECT 3: when path does not exist, this still writes ONE journal line
    marking the coming write as a creation (see _append_mutation's created
    param), so an apply that creates a file is not invisible to the journal
    just because there was nothing to back up. The return value is unchanged
    (still None for callers that only care whether a backup was made)."""
    if not os.path.exists(path):
        _append_mutation(path, None, None, _current_producer, created=True)
        return None
    return backup_file(path)


def apply(label, treats, mutate_fn, verify_fn):
    """The one shared tail. mutate_fn(): zero-arg, already does its own backup
    and write (each producer module keeps this itself, see design decision 2
    in docs/superpowers/plans/2026-08-13-solid-core-waveR-plan.md). mutate_fn
    returns an int rc: 0 (or any other falsy value, e.g. None from a lambda
    with no explicit return) means it actually applied something; any truthy
    (nonzero) rc means nothing was applied (a NO DATA no-op, a stale-source
    refusal, a missing proposal), and that rc propagates here untouched, with
    no verify step and no experiment opened for a change that never happened.
    verify_fn(): zero-arg, returns (ok: bool, report: str), run only after a
    successful mutate_fn.
    Refuses before mutate_fn runs if any experiment is open.
    On success, opens one experiment (mutate_fn already ran, so the fingerprint
    pinned here already reflects the change, see design decision 3).
    Returns (rc, message): rc 2 refused (experiment open), mutate_fn's own
    nonzero rc when it declined to apply anything, rc 1 verify failed (change
    stands, no experiment opened), rc 0 applied and experiment opened."""
    refusal = refuse_if_experiment_open()
    if refusal:
        return 2, refusal

    with producer_scope(label):
        mutate_rc = mutate_fn()
    if mutate_rc:
        return mutate_rc, ("nothing was applied, so no verification ran and no "
                           "experiment was opened. See the message above for why.")

    ok, report = verify_fn()
    if not ok:
        return 1, (f"applied, but verification failed, so no experiment was "
                    f"opened. The change is left in place; revert by hand from "
                    f"the backup this apply printed. Verify report: {report}")

    now = time.time()
    ex.cmd_start(label, cfg.ROOT, cfg.EXPERIMENT_DAYS, now, treats)
    close_by = time.strftime("%Y-%m-%d", time.gmtime(now + cfg.EXPERIMENT_DAYS * 86400))
    return 0, (f"applied and verified ({report}). Experiment '{label}' opened "
               f"to prove it; earliest clean close date {close_by} (start plus "
               f"the {cfg.EXPERIMENT_DAYS:g}-day window). Close it then with: "
               f'python3 experiment.py end "{label}"')
