#!/usr/bin/env python3
"""
cli.py: one entry point for Token Shield.

START HERE (three commands are a whole first run)
  python3 cli.py summary             where your tokens went and the one biggest
                                      thing you could still cut. This is also
                                      what runs with no argument at all.
  python3 cli.py experiment start|end <label> [--treats PATH]
                                      prove a change: start before you make it,
                                      end after, and the ledger judges it
  python3 cli.py dashboard           render the HTML dashboard and print its path

ADVANCED
  python3 cli.py experiment report   one row per experiment label, from the
                                      ledger (never summed across labels)
  python3 cli.py prices              per-model API-list-price equivalent of the
                                      native caching saving (not money anyone
                                      saved: the command says so first)
  python3 cli.py optimize            propose a safe, reversible CLAUDE.md diet
  python3 cli.py prune propose <id> [<id> ...] --bundle-id <bundle-id>
                                      propose a named bundle of plugins to
                                      disable (plugin_prune.py)
  python3 cli.py prune apply <bundle-id>
                                      apply a proposed prune bundle via
                                      guided apply (refuses if any experiment
                                      is open, auto-opens one on success)
  python3 cli.py trim [--file PATH]  propose trimming the auto-memory index
                                      back inside its load limit (defaults to
                                      this project's own index; memory_trim.py)
  python3 cli.py trim apply          apply the last trim proposal via guided
                                      apply (same refuse/verify/auto-experiment
                                      contract as prune above)
  python3 cli.py profile             deterministic session profile (profile.py)
  python3 cli.py advise              ranked next-move cards (advisor.py)
  python3 cli.py advise --decide <strategy-id> <done|not-now|never>
                                      record a card decision (treatment memory)
  python3 cli.py report              monthly report; --month YYYY-MM --out PATH
  python3 cli.py doctor              read-only ecosystem doctor: health,
                                      staleness, shared-hook facts (doctor.py)
  python3 cli.py uninstall           remove local Token Shield data: prints
                                      what exists, requires typing YES, deletes
  python3 cli.py uninstall --yes     the same, without the prompt. The only
                                      form that works from a management tool
                                      or a script: without it and without a
                                      terminal the command refuses and
                                      deletes nothing
  python3 cli.py -h | --help         this text
  python3 cli.py -V | --version      the installed version, read from
                                      .claude-plugin/plugin.json

The scripts underneath (measure_tokens, token_shield, pricing, experiment,
optimize, profile, advisor, report) stay the source of truth; this only
routes to them and never re-implements a metric. Kept small deliberately: a
command per feature is how a small tool turns into a sprawling one.
"""

import json
import os
import sys

import measure_tokens as mt
import config as cfg
import token_shield as ts
import metrics as met
import pricing as pr
import experiment as ex

# Aliases, not declarations: config.py owns both values now, and these two
# names stay here because they are a SEAM. Several tests monkeypatch cli.ROOT
# to point a run at a fixture directory, so rewriting this module's internals
# to read cfg.ROOT directly would leave those patches silently ineffective and
# the tests measuring this machine's real transcripts while still passing.
ROOT = cfg.ROOT
EXPERIMENT_DAYS = cfg.EXPERIMENT_DAYS

OUT = os.path.expanduser("~/.token-shield/token-shield.html")


def _verified_by_label():
    """VERIFIED floor changes, one row per label, in ledger order.

    Never summed across labels: two labels measure two different changes, and
    adding them produces a number neither experiment ever measured. Repeated
    runs of the same label collapse to the LATEST record, because they
    re-measure the same change and adding them counts it twice. A regression
    stays negative; clipping it to zero would hide a change that cost tokens.
    """
    if not os.path.exists(ex.LEDGER):
        return []
    rows = []
    with open(ex.LEDGER, errors="ignore") as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # sbe: allow-silent a ledger line that will not parse is skipped so one corrupt line cannot hide every verified experiment on the machine
    # Newest row per label FIRST (the shared rule), THEN the VERIFIED filter.
    # Reversed, as it was, a later NOT_PROVEN run did not supersede an earlier
    # VERIFIED one, so this kept reporting a proven saving for a claim the
    # newest run could not reproduce.
    out = []
    for label, r in met.latest_row_per_label(rows).items():
        if r.get("confidence") != "VERIFIED":
            continue
        fr = r.get("floor_reduction_tokens")
        if fr is None:
            continue
        out.append((label, fr))
    return out


