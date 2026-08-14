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
import hashlib
import os
import time

import experiment as ex
import cli as ts_cli  # ROOT, EXPERIMENT_DAYS: reused, never re-declared


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


def backup_file(path):
    """Mirrors optimize.cmd_apply's own backup, lines 195-199 of optimize.py:
    time.strftime stamp, '<path>.bak-<stamp>', full read then full write.
    Returns the backup path."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = f"{path}.bak-{stamp}"
    with open(path) as f:
        original = f.read()
    with open(backup, "w") as f:
        f.write(original)
    return backup


def backup_if_exists(path):
    """Like backup_file, but a no-op (returns None) when path does not exist
    yet. Used before an archive/history file gets written to, so a pre-
    existing archive is never silently overwritten, and a first-ever write
    (nothing there to back up) is not an error."""
    if not os.path.exists(path):
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
    ex.cmd_start(label, ts_cli.ROOT, ts_cli.EXPERIMENT_DAYS, now, treats)
    close_by = time.strftime("%Y-%m-%d", time.gmtime(now + ts_cli.EXPERIMENT_DAYS * 86400))
    return 0, (f"applied and verified ({report}). Experiment '{label}' opened "
               f"to prove it; earliest clean close date {close_by} (start plus "
               f"the {ts_cli.EXPERIMENT_DAYS:g}-day window). Close it then with: "
               f'python3 experiment.py end "{label}"')
