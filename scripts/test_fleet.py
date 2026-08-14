#!/usr/bin/env python3
"""Self-check for fleet.py, Fleet F1 and F2. No framework, no fixtures.

    python3 scripts/test_fleet.py

Every test runs on fixture ledgers, fixture git repos, and fixture queue
dirs under a temp dir, never the real ~/.claude/ or ~/.token-shield/.

F2 (init, join, leave, the registration record) is covered from the section
marked "F2:" onward, below the F1 tests it was appended to.
"""

import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time

import fleet as fl

HERE = os.path.dirname(os.path.abspath(__file__))

GIT_AVAILABLE = shutil.which("git") is not None


def _skip(name, reason):
    print(f"skip {name}: {reason}")


# --- fixture helpers ---------------------------------------------------------

def _telem_row(recorded_at, session_id="sess-x", input=0, output=0, cache_read=0,
               cache_write_5m=0, cache_write_1h=0, cache_write_unsplit=0):
    """One fixture telemetry ledger row, shaped like
    session_end_telemetry.record()'s output."""
    return {
        "recorded_at": recorded_at,
        "session_id": session_id,
        "input": input,
        "output": output,
        "cache_read": cache_read,
        "cache_write_5m": cache_write_5m,
        "cache_write_1h": cache_write_1h,
        "cache_write_unsplit": cache_write_unsplit,
        "first_request": input,
        "calls": 1,
    }


