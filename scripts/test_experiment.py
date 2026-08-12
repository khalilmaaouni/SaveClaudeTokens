#!/usr/bin/env python3
"""Calibrated checks for experiment.build_record, the VERIFIED verdict logic."""
import json
import os
import subprocess
import sys
import tempfile
import time

import experiment as ex
import measure_tokens as mt

HERE = os.path.dirname(os.path.abspath(__file__))

# Every module global compute_fingerprint reads, and the temp-dir name each is
# pointed at while a test runs. Repointing all of them is what keeps a
# fingerprint test from hashing the real machine's config, which would make it
# pass or fail on what happens to be installed.
_PATH_ATTRS = ("CLAUDE_MD_PATH", "SETTINGS_PATH", "CLAUDE_JSON_PATH",
               "SKILLS_DIR", "PLUGINS_CACHE")
_PATH_LEAVES = ("CLAUDE.md", "settings.json", "claude.json", "skills",
                os.path.join("plugins", "cache"))


def check(name, cond):
    print(("ok  " if cond else "FAIL ") + name)
    assert cond, name


def _point_paths_at(td):
    saved = tuple(getattr(ex, k) for k in _PATH_ATTRS)
    for attr, leaf in zip(_PATH_ATTRS, _PATH_LEAVES):
        setattr(ex, attr, os.path.join(td, leaf))
    os.makedirs(os.path.join(td, "skills"), exist_ok=True)
    os.makedirs(os.path.join(td, "plugins", "cache"), exist_ok=True)
    return saved


def _restore_paths(saved):
    for attr, value in zip(_PATH_ATTRS, saved):
        setattr(ex, attr, value)


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def _usage_line(ts, inp, sub=False):
    return json.dumps({"timestamp": ts, "isSidechain": sub,
                       "message": {"model": "claude-x", "usage": {
                           "input_tokens": inp, "cache_read_input_tokens": 1000,
                           "output_tokens": 5,
                           "cache_creation": {"ephemeral_5m_input_tokens": 10,
                                              "ephemeral_1h_input_tokens": 0}}}}) + "\n"


def _baseline(schema=mt.SCHEMA, window=30, fr=80000, sessions=10):
    return {"label": "t", "started": "2026-08-01T00:00:00", "window_days": window,
            "schema": schema, "cohort_start_ts": 1_000_000, "cohort_end_ts": 3_592_000,
            "fingerprint_start": None, "treats": None,
            "summary": {"first_request_median": fr, "normalized_input_total": 1_000_000,
                        "parent_sessions": sessions}}


def _after(window=30, fr=60000, sessions=10):
    return {"_window_days": window, "first_request_median": fr,
            "normalized_input_total": 800_000, "parent_sessions": sessions}


def test_clean_before_after_is_verified():
    rec = ex.build_record(_baseline(fr=80000), _after(fr=60000), "2026-08-30T00:00:00")
    check("clean before/after is VERIFIED", rec["confidence"] == "VERIFIED")
    check("floor reduction is measured correctly", rec["floor_reduction_tokens"] == 20000)
    check("no reasons on a verified record", rec["reasons"] == [])


def test_schema_change_is_not_proven():
    # Calibration: same inputs but a schema bump must flip VERIFIED to NOT_PROVEN.
    rec = ex.build_record(_baseline(schema=mt.SCHEMA - 1), _after(), "2026-08-30T00:00:00")
    check("schema change downgrades to NOT_PROVEN", rec["confidence"] == "NOT_PROVEN")
    check("schema change is named as the reason",
          any("schema" in r for r in rec["reasons"]))


def test_window_mismatch_is_not_proven():
    rec = ex.build_record(_baseline(window=30), _after(window=7), "2026-08-30T00:00:00")
    check("window mismatch downgrades to NOT_PROVEN", rec["confidence"] == "NOT_PROVEN")
    check("window mismatch is named", any("window" in r for r in rec["reasons"]))