def _print_verified_rows(rows, indent):
    for label, fr in rows:
        tail = ("fewer startup tokens per call" if fr >= 0
                else "MORE startup tokens per call (regression)")
        print(f"{indent}{label:<26} {fr:+,}  {tail}")


def state_line(verified):
    """The one top line state, as "STATE: <state> (<reason>)".

    Read through metrics.command_center_state and NEVER recomputed here. That
    function is the single source of truth for which of the four states shows,
    so the terminal, the dashboard panel and any later surface all say the same
    thing on the same day. A second copy of the priority order in this file is
    exactly the drift the state model memo exists to prevent.

    Every primitive is gathered defensively and degrades to a value the state
    function already handles: advise_result of None returns NO DATA rather than
    raising, which mirrors token_shield.py's own "degrade, do not take the
    render down" shape at its main() (lines 1115 to 1132). This line is the
    FIRST thing summary() prints, so it must never be the thing that stops the
    command running.
    """
    open_experiments = []
    advise_result = None
    strategy_count = 0
    try:
        open_experiments = ex.list_open_experiments() or []
    except (OSError, ValueError) as e:
        print(f"note: open experiments not read ({e})", file=sys.stderr)
    try:
        import advisor as adv
        profile = met.load_profile(adv.PROFILE_PATH)
        if profile is not None:
            strategies = adv.load_strategies()
            strategy_count = len(strategies)
            advise_result = adv.advise(profile, adv.load_treatments(), strategies)
    except (OSError, ValueError, ImportError) as e:
        print(f"note: advisor skipped ({e})", file=sys.stderr)
    state, reason = met.command_center_state(
        open_experiments, advise_result, verified, strategy_count)
    return f"STATE: {state} ({reason})"


def summary(days=30):
    if not os.path.isdir(ROOT):
        print("NO DATA: no Claude Code transcripts found.")
        return 2
    # One scan, reused. Collecting twice read every transcript on disk twice
    # and doubled the wait on the exact command a stranger is told to run
    # first. The line goes to stderr so a pipe stays clean, and it goes out
    # before the scan so the screen is never blank while a first timer decides
    # the thing has hung.
    print(f"Reading your Claude Code transcripts under {ROOT} (last {days:g} "
          "days). On a long history this takes a minute.", file=sys.stderr)
    sessions = mt.collect(ROOT, days)
    sm = mt.summarize(sessions)
    if not sm:
        print("NO DATA: no transcripts carried usage counters yet.")
        return 0
    sv = met.savings_breakdown(sm)
    native = sv["saved"]
    rx = met.prescriptions(sm, sessions)
    # The largest lever, never the sum. The levers overlap (they all cut the
    # same startup floor), so summing them double counts, and trial.py already
    # takes the max: a stranger who runs the trial and then this command has to
    # see one number, not two that contradict each other.
    tool = max((r["saving"] for r in rx), default=0)
    ver = _verified_by_label()

    # The state line goes FIRST, before the product's own name, because it is
    # the one sentence that tells the user whether anything below it can be
    # trusted. A NO DATA state above a wall of numbers is the whole point.
    print(state_line(ver))
    print("Token Shield")
    if ver:
        print("  VERIFIED     latest measured floor change per experiment "
              "(never summed across experiments):")
        _print_verified_rows(ver, "                 ")
    else:
        print("  VERIFIED     none yet. Run: python3 cli.py experiment start \"my-change\"")
    print(f"  NATIVE       {native/1e9:.1f}B token-units saved by Claude Code's caching "
          f"(Anthropic's, not this tool){ts.native_note(sv)}")
    print(f"  OPPORTUNITY  {tool/1e6:.0f}M token-units you could still cut (estimated, "
          f"from your own sessions)")
    if rx:
        top = max(rx, key=lambda r: r["saving"])
        print(f"\n  Top issue: {top['title']}")
        print(f"  Fix: {top['painkiller']}")
    print("\n  Prove it:  python3 cli.py experiment start \"my-change\"")
    print("  See it:    python3 cli.py dashboard")
    print("  In USD:    python3 cli.py prices")
    return 0