def _write_ledger(path, rows):
    with open(path, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def _exp_row(timestamp, label="claude-md-diet", confidence="VERIFIED",
             target_metric="first_request_median", metric_delta=1000.0,
             direction="saving", fingerprint_start="abc123",
             fingerprint_end="abc123"):
    """One fixture proof-ledger record, shaped like experiment.build_record's
    output. Carries extra fields (evidence, cohort_before, sessions_before)
    on purpose: _day_experiments must whitelist by construction, not by
    accident of what happens to be present."""
    return {
        "schema": 2,
        "timestamp": timestamp,
        "label": label,
        "confidence": confidence,
        "reasons": [],
        "target_metric": target_metric,
        "metric_before": 9000.0,
        "metric_after": 9000.0 - metric_delta,
        "metric_delta": metric_delta,
        "direction": direction,
        "fingerprint_start": fingerprint_start,
        "fingerprint_end": fingerprint_end,
        "cohort_before": {"start": "2026-08-01T00:00:00", "end": "2026-08-05T00:00:00"},
        "sessions_before": 5,
        "evidence": "API usage counters, before/after over the same window, "
                    "cohorted by message timestamp",
    }


def _write_exp_ledger(path, rows):
    with open(path, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


LOCAL_CONFIG = {"org": "acme", "team": "ios", "environment": "ci",
                "hostname": "khalils-mbp.local", "salt": "org-salt-xyz"}

# fleet.py's `import experiment as exp` is the same cached module object
# test_experiment.py imports as `ex` (sys.modules keys by module name, not
# by import site), so its proven _point_paths_at/_restore_paths pattern
# (repoint every module-global path compute_fingerprint reads at a temp
# dir, restore after) works unchanged here to keep cmd_build/cmd_push's
# real compute_fingerprint() call off the actual machine's ~/.claude/*.
_EXP_PATH_ATTRS = ("CLAUDE_MD_PATH", "SETTINGS_PATH", "CLAUDE_JSON_PATH",
                   "SKILLS_DIR", "PLUGINS_CACHE")
_EXP_PATH_LEAVES = ("CLAUDE.md", "settings.json", "claude.json", "skills",
                    os.path.join("plugins", "cache"))


def _point_exp_paths_at(td):
    saved = tuple(getattr(fl.exp, k) for k in _EXP_PATH_ATTRS)
    for attr, leaf in zip(_EXP_PATH_ATTRS, _EXP_PATH_LEAVES):
        setattr(fl.exp, attr, os.path.join(td, leaf))
    os.makedirs(os.path.join(td, "skills"), exist_ok=True)
    os.makedirs(os.path.join(td, "plugins", "cache"), exist_ok=True)
    return saved


def _restore_exp_paths(saved):
    for attr, value in zip(_EXP_PATH_ATTRS, saved):
        setattr(fl.exp, attr, value)


def _capture_stderr(fn, *args, **kwargs):
    real_stderr = sys.stderr
    buf = io.StringIO()
    sys.stderr = buf
    try:
        result = fn(*args, **kwargs)
    finally:
        sys.stderr = real_stderr
    return result, buf.getvalue()


def _capture_stdout(fn, *args, **kwargs):
    real_stdout = sys.stdout
    buf = io.StringIO()
    sys.stdout = buf
    try:
        result = fn(*args, **kwargs)
    finally:
        sys.stdout = real_stdout
    return result, buf.getvalue()


def _git(args, cwd):
    subprocess.run(["git"] + args, cwd=cwd, check=True, capture_output=True, text=True)


def _make_bare_store(d, org_profile=None):
    """A local bare git repo that stands in for the org's fleet store, plus
    one working clone used only to seed an initial commit (an empty bare
    repo with nothing on its default branch cannot be cloned into a usable
    working tree by `git clone` alone in the exact same way; seeding one
    commit keeps the fixture boring and realistic). When `org_profile` is
    given (a dict), it is committed alongside README as org-profile.json at
    the store root in the same seed commit, so a `fleet init` test can
    start from an already-initialized store without a separate init push."""
    bare = os.path.join(d, "store.git")
    os.makedirs(bare)
    _git(["init", "--quiet", "--bare"], bare)
    seed = os.path.join(d, "seed")
    _git(["clone", "--quiet", bare, seed], d)
    with open(os.path.join(seed, "README"), "w") as f:
        f.write("fleet store\n")
    _git(["add", "README"], seed)
    if org_profile is not None:
        with open(os.path.join(seed, "org-profile.json"), "w") as f:
            json.dump(org_profile, f)
        _git(["add", "org-profile.json"], seed)
    _git(["-c", "user.email=t@t", "-c", "user.name=t", "commit", "--quiet", "-m", "seed"], seed)
    _git(["push", "--quiet"], seed)
    return bare


def _commit_count(repo_dir):
    """Number of commits reachable from HEAD in `repo_dir` (bare or not);
    used by the join idempotency tests to prove a second join adds no new
    commit to the store."""
    proc = subprocess.run(["git", "log", "--oneline"], cwd=repo_dir,
                          capture_output=True, text=True, check=True)
    return len([l for l in proc.stdout.splitlines() if l.strip()])


# (a) record builder correctness ---------------------------------------------

def test_build_record_aggregates_counters_and_experiments_for_the_day():
    with tempfile.TemporaryDirectory() as d:
        ledger = os.path.join(d, "ledger.jsonl")
        _write_ledger(ledger, [
            _telem_row("2026-08-10T09:00:00", input=100, output=50, cache_read=700,
                      cache_write_5m=150, cache_write_1h=25, cache_write_unsplit=25),
            _telem_row("2026-08-10T14:00:00", input=200, output=75, cache_read=300),
            _telem_row("2026-08-11T09:00:00", input=999, output=999),  # different day
        ])
        exp_ledger = os.path.join(d, "savings.jsonl")
        _write_exp_ledger(exp_ledger, [
            _exp_row("2026-08-10T18:00:00"),
            _exp_row("2026-08-11T18:00:00"),  # different day
        ])
        record = fl.build_record(ledger, exp_ledger, "2026-08-10", LOCAL_CONFIG,
                                 config_fingerprint="fp-1", token_shield_version="1.8.0")

    assert record is not None
    assert record["schema"] == 1
    assert record["date"] == "2026-08-10"
    assert record["team"] == "ios"
    assert record["environment"] == "ci"
    assert record["config_fingerprint"] == "fp-1"
    assert record["token_shield_version"] == "1.8.0"
    assert record["machine_id"] == fl.compute_machine_id("khalils-mbp.local", "org-salt-xyz")

    counters = record["counters"]["unknown"]
    assert counters["input_tokens"] == 300
    assert counters["output_tokens"] == 125
    assert counters["cache_read_input_tokens"] == 1000
    assert counters["cache_creation_input_tokens"] == 200  # 150+25+25

    assert len(record["experiments"]) == 1
    exp_item = record["experiments"][0]
    assert exp_item["label"] == "claude-md-diet"
    assert exp_item["confidence"] == "VERIFIED"
    assert exp_item["timestamp"] == "2026-08-10T18:00:00"
    assert exp_item["target_metric"] == "first_request_median"
    assert exp_item["metric_delta"] == 1000.0
    assert exp_item["direction"] == "saving"


def test_build_record_is_no_data_when_the_day_has_nothing():
    with tempfile.TemporaryDirectory() as d:
        ledger = os.path.join(d, "ledger.jsonl")
        exp_ledger = os.path.join(d, "savings.jsonl")
        record = fl.build_record(ledger, exp_ledger, "2026-08-10", LOCAL_CONFIG)
    assert record is None


def test_build_record_reinjection_dropped_cache_creation_component():
    # Calibration proof kept as a runnable check: the aggregation must sum
    # ALL THREE cache-write ledger fields into cache_creation_input_tokens,
    # not just cache_write_5m. This exact scenario is what the manual
    # break/restore cycle (documented in the build report) exercised
    # against fleet._day_counters directly.
    with tempfile.TemporaryDirectory() as d:
        ledger = os.path.join(d, "ledger.jsonl")
        _write_ledger(ledger, [
            _telem_row("2026-08-10T09:00:00", input=10, cache_read=10,
                      cache_write_5m=1, cache_write_1h=2, cache_write_unsplit=3),
        ])
        counters = fl._day_counters(ledger, "2026-08-10")
    assert counters["unknown"]["cache_creation_input_tokens"] == 6


# (b) push against a local bare repo fixture lands the file at the exact path

def test_push_lands_the_file_at_the_exact_path_in_a_bare_repo():
    if not GIT_AVAILABLE:
        _skip("test_push_lands_the_file_at_the_exact_path_in_a_bare_repo", "no git binary")
        return
    with tempfile.TemporaryDirectory() as d:
        bare = _make_bare_store(d)
        record = {"schema": 1, "date": "2026-08-10", "counters": {}, "experiments": []}
        queue_dir = os.path.join(d, "queue")
        ok = fl.push_record(record, bare, "acme", "deadbeef" * 8, "2026-08-10",
                            queue_dir=queue_dir)
        assert ok is True

        check = os.path.join(d, "check")
        _git(["clone", "--quiet", bare, check], d)
        landed = os.path.join(check, "fleet", "acme", "deadbeef" * 8, "2026-08-10.json")
        assert os.path.isfile(landed)
        with open(landed) as f:
            stored = json.load(f)
        assert stored == record
        assert not os.path.isdir(queue_dir) or not os.listdir(queue_dir)


def test_push_twice_with_the_same_record_is_a_no_op_second_time():
    if not GIT_AVAILABLE:
        _skip("test_push_twice_with_the_same_record_is_a_no_op_second_time", "no git binary")
        return
    with tempfile.TemporaryDirectory() as d:
        bare = _make_bare_store(d)
        record = {"schema": 1, "date": "2026-08-10", "counters": {}, "experiments": []}
        ok1 = fl.push_record(record, bare, "acme", "cafefeed" * 8, "2026-08-10")
        ok2 = fl.push_record(record, bare, "acme", "cafefeed" * 8, "2026-08-10")
        assert ok1 is True
        assert ok2 is True


# (c) unreachable-store fixture queues locally with one warning, no raise ----

def test_push_to_unreachable_store_queues_locally_and_warns_once_no_raise():
    with tempfile.TemporaryDirectory() as d:
        unreachable = os.path.join(d, "does-not-exist", "store.git")
        queue_dir = os.path.join(d, "queue")
        record = {"schema": 1, "date": "2026-08-10", "counters": {}, "experiments": []}
        (ok, err) = _capture_stderr(fl.push_record, record, unreachable, "acme",
                                    "beefbeef" * 8, "2026-08-10", queue_dir=queue_dir)
        assert ok is False
        warn_lines = [l for l in err.strip().splitlines() if l.strip()]
        assert len(warn_lines) == 1
        assert warn_lines[0].startswith("warning:")
        queued = os.listdir(queue_dir)
        assert len(queued) == 1
        with open(os.path.join(queue_dir, queued[0])) as f:
            stored = json.load(f)
        assert stored == record


def test_queued_local_file_has_restrictive_permissions():
    with tempfile.TemporaryDirectory() as d:
        unreachable = os.path.join(d, "does-not-exist", "store.git")
        queue_dir = os.path.join(d, "queue")
        record = {"schema": 1, "date": "2026-08-10", "counters": {}, "experiments": []}
        _capture_stderr(fl.push_record, record, unreachable, "acme", "aa" * 32,
                        "2026-08-10", queue_dir=queue_dir)
        queued = os.path.join(queue_dir, os.listdir(queue_dir)[0])
        dir_mode = stat.S_IMODE(os.stat(queue_dir).st_mode)
        file_mode = stat.S_IMODE(os.stat(queued).st_mode)
    assert dir_mode == 0o700, oct(dir_mode)
    assert file_mode == 0o600, oct(file_mode)


# (d) reader refuses a newer-schema record ------------------------------------

def test_load_record_refuses_a_newer_schema_than_it_understands():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "future.json")
        with open(path, "w") as f:
            json.dump({"schema": fl.SCHEMA_VERSION + 1, "date": "2026-08-10"}, f)
        raised = False
        message = ""
        try:
            fl.load_record(path)
        except fl.FleetSchemaError as e:
            raised = True
            message = str(e)
    assert raised
    assert "newer" in message
    assert str(fl.SCHEMA_VERSION + 1) in message


def test_load_record_accepts_the_current_schema():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "current.json")
        with open(path, "w") as f:
            json.dump({"schema": fl.SCHEMA_VERSION, "date": "2026-08-10"}, f)
        record = fl.load_record(path)
    assert record["schema"] == fl.SCHEMA_VERSION


