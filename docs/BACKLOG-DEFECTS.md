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
| D23 | Critical | A counter too large for a float (401 bytes, under the size cap) raised `OverflowError` out of the validator, which was called OUTSIDE the try whose broad handler exists for exactly that. One record killed every machine's row. | [PR 69](https://github.com/khalilmaaouni/token-shield/pull/69) |
| D24 | Critical | An experiment whose `label` or `confidence` was not a string raised `unhashable type` or a str/int comparison, because both are used as a dict key, a set member and a sort key. One record killed the page. | [PR 69](https://github.com/khalilmaaouni/token-shield/pull/69) |
| D25 | Critical | A symlink AT the org directory escaped the store entirely and rendered an arbitrary outside directory with no refusal, because the symlink guard walks components strictly BELOW its root. | [PR 69](https://github.com/khalilmaaouni/token-shield/pull/69) |
| D26 | Critical | The page declared utf-8 but was written with the locale's codec, so under `LC_ALL=C` one non-ASCII byte anywhere in the store left a zero byte file. | [PR 69](https://github.com/khalilmaaouni/token-shield/pull/69) |

---

## OPEN, from the opus adversarial review round of 2026-08-15

Three independent opus reviewers, each briefed to REFUTE rather than confirm, were run against the proof engine, the zero-install trial, and the fleet dashboard as merged. Between them they found eight Criticals. Four (the dashboard set) were reproduced and fixed the same day in [PR 69](https://github.com/khalilmaaouni/token-shield/pull/69). The rest are below, in the order they should be taken.

Every finding here carries the reviewer's own reproduction output. None was accepted on argument alone.

---

### D12. A later NOT_PROVEN does not supersede an earlier VERIFIED
**Severity: Critical. Status: OPEN. This is the most damaging defect currently known.**

Every "latest record per label wins" reader filters to VERIFIED **before** picking the latest, so re-running a label and failing to prove it leaves the old VERIFIED claim standing. Sites: `scripts/token_shield.py:394`, `scripts/cli.py:73`, `scripts/share_card.py:70`.

With a ledger holding VERIFIED +24,000 (2026-07-01) then NOT_PROVEN (2026-08-14):

```
TOKEN SHIELD -- VERIFIED
claude-md-diet
+24,000 startup tokens/call, fewer
proven 2026-07-01
exit=0
```

**Why this is the worst one:** the share card is the artifact designed to LEAVE THE MACHINE. This publishes a proven claim that a later run failed to reproduce, which is the precise opposite of the product's entire market position. `_historical_check` does not save it, because it compares the old record's fingerprint against the environment, which still matches whenever the later failure was for any other reason.

**Smallest fix:** select the newest record per label FIRST, then drop it if its confidence is not VERIFIED.

---

### D13. A VERIFIED verdict can be manufactured entirely by parse failures
**Severity: Critical. Status: OPEN.**

The cohort reader silently discards unreadable transcripts and corrupt JSONL lines without incrementing any counter (`scripts/experiment.py:316` and `:323`). Both handlers are mirrored from `measure_tokens.read_session`, which DOES increment `SKIP_COUNTS`; the mirror dropped that half. A dropped first line also promotes a cheap mid-conversation turn to "first request".

Five after-cohort transcripts with identical content and an unchanged floor, two truncated mid-write and one unreadable:

```
=== experiment 'silent2': VERIFIED ===
first-request median improved: 81,000 -> 41,250 tokens per call
confidence: VERIFIED | reasons: []
floor_reduction_tokens: 39750.0 | direction: saving
mt.SKIP_COUNTS        : {'files': 0, 'lines': 0}
```

Nothing changed, and the ledger says 39,750 tokens per call proven.

**Smallest fix:** increment `SKIP_COUNTS` at both handlers, reset it in `collect_cohort`, and add a downgrade reason when either cohort's skip count is non-zero. NO DATA beats a guess.

---

### D14. A partly unreadable transcript tree silently under-counts, and says nothing
**Severity: Critical. Status: OPEN.**

`os.walk(root)` at `scripts/measure_tokens.py:118` is called with no `onerror`, so a `PermissionError` on a project subdirectory is swallowed before the file iterator ever sees it. `SKIP_COUNTS` stays zero, so the trial prints no skip warning. The honesty mechanism is blind to the most common real failure.

```
[all readable]        MEASURED  10 transcripts (10 sessions), 50 calls
[3 of 10 unreadable]  MEASURED  7 transcripts (7 sessions), 35 calls
[all readable]        NATIVE    36.0M base-input token-units saved
[3 of 10 unreadable]  NATIVE    25.2M base-input token-units saved
```

Thirty percent of the data vanished and the headline fell by 10.8M with nothing said. The all-unreadable case is worse: it tells the stranger to go and generate data they already have.

**Smallest fix:** pass an `onerror` callback to `os.walk` that increments the skip counter. The warning line already exists and already prints when non-zero.

---

### D15. Any non-integer usage value ends a stranger's first run in a traceback
**Severity: Critical. Status: OPEN.**

`scripts/measure_tokens.py:176` catches only `json.JSONDecodeError`, then adds whatever the record held. Reproduced with raw-byte fixtures appended after three valid records:

```
== nan:         CRASH ValueError: cannot convert float NaN to integer
== deepnest:    CRASH RecursionError: maximum recursion depth exceeded
== str_tokens:  CRASH TypeError: unsupported operand type(s) for +=: 'int' and 'str'
== list_tokens: CRASH TypeError: unsupported operand type(s) for +=: 'int' and 'list'
== infinity:    rc=0  (no crash, prints 0.000 share and 0.000 hit ratio as MEASURED facts)
```

The `infinity` case is the nastiest, because it does not crash: every ratio divides by infinity and the tool reports confident zeros. `str_tokens` is the shape a different tool or a schema variant writes.

**Honestly scoped by the reviewer:** no real Claude Code transcript producing these was found. It needs a foreign or corrupt `.jsonl` anywhere under the root, which `os.walk` recurses into unconditionally, and `--root` is a documented flag.

**Smallest fix:** one coercion helper in `read_session` applied to the five counters, and widen the except to include `RecursionError` and `ValueError`. One guard covers all six cases and every caller.

---

### D16. NATIVE is overstated when cache writes carry no TTL split
**Severity: Major. Status: OPEN.**

`scripts/token_shield.py:156` charges only `write_5m_total` and `write_1h_total` as write premium; `write_unsplit_total` is never charged. `read_session` sets `normalized_input = None` for exactly that data because the TTL is unknown, and the trial then prints a confident NATIVE figure from it anyway.

```
NESTED (TTL known):      normalized_input_total=1755000.0   NATIVE 4.2M
FLAT ONLY (TTL unknown): normalized_input_total=None        NATIVE 4.5M
```

Overstates by 5.9 percent at the cheapest TTL, 28.6 percent if those writes were one hour. This is the row the market position rests on. Not reproduced live: real data on this machine has `write_unsplit_total: 0`, so it is a schema-version path.

**Smallest fix:** charge a conservative floor for unsplit writes and append "TTL split unavailable on N transcripts" to the NATIVE line.

---

### D17. The trial and the command it recommends disagree about the same headline
**Severity: Major. Status: OPEN.**

`scripts/trial.py:92` takes the `max` saving; `scripts/cli.py:102` sums them. Same root, same window, same data:

```
trial ESTIMATED (max) = 216.9M | cli OPPORTUNITY (sum) = 228.2M
```

The stranger's second command contradicts their first, in the same words. **Smallest fix:** use `max` in both; summing overlapping levers double counts anyway.

---

### D18. `experiment report` prints a NOT_PROVEN delta beside the VERIFIED count
**Severity: Major. Status: OPEN.**

`aggregate_by_label` (`scripts/experiment.py:628`) collects `floor_reduction_tokens` from every record regardless of confidence:

```
claude-md-diet  2 runs  1 VERIFIED  1 NOT_PROVEN  latest floor reduction 41,999 tokens/call
```

A reader takes 41,999 as the verified figure. **Smallest fix:** skip records whose confidence is not VERIFIED when building that list.

---

### D19. The refusal's own printed remedy guarantees NOT_PROVEN
**Severity: Major. Status: OPEN.**

`cmd_end` refuses on cohort overlap and advises ending "with a smaller `--days` window". Taking that advice trips the window-length guard, which is an unconditional downgrade, and writes a permanent record into the append-only ledger which then feeds D18.

```
REFUSED: ... windows overlap ... Wait longer, or end with a smaller --days window
--- taking the printed advice: end --days 0.5 ---
=== experiment 'demo': NOT_PROVEN ===  - window changed (30 vs 0.5 days)
```

**Smallest fix:** delete the "or end with a smaller --days window" clause. The only sound path is waiting longer.

---

### D20. One label can render twice while the page says it renders once
**Severity: Major. Status: OPEN.**

The fleet dashboard keys latest-wins on (label, confidence), but the page copy reads "One row per label, the newest record only". A stale VERIFIED +1,500 can sit beside a newer NOT_PROVEN -400 under that sentence. The existing test passes only because its fixture never mixes confidences.

**Smallest fix:** pick one row per label across all confidences, matching the copy. Fixing the copy instead would be the dishonest half of the choice, and it interacts with D12, so take them together.

---

### D21. Smaller correctness and honesty gaps
**Severity: Minor. Status: OPEN.** Grouped because each is a few lines.

- The non-numeric guard in `experiment.py:542` is defeated three lines later at `:554`, which subtracts the same unvalidated values and raises `TypeError`. Only reachable from a hand-edited baseline, so it is a trust-boundary gap rather than a live path.
- A first-request share above 1.0 prints as garbage (`10 share of everything read`, `1042%`). Never seen on real data: 3,649 real sessions, max 1.00.
- The same number appears twice in two representations on one trial screen (`0.363 share` and `36%`).
- The home-path scrub compares prefixes without resolving symlinks, so on macOS the firmlink alias for the home directory leaks the account name and produces a nonsense path in the error cell.
- `os.listdir(org_dir)` is unguarded while the per-machine listdir is, so an unreadable org directory raises out of `render` against a docstring promising it never raises.
- `metric_delta: NaN` renders as `+nan`; a dict in `team` renders a Python repr; a filename of `9999-99-99.json` renders as a day because the filename is never validated.

---

### D22. Tests that pass for the wrong reason
**Severity: Major, because these are what let the Criticals through. Status: OPEN.**

- `test_share_card.py:90` asserts "the latest record wins" using two VERIFIED rows, so it cannot catch D12. Make the second NOT_PROVEN and the contract breaks.
- `test_trial.py:132` checks read-only behavior by grepping source text: it catches `open(p, "w")` but misses `open(p, "a")`, `Path(p).write_text(x)` and `os.rename`.
- `test_trial.py`'s no-data fixture is inert: `{"no": "usage here"}` fails the `"usage"` substring gate and is never parsed at all.
- `test_fleet_dashboard.py` had 23 tests passing with four Criticals live, because every fixture placed a hostile value of the CORRECT TYPE. The raw-byte fixtures added earlier widened coverage on bytes and size only.

**The pattern worth naming:** in this codebase, a test suite's blind spot has been a better predictor of where the next Critical lives than any other signal. Twice now, a unit passed its own calibrated tests and was still broken in a shape its fixtures could not express.

---

## OPEN, found earlier

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

## What held, which matters as much as what broke

A review that reports only findings says nothing about the rest. These were attacked with real reproductions and did not break.

- **NATIVE never leaks into the tool's own column.** Labeled as Anthropic's own caching at every call site, and the dashboard carries no native number at all, only a methodology pointer. No dollar figure anywhere in the output.
- **The trial is genuinely read-only and offline, proven at runtime rather than assumed.** With `open` patched to raise on any write mode, `socket` replaced by a raising subclass, and the remove and rename calls stubbed, a real run against the real transcripts finished clean: no write attempts, no network.
- **The README's exact command works from a fresh clone**, including the follow-on command it prints.
- **Subagent transcripts are not counted as sessions** (3,649 transcripts, 260 sessions on real data), and cache reads are never mixed into input totals.
- **Thin data stays honest:** one session gives NO DATA for share and hit ratio rather than a zero.
- **Direction signs are correct both ways** on up-is-better metrics, and a non-default metric can never render as a token saving.
- **The first-request share never exceeded 1.0** across 260 real parent sessions; the reviewer's hypothesis that subagents inflate it was refuted on real data.
- **`reconcile.py` fails closed**, printing NOT RECONCILED rather than silently agreeing.
- **On the fleet dashboard**, the previously fixed defects all held under fresh attack: invalid UTF-8 content, bare NaN and Infinity, 400,000-deep arrays, the size cap, date disagreement, a machine replaced by a file, symlinked record files and machine directories, a JSON scalar instead of an object, 50,000 keys in one bucket, and truncation before escaping.

## How this list is meant to be used

Take D12 first. It is the only defect here that puts a false claim in front of people outside this machine, and it is a small change: pick the newest record per label first, then check its confidence, rather than the other way round.

Then D13, D14 and D15, which share a shape worth fixing together: each turns a failure into a confident number instead of NO DATA. D14 and D15 are one guard each in `measure_tokens.py`, shared by every caller.

D22 is listed last but should be read first by whoever picks this up, because those weak tests are what let the Criticals through, and fixing a defect without fixing the test that missed it just resets the trap.

Every fix here ships the way everything else does: a test calibrated by reinjecting the defect first, because a test born green proves nothing.