def dashboard(days=30):
    import subprocess
    here = os.path.dirname(os.path.abspath(__file__))
    r = subprocess.run([sys.executable, os.path.join(here, "token_shield.py"),
                        "--out", OUT, "--days", str(days)], capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    if r.returncode == 0:
        print(f"open it:  {OUT}")
    else:
        sys.stderr.write(r.stderr)
    return r.returncode


def prices(days=90):
    pricing = pr.load_pricing()
    import time
    res = pr.price_saving(pr.saving_by_model(ROOT, days), pricing, time.strftime("%Y-%m-%d"))
    if res["status"] == "NO_PRICE_DATA":
        print(f"NO PRICE DATA: {res['reason']}. Saving still measured: "
              f"{res['saved_units']/1e9:.2f}B units.")
        return 0
    # The caveat leads, on its own line, before any figure. It used to sit at
    # the tail of the total line, in the same weight, under a six figure
    # headline: a reader takes the number and leaves the caveat there. The
    # grand total is gone with it, because summed these rows become one big
    # number that travels alone, and the saving it describes is Anthropic's
    # caching doing its job, never anything this tool did.
    print("This is not money you saved.")
    print("Claude Code's caching (Anthropic's own mechanism, not Token Shield) "
          "kept these tokens off the wire for you. No bill went down: on a "
          "subscription you pay the same either way.")
    print("The figures below are only what those same tokens would have cost at "
          "API list prices. They are worth reading one model at a time, when you "
          "are choosing a model, and worth nothing added together.")
    print()
    print(f"API-equivalent of the native caching saving (snapshot {res['snapshot']}):")
    for row in res["rows"]:
        u = f"${row['usd']:,.2f}" if row["usd"] is not None else "UNPRICED"
        print(f"  {row['model']:<26} {row['units']/1e9:6.2f}B units  {u}")
    return 0


def _version():
    """The version from the plugin manifest, or None when it cannot be read.

    Read from .claude-plugin/plugin.json rather than kept as a second copy
    here, because two copies of a version number drift and the manifest is
    the one the marketplace actually installs from."""
    manifest = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            ".claude-plugin", "plugin.json")
    try:
        with open(manifest, encoding="utf-8") as f:
            version = json.load(f).get("version")
    except (OSError, ValueError):
        return None  # sbe: allow-silent a manifest that will not read means the version is unknown, and main() prints NO DATA naming the file rather than a made-up version string
    return version if isinstance(version, str) and version else None


def uninstall(argv=()):
    """Destructive. Print an inventory, print the VERIFIED savings a user is
    about to lose, require a typed YES, then delete. Never touches
    ~/.claude/settings.json or CLAUDE.md; those are the user's own to edit.

    `--yes` skips the prompt, which is the only path that works under a
    management tool: this used to call sys.stdin.readline() unconditionally,
    so an MDM push, a CI job, or any run without a terminal attached blocked
    forever waiting for a person who was never going to type. Without the
    flag and without a terminal it now REFUSES and deletes nothing, because
    a removal that guesses consent from an empty pipe is worse than one that
    stops."""
    assume_yes = "--yes" in argv
    token_shield_dir = os.path.expanduser("~/.token-shield")
    claude_token_shield_dir = os.path.expanduser("~/.claude/token-shield")

    print("Token Shield uninstall")
    print("This removes local Token Shield data only. It never touches "
          "~/.claude/settings.json or CLAUDE.md.")
    print()

    found = []
    for base in (token_shield_dir, claude_token_shield_dir):
        if os.path.isdir(base):
            for root, _dirs, files in os.walk(base):
                for name in files:
                    found.append(os.path.join(root, name))

    if found:
        print("Found on disk:")
        for p in sorted(found):
            print(f"  {p}")
    else:
        print(f"Found on disk: nothing under {token_shield_dir} or "
              f"{claude_token_shield_dir}.")
    print()

    ver = _verified_by_label()
    if ver:
        print(f"Exit summary: {len(ver)} VERIFIED experiment(s) on record, "
              f"latest measured floor change each:")
        _print_verified_rows(ver, "  ")
        print("This history is deleted by this uninstall.")
    else:
        print("Exit summary: NO DATA. No VERIFIED experiments were on record.")
    print()

    if found:
        print("Removal is irreversible: your measurement history and treatment "
              "memory will be gone for good.")
        if not assume_yes:
            if not sys.stdin.isatty():
                print("Refused: nothing is attached to this command's input, so there is "
                      "no one to type YES. Nothing was deleted.")
                print("Re-run with --yes to remove everything listed above without a "
                      "prompt: python3 cli.py uninstall --yes")
                return 2
            print("Type YES to remove everything listed above. Anything else aborts "
                  "with nothing deleted.")
            answer = sys.stdin.readline().strip()
            if answer != "YES":
                print("Aborted. Nothing deleted.")
                return 1
        import shutil
        for base in (token_shield_dir, claude_token_shield_dir):
            if os.path.isdir(base):
                shutil.rmtree(base)
        print("Removed.")
    else:
        print("Nothing to remove.")

    print()
    print("This script does not remove the plugin itself. To finish:")
    print("  claude plugin uninstall token-shield")
    print("  If you ever ran /token-shield:start, also remove the opted-in "
          '"SessionEnd" hook by hand from ~/.claude/settings.json: look under '
          'hooks.SessionEnd for the entry whose command references '
          "session_end_telemetry.py (docs/TELEMETRY.md). This script does not "
          "touch settings.json.")
    return 0