# (e) the projection strips a smuggled non-whitelisted field -----------------

def test_projection_strips_a_smuggled_field_not_named_by_the_schema():
    with tempfile.TemporaryDirectory() as d:
        ledger = os.path.join(d, "ledger.jsonl")
        _write_ledger(ledger, [_telem_row("2026-08-10T09:00:00", input=100, cache_read=900)])
        exp_ledger = os.path.join(d, "savings.jsonl")
        candidate = fl.build_candidate(ledger, exp_ledger, "2026-08-10", LOCAL_CONFIG)
    assert candidate is not None

    # Bypass the schema walk: bolt fields onto the candidate the way a
    # careless future edit to build_candidate() might, one that a schema
    # bump never authorized. These are exactly the classes the design doc
    # names as deliberately absent (prompts, file contents, user names).
    candidate["user_name"] = "khalil"
    candidate["counters"]["unknown"]["prompt_snippet"] = "please summarize this file"
    # RED: looking at the raw candidate (pre-projection), the leak is there.
    assert candidate["user_name"] == "khalil"
    assert candidate["counters"]["unknown"]["prompt_snippet"] == "please summarize this file"

    schema = fl._load_schema()
    projected = fl.sig._project(schema, candidate)

    # GREEN: the schema walk is what stops it, not luck.
    assert "user_name" not in projected
    assert "prompt_snippet" not in projected["counters"]["unknown"]
    # And the legitimate fields the schema does name still made it through.
    assert projected["schema"] == 1
    assert projected["counters"]["unknown"]["input_tokens"] == 100


