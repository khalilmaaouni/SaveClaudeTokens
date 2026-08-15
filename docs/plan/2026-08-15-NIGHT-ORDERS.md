# Night orders, 2026-08-15 into 2026-08-16

Written by session adabd843 at the founder's instruction, before he slept. A
fresh session executes from THIS FILE plus `STATE.md`. Do not look for context
in a conversation; there is none to find.

## The three founder decisions that govern tonight

**FD4, merge authority.** An overnight session MAY merge its own pull request to
main, but ONLY when every one of these is true, checked in this order:

1. The full documented test line in `CLAUDE.md` exits 0 on THAT pull request's
   own head commit, not on an earlier one.
2. `cd /Users/khalil.maaouni/SaveClaudeTokens/mcp-server && python3 test_mcp_server.py`
   exits 0 and prints `13 passed`.

   NOTE, corrected before this file was an hour old, and the correction matters
   because the original would have blocked every merge tonight. This condition
   was first written as `python3 -m pip install ./mcp-server && cd mcp-server &&
   python3 test_mcp_server.py`. On this machine `pip install` exits 1, because
   the system Python is externally managed (PEP 668), so the `&&` chain never
   reaches the test and the gate fails closed forever. The reason it looked green
   when it was checked is worse than the bug: it was run as
   `pip install ... | tail -2 && ...`, and a pipeline reports the exit code of
   its LAST command, so `tail` returned 0 and hid pip's 1. Never verify a command
   through a pipe when the exit code is the thing you are verifying.

   The install was never load bearing anyway. `test_mcp_server.py` does
   `sys.path.insert(0, SRC)` and `sys.path.insert(0, SCRIPTS)` at lines 21 and
   22, so it imports from the source tree whether or not a package is installed,
   and `token_shield_mcp` is in fact not installed on this machine at all. The
   thing this step exists to catch, a `metrics.py` symbol move breaking
   `mcp-server/` (which went red on CI on 2026-08-14), is caught by that
   `SCRIPTS` path entry, not by the install. CI keeps its own install step and
   that is correct there: on a clean runner it also proves the package builds.
3. `python3 bench/test_bench.py && python3 bench/generate_corpus.py --out /tmp/bench-corpus && python3 bench/run_benchmark.py --corpus /tmp/bench-corpus`
   exits 0, started from the repository ROOT.
4. All three fail closed scans (secret, dash, attribution) are clean over the
   WHOLE pushed range, with the range resolved rather than silently empty.
5. The task's own done-check output is quoted in the pull request body.

Any one of these failing means the pull request WAITS for the founder. Do not
weaken a test to get green. Do not merge on a partial run. One branch at a time,
never stacked.

**FD5, the budget.** 1,600,000 output tokens across TWO sequential sessions,
each under the standard 800,000 hook enforced brake. No new dispatches at 80
percent of a session's brake (640,000). Hard stop at 100 percent. The second
session starts from the first one's checkpoint on disk, not from a live context.
HARD STOP 07:00 JST regardless of budget remaining.

**FD6, the status line is OUT tonight.** Task T3.0 requires adding a line to the
founder's own `settings.json` and he was not asked to do it before sleeping.
NOTHING overnight edits his settings, for any reason, however convenient. T3.0
and T3.1 both wait for him. Reorder around them.

## The work, in order. Do not reorder without a reason written down.

Main is at `477c645`, clean, zero open pull requests. (An earlier draft of this
file said `2582b47`, which was main BEFORE this file's own pull request merged. If
your HEAD does not match, run `git ls-remote origin main` and trust that.) Green there after the
merges: 532 checks across 23 suites, exit 0, `check_py311` clean over 56 files.

**1. T2.1, the state function.** The packet is standalone and complete at
`docs/plan/packets/T2.1-command-center-state.md`. It is now on main, so read it
from there. Model: sonnet, per the packet. Read `docs/plan/2026-08-15-STATE-MODEL.md`
sections 2, 2a, 3 and 4 first; 2a is the one that looks optional and is not.
Eight tests, each red before green.

**2. T2.5, the format canary.** Only after T2.1 MERGES, because it needs the
`parse_health` seam T2.1 creates. Spec is in the WBS task table and in section
2a of the state model memo. Layer 0, in `measure_tokens.py`. This is the
founder's FD1 from earlier tonight and it is the highest value item in the plan:
it is the alarm that stops the command center saying HEALTHY on a meter that can
no longer read its own input.