def main(argv):
    # Asking for help is not an error, so it exits 0. Falling through to the
    # unknown-command branch below is what made -h and --help exit 2.
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    # GNU's own standard for a command line tool is both --help AND --version;
    # only the first existed, so an administrator holding a thousand installs
    # had no way to ask any of them which build they were running.
    if argv and argv[0] in ("-V", "--version"):
        version = _version()
        print(f"token-shield {version}" if version
              else "token-shield NO DATA: .claude-plugin/plugin.json could not be read")
        return 0
    if not argv or argv[0] == "summary":
        return summary()
    cmd = argv[0]
    if cmd == "dashboard":
        return dashboard()
    if cmd == "prices":
        return prices()
    if cmd == "optimize":
        import subprocess
        here = os.path.dirname(os.path.abspath(__file__))
        return subprocess.run(
            [sys.executable, os.path.join(here, "optimize.py")] + argv[1:]).returncode
    if cmd == "prune":
        import subprocess
        here = os.path.dirname(os.path.abspath(__file__))
        return subprocess.run(
            [sys.executable, os.path.join(here, "plugin_prune.py")] + argv[1:]).returncode
    if cmd == "trim":
        import subprocess
        here = os.path.dirname(os.path.abspath(__file__))
        return subprocess.run(
            [sys.executable, os.path.join(here, "memory_trim.py")] + argv[1:]).returncode
    if cmd == "profile":
        import subprocess
        here = os.path.dirname(os.path.abspath(__file__))
        return subprocess.run(
            [sys.executable, os.path.join(here, "profile.py")] + argv[1:]).returncode
    if cmd == "advise":
        import subprocess
        here = os.path.dirname(os.path.abspath(__file__))
        rest = argv[1:]
        if "--deep" in rest:
            rest = [a for a in rest if a != "--deep"]
            return subprocess.run(
                [sys.executable, os.path.join(here, "deep_advisor.py")] + rest).returncode
        return subprocess.run(
            [sys.executable, os.path.join(here, "advisor.py")] + rest).returncode
    if cmd == "report":
        import subprocess
        here = os.path.dirname(os.path.abspath(__file__))
        return subprocess.run(
            [sys.executable, os.path.join(here, "report.py")] + argv[1:]).returncode
    if cmd == "doctor":
        import subprocess
        here = os.path.dirname(os.path.abspath(__file__))
        return subprocess.run(
            [sys.executable, os.path.join(here, "doctor.py")] + argv[1:]).returncode
    if cmd == "uninstall":
        return uninstall(argv[1:])
    if cmd == "experiment":
        # commands/optimize.md sends the reader here. Without this line it fell
        # into the usage error below, which named no working alternative, for a
        # report experiment.py has implemented all along.
        if len(argv) > 1 and argv[1] == "report":
            return ex.cmd_report()
        if len(argv) < 3 or argv[1] not in ("start", "end"):
            print("usage: cli.py experiment start|end <label> [--treats PATH]")
            print("       cli.py experiment report")
            return 2
        import time
        # cmd_start and cmd_end take epoch seconds and do their own window
        # arithmetic on them. A formatted string here is what made both
        # commands crash instead of run.
        now_ts = time.time()
        if argv[1] == "end":
            return ex.cmd_end(argv[2], ROOT, EXPERIMENT_DAYS, now_ts)
        treats = None
        if "--treats" in argv[3:]:
            i = argv.index("--treats", 3)
            if i + 1 < len(argv):
                treats = argv[i + 1]
        return ex.cmd_start(argv[2], ROOT, EXPERIMENT_DAYS, now_ts, treats)
    print(__doc__)
    # Same text as --help, so the exit code alone would not tell a user their
    # command was wrong. Name it, on stderr.
    print(f"unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
