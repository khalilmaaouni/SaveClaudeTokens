#!/usr/bin/env python3
"""Cases for the rationed-dispatch door in github_cost_wall.py.

Run as a FILE, never as an inline shell command: the wall is a PreToolUse hook
on Bash, so a command line containing the dispatch string trips the very wall
under test and the harness never runs. That is the wall working, and it is also
why these cases live here.
"""
import datetime
import json
import os
import subprocess
import sys

HOOK = os.path.expanduser("~/.claude/hooks/github_cost_wall.py")
GRANT = os.path.expanduser("~/.claude/actions-grant.json")
LEDGER = os.path.expanduser("~/.claude/actions-ledger.jsonl")
DISPATCH = "gh " + "workflow " + "run example-gates.yml -R acme/example-repo"

ok = True


def check(name, got, want):
    global ok
    if got != want:
        ok = False
        print("FAIL %-52s got %r want %r" % (name, got, want))
    else:
        print("pass %-52s %r" % (name, got))


def run(cmd):
    p = subprocess.run([sys.executable, HOOK], input=json.dumps({"tool_input": {"command": cmd}}),
                       capture_output=True, text=True)
    return p.returncode


def write_grant(**kw):
    base = {"repo": "acme/example-repo", "workflow": "example-gates.yml",
            "issued": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "estimated_minutes": 25, "reason": "fixture"}
    base.update(kw)
    with open(GRANT, "w") as fh:
        json.dump(base, fh)


saved_ledger = None
if os.path.exists(LEDGER):
    saved_ledger = open(LEDGER).read()

try:
    # The wall must keep refusing everything it refused before the door existed.
    for f in (GRANT,):
        if os.path.exists(f):
            os.remove(f)
    check("grantless dispatch is refused", run(DISPATCH), 2)
    check("enable is refused unconditionally", run("gh " + "workflow " + "enable x"), 2)
    check("rerun is refused", run("gh " + "run " + "rerun 123"), 2)
    check("re-enabling actions is refused",
          run("gh api repos/x/y/actions/permissions -f enabled=true"), 2)
    check("ordinary bash is untouched", run("ls -la"), 0)

    # The door itself.
    write_grant()
    open(LEDGER, "w").close()
    check("granted dispatch inside budget is allowed", run(DISPATCH), 0)
    check("the grant is consumed on use", os.path.exists(GRANT), False)
    check("a second run needs a fresh grant", run(DISPATCH), 2)

    # A grant is for ONE dispatch, not any dispatch.
    write_grant(workflow="some-other.yml")
    check("a grant for another workflow does not authorise this one", run(DISPATCH), 2)

    # Expiry, on a fixed clock rather than on when the suite happens to run.
    write_grant(issued=(datetime.datetime.now(datetime.timezone.utc)
                        - datetime.timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    check("an expired grant is refused", run(DISPATCH), 2)
    write_grant(issued="not a timestamp")
    check("an unreadable issued timestamp is refused", run(DISPATCH), 2)

    # The budget.
    with open(LEDGER, "w") as fh:
        fh.write(json.dumps({"ts": datetime.datetime.now(datetime.timezone.utc)
                             .strftime("%Y-%m-%dT%H:%M:%SZ"),
                             "estimated_minutes": 190, "note": "fixture"}) + "\n")
    write_grant(estimated_minutes=25)
    check("a grant that would breach the monthly cap is refused", run(DISPATCH), 2)
    write_grant(estimated_minutes=5)
    check("a grant that fits under the cap is allowed", run(DISPATCH), 0)
finally:
    for f in (GRANT,):
        if os.path.exists(f):
            os.remove(f)
    if saved_ledger is None:
        if os.path.exists(LEDGER):
            os.remove(LEDGER)
    else:
        with open(LEDGER, "w") as fh:
            fh.write(saved_ledger)

print("OK" if ok else "FAILED")
sys.exit(0 if ok else 1)