def test_projection_disabled_lets_the_smuggled_field_survive_build_record():
    # Calibration proof that build_record's OWN internal candidate is what
    # gets projected, not a copy this test built on the side: monkeypatch
    # the module-global build_candidate (build_record looks it up by name
    # at call time, so this reaches the real call inside build_record) to
    # bolt on a smuggled field, then confirm build_record's actual return
    # value still does not carry it. If build_record ever skipped its
    # sig._project() call (returned the raw candidate instead, exactly the
    # defect manually reinjected and reverted during F1 development, see
    # the build report), this assertion is the one that goes RED.
    with tempfile.TemporaryDirectory() as d:
        ledger = os.path.join(d, "ledger.jsonl")
        _write_ledger(ledger, [_telem_row("2026-08-10T09:00:00", input=100, cache_read=900)])
        exp_ledger = os.path.join(d, "savings.jsonl")

        real_build_candidate = fl.build_candidate

        def _smuggling_build_candidate(*args, **kwargs):
            candidate = real_build_candidate(*args, **kwargs)
            if candidate is not None:
                candidate["repo_name"] = "SaveClaudeTokens"
            return candidate

        fl.build_candidate = _smuggling_build_candidate
        try:
            record = fl.build_record(ledger, exp_ledger, "2026-08-10", LOCAL_CONFIG)
        finally:
            fl.build_candidate = real_build_candidate

    assert record is not None
    assert "repo_name" not in record  # GREEN: build_record never returns the raw candidate


# --- config helpers -----------------------------------------------------------

def test_read_local_config_returns_none_when_absent():
    with tempfile.TemporaryDirectory() as d:
        missing = os.path.join(d, "does-not-exist.json")
        assert fl._read_local_config(missing) is None


def test_read_local_config_returns_none_on_malformed_json():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "config.json")
        with open(path, "w") as f:
            f.write("not json")
        assert fl._read_local_config(path) is None


def test_compute_machine_id_is_stable_and_salt_dependent():
    a = fl.compute_machine_id("host-1", "salt-a")
    b = fl.compute_machine_id("host-1", "salt-a")
    c = fl.compute_machine_id("host-1", "salt-b")
    assert a == b
    assert a != c
    assert len(a) == 64  # sha256 hex digest