**3. T2.2, the PROVING panel** in `token_shield.py`. After T2.1 merges.

**4. T4.1, the install smoke.** Independent of everything above, all files NEW,
so it can run in a second lane in parallel with any of the above. One warning
the evidence audit found: the fixture corpus generator lives at
`bench/generate_corpus.py`, which is OUTSIDE T4.1's declared Files owned. Either
widen the fence deliberately and say so in the pull request, or drive the
generator as a subprocess without editing it. Do not silently edit a file
outside a fence.

**5. T2.3, the terminal state line** in `cli.py`. After T2.2 merges. `cli.py` is
a single writer queue: T2.3, then T1.1, then later T6.2 and T7.1, in that order,
never two at once.

If everything above lands, pull from the WBS Window 2 list in its stated order.
If nothing is pullable, say so in one line and stop rather than inventing work.

## Standing constraints, none optional

- Branch plus pull request. Never a direct commit to main.
- Every fix ships with a test calibrated by REINJECTING the defect (red) before
  the fix (green). A test born green proves nothing. Python caches bytecode by
  (mtime, size), so a same length edit reverted inside one second is served from
  cache: change the length or clear `__pycache__` when calibrating.
- No em dashes, no en dashes, anywhere, including commit messages and pull
  request text.
- No AI vendor attribution anywhere. Sole credited author: Khalil Maaouni.
- Python 3.11 floor.
- Confidence labels never merge, no cross label totals, NO DATA beats a guess.
- The release gate is CONTESTED ON MAIN. Treat it as HOLDING tonight: no tag, no
  release, no publish, no plugin update, no MCP client registration. Nothing in
  tonight's work order needs any of those, so holding costs nothing and is the
  safe reading of a contradiction nobody has resolved.

  The contradiction, so you do not have to rediscover it. `docs/ROADMAP.md` says
  the original `claude-md-diet` was closed early on the founder's explicit word
  with an honest NOT_PROVEN verdict, that under the ratified amendment either
  verdict OPENS the release boundary, and therefore that the boundary is OPEN;
  1.8.0 shipped on 2026-08-14 on that reading. The project `CLAUDE.md` says the
  gate holds until `claude-md-diet-v2` reaches VERIFIED or an honest NOT_PROVEN.
  Both files are on main. They disagree about whether a successor experiment
  re-closes a boundary its predecessor opened. That is a founder decision and it
  is in the morning packet. Do not resolve it yourself and do not release on the
  permissive reading.

  Either way, `claude-md-diet-v2` runs untouched: do not read it, shorten it, or
  help it. It is open, started 2026-08-13, 30 day window, verdict due about
  2026-09-12.
- NEW files declare their layer in `test_architecture.py` LAYERS in the same
  pull request. NEW test suites are added to `.github/workflows/ci.yml` AND to
  the `CLAUDE.md` documented test line in the same pull request.
- The documented suite alone is NOT a sufficient safety claim for a change that
  moves symbols other packages import. `mcp-server/` imports from `metrics.py`.
  This has already gone red on CI once for exactly that reason.

## Model routing, per the founder's standing law

Strongest tier orchestrates, judges, reviews and verifies. Sonnet implements
from a written packet. Haiku does mechanical bulk. Never a mechanical loop on
the strongest tier, and NEVER a cheap tier verifying anything. Every brief names
its tier and the reason.

Scope every subagent brief to a named question with a bounded file list and a
hard return cap. Evidence from tonight: a scoped audit given ten named claims to
disprove cost 77,000 tokens; an unscoped one asked to describe the codebase cost
390,000 the night before. Scope is the whole lever.

## Progress page and checkpointing

Checkpoint at EVERY green: commit on the working branch, update `STATE.md`,
refresh `GANTT.html` and republish it to
https://claude.ai/code/artifact/1f1c2319-6543-4e58-9e1f-54045f709117 (pass that
url so it updates in place rather than creating a second link). The page is
delivered, not merely written.

## What is owed to the founder in the morning

One handover packet as ONE zip, addressed to him by name, naming: what merged
with its proving command, what is in flight and its exact stop point, what was
not started, anything UNVERIFIED with its blocker, and the two items that need
his hand (T3.0's settings line, and any pull request that failed a gate and is
waiting).
