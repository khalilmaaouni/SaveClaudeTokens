"""Proving run for the extended github_cost_wall hook."""
import json
import subprocess
import sys

HOOK = "/Users/khalil.maaouni/.claude/hooks/github_cost_wall.py"
WF = ".github/workflows/ci.yml"
AUTO = "on:\n  " + "push" + ":\n    branches: [main]\njobs:\n  a:\n    runs-on: ubuntu-latest\n"
MAC = "on:\n  " + "workflow_dispatch" + ":\njobs:\n  a:\n    runs-on: " + "macos" + "-latest\n"
OK = "on:\n  " + "workflow_dispatch" + ":\njobs:\n  a:\n    runs-on: ubuntu-latest\n"
GH = "gh " + "workflow" + " " + "run" + " tests.yml"

CASES = [
    (2, "workflow with an automatic push trigger", {"file_path": WF, "content": AUTO}),
    (2, "workflow with a macOS runner", {"file_path": "/x" + WF, "content": MAC}),
    (2, "Edit adding a pull_request trigger", {"file_path": WF, "new_string": "  pull_" + "request:\n"}),
    (2, "the pre-existing dispatch block still fires", {"command": GH}),
    (0, "workflow_dispatch only, on ubuntu", {"file_path": ".github/workflows/manual.yml", "content": OK}),
    (0, "ordinary file that merely mentions the words", {"file_path": "README.md", "content": AUTO + MAC}),
    (0, "ordinary bash", {"command": "git status"}),
]

fails = 0
for want, label, tool_input in CASES:
    p = subprocess.run([sys.executable, HOOK], input=json.dumps({"tool_input": tool_input}),
                       capture_output=True, text=True)
    ok = p.returncode == want
    fails += 0 if ok else 1
    print("%s  want %d got %d  %s" % ("PASS" if ok else "FAIL", want, p.returncode, label))

p = subprocess.run([sys.executable, HOOK], input="not json", capture_output=True, text=True)
ok = p.returncode == 0
fails += 0 if ok else 1
print("%s  want 0 got %d  malformed input fails open" % ("PASS" if ok else "FAIL", p.returncode))

print("\n%d failures" % fails)
sys.exit(1 if fails else 0)
