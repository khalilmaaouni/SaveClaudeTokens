#!/usr/bin/env python3
"""
plugin_prune.py: propose a named bundle of plugins to disable, then apply it
only on an explicit yes, proven with an auto-opened experiment.

This tool never picks plugins for you. `context_lint.py` has no per-plugin
finding, and no file in this repo currently measures per-plugin usage
(automatic zero-use detection is out of scope for wave R; it is the natural
next step once discover_companions.py/doctor.py exist to supply real
usage-adjacent data). A prune bundle is therefore a founder-named or
agent-named list of currently-installed plugin ids, picked by reading
`claude plugin list --json`'s own output, never inferred.

ARGUMENT FORM (Ambiguity 1, `docs/superpowers/plans/2026-08-13-solid-core-waveR-plan.md`):
`claude plugin --help` documents only a positional `[plugin]` for both
`disable` and `enable`, with no stated format. The plan's own step 4 first
action would normally be a live disable/enable round trip on one real
installed plugin to confirm whether a bare name works. Wave R's build session
deliberately did NOT run that round trip: a live disable/enable on this
machine can drift ~/.claude.json and the plugin cache dirs, which sit inside
the open claude-md-diet-v2 experiment's config fingerprint (plugin
directories are hashed by compute_fingerprint and are NOT excludable by
--treats, see fact row in the plan's grounding table) and would force that
open experiment's verdict to NOT_PROVEN.

Resolved conservatively instead: this module always passes the FULL `id`
field exactly as `claude plugin list --json` prints it (confirmed real shape,
read-only call, this session):

  claude plugin list --json | head
  [
    {
      "id": "adobe-for-creativity@claude-plugins-official",
      "version": "1.1.0",
      "scope": "user",
      "enabled": false,
      ...
    },
    ...
  ]

So a bundle name must be the exact `<name>@<marketplace>` string, never a
bare name. Whether the bare-name form also works is UNVERIFIED pending a
live round trip run after the open experiment reaches a verdict; see
docs/CLAIMS.md.

USAGE
  python3 plugin_prune.py propose <id> [<id> ...] --bundle-id <bundle-id>
  python3 plugin_prune.py apply <bundle-id>
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

import guided_apply
import optimize

# R7/MAJOR: the strict plugin-id charset. Letters, digits, dot, underscore,
# at sign, hyphen; a hyphen is refused as the FIRST character because that is
# what makes a name indistinguishable from a CLI flag ("--all", "-a"). Any
# name failing this is refused by name, both at propose time and again at
# apply time (the bundle file is trusted data on disk, not a fresh input, but
# a tampered or hand-edited file is not this tool's problem to trust either).
PLUGIN_NAME_RE = re.compile(r"^[A-Za-z0-9._@][A-Za-z0-9._@-]*$")


def _valid_plugin_name(name):
    return isinstance(name, str) and bool(PLUGIN_NAME_RE.match(name))


def list_plugins():
    """subprocess.run(['claude', 'plugin', 'list', '--json']), parsed. Returns
    the real list of dicts (id, version, scope, enabled, ...) or raises with a
    clear message if the CLI is missing or the output is not valid JSON;
    never guesses a shape."""
    try:
        r = subprocess.run(["claude", "plugin", "list", "--json"],
                           capture_output=True, text=True, check=False)
    except FileNotFoundError as e:
        raise RuntimeError(f"'claude' CLI not found on PATH: {e}") from e
    if r.returncode != 0:
        raise RuntimeError(
            f"'claude plugin list --json' exited {r.returncode}: {r.stderr.strip()}")
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"'claude plugin list --json' did not print valid JSON: {e}") from e
    if not isinstance(data, list):
        raise RuntimeError("'claude plugin list --json' did not print a JSON array")
    return data


def _disable_cmd(plugin_id):
    return ["claude", "plugin", "disable", plugin_id]


def _enable_cmd(plugin_id):
    return ["claude", "plugin", "enable", plugin_id]


def _bundle_path(bundle_id):
    return os.path.join(optimize.review_dir(), f"plugin-prune-{bundle_id}.json")


def cmd_propose_bundle(names, bundle_id):
    """names: plugin ids the founder/agent picked from list_plugins()'s own
    output, never inferred (see module docstring: the full id, never a bare
    name). Writes a review file to ~/.token-shield/optimize/ (reuses
    optimize.review_dir(), same directory, same never-touch-anything-live
    contract) holding only the reviewed NAMES (R7/MAJOR: never argv; see
    cmd_apply_bundle), and prints each name's exact disable command and its
    exact matching enable command (the revert) for the founder to read
    before saying yes. Never calls subprocess itself."""
    if not names:
        print("NO DATA: no plugin names given.")
        return 2
    invalid = [n for n in names if not _valid_plugin_name(n)]
    if invalid:
        print(f"NO DATA: {len(invalid)} name(s) fail the plugin-id charset (letters, "
              f"digits, dot, underscore, at sign, hyphen never first): {invalid!r}. "
              f"Refusing rather than build a shell command from anything else.")
        return 2
    try:
        known = {p.get("id") for p in list_plugins()}
    except RuntimeError as e:
        print(f"NO DATA: cannot read the plugin list ({e}).")
        return 2
    unknown = [n for n in names if n not in known]
    if unknown:
        print(f"NO DATA: {len(unknown)} name(s) not found in `claude plugin list "
              f"--json` output: {', '.join(unknown)}. Pass the exact id field "
              f"(name@marketplace) that command prints; a bare name is not a "
              f"confirmed form (see this file's module docstring).")
        return 2
    bundle = {"bundle_id": bundle_id, "names": list(names)}
    path = _bundle_path(bundle_id)
    with open(path, "w") as f:
        json.dump(bundle, f, indent=2)
    print(f"=== proposed plugin prune bundle '{bundle_id}' ===")
    for n in names:
        print(f"  disable: {' '.join(_disable_cmd(n))}")
    print("revert (re-enable) with:")
    for n in names:
        print(f"  {' '.join(_enable_cmd(n))}")
    print(f"\nreview: {path}")
    print(f"apply:  python3 plugin_prune.py apply {bundle_id}")
    return 0


def cmd_apply_bundle(bundle_id):
    """Reads the review file cmd_propose_bundle wrote. This IS the mutate_fn
    passed to guided_apply.apply: reconstructs each disable/enable command
    from the bundle's "names" field ONLY, re-validated against the same
    strict charset propose already checked (R7/MAJOR: the bundle file used to
    store literal argv and run it verbatim, so a tampered or hand-edited
    bundle file could execute anything; commands are built fresh here from
    names, never read as argv off disk). Runs each disable command in order,
    prints each result, prints the full set of enable commands as the revert
    line. No file backup (there is nothing to back up: a plugin disable is
    reversed by its own enable command)."""
    path = _bundle_path(bundle_id)
    if not os.path.exists(path):
        print(f"NO DATA: no proposed bundle '{bundle_id}'. Run propose first.")
        return 2
    with open(path) as f:
        bundle = json.load(f)
    names = bundle.get("names") or []
    invalid = [n for n in names if not _valid_plugin_name(n)]
    if invalid:
        print(f"REFUSED: the bundle file names {invalid!r}, which fail the plugin-id "
              f"charset; refusing to build a command from any of it.")
        return 2
    for n in names:
        cmd = _disable_cmd(n)
        r = subprocess.run(cmd, capture_output=True, text=True)
        status = "ok" if r.returncode == 0 else f"FAILED ({r.returncode}): {r.stderr.strip()}"
        print(f"  {' '.join(cmd)}  ->  {status}")
    print("revert (re-enable) with:")
    for n in names:
        print(f"  {' '.join(_enable_cmd(n))}")
    return 0


def verify_bundle(names):
    """Re-runs list_plugins(), confirms every name in names now shows
    enabled: False. Returns (ok, report).
    R6/MAJOR: a name absent from the plugin list entirely is NOT confirmed
    disabled (NO DATA is not disabled-confirmed) and is reported separately
    from one that is still actively enabled.
    A `claude` CLI failure mid-verify (list_plugins raising) is a verify
    failure too, not an uncaught crash: the disables may already have run, so
    guided_apply.apply's own "applied, but verification failed" path (which
    leaves the change in place and opens no experiment) is the honest way to
    surface it."""
    try:
        plugins = {p.get("id"): p for p in list_plugins()}
    except RuntimeError as e:
        return False, f"cannot verify: {e}"
    still_enabled = []
    absent = []
    for n in names:
        p = plugins.get(n)
        if p is None:
            absent.append(n)
        elif p.get("enabled"):
            still_enabled.append(n)
    problems = []
    if still_enabled:
        problems.append(f"still enabled: {', '.join(still_enabled)}")
    if absent:
        problems.append(f"absent from the plugin list, not confirmed disabled: "
                        f"{', '.join(absent)}")
    if problems:
        return False, "; ".join(problems)
    return True, f"{len(names)} plugin(s) confirmed disabled"


def cmd_guided_apply_bundle(bundle_id):
    """The wave R entry point. Reads the proposed bundle's names (verify_bundle
    needs them), then calls guided_apply.apply(label, treats=None,
    mutate_fn=cmd_apply_bundle, verify_fn=lambda: verify_bundle(names)).
    treats=None: plugin directories are not excludable by --treats at all
    today (see module docstring); ordering, not exclusion, is what keeps this
    experiment from tripping its own confounder guard, since guided_apply.apply
    always pins the baseline AFTER mutate_fn runs."""
    path = _bundle_path(bundle_id)
    if not os.path.exists(path):
        print(f"NO DATA: no proposed bundle '{bundle_id}'. Run propose first.")
        return 2
    with open(path) as f:
        bundle = json.load(f)
    names = bundle.get("names") or []
    label = f"plugin-prune-{bundle_id}-guided-{time.strftime('%Y%m%d-%H%M%S')}"
    rc, msg = guided_apply.apply(label, None, lambda: cmd_apply_bundle(bundle_id),
                                 lambda: verify_bundle(names))
    print(msg)
    return rc


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    sub = ap.add_subparsers(dest="action")
    p_propose = sub.add_parser("propose", help="propose a named bundle of plugins to disable")
    p_propose.add_argument("names", nargs="+", help="exact plugin ids (name@marketplace)")
    p_propose.add_argument("--bundle-id", required=True)
    p_apply = sub.add_parser("apply", help="apply a proposed bundle via guided apply")
    p_apply.add_argument("bundle_id")
    a = ap.parse_args(argv)
    if a.action == "propose":
        return cmd_propose_bundle(a.names, a.bundle_id)
    if a.action == "apply":
        return cmd_guided_apply_bundle(a.bundle_id)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