def test_thin_data_is_not_proven():
    rec = ex.build_record(_baseline(sessions=10), _after(sessions=1), "2026-08-30T00:00:00")
    check("thin post-change data downgrades to NOT_PROVEN", rec["confidence"] == "NOT_PROVEN")


def test_no_verified_record_without_a_real_floor_on_both_sides():
    b = _baseline(); b["summary"]["first_request_median"] = None
    rec = ex.build_record(b, _after(), "2026-08-30T00:00:00")
    check("missing before-floor cannot be VERIFIED", rec["confidence"] == "NOT_PROVEN")


# --- v2: cohorts by message timestamp, non-overlap, config fingerprint, --treats ---

def test_overlap_refusal():
    reason_bad = ex.check_cohort_order(before_end_ts=1000, after_start_ts=500)
    check("overlapping windows return a reason", reason_bad is not None)
    check("reason names the overlap", "overlap" in reason_bad)
    reason_touching = ex.check_cohort_order(before_end_ts=1000, after_start_ts=1000)
    check("equal boundaries are refused, not allowed", reason_touching is not None)
    check("the equal-boundary reason names the shared boundary",
          "both sides" in reason_touching)
    reason_ok = ex.check_cohort_order(before_end_ts=1000, after_start_ts=1500)
    check("non-overlapping windows are fine", reason_ok is None)


def test_fingerprint_mismatch_is_not_proven():
    b = _baseline()
    b["fingerprint_start"] = "aaa"
    rec = ex.build_record(b, _after(), "2026-08-30T00:00:00", fingerprint_end="bbb")
    check("fingerprint mismatch downgrades to NOT_PROVEN", rec["confidence"] == "NOT_PROVEN")
    check("config-change reason is named",
          any("config changed during experiment window" in r for r in rec["reasons"]))
    rec_same = ex.build_record(b, _after(), "2026-08-30T00:00:00", fingerprint_end="aaa")
    check("matching fingerprints add no config-change reason",
          not any("config changed" in r for r in rec_same["reasons"]))


def test_treats_exclusion_keeps_treatment_edit_from_tripping_the_downgrade():
    with tempfile.TemporaryDirectory() as td:
        saved = _point_paths_at(td)
        try:
            _write(ex.CLAUDE_MD_PATH, "original content")
            _write(ex.SETTINGS_PATH, "{}")
            _write(ex.CLAUDE_JSON_PATH, '{"mcpServers": {}}')
            fp_before_excluded = ex.compute_fingerprint(treats=ex.CLAUDE_MD_PATH)
            fp_before_plain = ex.compute_fingerprint(treats=None)
            _write(ex.CLAUDE_MD_PATH, "edited by the treatment")
            fp_after_excluded = ex.compute_fingerprint(treats=ex.CLAUDE_MD_PATH)
            fp_after_plain = ex.compute_fingerprint(treats=None)
            check("excluding the treatment target keeps the fingerprint stable "
                  "across its own edit", fp_before_excluded == fp_after_excluded)
            check("without --treats the same edit changes the fingerprint",
                  fp_before_plain != fp_after_plain)
        finally:
            _restore_paths(saved)


def test_treats_blind_spot_is_named_on_the_record_and_at_close():
    # M5. --treats settings.json blinds the guard to that whole file. The
    # ratified answer is visibility, not key-level hashing: the exclusion is
    # recorded and printed, so nobody reads the guard as stronger than it is.
    with tempfile.TemporaryDirectory() as td:
        saved = _point_paths_at(td)
        try:
            _write(ex.CLAUDE_MD_PATH, "md")
            _write(ex.SETTINGS_PATH, "{}")
            _write(ex.CLAUDE_JSON_PATH, "{}")
            check("nothing is excluded without --treats",
                  ex.excluded_by_treats(None) == [])
            excluded = ex.excluded_by_treats(ex.SETTINGS_PATH)
            check("--treats settings.json names settings.json as the blind spot",
                  excluded == [ex.SETTINGS_PATH])
            check("an out-of-scope --treats target excludes nothing",
                  ex.excluded_by_treats(os.path.join(td, "somewhere-else.txt")) == [])

            b = _baseline()
            b["fingerprint_excluded"] = excluded
            b["treats"] = ex.SETTINGS_PATH
            rec = ex.build_record(b, _after(), "2026-08-30T00:00:00")
            check("the blind spot is recorded on the ledger record",
                  rec["fingerprint_excluded"] == [ex.SETTINGS_PATH])
            check("the treated path is recorded on the ledger record",
                  rec["treats"] == ex.SETTINGS_PATH)
        finally:
            _restore_paths(saved)