def test_cmd_build_falls_back_to_real_compute_fingerprint_off_a_fixture_config():
    # Exercises cmd_build's "no --config-fingerprint given" branch, which
    # calls the real exp.compute_fingerprint() in production. Safe here
    # only because _point_exp_paths_at repoints every module-global path
    # that function reads at a temp dir first (the same technique
    # test_experiment.py already uses on the same, cached module object),
    # so this never hashes the real machine's ~/.claude/*.
    with tempfile.TemporaryDirectory() as d:
        saved = _point_exp_paths_at(d)
        try:
            with open(fl.exp.CLAUDE_MD_PATH, "w") as f:
                f.write("fixture claude.md\n")
            with open(fl.exp.SETTINGS_PATH, "w") as f:
                f.write("{}")

            config_path = os.path.join(d, "fleet-config.json")
            with open(config_path, "w") as f:
                json.dump(LOCAL_CONFIG, f)
            ledger = os.path.join(d, "ledger.jsonl")
            _write_ledger(ledger, [_telem_row("2026-08-10T09:00:00", input=100, cache_read=900)])
            exp_ledger = os.path.join(d, "savings.jsonl")

            real_stdout = sys.stdout
            buf = io.StringIO()
            sys.stdout = buf
            try:
                rc = fl.cmd_build("2026-08-10", config_path, ledger, exp_ledger,
                                  None, "1.8.0")  # config_fingerprint=None -> real call
            finally:
                sys.stdout = real_stdout
            # Same fixture dir, same paths, still repointed: proves the
            # fixture files' content (not the real machine's) drove the
            # hash, since compute_fingerprint's manifest includes the
            # path string itself (a file move changes the hash on
            # purpose), so a replay must reuse these exact paths.
            replay = fl.exp.compute_fingerprint()
            printed = buf.getvalue()
        finally:
            _restore_exp_paths(saved)

    assert rc == 0
    record = json.loads(printed)
    assert isinstance(record.get("config_fingerprint"), str)
    assert len(record["config_fingerprint"]) > 0
    assert replay == record["config_fingerprint"]


# --- CLI-level NO DATA / refusal paths ----------------------------------------

def test_cmd_build_no_data_when_config_missing():
    with tempfile.TemporaryDirectory() as d:
        missing_config = os.path.join(d, "no-config.json")
        rc, err = _capture_stderr(fl.cmd_build, "2026-08-10", missing_config,
                                  os.path.join(d, "ledger.jsonl"),
                                  os.path.join(d, "savings.jsonl"),
                                  "fp", "1.8.0")
    assert rc == 2
    assert "NO DATA" in err


def test_cmd_build_no_data_when_day_is_empty():
    with tempfile.TemporaryDirectory() as d:
        config_path = os.path.join(d, "config.json")
        with open(config_path, "w") as f:
            json.dump(LOCAL_CONFIG, f)
        rc, err = _capture_stderr(fl.cmd_build, "2026-08-10", config_path,
                                  os.path.join(d, "ledger.jsonl"),
                                  os.path.join(d, "savings.jsonl"),
                                  "fp", "1.8.0")
    assert rc == 2
    assert "NO DATA" in err


def test_cmd_push_refuses_without_org_or_salt():
    with tempfile.TemporaryDirectory() as d:
        config_path = os.path.join(d, "config.json")
        with open(config_path, "w") as f:
            json.dump({"team": "ios"}, f)  # no org, no salt
        ledger = os.path.join(d, "ledger.jsonl")
        _write_ledger(ledger, [_telem_row("2026-08-10T09:00:00", input=100, cache_read=900)])
        rc, err = _capture_stderr(fl.cmd_push, "2026-08-10", config_path, ledger,
                                  os.path.join(d, "savings.jsonl"), "fp", "1.8.0",
                                  os.path.join(d, "nonexistent.git"), None)
    assert rc == 2
    assert "refused" in err


# --- F2: build_registration_record --------------------------------------------

def test_build_registration_record_is_never_none_even_for_an_empty_day():
    record = fl.build_registration_record("2026-08-10", LOCAL_CONFIG,
                                          config_fingerprint="fp-1",
                                          token_shield_version="1.8.0")
    assert record is not None
    assert record["schema"] == fl.SCHEMA_VERSION
    assert record["date"] == "2026-08-10"
    assert record["counters"] == {}
    assert record["experiments"] == []
    assert record["team"] == "ios"
    assert record["environment"] == "ci"
    assert record["machine_id"] == fl.compute_machine_id("khalils-mbp.local", "org-salt-xyz")
    assert record["config_fingerprint"] == "fp-1"
    assert record["token_shield_version"] == "1.8.0"


def test_build_registration_record_projection_strips_a_smuggled_field():
    # Same discipline as F1's test_projection_strips_a_smuggled_field: bolt
    # a field the schema never names onto the candidate the way a careless
    # edit might, and prove sig._project (not luck) is what removes it.
    real_project = fl.sig._project

    def _smuggling_project(schema, candidate):
        candidate["user_name"] = "khalil"
        return real_project(schema, candidate)

    fl.sig._project = _smuggling_project
    try:
        record = fl.build_registration_record("2026-08-10", LOCAL_CONFIG)
    finally:
        fl.sig._project = real_project
    assert "user_name" not in record


# --- F2: fleet init -------------------------------------------------------------

DEFAULT_ORG_PROFILE = {"schema": 1, "org": "acme", "salt": "org-salt-xyz",
                       "default_mode": "conservative", "telemetry": "counters_only",
                       "push_cadence": "manual"}


