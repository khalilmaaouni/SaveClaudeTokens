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
import time

import experiment as ex
import cli as ts_cli  # ROOT, EXPERIMENT_DAYS: reused, never re-declared


def refuse_if_experiment_open():
    """None if clear to apply, else a REFUSED string naming every open label
    and the exact command to close each one, matching the refusal wording
    style experiment.py's own cmd_end overlap refusal already uses."""
    open_now = ex.list_open_experiments()
    if not open_now:
        return None
    lines = ["REFUSED: an experiment is already open. Applying now would change "
             "the config that experiment is measuring and would force its "
             "verdict to NOT_PROVEN when it later closes."]
    for baseline in open_now:
        label = baseline.get("label")
        started = baseline.get("started")
        lines.append(f'  - "{label}" started {started}. Close it first: '
                     f'python3 experiment.py end "{label}"')
    return "\n".join(lines)


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


def apply(label, treats, mutate_fn, verify_fn):
    """The one shared tail. mutate_fn(): zero-arg, already does its own backup
    and write (each producer module keeps this itself, see design decision 2
    in docs/superpowers/plans/2026-08-13-solid-core-waveR-plan.md). verify_fn():
    zero-arg, returns (ok: bool, report: str), run only after mutate_fn.
    Refuses before mutate_fn runs if any experiment is open.
    On success, opens one experiment (mutate_fn already ran, so the fingerprint
    pinned here already reflects the change, see design decision 3).
    Returns (rc, message): rc 2 refused, rc 1 verify failed (change stands,
    no experiment opened), rc 0 applied and experiment opened."""
    refusal = refuse_if_experiment_open()
    if refusal:
        return 2, refusal

    mutate_fn()
    ok, report = verify_fn()
    if not ok:
        return 1, (f"applied, but verification failed, so no experiment was "
                    f"opened. The change is left in place; revert by hand from "
                    f"the backup this apply printed. Verify report: {report}")

    ex.cmd_start(label, ts_cli.ROOT, ts_cli.EXPERIMENT_DAYS, time.time(), treats)
    return 0, (f"applied and verified ({report}). Experiment '{label}' opened "
               f"to prove it; close it later with: python3 experiment.py end "
               f'"{label}"')
