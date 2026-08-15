# Token Shield: clean start handover

Written 2026-08-15 by the Fable orchestrator of session 2d9f807a. Every figure came from a command run in that session, after the last edit it describes. Repo `~/SaveClaudeTokens`, public at github.com/khalilmaaouni/token-shield.

Read this file, run the four start-line checks, then go to "Your first three moves". Nothing else is required reading.

---

## 1. Where the project actually is

**One branch, one worktree, nothing in flight.** `git ls-remote --heads origin` prints `refs/heads/main` and nothing else. Local main is at `800dd51`. There are no open pull requests and no live fences.

Merged today, in order, each verified before the next opened: Fleet F2 (the one line org install), the competitive field map, BX1 (the zero install trial), a CI wiring rider, and Fleet F3 (the org-wide dashboard, after its review blocked it and the fix was verified). Five pull requests, 60 through 64, all closed and their branches deleted after each was individually proven merged.

**The proving number:** the documented suite line, run verbatim on merged main after the last merge, prints **427 checks green across 22 suites**, exit 0, with `check_py311` clean over 52 files.

**The product as it stands.** The free core is feature complete: it measures real usage from local transcripts, advises, reduces behind a backup-diff-confirm gate, and proves results with labeled experiments that will publish an honest NOT_PROVEN. Fleet is now complete through F3: an organisation installs with one line onto a private git store with no server, and gets an org-wide dashboard that turns every broken or hostile machine record into its own named NO DATA row rather than an outage. A stranger can try the whole thing with one command and install nothing. Version 1.8.0 is released and installed here; the MCP server is registered and connected.

**Nothing is blocked and nothing is half-finished.** Section 4 is a clean set of next moves, not a rescue list.

---

## 2. Start-line checks, run these before touching anything

```bash
cd ~/SaveClaudeTokens && git log --oneline -1 && git status --short
git ls-remote --heads origin
gh pr list --state open
git worktree list
```

Expected: main `800dd51`; remote holds `main` only; zero open pull requests; one worktree; local branches `main` plus `build/signals-s1-impl` (a deliberately kept archive ref whose content was superseded by the branch that merged as PR 55, kept under never-lose-work and safe to delete the day Khalil names it).

Then re-prove the suite yourself rather than trusting this document. The command is in `CLAUDE.md` under "Commands (documented, never guessed)". Copy it verbatim; do not retype it from memory.

---

## 3. The strategy, in one page

**North star.** Every Claude session costs the least it can while losing no quality, and the method is portable and provable enough that strangers can install it and trust its numbers.

**What the competitive research established today.** Two tools dominate the "reduce Claude Code tokens" search by audience: one at roughly 76,000 stars, one at roughly 20,000, both updated within two days of the research. We do not win on volume and should stop imagining we will.

**The moat, stated precisely, because every roadmap decision follows from it.** No tool in the field, inside Claude Code or outside it, does either of these:

1. Separates what Anthropic's prompt caching already saved from what the tool itself saved. Every large headline percentage published in this space conflates the two.
2. Isolates a single variable so a percentage can be attributed to one cause. Every reduction tool bundles compression with caching with hook rewriting, which means none of their numbers can be traced to a mechanism.

Our label discipline (VERIFIED, MEASURED, ESTIMATED, NATIVE, RECOMMENDED, and NO DATA over a guess) is not decoration. It is the product. Full evidence in `docs/research/2026-08-15-competitive-field-map.md`.

**Two threats worth respecting.** Proxy tools enforce budgets by blocking requests; every Claude Code tool including ours only reports. Editor plugins show cost live per task; our dashboard is a post mortem. Both are real gaps and neither is in the ratified plan. See section 6.

---

## 4. Your first three moves

### Move 1: BX3, the Waste Score, and publish the formula first

This is the highest-leverage unit left in the ratified plan and the one that compounds with everything else. One number from a published, fixed, open formula over MEASURED inputs, comparable across machines, usable as a continuous integration budget the way teams ship at a Lighthouse score.

**The sequencing is the whole trick and it is not negotiable: the formula document is published BEFORE the first score renders anywhere.** A score whose formula arrives afterwards is marketing. A score whose formula arrived first is a standard. That difference is the entire reason this unit exists, and it is the same trust posture that makes the labels worth anything.

Size M. It touches the profile and the dashboard, so expect one fix round.

### Move 2: BX1b, finish the zero install promise

BX1 shipped as `git clone ... && python3 token-shield/scripts/trial.py`. It works, it is honest, and it was verified end to end from a fresh clone. But the competitors it answers won their audiences on a true one-liner that leaves nothing behind.

A root `pyproject.toml` with a `token-shield-trial` entry point would make this work:

```bash
uvx --from git+https://github.com/khalilmaaouni/token-shield token-shield-trial
```

That needs no publish to any package index, so it stays inside the release gate. It is a small unit with one real risk to think about first: a packaging file at the root of a repository that is also a Claude Code plugin and its own marketplace. Check that it does not confuse plugin loading before committing to it.

### Move 3: BX2, put the cost delta inside the review surface