def test_fingerprint_covers_claude_json_and_skill_files():
    # M6. mcpServers live in ~/.claude.json and skills load from
    # ~/.claude/skills/*/SKILL.md. Both change the startup floor, so a
    # fingerprint blind to them credits their effect to the named treatment.
    with tempfile.TemporaryDirectory() as td:
        saved = _point_paths_at(td)
        try:
            _write(ex.CLAUDE_MD_PATH, "md")
            _write(ex.SETTINGS_PATH, "{}")
            _write(ex.CLAUDE_JSON_PATH, '{"mcpServers": {}}')
            skill = os.path.join(ex.SKILLS_DIR, "some-skill", "SKILL.md")
            _write(skill, "original skill")
            base = ex.compute_fingerprint()

            _write(ex.CLAUDE_JSON_PATH, '{"mcpServers": {"new": {}}}')
            check("adding an MCP server to ~/.claude.json moves the fingerprint",
                  ex.compute_fingerprint() != base)

            _write(ex.CLAUDE_JSON_PATH, '{"mcpServers": {}}')
            check("restoring ~/.claude.json restores the fingerprint",
                  ex.compute_fingerprint() == base)

            _write(skill, "edited skill")
            check("editing a SKILL.md moves the fingerprint",
                  ex.compute_fingerprint() != base)

            _write(skill, "original skill")
            _write(os.path.join(ex.SKILLS_DIR, "brand-new", "SKILL.md"), "new one")
            check("installing a new skill moves the fingerprint",
                  ex.compute_fingerprint() != base)
        finally:
            _restore_paths(saved)


def test_fingerprint_manifest_resists_a_content_swap_between_files():
    # m10. Concatenating file bytes with no delimiter hashes "ab" + "c" the
    # same as "a" + "bc". A per-file manifest of sha lines cannot.
    with tempfile.TemporaryDirectory() as td:
        saved = _point_paths_at(td)
        try:
            _write(ex.CLAUDE_JSON_PATH, "{}")
            _write(ex.CLAUDE_MD_PATH, "ab")
            _write(ex.SETTINGS_PATH, "c")
            split_one = ex.compute_fingerprint()
            _write(ex.CLAUDE_MD_PATH, "a")
            _write(ex.SETTINGS_PATH, "bc")
            split_two = ex.compute_fingerprint()
            check("moving a byte across the file boundary moves the fingerprint",
                  split_one != split_two)
        finally:
            _restore_paths(saved)


def test_timestamp_cohorting_ignores_records_outside_window_in_same_file():
    with tempfile.TemporaryDirectory() as td:
        fp = os.path.join(td, "session.jsonl")

        def usage_line(ts, inp):
            return {"timestamp": ts, "isSidechain": False,
                    "message": {"model": "claude-x", "usage": {
                        "input_tokens": inp, "cache_read_input_tokens": 0,
                        "output_tokens": 5,
                        "cache_creation": {"ephemeral_5m_input_tokens": 0,
                                           "ephemeral_1h_input_tokens": 0}}}}

        with open(fp, "w") as f:
            f.write(json.dumps(usage_line("2020-01-01T00:00:00+00:00", 999999)) + "\n")
            f.write(json.dumps(usage_line("2026-08-10T00:00:00+00:00", 111)) + "\n")

        start_ts = ex._parse_ts("2026-08-01T00:00:00+00:00")
        end_ts = ex._parse_ts("2026-08-20T00:00:00+00:00")
        cohort = ex.collect_cohort(td, start_ts, end_ts)
        check("only the in-window record contributes to the cohort", len(cohort) == 1)
        check("the resumed old record's tokens are excluded from the totals",
              cohort[0]["input"] == 111)


