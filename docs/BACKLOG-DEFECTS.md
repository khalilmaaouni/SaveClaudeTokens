# Defect backlog

Every entry below was found by an adversarial review or by an orchestrator reproducing one. Nothing here is a guess: an entry either carries the reproduction that showed it, or it says plainly that it was reasoned about and not demonstrated.

Opened 2026-08-15 by session 2d9f807a at the founder's request, to hold what is known-broken but not yet fixed, so it stops living in session logs nobody rereads.

Severity means: **Critical** is wrong output a user would act on, data loss, or a security or privacy failure. **Major** is a real defect with a workaround or a narrow trigger. **Minor** is cosmetic, or correct but confusing.

Status is one of OPEN, IN PROGRESS, FIXED (with the pull request that did it), or WONTFIX (with the reason and who decided).

---

## FIXED this session, listed so the backlog is not read as the whole picture

| # | Severity | What | Fixed by |
|---|---|---|---|
| D1 | Critical | The proof engine could never reach VERIFIED. The config fingerprint hashed the raw bytes of `~/.claude.json`, which Claude Code rewrites several times a minute (`lastUsedAt`, `usageCount`), so `fingerprint_start != fingerprint_end` always held and the downgrade reason `config changed during experiment window` fired on every experiment. | [PR 65](https://github.com/khalilmaaouni/token-shield/pull/65) |
| D2 | Critical | The fleet dashboard died entirely on three separate single inputs, losing every machine's row instead of one: a non-UTF-8 file, a `NaN` counter, and stack-exhausting nesting. Root cause shared: the loader caught a named subset of exceptions on input any org member can write. | [PR 64](https://github.com/khalilmaaouni/token-shield/pull/64) |
| D3 | Critical | A symlink in the fleet store made the dashboard read and render content from outside the store. The write path had been hardened against exactly this; nobody carried it to the read path. | [PR 64](https://github.com/khalilmaaouni/token-shield/pull/64) |
| D4 | Critical | The dashboard page title accepted a script injection while the body escaped correctly, and `--org ../../elsewhere` read records outside the org tree. | [PR 64](https://github.com/khalilmaaouni/token-shield/pull/64) |
| D5 | Major | Dashboard error rows published the admin's absolute home path, and so their account name, into a page every member of the organisation opens. | [PR 64](https://github.com/khalilmaaouni/token-shield/pull/64) |
| D6 | Major | The latest-record-wins rule was reimplemented in the dashboard with an inverted tiebreak, so two machines pushing one label at the same timestamp gave the org page a different winner than the single-machine page. | [PR 64](https://github.com/khalilmaaouni/token-shield/pull/64) |
| D7 | Major | `scripts/test_trial.py` was in neither the documented suite line nor CI, so nothing would have caught a regression in the zero-install trial. Found by grep immediately after the merge. | [PR 63](https://github.com/khalilmaaouni/token-shield/pull/63) |

---

## OPEN

### D8. A legacy baseline can never be closed, so it looks open forever
**Severity:** Major. **Status:** OPEN. **Found:** 2026-08-14, recorded in `STATE.md`, not yet fixed.

`cmd_end` on a legacy baseline cannot reach a close: the close-match path requires `cohort_before.end == baseline cohort_end_ts`, and a legacy baseline carries neither field. The experiment therefore stays open-looking permanently, and the only way it was resolved in practice was an operator archiving the file by hand.

**Why it matters beyond tidiness:** an experiment that reads as open blocks the apply interlock, so one unclosable legacy record can refuse every guided apply on the machine indefinitely.

**Smallest fix:** `cmd_end` should detect a baseline that predates the cohort fields and close it with an explicit NO DATA verdict naming the missing fields, rather than silently failing the match. Do not invent the missing values.

**Reproduction:** not re-run this session. The behavior is recorded from the 2026-08-14 session which hit it live and archived `shrink-claude-md` by hand as a result.

---

### D9. Per-model counters bucket everything under "unknown"
**Severity:** Major. **Status:** OPEN. **Disclosed by the builder rather than hidden**, 2026-08-14, Fleet F1.

Fleet records carry per-model counters, but the telemetry ledger records a model COUNT and never a model IDENTITY, so every counter lands under `unknown`. The fleet dashboard's per-model table is therefore structurally empty of real model names.

**Why it matters:** model mix is one of the confounds the experiment engine downgrades on, and it is one of the four waste lenses the product sells. A per-model view that can only ever say `unknown` is a promise the data cannot keep.

**Smallest fix:** either capture model identity at the telemetry boundary, or remove the per-model table and say NO DATA with the reason, rather than rendering a table whose only row is `unknown`. The second is honest and cheap; the first is the real fix.

---

### D10. BrotherMode: Windows on Python 3.9 has failed every CI run since 2026-08-10
**Severity:** Major. **Status:** OPEN, in a different repository. **Diagnosed read-only this session.**

`tools/bm_controller.py`'s `_unattended_fence_canary` passes a subprocess a custom `env` dictionary that omits `SystemRoot`. Python 3.9 on Windows needs it during hash-randomization initialisation and crashes without it; 3.11 and later tolerate it, which is exactly why `store (windows-latest, 3.x)` stays green while `store (windows-latest, 3.9)` fails. Introduced at commit `af666fc0`.

**Smallest fix:** add `SystemRoot` to `canary_env` in that one function.

**Not fixed here on purpose:** that repository had a live fence from another session at the time. Handing over a diagnosis was correct; crossing their fence was not.

**Stated as inference, not verified:** the CPython reason for the version split is the standard explanation for that signature and was not confirmed against CPython source. The failure itself, its isolation to that one matrix leg, and the introducing commit were all verified from real logs.

---

### D11. The integrity self-check cannot run on the copy that most needs it
**Severity:** Minor, but the reasoning is worth keeping. **Status:** OPEN by design, recorded for a decision rather than a fix.

The `CHECKSUMS.sha256` self-check declines to compare when the working tree has uncommitted changes, reporting SKIP with an honest reason rather than risking a false alarm. That is the right default. The consequence is that a hand-edited live install, which is precisely the case where tampering or a half-finished update matters most, reports SKIP rather than FAIL.

**Observed live this session:** editing the installed skill produced `SKIP: the file-integrity check did NOT run this time`, and `doctor` still exited 0.

**Possible direction, not a decision:** a `--strict` mode that treats SKIP as failure, so an automated check can demand a real answer while an interactive run keeps the forgiving default. The founder should decide whether that is worth the surface.

---

## How this list is meant to be used

Take the Criticals first, and take D8 before D9 because an unclosable experiment can block applies on a real machine today while the per-model gap only makes one table honest-but-empty.

Every fix here ships the way everything else does: a test calibrated by reinjecting the defect first, because a test born green proves nothing.
