#!/usr/bin/env python3
"""
cli.py: one entry point for Token Shield.

  python3 cli.py                     quick honest summary (same as `summary`)
  python3 cli.py summary
  python3 cli.py dashboard           render the HTML dashboard and print its path
  python3 cli.py experiment start|end <label> [--treats PATH]
  python3 cli.py prices              per-model USD-equivalent of the saving
  python3 cli.py optimize            propose a safe, reversible CLAUDE.md diet
  python3 cli.py profile             deterministic session profile (profile.py)
  python3 cli.py advise              ranked next-move cards (advisor.py)
  python3 cli.py advise --decide <strategy-id> <done|not-now|never>
                                      record a card decision (treatment memory)
  python3 cli.py report              monthly report; --month YYYY-MM --out PATH
  python3 cli.py uninstall           remove local Token Shield data: prints
                                      what exists, requires typing YES, deletes

The scripts underneath (measure_tokens, token_shield, pricing, experiment,
optimize, profile, advisor, report) stay the source of truth; this only
routes to them and never re-implements a metric. Kept small deliberately: a
command per feature is how a small tool turns into a sprawling one.
"""

import json
import os
import sys

import measure_tokens as mt
import token_shield as ts
import pricing as pr
import experiment as ex

ROOT = os.path.expanduser("~/.claude/projects")
OUT = os.path.expanduser("~/.token-shield/token-shield.html")
EXPERIMENT_DAYS = 30  # window length both cohorts of an experiment must share


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
    latest = {}
    order = []
    with open(ex.LEDGER, errors="ignore") as f:
        for line in f:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("confidence") != "VERIFIED":
                continue
            fr = r.get("floor_reduction_tokens")
            if fr is None:
                continue
            label = r.get("label") or "(unlabeled)"
            if label not in latest:
                order.append(label)
            latest[label] = fr
    return [(label, latest[label]) for label in order]


def _print_verified_rows(rows, indent):
    for label, fr in rows:
        tail = ("fewer startup tokens per call" if fr >= 0
                else "MORE startup tokens per call (regression)")
        print(f"{indent}{label:<26} {fr:+,}  {tail}")


def summary(days=30):
    if not os.path.isdir(ROOT):
        print("NO DATA: no Claude Code transcripts found.")
        return 2
    sm = mt.summarize(mt.collect(ROOT, days))
    if not sm:
        print("NO DATA: no transcripts carried usage counters yet.")
        return 0
    native = ts.savings_breakdown(sm)["saved"]
    rx = ts.prescriptions(sm, mt.collect(ROOT, days))
    tool = sum(r["saving"] for r in rx)
    ver = _verified_by_label()

    print("Token Shield")
    if ver:
        print("  VERIFIED     latest measured floor change per experiment "
              "(never summed across experiments):")
        _print_verified_rows(ver, "                 ")
    else:
        print("  VERIFIED     none yet. Run: python3 cli.py experiment start \"my-change\"")
    print(f"  NATIVE       {native/1e9:.1f}B token-units saved by Claude Code's caching "
          f"(Anthropic's, not this tool)")
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
    print(f"API-equivalent of the native caching saving (snapshot {res['snapshot']}):")
    for row in res["rows"]:
        u = f"${row['usd']:,.2f}" if row["usd"] is not None else "UNPRICED"
        print(f"  {row['model']:<26} {row['units']/1e9:6.2f}B units  {u}")
    print(f"  total  ${res['usd']:,.2f} API-equivalent. On a subscription the bill did not "
          f"drop by this; it is API-list-price equivalent.")
    return 0


def uninstall():
    """Destructive. Print an inventory, print the VERIFIED savings a user is
    about to lose, require a typed YES, then delete. Never touches
    ~/.claude/settings.json or CLAUDE.md; those are the user's own to edit."""
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
    if cmd == "profile":
        import subprocess
        here = os.path.dirname(os.path.abspath(__file__))
        return subprocess.run(
            [sys.executable, os.path.join(here, "profile.py")] + argv[1:]).returncode
    if cmd == "advise":
        import subprocess
        here = os.path.dirname(os.path.abspath(__file__))
        return subprocess.run(
            [sys.executable, os.path.join(here, "advisor.py")] + argv[1:]).returncode
    if cmd == "report":
        import subprocess
        here = os.path.dirname(os.path.abspath(__file__))
        return subprocess.run(
            [sys.executable, os.path.join(here, "report.py")] + argv[1:]).returncode
    if cmd == "uninstall":
        return uninstall()
    if cmd == "experiment":
        if len(argv) < 3 or argv[1] not in ("start", "end"):
            print("usage: cli.py experiment start|end <label> [--treats PATH]")
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
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