def test_legacy_v1_baseline_can_never_be_verified():
    # C2. A v1.6 snapshot carries no fingerprint_start, no cohort_end_ts and
    # no treats. Every v2 guard is written as "downgrade if this moved", and a
    # missing field never moves, so such a baseline used to print VERIFIED
    # with not one of the v2 checks having run.
    legacy = {"label": "v16-era", "started": "2026-07-01T00:00:00",
              "window_days": 30, "schema": mt.SCHEMA,
              "summary": {"first_request_median": 80000,
                          "normalized_input_total": 1_000_000,
                          "parent_sessions": 10}}
    rec = ex.build_record(legacy, _after(fr=60000), "2026-08-30T00:00:00",
                          fingerprint_end="whatever")
    check("a legacy baseline is never VERIFIED", rec["confidence"] == "NOT_PROVEN")
    check("the reason names the legacy baseline by label",
          any("legacy baseline 'v16-era'" in r for r in rec["reasons"]))
    check("the reason names the fields that are missing",
          any("fingerprint_start" in r and "cohort_end_ts" in r and "treats" in r
              for r in rec["reasons"]))
    check("legacy_baseline_reason passes a complete v2 snapshot",
          ex.legacy_baseline_reason(_baseline()) is None)
    for key in ex.V2_BASELINE_KEYS:
        partial = _baseline()
        del partial[key]
        check(f"a baseline missing {key} alone is still not comparable",
              ex.legacy_baseline_reason(partial) is not None)


def test_min_sessions_guards_both_cohorts():
    # M4. The floor of a one-session before cohort is one session's floor, so
    # a thin baseline is exactly as unmeasurable as a thin after cohort.
    thin_before = ex.build_record(_baseline(sessions=1), _after(sessions=10),
                                  "2026-08-30T00:00:00")
    check("a one-session baseline cannot be VERIFIED",
          thin_before["confidence"] == "NOT_PROVEN")
    check("the thin before cohort is named as the reason",
          any("sessions before the change" in r for r in thin_before["reasons"]))
    thin_after = ex.build_record(_baseline(sessions=10), _after(sessions=1),
                                 "2026-08-30T00:00:00")
    check("a one-session after cohort still cannot be VERIFIED",
          thin_after["confidence"] == "NOT_PROVEN")
    check("the thin after cohort is named as the reason",
          any("sessions after the change" in r for r in thin_after["reasons"]))
    check("both cohorts at the minimum is VERIFIED",
          ex.build_record(_baseline(sessions=ex.MIN_SESSIONS),
                          _after(sessions=ex.MIN_SESSIONS),
                          "2026-08-30T00:00:00")["confidence"] == "VERIFIED")


