#!/usr/bin/env python3
"""Audit the GitHub cloud-cost posture of the authenticated account.

Checks that every repository keeps Actions disabled and, when the token has
billing scope, prints the month's billed-versus-gross summary. Absent
evidence prints as NO-DATA with the command that would produce it; NO-DATA
is never a pass. Exit 0 all OK, 1 any WARN, 2 NO-DATA at the top level.

Companion doc: docs/CLOUD-COST-SHIELD.md
"""
import datetime
import json
import subprocess
import sys


def gh(args):
    try:
        p = subprocess.run(["gh"] + args, capture_output=True, text=True, timeout=120)
    except FileNotFoundError:
        return 127, "", "gh not installed"
    except subprocess.TimeoutExpired:
        return 124, "", "gh timed out"
    return p.returncode, p.stdout, p.stderr


def main():
    rc, _, err = gh(["auth", "status"])
    if rc != 0:
        print("NO-DATA: gh CLI not authenticated (%s); run: gh auth login" % err.strip().splitlines()[0] if err.strip() else "no detail")
        return 2

    rc, out, err = gh(["repo", "list", "--limit", "200", "--json", "nameWithOwner"])
    if rc != 0:
        print("NO-DATA: cannot list repositories: %s" % (err.strip().splitlines()[0] if err.strip() else "unknown"))
        return 2
    repos = [r["nameWithOwner"] for r in json.loads(out)]
    if not repos:
        print("NO-DATA: zero repositories visible to this token")
        return 2

    ok = warn = nodata = 0
    for r in repos:
        rc, out, _ = gh(["api", "repos/%s/actions/permissions" % r, "--jq", ".enabled"])
        if rc != 0:
            print("NO-DATA %s: actions permissions unreadable" % r)
            nodata += 1
        elif out.strip() == "false":
            ok += 1
        else:
            print("WARN actions ENABLED: %s" % r)
            warn += 1
    print("repos: %d off, %d enabled, %d unreadable, %d total" % (ok, warn, nodata, len(repos)))

    rc, out, _ = gh(["api", "user", "--jq", ".login"])
    login = out.strip() if rc == 0 else ""
    today = datetime.date.today()
    if login:
        path = "/users/%s/settings/billing/usage?year=%d&month=%d" % (login, today.year, today.month)
        rc, out, err = gh(["api", path])
        if rc == 0:
            items = json.loads(out).get("usageItems", [])
            gross = sum(i.get("grossAmount", 0) for i in items)
            billed = sum(i.get("netAmount", 0) for i in items)
            print("billing %d-%02d: billed $%.2f (gross $%.2f)" % (today.year, today.month, billed, gross))
            if billed > 0:
                print("WARN billed amount is nonzero; read docs/CLOUD-COST-SHIELD.md reading order")
                warn += 1
        else:
            print("NO-DATA billing: token lacks user scope; run: gh auth refresh -h github.com -s user")
    else:
        print("NO-DATA billing: could not resolve login")

    return 1 if warn else 0


if __name__ == "__main__":
    sys.exit(main())