def test_init_writes_org_profile_and_prints_the_disclosure():
    if not GIT_AVAILABLE:
        _skip("test_init_writes_org_profile_and_prints_the_disclosure", "no git binary")
        return
    with tempfile.TemporaryDirectory() as d:
        bare = _make_bare_store(d)
        rc, out = _capture_stdout(fl.cmd_init, bare, "acme", "org-salt-xyz", "balanced", False)
        assert rc == 0
        assert "NEVER SHARED" in out
        assert "prompts" in out
        assert "initialized fleet store" in out

        check = os.path.join(d, "check")
        _git(["clone", "--quiet", bare, check], d)
        with open(os.path.join(check, "org-profile.json")) as f:
            profile = json.load(f)
        assert profile["org"] == "acme"
        assert profile["salt"] == "org-salt-xyz"
        assert profile["default_mode"] == "balanced"
        assert profile["telemetry"] == "counters_only"
        assert os.path.isfile(os.path.join(check, "fleet", ".gitkeep"))


def test_init_disclosure_prints_even_when_the_store_is_unreachable():
    # Calibrates the "disclosure prints before anything is created"
    # ordering: if a future edit moved the print(DISCLOSURE_TEXT) call
    # after the clone succeeded, this goes red the moment the store cannot
    # be reached at all, because the disclosure would never print. During
    # development this was proven by moving the print call after the
    # clone's ok check, confirming this assertion fails, then restoring it.
    with tempfile.TemporaryDirectory() as d:
        unreachable = os.path.join(d, "does-not-exist", "store.git")
        rc, out = _capture_stdout(fl.cmd_init, unreachable, "acme", "salt-x", "balanced", False)
    assert rc == 2
    assert "NEVER SHARED" in out
    assert "prompts" in out


def test_init_refuses_to_overwrite_existing_profile_without_force():
    if not GIT_AVAILABLE:
        _skip("test_init_refuses_to_overwrite_existing_profile_without_force", "no git binary")
        return
    with tempfile.TemporaryDirectory() as d:
        bare = _make_bare_store(d, org_profile=DEFAULT_ORG_PROFILE)
        rc, err = _capture_stderr(fl.cmd_init, bare, "acme", "new-salt", "balanced", False)
        assert rc == 2
        assert "force" in err

        check = os.path.join(d, "check")
        _git(["clone", "--quiet", bare, check], d)
        with open(os.path.join(check, "org-profile.json")) as f:
            stored = json.load(f)
    assert stored == DEFAULT_ORG_PROFILE


def test_init_with_force_overwrites_existing_profile():
    if not GIT_AVAILABLE:
        _skip("test_init_with_force_overwrites_existing_profile", "no git binary")
        return
    with tempfile.TemporaryDirectory() as d:
        bare = _make_bare_store(d, org_profile=DEFAULT_ORG_PROFILE)
        rc, _out = _capture_stdout(fl.cmd_init, bare, "acme", "new-salt", "aggressive", True)
        assert rc == 0

        check = os.path.join(d, "check")
        _git(["clone", "--quiet", bare, check], d)
        with open(os.path.join(check, "org-profile.json")) as f:
            stored = json.load(f)
    assert stored["salt"] == "new-salt"
    assert stored["default_mode"] == "aggressive"


def test_init_refuses_an_invalid_default_mode():
    with tempfile.TemporaryDirectory() as d:
        unused_store = os.path.join(d, "unused.git")
        rc, err = _capture_stderr(fl.cmd_init, unused_store, "acme", "salt-x", "chaotic", False)
        assert rc == 2
        assert "--default-mode" in err
        assert not os.path.exists(unused_store)  # refused before ever touching the store


class _FakeNonTtyStdin:
    def isatty(self):
        return False


def test_init_refuses_missing_required_values_without_a_tty():
    real_stdin = sys.stdin
    sys.stdin = _FakeNonTtyStdin()
    try:
        rc, err = _capture_stderr(fl.cmd_init, None, None, None, None, False)
    finally:
        sys.stdin = real_stdin
    assert rc == 2
    assert "refused" in err
    assert "store" in err


# --- F2: fleet join ---------------------------------------------------------------

def _join_args(store, config_path, queue_dir, team="ios", environment="ci",
               hostname="test-host", day="2026-08-14"):
    return (store, "acme", "org-salt-xyz", team, environment, hostname, day,
           config_path, queue_dir, "fp-1", "1.8.0")