def test_straddling_transcript_contributes_no_first_request():
    # M7. A transcript resumed across the cohort boundary has its first
    # in-window record mid-conversation. Counting that cheap turn as a startup
    # floor is how a floor reduction gets invented out of a resumed session.
    with tempfile.TemporaryDirectory() as td:
        straddler = os.path.join(td, "straddler.jsonl")
        with open(straddler, "w") as f:
            f.write(_usage_line("2026-08-01T00:00:00+00:00", 90000))
            f.write(_usage_line("2026-08-05T00:00:00+00:00", 300))
            f.write(_usage_line("2026-08-12T00:00:00+00:00", 400))
        fresh = os.path.join(td, "fresh.jsonl")
        with open(fresh, "w") as f:
            f.write(_usage_line("2026-08-11T00:00:00+00:00", 70000))
            f.write(_usage_line("2026-08-12T00:00:00+00:00", 500))

        start_ts = ex._parse_ts("2026-08-10T00:00:00+00:00")
        end_ts = ex._parse_ts("2026-08-20T00:00:00+00:00")
        cohort = {os.path.basename(s["file"]): s
                  for s in ex.collect_cohort(td, start_ts, end_ts)}
        check("both transcripts are in the cohort", set(cohort) ==
              {"straddler.jsonl", "fresh.jsonl"})
        check("the straddler is marked as one", cohort["straddler.jsonl"]["straddler"])
        check("the straddler contributes no first_request",
              cohort["straddler.jsonl"]["first_request"] == 0)
        check("the straddler's in-window tokens stay in the totals",
              cohort["straddler.jsonl"]["input"] == 400)
        check("a transcript that starts inside the window is not a straddler",
              not cohort["fresh.jsonl"]["straddler"])
        check("its genuine first record is the first_request",
              cohort["fresh.jsonl"]["first_request"] == 70000 + 1000 + 10)
        sm = mt.summarize(list(cohort.values()))
        check("only the genuine session reaches the floor median",
              sm["first_request_n"] == 1)
        check("the floor median is the genuine session's floor, not the "
              "straddler's mid-conversation turn",
              sm["first_request_median"] == 70000 + 1000 + 10)


def test_cohort_window_is_half_open_at_the_end():
    # m9. A record at exactly T used to land in both [T-n, T] and [T, T+n].
    with tempfile.TemporaryDirectory() as td:
        fp = os.path.join(td, "boundary.jsonl")
        with open(fp, "w") as f:
            f.write(_usage_line("2026-08-10T00:00:00+00:00", 111))

        boundary = ex._parse_ts("2026-08-10T00:00:00+00:00")
        before = ex.collect_cohort(td, boundary - 86400, boundary)
        after = ex.collect_cohort(td, boundary, boundary + 86400)
        check("the boundary record is excluded from the window that ends on it",
              before == [])
        check("the boundary record is included in the window that starts on it",
              len(after) == 1 and after[0]["input"] == 111)


def test_per_label_aggregation_never_sums_across_labels():
    records = [
        {"label": "a", "confidence": "VERIFIED", "floor_reduction_tokens": 1000},
        {"label": "a", "confidence": "VERIFIED", "floor_reduction_tokens": 2000},
        {"label": "b", "confidence": "NOT_PROVEN", "floor_reduction_tokens": 500000},
    ]
    by_label = ex.aggregate_by_label(records)
    check("each label gets its own row", set(by_label) == {"a", "b"})
    check("label a's reductions never include label b's number",
          500000 not in by_label["a"]["reductions"])
    check("label b's reductions never include label a's numbers",
          1000 not in by_label["b"]["reductions"]
          and 2000 not in by_label["b"]["reductions"])


# --- the cli routing itself, run end to end under a sandbox HOME ---

def _run_cli(home, args):
    """Run cli.py in a subprocess whose HOME is a throwaway directory, so the
    routing is exercised for real without reading or writing the machine's own
    ~/.claude. Both scripts resolve their paths from HOME at import time."""
    env = dict(os.environ)
    env["HOME"] = home
    return subprocess.run([sys.executable, os.path.join(HERE, "cli.py")] + args,
                          cwd=HERE, env=env, capture_output=True, text=True)