A GitHub Action that comments the measured context-cost delta of `CLAUDE.md`, hook, and plugin manifest changes on a pull request, before merge. Nobody in this field sees token waste at the moment they add three hundred lines of memory file, which is exactly the moment the decision is cheap to reverse.

Size M. It pairs with BX3: once the Waste Score exists, this becomes the budget gate.

### Then: Fleet F4 and F5, and the rest of the ratified plan

F4 is the org profile with soft budgets (an unreachable store never gates a developer; a breach advises, never blocks). F5 is signed receipts. Both are in `docs/superpowers/plans/`. Signals stays held at S2 by earlier decision, and LAB1 stays parked until the verdict.

---

## 5. The gates, none of which have moved

- Branch plus pull request, never a direct commit to main.
- Before any push, over the whole pushed range, fail closed: secret scan, dash scan, attribution scan. Any hit stops the push.
- No AI vendor attribution anywhere. Sole credited author is Khalil Maaouni.
- No em dashes and no en dashes anywhere. A test needle that needs one builds it from its unicode codepoint.
- Python 3.11 floor; `scripts/check_py311.py` must stay clean.
- Every fix ships with a test calibrated by reinjecting the defect first. A test born green proves nothing.
- Nothing is done without the verifying command run after the last edit and its output quoted.

**The release boundary, still closed.** No version tag, no release, no plugin publish, and no local plugin update or MCP re-registration on this machine until the `claude-md-diet-v2` experiment reaches its verdict, near 2026-09-13. Its baseline is byte-untouched (shasum `70168cac`). Building is authorized; releasing is not. Tagging and publishing to the world is fine when the verdict lands; installing the result on this machine is what would corrupt the experiment.

---

## 6. Open questions for Khalil, none blocking

1. **Two moves the research surfaced that are not in the ratified plan.** A hard budget brake that stops spend at the boundary, and a live per-task cost counter. Recommendation: the counter first, because it is smaller and compounds with the MEASURED labels; the brake collides with the zero-hooks-by-default invariant and deserves its own design round.
2. **Should `docs/handover/` be tracked in git?** It is excluded on this machine only, via `.git/info/exclude` line 12, not in the shared `.gitignore`. Yet `STATE.md` points future sessions at files inside it, so that pointer is a promise the repository cannot keep. A durable copy is archived at `~/Documents/BrotherArchive/tokenshield-handover-docs/2026-08-15-snapshot`. Recommendation: track it, since these are project history rather than machine state.
3. **Signals holds at S2** by earlier decision: client ready, nothing deployed, nothing sent, awaiting the consent layer and an endpoint decision. **LAB1 stays parked** until the verdict.

---

## 7. Working rules that were paid for in real defects

1. Reproduce a reviewer's findings yourself before accepting them, and re-run its attacks against the fix. This has found further defects inside fixes more than once.
2. An adopted lane is verified from its commits, never from the state of the folder it was left in. One worktree carried an uncommitted edit that removed the exact protection its security review had just forced in.
3. Never `git checkout --` a file while your own uncommitted work is in it. Commit first, or reinject into a copy. This cost work twice in one session even with the rule written down.
4. Every cross-tree git command and every restore uses an absolute path or `git -C <abs path>`. A relative path after a directory change has produced confidently wrong results repeatedly.
5. Clear `__pycache__` between reinjection steps. Python invalidates cached bytecode by modification time and size, so a same-length mutation can leave a stale `.pyc` and give a false green.
6. Defense in depth breaks calibration: if two guards cover one hole, removing one leaves the suite green. Calibrate against the primary guard and say which one you targeted.
7. When a fence excludes the file that wires a test into CI, grep for the gap immediately after the merge. It happened to BX1 and was caught only because the F3 review had just flagged the same class.
8. Declare the spend ceiling at the start, and when a guard refuses, stop and hand over rather than route around it.
9. **Check your harness before you believe your result.** Three times in one session a check returned a confidently wrong answer because the fixture asked a different question than the one intended: a grep for a machine id when the page renders directory names, a leak check against a temp path when the scrub targets the real home, and a store in `tempfile` when the finding only appears under the home directory. When a repro comes back clean, suspect the harness first.
10. **When two branches both touch the suite line, resolve to the union, never to a side.** Merging main into F3 conflicted on both `CLAUDE.md` and `ci.yml`, because one side had just added `test_trial.py` and the other `test_fleet_dashboard.py`. Taking either side whole would have silently dropped a suite from CI, which is the failure the wiring rider existed to prevent.

---

## 8. Where the evidence lives

- `STATE.md` (machine-local, not in git): the fence registry, every decision with its flip condition, and the quoted evidence lines.
- `GANTT.html`, published at https://claude.ai/code/artifact/89b7616a-9fe7-4dda-b7dd-286b48d7452e: the command center. Republish it at every closed loop and put it in front of Khalil rather than naming its path.
- `docs/research/2026-08-15-competitive-field-map.md`: the competitive evidence.
- `docs/superpowers/plans/2026-08-14-claude-domination-plan.md`: the ratified strategy.
- Kay Vault, `10-Projects/saveclaudetokens/`: session logs and the failure index. Check the failure index before working in any area.