def test_join_writes_local_config_and_lands_the_registration_in_a_bare_repo():
    if not GIT_AVAILABLE:
        _skip("test_join_writes_local_config_and_lands_the_registration_in_a_bare_repo", "no git binary")
        return
    with tempfile.TemporaryDirectory() as d:
        bare = _make_bare_store(d)
        config_path = os.path.join(d, "fleet-config.json")
        queue_dir = os.path.join(d, "queue")
        rc, out = _capture_stdout(fl.cmd_join, *_join_args(bare, config_path, queue_dir))
        assert rc == 0
        assert "joined fleet" in out

        with open(config_path) as f:
            local_config = json.load(f)
        assert local_config["org"] == "acme"
        assert local_config["salt"] == "org-salt-xyz"
        assert local_config["hostname"] == "test-host"
        assert local_config["team"] == "ios"
        assert local_config["environment"] == "ci"
        assert local_config["store"] == bare

        machine_id = fl.compute_machine_id("test-host", "org-salt-xyz")
        check = os.path.join(d, "check")
        _git(["clone", "--quiet", bare, check], d)
        landed = os.path.join(check, "fleet", "acme", machine_id, "2026-08-14.json")
        assert os.path.isfile(landed)
        with open(landed) as f:
            record = json.load(f)
    assert record["machine_id"] == machine_id
    assert record["team"] == "ios"
    assert record["environment"] == "ci"
    assert record["counters"] == {}
    assert record["experiments"] == []
    assert record["config_fingerprint"] == "fp-1"
    assert record["token_shield_version"] == "1.8.0"


def test_join_writes_config_with_restrictive_permissions():
    with tempfile.TemporaryDirectory() as d:
        unreachable = os.path.join(d, "does-not-exist", "store.git")
        config_path = os.path.join(d, "nested", "fleet-config.json")
        queue_dir = os.path.join(d, "queue")
        _capture_stdout(fl.cmd_join, *_join_args(unreachable, config_path, queue_dir))
        dir_mode = stat.S_IMODE(os.stat(os.path.dirname(config_path)).st_mode)
        file_mode = stat.S_IMODE(os.stat(config_path).st_mode)
    assert dir_mode == 0o700, oct(dir_mode)
    assert file_mode == 0o600, oct(file_mode)


def test_join_to_an_unreachable_store_still_writes_config_and_never_blocks():
    with tempfile.TemporaryDirectory() as d:
        unreachable = os.path.join(d, "does-not-exist", "store.git")
        config_path = os.path.join(d, "fleet-config.json")
        queue_dir = os.path.join(d, "queue")
        rc, err = _capture_stderr(fl.cmd_join, *_join_args(unreachable, config_path, queue_dir))
        assert rc == 0  # never blocked by an unreachable store
        assert os.path.isfile(config_path)
        warn_lines = [l for l in err.strip().splitlines() if l.strip()]
        assert len(warn_lines) == 1
        assert warn_lines[0].startswith("warning:")
        assert os.path.isdir(queue_dir)
        assert len(os.listdir(queue_dir)) == 1


def test_join_refuses_missing_org_or_salt():
    with tempfile.TemporaryDirectory() as d:
        config_path = os.path.join(d, "fleet-config.json")
        rc, err = _capture_stderr(fl.cmd_join, "https://example.invalid/store.git",
                                  None, None, None, None, "host", "2026-08-14",
                                  config_path, None, "fp", "1.8.0")
        assert rc == 2
        assert "refused" in err
        assert not os.path.isfile(config_path)


def test_join_twice_is_idempotent_one_commit_in_the_store():
    if not GIT_AVAILABLE:
        _skip("test_join_twice_is_idempotent_one_commit_in_the_store", "no git binary")
        return
    with tempfile.TemporaryDirectory() as d:
        bare = _make_bare_store(d)
        config_path = os.path.join(d, "fleet-config.json")
        queue_dir = os.path.join(d, "queue")
        args = _join_args(bare, config_path, queue_dir)

        rc1, _ = _capture_stdout(fl.cmd_join, *args)
        commits_after_first = _commit_count(bare)
        rc2, err2 = _capture_stderr(fl.cmd_join, *args)
        commits_after_second = _commit_count(bare)
        # A genuine no-op re-join never falls back to the local queue: it
        # recognizes nothing changed before ever attempting a commit. A
        # regression that removed that early check still leaves the commit
        # count unchanged (git itself refuses an empty commit), but it
        # would start queuing and warning on every idempotent re-join,
        # which this catches.
        assert err2 == ""
        assert not os.path.isdir(queue_dir) or not os.listdir(queue_dir)
    assert rc1 == 0 and rc2 == 0
    assert commits_after_second == commits_after_first  # one registration, second join changes nothing