def test_cli_experiment_start_runs_and_pins_a_baseline():
    # C1. cmd_start takes five arguments and an epoch float; the cli passed
    # four and a strftime string, so this path raised TypeError every time.
    with tempfile.TemporaryDirectory() as home:
        os.makedirs(os.path.join(home, ".claude", "projects"))
        r = _run_cli(home, ["experiment", "start", "cli-smoke"])
        check("cli experiment start exits 0", r.returncode == 0)
        check("cli experiment start does not raise", "Traceback" not in r.stderr)
        snap = os.path.join(home, ".claude", "token-shield", "experiments",
                            "cli-smoke.json")
        check("cli experiment start pins a baseline file", os.path.exists(snap))
        with open(snap) as f:
            baseline = json.load(f)
        check("the pinned baseline carries the whole v2 shape",
              all(k in baseline for k in ex.V2_BASELINE_KEYS))
        check("cohort_end_ts is an epoch number, not a formatted string",
              isinstance(baseline["cohort_end_ts"], (int, float)))


def test_cli_experiment_end_on_a_legacy_baseline_is_not_proven():
    # C1 and C2 through the cli: `end` used to raise TypeError on the string
    # timestamp before it could reach any verdict at all.
    with tempfile.TemporaryDirectory() as home:
        os.makedirs(os.path.join(home, ".claude", "projects"))
        exp_dir = os.path.join(home, ".claude", "token-shield", "experiments")
        os.makedirs(exp_dir)
        with open(os.path.join(exp_dir, "v16.json"), "w") as f:
            json.dump({"label": "v16", "started": "2026-07-01T00:00:00",
                       "window_days": 30, "schema": mt.SCHEMA,
                       "summary": {"first_request_median": 80000,
                                   "normalized_input_total": 1_000_000,
                                   "parent_sessions": 10}}, f)
        r = _run_cli(home, ["experiment", "end", "v16"])
        check("cli experiment end exits 0", r.returncode == 0)
        check("cli experiment end does not raise", "Traceback" not in r.stderr)
        check("a legacy baseline ends NOT_PROVEN, never VERIFIED",
              "NOT_PROVEN" in r.stdout and "VERIFIED" not in r.stdout)
        check("the legacy baseline is named in the printed reason",
              "legacy baseline 'v16'" in r.stdout)


def test_cli_summary_reports_verified_per_label_and_never_sums():
    # C3. Three VERIFIED records, two of them the same label, one of them a
    # regression, used to print one clipped cross-label total of 10,000.
    with tempfile.TemporaryDirectory() as home:
        projects = os.path.join(home, ".claude", "projects", "p")
        os.makedirs(projects)
        now = time.time()
        for i in range(3):
            with open(os.path.join(projects, f"s{i}.jsonl"), "w") as f:
                for j in range(3):
                    stamp = time.strftime("%Y-%m-%dT%H:%M:%S+00:00",
                                          time.gmtime(now - 86400 - j * 60))
                    f.write(_usage_line(stamp, 50000 if j == 0 else 300))
        store = os.path.join(home, ".claude", "token-shield")
        os.makedirs(store)
        with open(os.path.join(store, "savings.jsonl"), "w") as f:
            for label, fr in (("diet-claude-md", 5000), ("prune-mcp", -8000),
                              ("diet-claude-md", 5000)):
                f.write(json.dumps({"schema": 2, "label": label,
                                    "confidence": "VERIFIED",
                                    "floor_reduction_tokens": fr}) + "\n")

        r = _run_cli(home, ["summary"])
        check("cli summary exits 0", r.returncode == 0)
        check("cli summary does not raise", "Traceback" not in r.stderr)
        check("each label gets its own row",
              "diet-claude-md" in r.stdout and "prune-mcp" in r.stdout)
        check("the regression is shown as a negative number, not clipped",
              "-8,000" in r.stdout)
        check("the repeated label is counted once, at its latest value",
              r.stdout.count("+5,000") == 1)
        check("no cross-label total is printed anywhere", "10,000" not in r.stdout)
        check("the regression is called what it is", "regression" in r.stdout)


if __name__ == "__main__":
    n = 0
    for name in sorted(dir(sys.modules[__name__])):
        if name.startswith("test_"):
            globals()[name]()
            n += 1
    print(f"\n{n} passed")
