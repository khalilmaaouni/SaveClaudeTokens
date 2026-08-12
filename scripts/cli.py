#!/usr/bin/env python3
"""
cli.py: one entry point for Token Shield.

  python3 cli.py                     quick honest summary (same as `summary`)
  python3 cli.py summary
  python3 cli.py dashboard           render the HTML dashboard and print its path
  python3 cli.py experiment start|end <label>
  python3 cli.py prices              per-model USD-equivalent of the saving
  python3 cli.py optimize            propose a safe, reversible CLAUDE.md diet
  python3 cli.py profile             deterministic session profile (profile.py)
  python3 cli.py advise              ranked next-move cards (advisor.py)
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


def _verified_from_ledger():
    """Sum the floor reductions of VERIFIED experiment records. This is the only
    number the tool is allowed to call VERIFIED."""
    if not os.path.exists(ex.LEDGER):
        return None
    n = 0
    floor = 0
    with open(ex.LEDGER, errors="ignore") as f:
        for line in f:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("confidence") == "VERIFIED" and r.get("floor_reduction_tokens"):
                n += 1
                floor += max(0, r["floor_reduction_tokens"])
    return {"experiments": n, "floor_reduction": floor}


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
    ver = _verified_from_ledger()

    print("Token Shield")
    if ver and ver["experiments"]:
        print(f"  VERIFIED     {ver['floor_reduction']:,} fewer startup tokens per call, "
              f"across {ver['experiments']} experiment(s)")
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

    ver = _verified_from_ledger()
    if ver and ver["experiments"]:
        print(f"Exit summary: {ver['experiments']} VERIFIED experiment(s) on record, "
              f"{ver['floor_reduction']:,} tokens of proven floor reduction. "
              f"This history is deleted by this uninstall.")
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
            print("usage: cli.py experiment start|end <label>")
            return 2
        import time
        now = time.strftime("%Y-%m-%dT%H:%M:%S%z") or time.strftime("%Y-%m-%dT%H:%M:%S")
        fn = ex.cmd_start if argv[1] == "start" else ex.cmd_end
        return fn(argv[2], os.path.expanduser("~/.claude/projects"), 30, now)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