def test_join_idempotency_guard_calibrated_break_then_restore():
    # Calibration: temporarily breaks the exact guard (_has_staged_changes)
    # that makes a second join a no-op at the git level, proving this test
    # suite would catch a regression that reintroduced a duplicate
    # registration commit. Forcing _has_staged_changes to lie ("changed")
    # is not enough on its own: git's own `commit` refuses an empty commit,
    # so a second, independent safety net still saves an otherwise-broken
    # guard. The commit call is forced to `--allow-empty` too, the same way
    # a real regression might (a future edit adds --allow-empty for some
    # unrelated flaky-diff reason and only then exposes the missing guard),
    # so this calibration actually reaches the duplicate-commit failure it
    # claims to catch. Both fakes are restored in a `finally`, so no other
    # test observes either one broken.
    if not GIT_AVAILABLE:
        _skip("test_join_idempotency_guard_calibrated_break_then_restore", "no git binary")
        return
    with tempfile.TemporaryDirectory() as d:
        bare = _make_bare_store(d)
        config_path = os.path.join(d, "fleet-config.json")
        queue_dir = os.path.join(d, "queue")
        args = _join_args(bare, config_path, queue_dir)

        real_has_staged_changes = fl._has_staged_changes
        real_run_git = fl._run_git

        def _fake_run_git(git_args, cwd=None, timeout=30):
            if "commit" in git_args:
                idx = git_args.index("commit")
                git_args = git_args[:idx + 1] + ["--allow-empty"] + git_args[idx + 1:]
            return real_run_git(git_args, cwd=cwd, timeout=timeout)

        fl._has_staged_changes = lambda clone_dir: True  # BROKEN: always claims "changed"
        fl._run_git = _fake_run_git  # BROKEN: lets an empty commit through anyway
        try:
            _capture_stdout(fl.cmd_join, *args)
            commits_after_first = _commit_count(bare)
            _capture_stdout(fl.cmd_join, *args)
            commits_after_second_broken = _commit_count(bare)
        finally:
            fl._has_staged_changes = real_has_staged_changes
            fl._run_git = real_run_git

        # RED: with the guard broken, the second join added a duplicate commit.
        assert commits_after_second_broken == commits_after_first + 1

        # GREEN: with the real guard restored, a third join changes nothing.
        _capture_stdout(fl.cmd_join, *args)
        commits_after_restored = _commit_count(bare)
    assert commits_after_restored == commits_after_second_broken


def test_join_default_day_is_today():
    with tempfile.TemporaryDirectory() as d:
        unreachable = os.path.join(d, "does-not-exist", "store.git")  # keep it offline and fast
        config_path = os.path.join(d, "fleet-config.json")
        queue_dir = os.path.join(d, "queue")
        rc, _out = _capture_stdout(
            fl.cmd_join, unreachable, "acme", "org-salt-xyz", None, None, "test-host",
            None,  # no --day: must default to today
            config_path, queue_dir, "fp-1", "1.8.0")
        assert rc == 0
        today = time.strftime("%Y-%m-%d")
        queued = os.listdir(queue_dir)
        assert len(queued) == 1
        assert queued[0].endswith(f"__{today}.json")


# --- F2: fleet leave --------------------------------------------------------------

def test_leave_removes_the_local_config():
    with tempfile.TemporaryDirectory() as d:
        config_path = os.path.join(d, "fleet-config.json")
        with open(config_path, "w") as f:
            json.dump({"org": "acme"}, f)
        rc, out = _capture_stdout(fl.cmd_leave, config_path)
        assert rc == 0
        assert not os.path.isfile(config_path)
        assert "left the fleet" in out


def test_leave_when_never_joined_is_a_harmless_noop():
    with tempfile.TemporaryDirectory() as d:
        config_path = os.path.join(d, "does-not-exist.json")
        rc, out = _capture_stdout(fl.cmd_leave, config_path)
        assert rc == 0
        assert not os.path.isfile(config_path)
        assert "not joined" in out


def test_leave_then_join_reregisters():
    if not GIT_AVAILABLE:
        _skip("test_leave_then_join_reregisters", "no git binary")
        return
    with tempfile.TemporaryDirectory() as d:
        bare = _make_bare_store(d)
        config_path = os.path.join(d, "fleet-config.json")
        queue_dir = os.path.join(d, "queue")
        args = _join_args(bare, config_path, queue_dir)

        _capture_stdout(fl.cmd_join, *args)
        assert os.path.isfile(config_path)

        fl.cmd_leave(config_path)
        assert not os.path.isfile(config_path)

        rc, out = _capture_stdout(fl.cmd_join, *args)
        assert rc == 0
        assert "joined fleet" in out
        assert os.path.isfile(config_path)
        with open(config_path) as f:
            cfg = json.load(f)
        assert cfg["org"] == "acme"
        assert cfg["hostname"] == "test-host"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
