# Solid Core wave R: implementation plan (native reduction, guided apply)

Date: 2026-08-13. Status: PLAN ONLY, no implementation file exists yet. This document turns Pillar R of `docs/superpowers/specs/2026-08-13-solid-core-design.md` into steps a future builder session can run without making a design decision. Every step names its exact paths and ends with a command that proves the step landed.

Wave R implementation is founder-ordered (this plan exists because the founder asked for it). That order is not the same thing as authorization to change a live config file. Every actual apply still needs the founder's explicit yes at the moment it runs, and no apply may run while any experiment is open, because an apply changes the config fingerprint and would force that open experiment to NOT_PROVEN when it later closes. Step 1 below builds the interlock that enforces the second rule mechanically; the first rule (the founder's yes) is enforced by keeping every apply a separate, explicit invocation from its own propose step, the same split `optimize.py` already uses, never a script that writes on its own say-so.

## THE GATE (read this before touching anything)

No file this plan names gets created until the claude-md-diet experiment reaches a verdict in the proof ledger: VERIFIED or an honest NOT_PROVEN. Check before step 1:

```bash
cd /Users/khalil.maaouni/SaveClaudeTokens && python3 scripts/cli.py experiment report
```

Look for a `claude-md-diet` row with a VERIFIED or NOT_PROVEN count greater than 0. If the row is absent, or shows 0 runs, STOP. Do not create any file listed in this plan. Report the gate as closed and wait. (Per `STATE.md` line 114 this diet was already applied by hand once and the finding it targeted is gone; that is a separate, already-closed fact from whether the ledger carries a verdict record for the label. Run the command above and read what it actually prints, do not infer the verdict from `STATE.md` prose.)

## Scope

In scope: the shared apply contract (`scripts/guided_apply.py`), the interlock it depends on (`experiment.list_open_experiments`), the three guided applies named in the spec (CLAUDE.md diet apply, plugin prune bundles, memory index trim), their calibrated tests, and the documentation and command-file updates that describe them to a founder or an agent running the command.

Out of scope, not touched by this plan: Pillar T's multi-treatment waterfall (v1.9 ecosystem layer per the spec), Pillar A's automation levels (OBSERVE/ASSIST/ACT, a separate wave with its own flip condition), Pillar P personalization, and `scripts/discover_companions.py` / `scripts/doctor.py` from the sibling `docs/superpowers/plans/2026-08-13-v18-wave1-plan.md` (that plan is itself PLAN ONLY behind the same gate; wave R's plugin prune bundle does not depend on it and must not be blocked waiting for it).

## A hard constraint found during grounding, not a design choice: the 6 command file cap

`CLAUDE.md` line 27: "Command surface is capped at 6 command files." The repo already has exactly 6, confirmed by listing the directory:

```
commands/advisor.md  commands/monthly.md  commands/optimize.md
commands/stats.md    commands/start.md    commands/token-audit.md
```

Wave R adds two more user-facing applies (plugin prune, memory trim) alongside the existing CLAUDE.md diet apply. None of them may get a new command file without deleting one of the six first, which this plan does not do and was not asked to do. All three guided applies are therefore documented as additional numbered sections inside the existing `commands/optimize.md`, which already carries the "propose it, show the diff, apply only on yes" ceremony this plan extends to the other two applies. If a future session wants separate command files, that is a scope decision for the founder, not something step 3 to 5 below may take on its own.

## Grounding: exact existing functions and facts this plan reuses, never reimplements

Every name below was read directly from the file named, on this date. A builder session must re-grep before use in case the file moved since this plan was written.

| Name | Source | Shape |
|---|---|---|
| `propose(text, notes_rel="claude-history.md")` | `scripts/optimize.py:101` | pure, returns `(new_text, notes_text, moved, before_tok, after_tok)` |
| `classify(heading, body)` | `scripts/optimize.py:85` | pure, returns `(verdict, reason)`; `HARD` never moves |
| `split_sections(text)` | `scripts/optimize.py:67` | pure, splits on top level `## ` headings |
| `est_tokens(text)` | `scripts/optimize.py:62` | pure, `len(text) / 4` rounded, always labeled ESTIMATED |
| `cmd_propose(path)` | `scripts/optimize.py:134` | writes proposal files to `~/.token-shield/optimize/`, never touches `path`, returns an int exit code |
| `cmd_apply()` | `scripts/optimize.py:182` | reads the last proposal, backs the source up to `<path>.bak-<stamp>`, writes the new text and the notes file, prints the revert line, returns an int exit code |
| `review_dir()` | `scripts/optimize.py:128` | `~/.token-shield/optimize`, created if missing |
| `check(path, is_memory_index)` | `scripts/context_lint.py:94` | reads one file, returns `(findings, stats)`; `stats` carries `raw_bytes`, `loaded_bytes`, `loaded_lines` |
| `truncation_report(text, max_lines, max_bytes)` | `scripts/context_lint.py:66` | pure, returns `None` or `{"cut_at_line", "total_lines", "dropped_lines", "loaded_bytes", "reason"}` |
| `loaded_content(text)` | `scripts/context_lint.py:54` | pure, strips frontmatter and block HTML comments, what Claude Code actually loads |
| `BULLET` | `scripts/context_lint.py:49` regex | matches a `-`/`*`/`+` bullet line, group 1 is its text |
| `MEMORY_MAX_LINES`, `MEMORY_MAX_BYTES` | `scripts/context_lint.py:39-40` | `200`, `25 * 1024`, the documented hard load limit |
| `expected_memory_index_path(cwd=None)` | `scripts/context_lint.py:245` | pure, the auto-memory MEMORY.md path for a project |
| `compute_fingerprint(treats=None)` | `scripts/experiment.py:122` | sha256 over CLAUDE.md, settings.json, `~/.claude.json`, every `skills/*/SKILL.md`, and every plugin dir under `plugins/cache/*/*`; `treats` blinds one file's own line to `EXCLUDED` |
| `excluded_by_treats(treats=None)` | `scripts/experiment.py:101` | the in-scope files list, not plugin dirs; plugin dirs cannot currently be excluded from the fingerprint by `--treats` at all (see Ambiguity/fact 3 below) |
| `fingerprint_files()` | `scripts/experiment.py:88` | `[CLAUDE_MD_PATH, SETTINGS_PATH, CLAUDE_JSON_PATH] + skills/**/SKILL.md`; auto-memory MEMORY.md files are never in this list |
| `cmd_start(label, root, days, now_ts, treats)` | `scripts/experiment.py:422` | pins the before baseline, writes `EXP_DIR/<label>.json`, prints, returns an int exit code |
| `cmd_end(label, root, days, now_ts)` | `scripts/experiment.py:445` | compares against the baseline, appends one record to `LEDGER`, prints, returns an int exit code; does NOT delete or mark the baseline file it read |
| `EXP_DIR`, `LEDGER` | `scripts/experiment.py:52-53` | `~/.claude/token-shield/experiments`, `~/.claude/token-shield/savings.jsonl` |
| `build_record(baseline, after_sm, ended_iso, fingerprint_end)` | `scripts/experiment.py:303` | pure, the confidence verdict logic |
| `ROOT`, `EXPERIMENT_DAYS` | `scripts/cli.py:34,36` | `~/.claude/projects`, `30`; every `experiment start`/`end` call in this repo uses these two values, guided apply reuses them rather than hard-coding a second `30` |
| `main(argv)` command dispatch | `scripts/cli.py:207` | the `optimize`/`profile`/`advise`/`report`/`experiment` subcommands each `subprocess.run` the named script; a new subcommand follows the same one-line pattern |
| `claude plugin list --json` real output shape | confirmed and quoted in `docs/superpowers/plans/2026-08-13-v18-wave1-plan.md:48` | JSON array; real fields `id` (`"<name>@<marketplace>"`), `version`, `scope`, `enabled` (bool), `installPath`, `installedAt`, `lastUpdated` |
| `claude plugin --help` subcommand list | confirmed this session (quoted below) | `disable [options] [plugin]`, `enable [options] <plugin>`, positional argument named `plugin` in both |

Two rows above (`claude plugin list --json` shape, `claude plugin --help`) were re-confirmed during this planning pass, not carried over blindly from the sibling plan; the exact `--help` text captured this session:

```
disable [options] [plugin]           Disable an enabled plugin
enable [options] <plugin>            Enable a disabled plugin
```

`disable` additionally takes `-a/--all` and `-s/--scope <scope>` (user, project, local; default auto-detect). Neither `--help` output states whether the positional `plugin` argument accepts a bare name or requires the full `name@marketplace` id when more than one marketplace installs the same name. This is Ambiguity 1 below; step 4 resolves it against the real CLI before wiring the exact call, not from this table.

## Design decisions this plan makes mechanically, flagged for confirmation

1. **No stdin confirmation prompt anywhere in this plan's Python.** `commands/optimize.md` already shows that the "propose it, show the diff, ask yes, apply" ceremony in this repo runs as chat turns driven by a command file read by the agent, not as a Python `input()` loop (`cli.py`'s `uninstall()` is the one exception, and it exists so uninstall is safely runnable standalone outside a command file too). Guided apply keeps the existing two-invocation split: a `propose`/`bundle` step that only reads and writes to a review directory, and a separate `apply`/`--apply` step that a founder or an agent runs only after the yes was already given in chat. `scripts/guided_apply.py` therefore has no prompt-reading code and needs no fake-stdin tests. If a future session wants a hard, code-level ask (not just command-file prose), that is a bigger interactive-CLI change out of scope here; flag it instead of building it silently.
2. **`scripts/guided_apply.py` provides only the two things all three applies actually share: the open-experiment refusal gate, and the "run the mutation, verify it, auto-open one experiment" tail.** Each producer module (`optimize.py`, `plugin_prune.py`, `memory_trim.py`) keeps its own backup-and-write logic, mirroring `optimize.py`'s existing `cmd_apply` shape, because the three applies back up genuinely different things (a text file's old content; nothing, since a plugin disable is reversed by its own enable command; a text file's old content again) and forcing one shared backup function onto all three would be exactly the "config for a value that never changes" `guided_apply.py` should not carry.
3. **The experiment's fingerprint gets pinned AFTER the mutation, not before.** For CLAUDE.md diet, `--treats` already makes the timing irrelevant (the file's own line hashes to `EXCLUDED` either way). For plugin prune, timing is NOT optional: `fingerprint_files()` and `excluded_by_treats()` never cover the plugin-directory lines `compute_fingerprint` appends (see fact row above), so there is no way to blind the fingerprint to a plugin's own directory disappearing or changing. Pinning the baseline immediately after the disable, instead of before it, means `fingerprint_start` already reflects the new plugin state, so the experiment's own change never trips its own guard. `scripts/guided_apply.py`'s `apply()` therefore always calls `mutate_fn()` before `experiment.cmd_start(...)`, for all three applies, so the ordering is one rule instead of three.
4. **On a verify failure, the change is left in place, not auto-reverted, and no experiment gets opened.** The mutation already wrote the file (or ran the disable), and the backup or revert command already exists; auto-reverting on top of a print-only verify check adds a second silent mutation to reason about, and opening an experiment over a change that failed its own verification would produce a real ledger record about a bad state. The founder gets the revert instructions printed and reverts by hand if they want to.
5. **Every apply's label gets a timestamp suffix (`<name>-guided-<stamp>`), never a bare fixed label.** The founder's own prior "claude-md-diet" run (the one gating v1.8, per `STATE.md`) is a separate label and must not collide with a guided run; re-running the same guided apply twice must not silently overwrite one ledger row's meaning with another's, since `report`'s aggregation collapses repeated same-label rows to the latest.

## Ambiguities and facts to confirm before writing code, not to guess past

1. **Whether `claude plugin disable` accepts a bare plugin name or requires `name@marketplace`.** `--help` shows only a positional `[plugin]`, no format documented. Step 4's first action is to run `claude plugin list --json`, pick one real installed name from this machine, and test `claude plugin disable <bare-name>` against `claude plugin enable <bare-name>` immediately after (so the net effect is zero), reading the `enabled` field before and after to confirm the bare form works, before writing any code that assumes it. If the bare form fails or is ambiguous across two marketplaces installing the same name, fall back to the full `id` string `claude plugin list --json` already returns.
2. **What a "prune bundle" is grounded in.** The spec says "context_lint findings become named disable bundles," but `context_lint.py` as it stands has no plugin-level finding at all (only `profile.py:176`'s `_plugin_count`, a bare count, not names). No file in this repo currently measures per-plugin usage. Building automatic zero-use detection is out of scope for wave R (that is exactly what `discover_companions.py`/`doctor.py` in the sibling v1.8 plan would eventually feed; wave R must not silently absorb that scope). `plugin_prune.py`'s bundle is therefore a founder-named or agent-named list of currently-installed plugin ids, listed via `claude plugin list --json` for the founder to pick from, never an automatic "this one looks unused" inference. State this plainly to the founder if asked why the tool does not pick for them.
3. **The plugin-directory fingerprint gap is a genuine pre-existing hole, not something this plan is asked to close.** Design decision 3 above works around it by fixed ordering; it does not fix `compute_fingerprint`/`excluded_by_treats` to support excluding a plugin directory by name. If a later plugin change happens between a guided prune's `cmd_start` and its `cmd_end` (someone installs or updates an unrelated plugin), that experiment will correctly downgrade to NOT_PROVEN under the existing guard, exactly as it should; this plan does not weaken that guard to make plugin-prune experiments easier to verify.

## Implementation steps

### Step 1: the interlock, `experiment.list_open_experiments`

File: `scripts/experiment.py`, add a new function near `cmd_report` (before `main`).

`cmd_end` never deletes or marks the baseline snapshot file it reads from `EXP_DIR`, so file presence alone cannot answer "is this experiment still open." The only reliable match between a start and its close is the pair `(label, cohort_end_ts)`: `cmd_start` writes `cohort_end_ts` into the baseline, and `build_record` copies that same value verbatim into every ledger record's `cohort_before["end"]`. A baseline whose `(label, cohort_end_ts)` pair has no matching ledger record was started but never ended.

```python
def list_open_experiments(exp_dir=EXP_DIR, ledger=LEDGER):
    """Every baseline snapshot in exp_dir with no matching close in the ledger.
    cmd_end never deletes or marks the file it reads, so this is the only way
    to tell 'started, never ended' from 'started, ended, file just still there'.
    Returns a list of the raw baseline dicts (label, started, fingerprint_start,
    treats, ...), sorted by started ascending, [] when nothing is open."""
```

Read every `*.json` file under `exp_dir` as a baseline dict; read every line of `ledger` as a record, building a set of `(label, cohort_before.end)` pairs already closed; return the baselines whose `(label, cohort_end_ts)` is not in that set. Non-JSON or unreadable files are skipped, not raised on, matching every other read in this module (`cmd_end`'s own `try/except (OSError, json.JSONDecodeError)` at line 450 is the sibling to mirror).

Estimate: 1 to 2 hours, high confidence; this is one read-only function over data shapes `cmd_start`/`build_record` already produce.

Done check (uses a temp `EXP_DIR`/`LEDGER`, never the real ones on this machine):
```bash
cd /Users/khalil.maaouni/SaveClaudeTokens/scripts && python3 -c "
import json, os, tempfile
import experiment as ex
with tempfile.TemporaryDirectory() as d:
    ex.EXP_DIR = os.path.join(d, 'experiments'); os.makedirs(ex.EXP_DIR)
    ex.LEDGER = os.path.join(d, 'savings.jsonl')
    open(os.path.join(ex.EXP_DIR, 'open-one.json'), 'w').write(
        json.dumps({'label': 'open-one', 'cohort_end_ts': 100.0, 'started': 'x'}))
    open(os.path.join(ex.EXP_DIR, 'closed-one.json'), 'w').write(
        json.dumps({'label': 'closed-one', 'cohort_end_ts': 200.0, 'started': 'y'}))
    with open(ex.LEDGER, 'w') as f:
        f.write(json.dumps({'label': 'closed-one', 'cohort_before': {'end': 200.0}}) + '\n')
    open_now = ex.list_open_experiments()
    labels = sorted(o['label'] for o in open_now)
    assert labels == ['open-one'], labels
    print('list_open_experiments ok:', labels)
"
```
Must print `list_open_experiments ok: ['open-one']`.

Add the calibrated test `test_list_open_experiments_matches_by_label_and_cohort_end` to `scripts/test_experiment.py`, mirroring the file's own `_point_paths_at`/`_restore_paths` temp-dir pattern (lines 30-40) so it never touches the real machine's ledger. Cover: a baseline with no ledger entry is open; a baseline with a matching `(label, end)` ledger entry is closed; a baseline whose ledger entry has the SAME label but a DIFFERENT `cohort_before.end` (a later re-run) is still open, since that specific start was never closed.

### Step 2: the shared contract, `scripts/guided_apply.py`

File: `scripts/guided_apply.py` (new).

```python
import time
import experiment as ex
import cli as ts_cli  # ROOT, EXPERIMENT_DAYS: reused, never re-declared


def refuse_if_experiment_open():
    """None if clear to apply, else a REFUSED string naming every open label."""


def backup_file(path):
    """Mirrors optimize.cmd_apply's own backup, lines 195-199 of optimize.py:
    time.strftime stamp, '<path>.bak-<stamp>', full read then full write.
    Returns the backup path."""


def apply(label, treats, mutate_fn, verify_fn):
    """The one shared tail. mutate_fn(): zero-arg, already does its own backup
    and write (each producer module keeps this itself, see design decision 2).
    verify_fn(): zero-arg, returns (ok: bool, report: str), run only after
    mutate_fn. Refuses before mutate_fn runs if any experiment is open.
    On success, opens one experiment (mutate_fn already ran, so the fingerprint
    pinned here already reflects the change, see design decision 3).
    Returns (rc, message): rc 2 refused, rc 1 verify failed (change stands,
    no experiment opened), rc 0 applied and experiment opened."""
```

`refuse_if_experiment_open` calls `ex.list_open_experiments()` and formats every open label plus its `started` timestamp into one REFUSED string naming the exact command to close it (`python3 experiment.py end "<label>"`), matching the refusal wording style `experiment.py`'s own `cmd_end` overlap refusal already uses (lines 463-467).

Estimate: 3 to 5 hours, medium confidence; small module, but `apply()`'s three-way return contract needs care and its own test for each branch.

Done check:
```bash
cd /Users/khalil.maaouni/SaveClaudeTokens/scripts && python3 -c "
import sys
import guided_apply as ga
assert callable(ga.refuse_if_experiment_open)
assert callable(ga.backup_file)
assert callable(ga.apply)
print('guided_apply imports ok')
"
```
Must print `guided_apply imports ok`.

Write `scripts/test_guided_apply.py`, mirroring `test_experiment.py`'s temp-dir/monkeypatch pattern for anything touching `ex.EXP_DIR`/`ex.LEDGER`, and monkeypatching `ex.cmd_start` to a stub that records its call args instead of touching real transcripts (`ts_cli.ROOT` on a real machine may not exist in CI). Calibrated cases, each named for the behavior it locks in:
- `test_apply_refuses_when_an_experiment_is_open`: seed one open baseline, call `apply(...)`, assert `mutate_fn` was never called (a `called = []` flag closure) and rc is 2.
- `test_apply_runs_mutate_then_verify_then_opens_experiment_on_success`: no open experiment, `mutate_fn` sets a flag, `verify_fn` returns `(True, "ok")`, assert the stubbed `cmd_start` was called with the exact `label`/`treats` passed in, rc is 0.
- `test_apply_does_not_open_experiment_on_verify_failure`: `verify_fn` returns `(False, "bad")`, assert `mutate_fn` WAS called (the write already happened) but the stubbed `cmd_start` was NOT called, rc is 1.
- `test_backup_file_matches_optimize_cmd_apply_pattern`: write a temp file, call `backup_file`, assert the backup's content equals the original and the backup path matches the `.bak-` naming convention `optimize.py` already uses.

### Step 3: CLAUDE.md diet, guided apply

File: `scripts/optimize.py`, add (no existing function is removed or renamed; `cmd_propose`/`cmd_apply` stay exactly as they are today for any script or CI path that already calls them directly):

```python
def verify_diet(original_text, path):
    """Re-runs context_lint.check(path, is_memory_index=False) after an apply
    and confirms the loaded line count actually dropped from original_text's.
    Returns (ok, report)."""


def cmd_guided_apply(path):
    """The wave R entry point. Reads path's current text (for verify_diet's
    before count), then calls guided_apply.apply(label, treats=path,
    mutate_fn=cmd_apply, verify_fn=lambda: verify_diet(original, path))."""
```

`cmd_guided_apply` requires `import context_lint` (top of `optimize.py`) and `import guided_apply`. Label: `f"claude-md-diet-guided-{time.strftime('%Y%m%d-%H%M%S')}"`. `treats=path` so the diet's own file edit never trips `compute_fingerprint`'s confounder guard (the existing `--treats` mechanism already covers a plain file path; see the grounding table).

Add a `--guided-apply` flag to `main()`'s `argparse` block, calling `cmd_guided_apply(a.file)` instead of `cmd_apply()` when passed. `optimize.py`'s existing `--apply` flag is untouched.

Estimate: 2 to 3 hours, high confidence; almost entirely composition of already-built pieces.

Done check:
```bash
cd /Users/khalil.maaouni/SaveClaudeTokens/scripts && python3 -c "
import os, tempfile, time
import optimize as opt
with tempfile.TemporaryDirectory() as d:
    src = os.path.join(d, 'CLAUDE.md')
    body = ('## History\n' + 'On 2026-08-01 the postmortem after the 2026-07-31 '
            'incident was ratified. ' * 30)
    open(src, 'w').write(body)
    opt.cmd_propose(src)
    ok, report = opt.verify_diet(body, src) if False else (None, None)  # placeholder, real call happens post-apply in cmd_guided_apply
    print('optimize.py exposes verify_diet and cmd_guided_apply:',
          hasattr(opt, 'verify_diet'), hasattr(opt, 'cmd_guided_apply'))
"
```
Must print `optimize.py exposes verify_diet and cmd_guided_apply: True True`. (The real end-to-end apply path is exercised by the calibrated test below, not this smoke check; the smoke check only proves the new names exist and import cleanly, since `cmd_guided_apply` itself calls `guided_apply.apply`, which needs the interlock and a real or stubbed transcripts root to run all the way through.)

Add `test_verify_diet_reports_the_line_count_drop` and `test_cmd_guided_apply_refuses_when_experiment_open` to `scripts/test_optimize.py`, the second monkeypatching `guided_apply.refuse_if_experiment_open` to return a fixed string and asserting the source file is left byte-for-byte unchanged (mirrors the existing `test_cmd_propose_never_writes_the_source_claude_md` pattern at line 58 of that file, but for the guided-apply path instead of propose).

Update `commands/optimize.md`: after step 4 (the existing `--apply` step), add a step 4a naming `--guided-apply` as the path that also opens the proof experiment automatically, and note the label naming convention so the founder recognizes their own runs in `experiment report` output later.

### Step 4: plugin prune bundles

File: `scripts/plugin_prune.py` (new).

First action, before writing any function body: run `claude plugin list --json`, pick one real installed plugin id from this machine's own output, and test `claude plugin disable <bare-name>` immediately followed by `claude plugin enable <bare-name>`, confirming via a second `claude plugin list --json` read that `enabled` went `true` to `false` and back to `true`. Record which argument form actually worked (bare name, or the full `name@marketplace` id) directly in this file's module docstring, quoting the real command and its result, per Ambiguity 1. Do not write `_disable_cmd`/`_enable_cmd` below until this is done.

```python
def list_plugins():
    """subprocess.run(['claude', 'plugin', 'list', '--json']), parsed. Returns
    the real list of dicts (id, version, scope, enabled, ...) or raises with a
    clear message if the CLI is missing or the output is not valid JSON;
    never guesses a shape."""


def cmd_propose_bundle(names, bundle_id):
    """names: plugin ids or bare names the founder/agent picked from
    list_plugins()'s own output, never inferred. Writes a review file to
    ~/.token-shield/optimize/plugin-prune-<bundle_id>.json (reuses
    optimize.review_dir(), same directory, same never-touch-anything-live
    contract) listing each name's exact disable command and its exact
    matching enable command (the revert), and prints them for the founder to
    read before saying yes. Never calls subprocess itself."""


def cmd_apply_bundle(bundle_id):
    """Reads the review file cmd_propose_bundle wrote. This IS the mutate_fn
    passed to guided_apply.apply: runs each disable command in order, prints
    each result, prints the full set of enable commands as the revert line.
    No file backup (there is nothing to back up; see design decision 2)."""


def verify_bundle(names):
    """Re-runs list_plugins(), confirms every name in names now shows
    enabled: False. Returns (ok, report)."""
```

CLI wiring: extend `scripts/cli.py`'s `main(argv)` with a `prune` subcommand following the exact one-line `subprocess.run([...] + argv[1:])` pattern the `optimize`/`profile`/`advise`/`report` branches already use (lines 215-229 of `cli.py`), so `python3 cli.py prune propose <names...> --bundle-id <id>` and `python3 cli.py prune apply <id>` route to `plugin_prune.py`. Update the module docstring's usage block at the top of `cli.py` (lines 4-17) with the new line, matching its existing style exactly.

Label for the auto-opened experiment: `f"plugin-prune-{bundle_id}-guided-{time.strftime('%Y%m%d-%H%M%S')}"`. `treats=None` (plugin directories are not excludable by `--treats` at all today, per Ambiguity 3; ordering, not exclusion, is what keeps this experiment from tripping its own guard, per design decision 3).

Estimate: 4 to 6 hours, medium confidence; the CLI-argument-format confirmation sub-step could take longer if the bare-name form does not work cleanly across marketplaces, which would add a lookup-by-id step before the disable call.

Done check (uses a monkeypatched `list_plugins`, never calls the real `claude` binary, so it runs in CI without a live plugin list):
```bash
cd /Users/khalil.maaouni/SaveClaudeTokens/scripts && python3 -c "
import plugin_prune as pp
orig = pp.list_plugins
pp.list_plugins = lambda: [{'id': 'demo-plugin@demo-market', 'enabled': False}]
ok, report = pp.verify_bundle(['demo-plugin@demo-market'])
pp.list_plugins = orig
assert ok, report
print('verify_bundle ok:', report)
"
```
Must print `verify_bundle ok: ...` with `ok` true.

Write `scripts/test_plugin_prune.py`: monkeypatch `subprocess.run` (never invoke the real `claude` binary in a test) to cover `cmd_propose_bundle` writing the review file with both commands present for a fixture name, `cmd_apply_bundle` calling disable for every named plugin and printing every matching enable command, and `verify_bundle` correctly reporting `ok=False` when a plugin comes back still `enabled: True`.

Update `commands/optimize.md`: add a new top-level section "Prune plugins you do not use" after the existing CLAUDE.md diet steps, naming `cli.py prune propose`/`prune apply`, the founder-picks-the-names contract from Ambiguity 2 (this tool never infers zero-use on its own), and the same "explicit yes before apply" ceremony as the diet section.

### Step 5: memory index trim

File: `scripts/memory_trim.py` (new). Mirrors `optimize.py`'s propose/apply/pointer shape as closely as the different file format allows (per the CLAUDE.md rule to mirror the closest sibling), operating on bullet lines via `context_lint.BULLET` instead of `## ` sections.

```python
def propose_trim(path, keep_lines=None):
    """keep_lines defaults to context_lint.MEMORY_MAX_LINES (200). Reads path,
    calls context_lint.truncation_report on its loaded_content to find the
    real cut point (None if the file is already within its limit: nothing to
    propose, caller prints NO DATA and returns cleanly). Parses bullet lines
    via context_lint.BULLET. Moves bullets starting from the ones AT OR PAST
    the reported cut_at_line first (they already never load, so moving them
    costs nothing behaviorally) into a memory-archive.md text, leaving a
    one-line pointer per moved bullet, mirroring optimize.propose's own
    pointer style, until the remaining index fits within keep_lines. Returns
    (new_text, archive_text, moved, before_lines, after_lines)."""


def cmd_propose(path):
    """Writes new_text/archive_text/a diff to optimize.review_dir() (reused,
    not duplicated) under memory-trim-specific filenames, prints the same
    kind of before/after report cmd_propose in optimize.py prints. Never
    touches path."""


def cmd_apply():
    """Reads the review files cmd_propose wrote. Backs path up via
    guided_apply.backup_file, writes new_text to path and archive_text to
    memory-archive.md beside it. This IS the mutate_fn passed to
    guided_apply.apply."""


def verify_trim(path):
    """Re-runs context_lint.check(path, is_memory_index=True) and confirms
    the HIGH truncation finding is gone (or, if the file was already right at
    the edge, that dropped_lines strictly decreased). Returns (ok, report)."""
```

`treats=None`: `fingerprint_files()` never includes any MEMORY.md path (confirmed in the grounding table), so a memory trim cannot trip the confounder guard at all and needs no exclusion.

Label: `f"memory-trim-guided-{time.strftime('%Y%m%d-%H%M%S')}"`.

CLI wiring: a `trim` subcommand in `scripts/cli.py`'s `main(argv)`, same one-line pattern as `prune` above, defaulting `path` to `context_lint.expected_memory_index_path()` (reused, not re-derived).

Estimate: 3 to 5 hours, medium confidence; the "move from the cut point backward until it fits" loop needs a calibrated test for the boundary case where the file is already exactly at the limit.

Done check:
```bash
cd /Users/khalil.maaouni/SaveClaudeTokens/scripts && python3 -c "
import os, tempfile
import memory_trim as mtrim
with tempfile.TemporaryDirectory() as d:
    p = os.path.join(d, 'MEMORY.md')
    lines = [f'- [Item {i}](item-{i}.md) - a memory pointer line long enough to count.' for i in range(260)]
    open(p, 'w').write('\n'.join(lines) + '\n')
    new_text, archive_text, moved, before, after = mtrim.propose_trim(p)
    assert after < before, (before, after)
    assert len(new_text.splitlines()) <= 200, len(new_text.splitlines())
    assert moved, 'expected at least one bullet moved'
    print('propose_trim ok:', before, '->', after, 'lines,', len(moved), 'moved')
"
```
Must print `propose_trim ok: 260 -> <N> lines, <M> moved` with the after-count at or under 200.

Write `scripts/test_memory_trim.py`, mirroring `test_optimize.py`'s structure exactly (a `check(name, cond)` helper, one `test_*` function per behavior, a `__main__` runner): cover a file already within the limit (`propose_trim` returns nothing to move, `cmd_propose` reports NO DATA and exits 0), a file with more bullets than fit (moved bullets appear verbatim in the archive, never dropped entirely), and `cmd_apply` never writing the source path when called without a prior `cmd_propose` (mirrors `test_cmd_propose_never_writes_the_source_claude_md`'s exact assertion style, applied to `cmd_apply`'s NO DATA path instead).

Update `commands/optimize.md`: add a third top-level section "Trim the memory index" after the plugin-prune section, describing the guided-apply ceremony and, since the memory index is Claude Code's own auto-generated file rather than a hand-written rulebook, noting explicitly that hard-rule-style content never lives there so there is no `HARD` classification step to explain (unlike the CLAUDE.md diet section).

### Step 6: wire the three new test files into the documented full suite

File: `CLAUDE.md` line 8 (the one-line full test suite command). Add `test_guided_apply.py`, `test_plugin_prune.py`, and `test_memory_trim.py` to the `&&`-chained list, in the same position (after the module they test, `test_optimize.py`, `test_experiment.py`, keeping the file's existing left-to-right grouping by subject) as every other test file already sits. Copy the line, edit it, do not retype it from memory.

Estimate: 15 to 30 minutes, high confidence.

Done check (the exact command CLAUDE.md now documents, run from repo root, must exit 0):
```bash
cd /Users/khalil.maaouni/SaveClaudeTokens && python3 scripts/check_py311.py && cd scripts && python3 test_measure_tokens.py && python3 test_tools.py && python3 test_pricing.py && python3 test_experiment.py && python3 test_optimize.py && python3 test_profile.py && python3 test_advisor.py && python3 test_report.py && python3 test_guided_apply.py && python3 test_plugin_prune.py && python3 test_memory_trim.py
```
Must exit 0 with every file printing its own passed count.

### Step 7: docs

Files to update, each with the specific addition named:

- `README.md`: near the existing `optimize.py`/`context_lint.py` description (around line 118), add one paragraph naming the three guided applies and the one-line fact that every apply opens its own experiment automatically, pointing at `docs/superpowers/specs/2026-08-13-solid-core-design.md`'s Pillar R section rather than re-explaining the contract in a second place.
- `docs/MAINTENANCE.md`: the existing plugin-disable line (around line 37, `claude plugin disable <name>`, re-enable with `enable`) gets a one-line pointer to the new guided `cli.py prune` path as the reviewed, experiment-backed way to do the same thing, without removing the manual instructions (a founder doing it by hand is still a valid path and this plan does not take that away).
- `docs/ROADMAP.md`: mark wave R as shipped where the roadmap currently lists it as designed-not-built, quoting the actual done-check output from step 6 as the evidence line, matching the roadmap's own existing evidence-citation style (re-grep the file for its exact phrasing convention before editing; do not invent a new format for one entry).
- `docs/CLAIMS.md`: add one row per new confirmed fact this plan produces (the working `claude plugin disable` argument form found in step 4, the memory-index fingerprint-exclusion fact already stated in this plan's grounding table), following the file's existing `| ID | claim | status | evidence |` row shape exactly.

Estimate: 2 to 3 hours total across all four files, high confidence; this is prose, not code, and every fact it states was already produced by an earlier step.

Done check:
```bash
cd /Users/khalil.maaouni/SaveClaudeTokens && grep -n "guided" README.md docs/MAINTENANCE.md docs/ROADMAP.md docs/CLAIMS.md
```
Must print at least one matching line from each of the four files.

### Step 8: dash and attribution scan on every file this plan touched

Run the same fail-closed scans `CLAUDE.md`'s gates section and the `github-desktop-push` skill require before any push, over the full set of files this plan created or edited: `scripts/experiment.py`, `scripts/guided_apply.py`, `scripts/test_guided_apply.py`, `scripts/optimize.py`, `scripts/test_optimize.py`, `scripts/plugin_prune.py`, `scripts/test_plugin_prune.py`, `scripts/memory_trim.py`, `scripts/test_memory_trim.py`, `scripts/cli.py`, `CLAUDE.md`, `README.md`, `docs/MAINTENANCE.md`, `docs/ROADMAP.md`, `docs/CLAIMS.md`, `commands/optimize.md`.

Done check:
```bash
cd /Users/khalil.maaouni/SaveClaudeTokens && perl -CSD -ne 'print "$ARGV:$.:$_" if /\x{2014}|\x{2013}/' scripts/experiment.py scripts/guided_apply.py scripts/test_guided_apply.py scripts/optimize.py scripts/test_optimize.py scripts/plugin_prune.py scripts/test_plugin_prune.py scripts/memory_trim.py scripts/test_memory_trim.py scripts/cli.py CLAUDE.md README.md docs/MAINTENANCE.md docs/ROADMAP.md docs/CLAIMS.md commands/optimize.md
grep -rniE "co-authored-by: (claude|opus|sonnet|haiku|fable)|noreply@anthropic|generated with \[claude code\]" scripts/experiment.py scripts/guided_apply.py scripts/test_guided_apply.py scripts/optimize.py scripts/test_optimize.py scripts/plugin_prune.py scripts/test_plugin_prune.py scripts/memory_trim.py scripts/test_memory_trim.py scripts/cli.py CLAUDE.md README.md docs/MAINTENANCE.md docs/ROADMAP.md docs/CLAIMS.md commands/optimize.md
```
Both commands must print nothing.

## Total estimate

Steps 1 to 8 combined: 16 to 26 working hours (roughly 2 to 4 working days at sustained pace), medium confidence, matching the spec's own top-level "2 to 4 working days" figure for wave R. The widest source of variance is step 4's CLI-argument-format confirmation: if the bare plugin name does not work cleanly, the fallback (looking up and passing the full `name@marketplace` id) adds an estimated 1 to 3 hours, already inside the range above.

## What this plan does not resolve, stated so the next reader does not assume it was missed by accident

- Whether `commands/optimize.md`'s single-file, three-section shape is the right long-term home for all of Pillar R, versus retiring an existing command to make room for dedicated files, is a founder call this plan does not make (see the 6 file cap section above).
- Automatic zero-use plugin detection (Ambiguity 2) is explicitly not built here; it is the natural next step once `discover_companions.py`/`doctor.py` from the sibling v1.8 wave exists and can supply real usage-adjacent data.
- The plugin-directory fingerprint exclusion gap (Ambiguity 3, `excluded_by_treats` never covering plugin dirs) is worked around by ordering for wave R's own experiments but is not closed as a general capability; a future wave doing anything else with plugin directories mid-experiment will hit the same hole.
