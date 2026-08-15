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
import token_shield as ts

import metrics as met
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
            "fingerprint_start": None, "fingerprint_method": ex.FINGERPRINT_METHOD,
            "treats": None,
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
    # m1. NOT_PROVEN alone does not say which cohort was too thin to trust;
    # the reason must name the side, the same way every sibling reason does
    # (schema names the schema, window names both window lengths).
    rec = ex.build_record(_baseline(sessions=10), _after(sessions=1), "2026-08-30T00:00:00")
    check("thin post-change data downgrades to NOT_PROVEN", rec["confidence"] == "NOT_PROVEN")
    check("the reason names the after side as the thin one",
          any("after the change" in r for r in rec["reasons"]))
    check("the before side, which was not thin, is not named",
          not any("before the change" in r for r in rec["reasons"]))

    rec_before = ex.build_record(_baseline(sessions=1), _after(sessions=10),
                                 "2026-08-30T00:00:00")
    check("the reason names the before side when that is the thin one",
          any("before the change" in r for r in rec_before["reasons"]))
    check("the after side, which was not thin, is not named",
          not any("after the change" in r for r in rec_before["reasons"]))


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


def test_canonical_fingerprint_ignores_volatile_telemetry_keys():
    # H1 (the real defect). ~/.claude.json is Claude Code's own live state
    # file; lastUsedAt and usageCount move on their own several times a
    # minute with zero configuration change involved. A raw-byte hash of the
    # file therefore differs between fingerprint_start and fingerprint_end on
    # EVERY experiment, appending "config changed during experiment window"
    # every single time, which makes VERIFIED structurally unreachable.
    #
    # RED (without _strip_volatile / canonical hashing, i.e. a plain
    # hashlib.sha256 of the raw bytes as the original code did): the two
    # fingerprints below differ, because "usageCount": 53811 vs 53839 and
    # "lastUsedAt" moved, and the assertion below fails.
    with tempfile.TemporaryDirectory() as td:
        saved = _point_paths_at(td)
        try:
            _write(ex.CLAUDE_MD_PATH, "md")
            _write(ex.SETTINGS_PATH, "{}")
            _write(ex.CLAUDE_JSON_PATH, json.dumps({
                "mcpServers": {"foo": {"command": "bar"}},
                "lastUsedAt": 1786754517692, "usageCount": 53811}))
            fp_before = ex.compute_fingerprint()
            _write(ex.CLAUDE_JSON_PATH, json.dumps({
                "mcpServers": {"foo": {"command": "bar"}},
                "lastUsedAt": 1786754553039, "usageCount": 53839}))
            fp_after = ex.compute_fingerprint()
            check("a fingerprint pair differing ONLY in lastUsedAt/usageCount "
                  "is EQUAL, not flagged as a config change",
                  fp_before == fp_after)
        finally:
            _restore_paths(saved)


def test_canonical_fingerprint_still_moves_on_a_real_config_change():
    # The mirror of the test above, and the more important of the two: a
    # fingerprint that never moves would be a worse defect than the one
    # being fixed, since it would blind the guard entirely rather than
    # merely over-trip it. Adding a real MCP server entry, alongside
    # telemetry noise that must NOT move the hash, still has to move it.
    #
    # RED (if volatile-key stripping were implemented by blinding the whole
    # file instead of removing just the named keys, e.g. always returning a
    # constant hash for ~/.claude.json): this assertion fails because the
    # real mcpServers change would not be seen either.
    with tempfile.TemporaryDirectory() as td:
        saved = _point_paths_at(td)
        try:
            _write(ex.CLAUDE_MD_PATH, "md")
            _write(ex.SETTINGS_PATH, "{}")
            _write(ex.CLAUDE_JSON_PATH, json.dumps({
                "mcpServers": {}, "lastUsedAt": 1000, "usageCount": 1}))
            fp_before = ex.compute_fingerprint()
            _write(ex.CLAUDE_JSON_PATH, json.dumps({
                "mcpServers": {"new-server": {"command": "x"}},
                "lastUsedAt": 2000, "usageCount": 2}))
            fp_after = ex.compute_fingerprint()
            check("adding a real MCP server entry still moves the fingerprint, "
                  "even though lastUsedAt/usageCount moved alongside it",
                  fp_before != fp_after)
        finally:
            _restore_paths(saved)


def test_unparseable_json_file_still_fingerprints_visibly_not_silently():
    # M3. Dropping a file that fails to parse as JSON from the fingerprint
    # would blind the guard, a worse defect than the raw-byte-telemetry one
    # being fixed. It must still contribute a hash (raw bytes), and the
    # method used must be visible to a caller, so a canonical hash is never
    # confused with a raw-byte one.
    #
    # RED (if a JSONDecodeError were treated as "skip this file", e.g.
    # `continue`-ing past it in compute_fingerprint instead of falling back
    # to raw bytes): the digest for the corrupt file would be identical to
    # not fingerprinting it at all, so the "moves when repaired" assertion
    # below would still pass by accident, but the method check catches the
    # silent-drop case directly, and a MISSING-file digest check confirms it
    # is not being treated as absent.
    with tempfile.TemporaryDirectory() as td:
        broken = os.path.join(td, "broken.json")
        _write(broken, '{"mcpServers": {"a": ')  # truncated, invalid JSON
        digest, method = ex._sha_file(broken)
        check("an unparseable JSON file still gets a real digest, not MISSING",
              digest != "MISSING")
        check("an unparseable JSON file is hashed as raw bytes, and that is "
              "visible on the returned method", method == "raw")

        valid = os.path.join(td, "valid.json")
        _write(valid, '{"mcpServers": {"a": {}}}')
        digest_valid, method_valid = ex._sha_file(valid)
        check("a file that parses as JSON is hashed canonically, visibly "
              "distinct from the raw-byte fallback", method_valid == "json")
        check("repairing the file changes its digest (it was not silently "
              "dropped from the fingerprint while broken)", digest != digest_valid)

        markdown = os.path.join(td, "CLAUDE.md")
        _write(markdown, "not json at all, plain markdown")
        digest_md, method_md = ex._sha_file(markdown)
        check("a file that is not JSON keeps being hashed as raw bytes, "
              "exactly as before this change", method_md == "raw")


def test_baseline_with_no_fingerprint_method_reports_no_data_and_still_closes():
    # H1, the hard part: a baseline pinned before this fix (fingerprint_start
    # computed with the OLD raw-byte method) must not be compared
    # byte-for-byte against a fingerprint_end computed with the NEW
    # canonical method: they would differ even if nothing changed, which
    # both reproduces the defect this fix targets and falsely flags a real
    # running experiment as "config changed". This is exactly the shape of
    # the live claude-md-diet-v2 baseline on this machine.
    #
    # RED (without the fp_method check in build_record, i.e. comparing
    # fp_start directly to fingerprint_end whenever both are present): this
    # asserts NOT_PROVEN with reasons containing "NO DATA", but the old code
    # would instead append the generic "config changed during experiment
    # window" reason (or, if the strings happened to match, wrongly stay
    # silent) with no NO DATA wording anywhere, and the assertions below fail.
    b = _baseline()
    b["fingerprint_start"] = "old-raw-byte-hash"
    del b["fingerprint_method"]  # exactly what a pre-fix baseline looks like
    rec = ex.build_record(b, _after(), "2026-08-30T00:00:00",
                          fingerprint_end="new-canonical-hash")
    check("a baseline with no fingerprint_method still closes (does not crash, "
          "and gets a verdict)", rec["confidence"] in ("VERIFIED", "NOT_PROVEN"))
    check("a baseline with no fingerprint_method downgrades to NOT_PROVEN",
          rec["confidence"] == "NOT_PROVEN")
    check("the config check reports NO DATA by name, not 'config changed'",
          any("NO DATA" in r for r in rec["reasons"]))
    check("the old false-positive wording is not used for this case",
          not any(r == "config changed during experiment window"
                  for r in rec["reasons"]))

    # A baseline whose method differs from the CURRENT one (not just absent)
    # gets the same NO DATA treatment, not a silent pass and not a false
    # "config changed".
    b2 = _baseline()
    b2["fingerprint_start"] = "old-raw-byte-hash"
    b2["fingerprint_method"] = ex.FINGERPRINT_METHOD - 1
    rec2 = ex.build_record(b2, _after(), "2026-08-30T00:00:00",
                           fingerprint_end="new-canonical-hash")
    check("a baseline whose fingerprint_method differs from the current one "
          "also reports NO DATA", any("NO DATA" in r for r in rec2["reasons"]))

    # A baseline whose method MATCHES the current one still gets the normal,
    # meaningful comparison: a real difference is still "config changed".
    b3 = _baseline()
    b3["fingerprint_start"] = "same-method-hash"
    rec3 = ex.build_record(b3, _after(), "2026-08-30T00:00:00",
                           fingerprint_end="a-different-hash")
    check("a matching fingerprint_method still catches a real config change",
          any(r == "config changed during experiment window" for r in rec3["reasons"]))


def test_cli_experiment_end_on_a_pre_fix_fingerprint_baseline_closes_cleanly():
    # The end-to-end version of the test above, through the real cmd_start /
    # cmd_end CLI path: a baseline written to disk with an old-style
    # fingerprint_start and no fingerprint_method key (simulating a baseline
    # pinned before this fix landed) must still `end` successfully, exit 0,
    # and print NOT_PROVEN with a NO DATA reason rather than crash or print a
    # false "config changed".
    with tempfile.TemporaryDirectory() as home:
        os.makedirs(os.path.join(home, ".claude", "projects"))
        exp_dir = os.path.join(home, ".claude", "token-shield", "experiments")
        os.makedirs(exp_dir)
        with open(os.path.join(exp_dir, "pre-fix.json"), "w") as f:
            json.dump({"label": "pre-fix", "started": "2026-07-01T00:00:00",
                       "window_days": 30, "schema": mt.SCHEMA,
                       "cohort_start_ts": 0.0, "cohort_end_ts": 1.0,
                       "fingerprint_start": "old-raw-byte-hash", "treats": None,
                       "fingerprint_excluded": [],
                       "summary": {"first_request_median": 80000,
                                   "normalized_input_total": 1_000_000,
                                   "parent_sessions": 10}}, f)
        r = _run_cli(home, ["experiment", "end", "pre-fix"])
        check("ending a pre-fix baseline exits 0, does not crash", r.returncode == 0)
        check("ending a pre-fix baseline does not raise", "Traceback" not in r.stderr)
        check("a pre-fix fingerprint baseline ends NOT_PROVEN",
              "NOT_PROVEN" in r.stdout)
        check("the NO DATA reason for the fingerprint method is printed",
              "NO DATA" in r.stdout)


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


def test_record_carries_per_cohort_evidence_scale():
    # M1. A VERIFIED record used to show a floor delta with no sense of how
    # much evidence sits behind it. The record now names the session count on
    # each side (the same parent_sessions counts the thin-data gate already
    # computes) and a dispersion figure per cohort, None (typed the same as
    # every other absent-numeric field) when the cohort is too small for
    # summarize() to compute a p90 at all; NO DATA wording is a renderer's
    # job, not the record's.
    rec = ex.build_record(_baseline(sessions=12), _after(sessions=15),
                          "2026-08-30T00:00:00")
    check("sessions_before reflects the baseline cohort size",
          rec["sessions_before"] == 12)
    check("sessions_after reflects the after cohort size",
          rec["sessions_after"] == 15)
    check("no p90 in the fixtures reads None, never a guess and never a string",
          rec["dispersion_before"] is None and rec["dispersion_after"] is None)

    b = _baseline(sessions=12)
    b["summary"]["first_request_p90"] = 95000
    after = _after(sessions=15)
    after["first_request_p90"] = 71000
    rec2 = ex.build_record(b, after, "2026-08-30T00:00:00")
    check("a real p90 is carried through instead of None",
          rec2["dispersion_before"] == 95000 and rec2["dispersion_after"] == 71000)


def test_direction_field_distinguishes_regression_from_saving():
    # C2. VERIFIED alone does not say whether the floor got better or worse;
    # a -8000 regression used to carry the same shape as a +8000 saving.
    rec_saving = ex.build_record(_baseline(fr=80000), _after(fr=60000),
                                 "2026-08-30T00:00:00")
    check("a real reduction reads as a saving", rec_saving["direction"] == "saving")

    rec_regression = ex.build_record(_baseline(fr=60000), _after(fr=68000),
                                     "2026-08-30T00:00:00")
    check("a real increase reads as a regression",
          rec_regression["direction"] == "regression")
    check("a regression still carries a negative floor_reduction_tokens",
          rec_regression["floor_reduction_tokens"] == -8000)

    rec_flat = ex.build_record(_baseline(fr=60000), _after(fr=60000),
                               "2026-08-30T00:00:00")
    check("no change reads as flat", rec_flat["direction"] == "flat")


def test_dominant_model_change_is_not_proven():
    # M2. A floor change measured across a model switch might come from the
    # new model, not the named treatment. The trigger is the DOMINANT model
    # per cohort (most sessions, ties broken lexically), not full-set
    # equality, so this fixture keeps the full _models sets identical and
    # only moves which model is dominant.
    b = _baseline()
    b["summary"]["_models"] = ["claude-opus-5", "claude-sonnet-5"]
    b["summary"]["_dominant_model"] = "claude-opus-5"
    after_same = _after()
    after_same["_models"] = ["claude-opus-5", "claude-sonnet-5"]
    after_same["_dominant_model"] = "claude-opus-5"
    rec_same = ex.build_record(b, after_same, "2026-08-30T00:00:00")
    check("a matching dominant model adds no reason",
          not any("dominant model" in r for r in rec_same["reasons"]))
    check("a matching dominant model stays VERIFIED",
          rec_same["confidence"] == "VERIFIED")

    after_diff = _after()
    after_diff["_models"] = ["claude-opus-5", "claude-sonnet-5"]
    after_diff["_dominant_model"] = "claude-sonnet-5"
    rec_diff = ex.build_record(b, after_diff, "2026-08-30T00:00:00")
    check("a dominant-model switch downgrades to NOT_PROVEN",
          rec_diff["confidence"] == "NOT_PROVEN")
    check("the dominant-model reason names the change",
          any("dominant model changed" in r for r in rec_diff["reasons"]))
    check("the full model sets still ride along on the record for transparency",
          rec_diff["models_before"] == ["claude-opus-5", "claude-sonnet-5"]
          and rec_diff["models_after"] == ["claude-opus-5", "claude-sonnet-5"])


def test_minor_model_variation_does_not_trigger_the_confound_guard():
    # M2. A routine minor-version bump (or an extra model touching one
    # session out of many) moves the full _models set without moving which
    # model is DOMINANT. That must not by itself downgrade every experiment,
    # only a real change in which model carried most of the cohort.
    b = _baseline()
    b["summary"]["_models"] = ["claude-opus-5"]
    b["summary"]["_dominant_model"] = "claude-opus-5"
    after = _after()
    after["_models"] = ["claude-opus-5", "claude-opus-5-preview"]
    after["_dominant_model"] = "claude-opus-5"
    rec = ex.build_record(b, after, "2026-08-30T00:00:00")
    check("a full-set difference with the same dominant model adds no reason",
          not any("dominant model" in r for r in rec["reasons"]))
    check("it stays VERIFIED", rec["confidence"] == "VERIFIED")


def test_model_tracking_missing_on_one_side_is_not_proven():
    # C1 (critical fix round). Both live baselines on disk predate _models,
    # so a naive "only compare when both sides carry data" guard skips
    # silently on every real claude-md-diet close, appending nothing and
    # writing VERIFIED beside models_before: null. NO DATA beats a guess:
    # exactly one side missing model tracking is itself a downgrade.
    b_missing = _baseline()  # no "_models" key at all, like a real old baseline
    after_populated = _after()
    after_populated["_models"] = ["claude-opus-5"]
    after_populated["_dominant_model"] = "claude-opus-5"
    rec = ex.build_record(b_missing, after_populated, "2026-08-30T00:00:00")
    check("one side missing model tracking downgrades to NOT_PROVEN",
          rec["confidence"] == "NOT_PROVEN")
    check("the reason names it as impossible to compare, not a mismatch",
          any("cannot be compared" in r for r in rec["reasons"]))
    check("the reason names the before side as the one predating tracking",
          any("before cohort predates model tracking" in r for r in rec["reasons"]))

    b_populated = _baseline()
    b_populated["summary"]["_models"] = ["claude-opus-5"]
    b_populated["summary"]["_dominant_model"] = "claude-opus-5"
    after_missing = _after()  # no "_models" key
    rec2 = ex.build_record(b_populated, after_missing, "2026-08-30T00:00:00")
    check("the reverse asymmetry also downgrades",
          rec2["confidence"] == "NOT_PROVEN")
    check("the reason names the after side this time",
          any("after cohort predates model tracking" in r for r in rec2["reasons"]))


def test_measure_cohort_dominant_model_is_by_session_count_not_call_count():
    # M2. Dominance is defined as "used in the most SESSIONS", not "used in
    # the most usage records": a chatty single session on model-b must not
    # outrank model-a just because model-b logged more individual calls.
    def line(ts, model, sub=False):
        return json.dumps({"timestamp": ts, "isSidechain": sub,
                           "message": {"model": model, "usage": {
                               "input_tokens": 100, "cache_read_input_tokens": 0,
                               "output_tokens": 5,
                               "cache_creation": {"ephemeral_5m_input_tokens": 0,
                                                  "ephemeral_1h_input_tokens": 0}}}}) + "\n"

    with tempfile.TemporaryDirectory() as td:
        # Two sessions on model-a (one call each).
        with open(os.path.join(td, "s1.jsonl"), "w") as f:
            f.write(line("2026-08-10T00:00:00+00:00", "model-a"))
        with open(os.path.join(td, "s2.jsonl"), "w") as f:
            f.write(line("2026-08-11T00:00:00+00:00", "model-a"))
        # One session on model-b, but five calls in it.
        with open(os.path.join(td, "s3.jsonl"), "w") as f:
            for i in range(5):
                f.write(line(f"2026-08-12T0{i}:00:00+00:00", "model-b"))

        start_ts = ex._parse_ts("2026-08-01T00:00:00+00:00")
        end_ts = ex._parse_ts("2026-08-20T00:00:00+00:00")
        sm = ex._measure_cohort(td, start_ts, end_ts, 30)
        check("model-a wins on session count despite fewer calls",
              sm["_dominant_model"] == "model-a")
        check("the full set still names both models",
              sm["_models"] == ["model-a", "model-b"])


def test_model_mix_neither_side_tracked_is_not_a_mismatch():
    # Neither a legacy baseline nor a hand-built fixture carries _models at
    # all; that is genuinely "no data on either side", not a comparison
    # gone wrong, so it must not be flagged the way one-sided absence is.
    rec = ex.build_record(_baseline(), _after(), "2026-08-30T00:00:00")
    check("no model data on either side adds no model-related reason",
          not any("model" in r for r in rec["reasons"]))
    check("no model data on either side stays VERIFIED",
          rec["confidence"] == "VERIFIED")


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


# --- target_metric: each experiment judged on the metric it declares ---

def test_legacy_baseline_without_target_metric_is_judged_exactly_as_before():
    # target_metric is an OPTIONAL field added this unit. Every baseline ever
    # pinned before today carries no such key at all, and must be judged
    # exactly as it always has: on first_request_median, with the existing
    # fields carrying the existing values.
    baseline = _baseline(fr=80000)
    check("no target_metric key on an old-shape baseline", "target_metric" not in baseline)
    rec = ex.build_record(baseline, _after(fr=60000), "2026-08-30T00:00:00")
    check("an undeclared metric reads as the default", rec["target_metric"] == ex.DEFAULT_METRIC)
    check("metric_before mirrors first_request_before for the default metric",
          rec["metric_before"] == rec["first_request_before"] == 80000)
    check("metric_after mirrors first_request_after for the default metric",
          rec["metric_after"] == rec["first_request_after"] == 60000)
    check("metric_delta mirrors floor_reduction_tokens for the default metric",
          rec["metric_delta"] == rec["floor_reduction_tokens"] == 20000)
    check("verdict is VERIFIED exactly as before this unit", rec["confidence"] == "VERIFIED")
    check("direction is unchanged", rec["direction"] == "saving")


def test_declared_metric_is_the_one_actually_compared():
    # Field names are exact summarize() keys (grepped from measure_tokens.py):
    # hit_ratio_median is a real summary field. Declaring it must route the
    # comparison and the verdict through THAT key, not first_request_median,
    # even when first_request_median itself would say something different.
    #
    # m1 (rewritten). The old version of this test asserted the raw signed
    # delta (0.5 - 0.9 == -0.4) and never looked at direction at all, so it
    # stayed green while C1 stamped this exact real cache-hit IMPROVEMENT as
    # "regression" (hit_ratio_median is up-is-better, so a negative
    # before-minus-after delta is the win, not the loss) and C2 leaked a
    # 999,998-token floor_reduction_tokens out of a metric that never
    # measured the floor. This version asserts the MEANING: which way the
    # verdict says things moved, and what a downstream consumer sees.
    b = _baseline(fr=999999)
    b["target_metric"] = "hit_ratio_median"
    b["summary"]["hit_ratio_median"] = 0.5
    after = _after(fr=1)
    after["hit_ratio_median"] = 0.9
    rec = ex.build_record(b, after, "2026-08-30T00:00:00")
    check("target_metric is carried on the record", rec["target_metric"] == "hit_ratio_median")
    check("metric_before reads the declared field, not first_request_median",
          rec["metric_before"] == 0.5)
    check("metric_after reads the declared field, not first_request_median",
          rec["metric_after"] == 0.9)
    check("metric_delta is the raw before-minus-after (documented convention), "
          "not yet direction-adjusted",
          abs(rec["metric_delta"] - (0.5 - 0.9)) < 1e-9)
    check("a 0.5 -> 0.9 cache-hit gain is stamped a saving, not a regression (C1)",
          rec["direction"] == "saving")
    check("the declared metric is present on both sides, so the verdict is VERIFIED",
          rec["confidence"] == "VERIFIED")
    check("first_request_before/after still carry the floor numbers untouched",
          rec["first_request_before"] == 999999 and rec["first_request_after"] == 1)
    check("a non-default-metric record never claims a token floor reduction it "
          "did not measure (C2)", rec["floor_reduction_tokens"] is None)


def test_absent_declared_metric_downgrades_with_metric_not_measured_reason():
    b = _baseline()
    b["target_metric"] = "output_total"  # never recorded on this baseline's summary
    after = _after()
    after["output_total"] = 12345  # present after, absent before: still a downgrade
    rec = ex.build_record(b, after, "2026-08-30T00:00:00")
    check("missing declared metric on one side downgrades to NOT_PROVEN",
          rec["confidence"] == "NOT_PROVEN")
    check("the reason literally says metric not measured",
          any("metric not measured" in r for r in rec["reasons"]))
    check("the reason names the missing metric",
          any("output_total" in r for r in rec["reasons"]))
    check("no guess is made: metric_before/after are None, not a stand-in value",
          rec["metric_before"] is None and rec["metric_after"] is not None)


def test_up_metric_degradation_is_stamped_a_regression():
    # C1, the other half. hit_ratio_median going DOWN (0.80 -> 0.55) is a real
    # collapse and must read as "regression", the mirror of the improvement
    # case above. The inverted code stamped this "saving" instead, because it
    # judged every metric by "did the raw before-minus-after go positive".
    b = _baseline()
    b["target_metric"] = "hit_ratio_median"
    b["summary"]["hit_ratio_median"] = 0.80
    after = _after()
    after["hit_ratio_median"] = 0.55
    rec = ex.build_record(b, after, "2026-08-30T00:00:00")
    check("a 0.80 -> 0.55 cache-hit collapse is stamped a regression",
          rec["direction"] == "regression")
    check("a non-default-metric record still claims no floor reduction",
          rec["floor_reduction_tokens"] is None)


def test_non_default_metric_verified_record_never_reaches_verified_by_label():
    # C2. A VERIFIED hit-ratio experiment used to leak floor_reduction_tokens
    # computed from first_request_median regardless of what was declared, so
    # token_shield.verified_by_label (the dashboard's own reader of the
    # ledger) rendered a hit-ratio experiment as a proven token saving it
    # never measured. floor_reduction_tokens is None for a non-default
    # metric, and verified_by_label already skips a record whose delta is
    # not a real number, so the label must not appear in its output at all.
    b = _baseline(fr=999999)
    b["target_metric"] = "hit_ratio_median"
    b["summary"]["hit_ratio_median"] = 0.5
    after = _after(fr=1)
    after["hit_ratio_median"] = 0.9
    rec = ex.build_record(b, after, "2026-08-30T00:00:00")
    check("sanity: this record is VERIFIED", rec["confidence"] == "VERIFIED")
    check("sanity: floor_reduction_tokens is None on a non-default metric",
          rec["floor_reduction_tokens"] is None)
    rows = [dict(rec, timestamp=rec.get("timestamp") or "2026-08-30T00:00:00")]
    out = met.verified_by_label(rows)
    check("a non-default-metric VERIFIED record contributes no row to "
          "verified_by_label (a hit-ratio proof must never render as a "
          "token saving)", out == [])


def test_non_numeric_target_metric_downgrades_instead_of_crashing():
    # M1. A target_metric that is present on both sides but not numeric (a
    # model name string, a list of models) used to raise TypeError trying to
    # subtract them. Absent-metric already downgraded honestly (see the test
    # above); present-and-unsubtractable must downgrade the same way, not
    # crash the whole `end` command.
    b = _baseline()
    b["target_metric"] = "_dominant_model"
    b["summary"]["_dominant_model"] = "opus"
    after = _after()
    after["_dominant_model"] = "opus"
    rec = ex.build_record(b, after, "2026-08-30T00:00:00")
    check("a non-numeric metric downgrades to NOT_PROVEN instead of raising",
          rec["confidence"] == "NOT_PROVEN")
    check("the reason says non-numeric and names the key",
          any("non-numeric" in r and "_dominant_model" in r for r in rec["reasons"]))
    check("no metric_delta is fabricated from an unsubtractable pair",
          rec["metric_delta"] is None)
    check("no direction is fabricated either", rec["direction"] is None)

    b2 = _baseline()
    b2["target_metric"] = "_models"
    b2["summary"]["_models"] = ["opus"]
    after2 = _after()
    after2["_models"] = ["opus", "sonnet"]
    rec2 = ex.build_record(b2, after2, "2026-08-30T00:00:00")
    check("a list-valued metric downgrades the same way, not raising",
          rec2["confidence"] == "NOT_PROVEN")
    check("the reason names _models",
          any("non-numeric" in r and "_models" in r for r in rec2["reasons"]))


def test_cli_start_refuses_an_unknown_metric_before_writing_anything():
    # M2. A typo'd --metric used to be accepted with exit 0 and pinned a
    # baseline that could only be discovered wrong 30 days later at `end`.
    # It must refuse at start, exit 2, name the bad value, and list the
    # valid ones, and it must not write a baseline file at all.
    with tempfile.TemporaryDirectory() as home:
        os.makedirs(os.path.join(home, ".claude", "projects"))
        r = _run_experiment_cli(home, ["start", "typo-metric-smoke",
                                       "--metric", "hit_ratio_medain"])
        check("an unknown --metric exits 2, not 0", r.returncode == 2)
        check("the refusal names the bad value", "hit_ratio_medain" in r.stdout)
        check("the refusal lists the valid metrics",
              "hit_ratio_median" in r.stdout and "first_request_median" in r.stdout)
        snap = os.path.join(home, ".claude", "token-shield", "experiments",
                            "typo-metric-smoke.json")
        check("no baseline file is written for a refused start",
              not os.path.exists(snap))

    with tempfile.TemporaryDirectory() as home:
        os.makedirs(os.path.join(home, ".claude", "projects"))
        r = _run_experiment_cli(home, ["start", "valid-metric-smoke",
                                       "--metric", "hit_ratio_median"])
        check("a metric that is in METRIC_DIRECTIONS is accepted, exit 0",
              r.returncode == 0)


def test_experiment_cli_start_with_metric_flag_stores_target_metric():
    # cmd_start's own CLI (python3 experiment.py start ... --metric X) is the
    # entry point that declares a target_metric; cli.py's hand-rolled
    # subcommand parsing is untouched by this unit and still only knows
    # --treats, so this exercises experiment.py's argparse directly.
    with tempfile.TemporaryDirectory() as home:
        os.makedirs(os.path.join(home, ".claude", "projects"))
        r = _run_experiment_cli(home, ["start", "cli-metric-smoke",
                                       "--metric", "hit_ratio_median"])
        check("experiment.py start with --metric exits 0", r.returncode == 0)
        check("experiment.py start with --metric does not raise",
              "Traceback" not in r.stderr)
        snap = os.path.join(home, ".claude", "token-shield", "experiments",
                            "cli-metric-smoke.json")
        with open(snap) as f:
            baseline = json.load(f)
        check("the declared metric is stored on the baseline",
              baseline.get("target_metric") == "hit_ratio_median")

    with tempfile.TemporaryDirectory() as home:
        os.makedirs(os.path.join(home, ".claude", "projects"))
        r = _run_experiment_cli(home, ["start", "cli-no-metric-smoke"])
        check("experiment.py start without --metric exits 0", r.returncode == 0)
        snap = os.path.join(home, ".claude", "token-shield", "experiments",
                            "cli-no-metric-smoke.json")
        with open(snap) as f:
            baseline = json.load(f)
        check("target_metric key is absent from the baseline when --metric is "
              "not passed (purely additive, optional field)",
              "target_metric" not in baseline)


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


def _run_experiment_cli(home, args):
    """Same sandboxing as _run_cli, but drives experiment.py's own argparse
    directly (the --metric flag lives there; cli.py's hand-rolled subcommand
    parsing is out of scope for this unit)."""
    env = dict(os.environ)
    env["HOME"] = home
    return subprocess.run([sys.executable, os.path.join(HERE, "experiment.py")] + args,
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
        check("a freshly pinned baseline records the current fingerprint method",
              baseline.get("fingerprint_method") == ex.FINGERPRINT_METHOD)


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


def test_list_open_experiments_matches_by_label_and_cohort_end():
    # The interlock wave R's guided apply depends on: a baseline is "open"
    # only if no ledger record closes that EXACT (label, cohort_end_ts) pair,
    # never by label alone (a later re-run must not read as closing an
    # earlier, still-open start of the same label).
    saved_exp_dir, saved_ledger = ex.EXP_DIR, ex.LEDGER
    with tempfile.TemporaryDirectory() as d:
        ex.EXP_DIR = os.path.join(d, "experiments")
        ex.LEDGER = os.path.join(d, "savings.jsonl")
        os.makedirs(ex.EXP_DIR)
        _write(os.path.join(ex.EXP_DIR, "open-one.json"),
              json.dumps({"label": "open-one", "cohort_end_ts": 100.0,
                          "started": "2026-08-01T00:00:00"}))
        _write(os.path.join(ex.EXP_DIR, "closed-one.json"),
              json.dumps({"label": "closed-one", "cohort_end_ts": 200.0,
                          "started": "2026-08-02T00:00:00"}))
        _write(os.path.join(ex.EXP_DIR, "rerun.json"),
              json.dumps({"label": "rerun", "cohort_end_ts": 400.0,
                          "started": "2026-08-04T00:00:00"}))
        with open(ex.LEDGER, "w") as f:
            f.write(json.dumps({"label": "closed-one",
                                "cohort_before": {"end": 200.0}}) + "\n")
            # Same label as "rerun", but this ledger record closes a
            # DIFFERENT start (end 300.0, not the 400.0 baseline above), the
            # way a later re-run of the same label would.
            f.write(json.dumps({"label": "rerun",
                                "cohort_before": {"end": 300.0}}) + "\n")
        open_now = ex.list_open_experiments()
        labels = sorted(o["label"] for o in open_now)
        check("a baseline with no ledger entry at all is open",
              "open-one" in labels)
        check("a baseline whose (label, end) has a matching ledger record is closed",
              "closed-one" not in labels)
        check("same label but a different cohort_end_ts (a later re-run) stays open",
              "rerun" in labels)
    ex.EXP_DIR, ex.LEDGER = saved_exp_dir, saved_ledger


def test_list_open_experiments_fails_closed_on_unreadable_or_corrupt_baseline():
    # R3/R3b/CRITICAL, calibrated red-then-green: list_open_experiments used
    # to `continue` (skip) past a baseline file it could not open or parse,
    # so a genuinely open experiment whose write got interrupted (a crash
    # mid json.dump, or a permission-denied file) silently read as "not
    # open". It must fail CLOSED instead: come back as an entry the caller
    # can see, marked unreadable, naming the file.
    saved_exp_dir, saved_ledger = ex.EXP_DIR, ex.LEDGER
    with tempfile.TemporaryDirectory() as d:
        ex.EXP_DIR = os.path.join(d, "experiments")
        ex.LEDGER = os.path.join(d, "savings.jsonl")
        os.makedirs(ex.EXP_DIR)
        try:
            truncated = os.path.join(ex.EXP_DIR, "truncated.json")
            with open(truncated, "w") as f:
                f.write('{"label": "live", "cohort_end_ts": 100')  # invalid JSON
            open_now = ex.list_open_experiments()
            check("a truncated baseline still counts as open",
                  any(o.get("_unreadable") == truncated for o in open_now))

            os.remove(truncated)
            stray = os.path.join(ex.EXP_DIR, "stray.json")
            with open(stray, "w") as f:
                f.write("[]")  # valid JSON, not a dict: baseline.get() would crash
            open_now2 = ex.list_open_experiments()
            check("a non-dict JSON value counts as open, not a crash",
                  any(o.get("_unreadable") == stray for o in open_now2))

            os.remove(stray)
            unreadable = os.path.join(ex.EXP_DIR, "noperm.json")
            with open(unreadable, "w") as f:
                f.write('{"label": "live", "cohort_end_ts": 100.0, "started": "x"}')
            os.chmod(unreadable, 0o000)
            try:
                open_now3 = ex.list_open_experiments()
                check("a permission-denied baseline counts as open",
                      any(o.get("_unreadable") == unreadable for o in open_now3))
            finally:
                os.chmod(unreadable, 0o600)
        finally:
            ex.EXP_DIR, ex.LEDGER = saved_exp_dir, saved_ledger


def test_a_cohort_that_skipped_files_or_lines_is_not_proven():
    """A VERIFIED verdict could be manufactured entirely by parse failures.

    This module's cohort reader mirrors measure_tokens.read_session but
    copied only its two skip handlers, not the counter increments that go
    with them, so an unreadable transcript or a truncated line vanished
    without trace. A dropped FIRST line is the sharp end: it promotes a
    cheap mid-conversation turn to "first request", which is the exact
    number this verdict compares. The reviewer produced a clean VERIFIED
    with a 39,750 token saving from five transcripts whose content had not
    changed at all.

    RED before the fix: reasons == [] and confidence == VERIFIED with
    skipped files and lines on the after cohort."""
    after = _after(fr=60000)
    after["_skipped_files"] = 1
    after["_skipped_lines"] = 2
    rec = ex.build_record(_baseline(fr=80000), after, "2026-08-30T00:00:00")
    check("a cohort with skipped input is not VERIFIED",
          rec["confidence"] == "NOT_PROVEN")
    check("the skip is named as the reason, with its counts",
          any("skipped 1 unreadable file(s) and 2 undecodable line(s)" in r
              for r in rec["reasons"]))

    # The mirror case, so the guard cannot degenerate into downgrading
    # everything: a cohort that skipped nothing still reaches VERIFIED.
    clean = _after(fr=60000)
    clean["_skipped_files"] = 0
    clean["_skipped_lines"] = 0
    rec_ok = ex.build_record(_baseline(fr=80000), clean, "2026-08-30T00:00:00")
    check("a cohort that skipped nothing is still VERIFIED",
          rec_ok["confidence"] == "VERIFIED")


# --- Wave 2: the four proof-ledger defects (D18, D19, D8, D21a) --------------

def test_an_unproven_delta_never_rides_the_verified_row():
    """D18. aggregate_by_label collected floor_reduction_tokens from EVERY
    record whatever its confidence, and cmd_report prints the LAST one on a
    line that opens with the VERIFIED count. So a label with two proven runs
    and one later unproven one printed

        diet   3 runs   2 VERIFIED   1 NOT_PROVEN   latest floor reduction 99,999

    where 99,999 is the UNPROVEN number, sitting in the column a reader takes
    as the verified result. This is the product's own promise inverted: the
    whole point of the confidence label is that an unproven number cannot
    borrow a proven one's authority.

    The rule: reductions carries VERIFIED records only, and a label with no
    verified run reports nothing rather than its newest guess."""
    records = [
        {"label": "diet", "confidence": "VERIFIED", "floor_reduction_tokens": 1000},
        {"label": "diet", "confidence": "VERIFIED", "floor_reduction_tokens": 2000},
        {"label": "diet", "confidence": "NOT_PROVEN", "floor_reduction_tokens": 99999},
        {"label": "onlybad", "confidence": "NOT_PROVEN", "floor_reduction_tokens": 4242},
    ]
    by_label = ex.aggregate_by_label(records)
    check("counts still see every record", by_label["diet"]["count"] == 3)
    check("the verified and unproven tallies are unchanged",
          by_label["diet"]["verified"] == 2 and by_label["diet"]["not_proven"] == 1)
    check("the unproven delta is not in the reductions list",
          99999 not in by_label["diet"]["reductions"])
    check("the newest VERIFIED delta is what remains",
          by_label["diet"]["reductions"][-1] == 2000)
    check("a label with no verified run reports no reduction at all",
          by_label["onlybad"]["reductions"] == [])
    check("...while still counting its run", by_label["onlybad"]["count"] == 1)


def test_the_overlap_refusal_never_advises_a_smaller_window():
    """D19. The refusal told the reader to 'wait longer, or end with a smaller
    --days window'. Taking the second half of that advice is strictly harmful:
    a smaller window trips build_record's own window-length guard, which is an
    unconditional downgrade, and cmd_end writes that NOT_PROVEN permanently
    into an APPEND-ONLY ledger. The reader follows our instruction and buys a
    permanent unproven verdict, which then feeds D18 above.

    Waiting longer is the only sound path, so it is the only one offered.

    Checked by RUNNING the refusal and reading what it printed, not by
    grepping the source: a source grep would also match the comment in
    experiment.py explaining why the advice was removed, which is how a
    wording test quietly stops testing anything."""
    import contextlib
    import io

    now = 3_600_000
    with tempfile.TemporaryDirectory() as d:
        saved_dir, saved_ledger = ex.EXP_DIR, ex.LEDGER
        ex.EXP_DIR = os.path.join(d, "experiments")
        ex.LEDGER = os.path.join(d, "savings.jsonl")
        os.makedirs(ex.EXP_DIR)
        # cohort_end_ts sits at "now", so the after cohort (now - 30 days)
        # starts well before the before cohort ended: a guaranteed overlap.
        b = _baseline()
        b["cohort_end_ts"] = now
        with open(os.path.join(ex.EXP_DIR, "t.json"), "w") as f:
            json.dump(b, f)
        temp_ledger = ex.LEDGER  # read BEFORE the restore below, or this
                                 # checks the real machine's ledger instead
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                rc = ex.cmd_end("t", os.path.join(d, "root"), 30, now)
            ledger_written = os.path.exists(temp_ledger)
        finally:
            ex.EXP_DIR, ex.LEDGER = saved_dir, saved_ledger
        printed = out.getvalue()

    check("an overlapping close is refused", rc == 2)
    check("it still refuses without writing to the append-only ledger",
          not ledger_written)
    check("the refusal no longer advises shortening the window",
          "smaller --days" not in printed)
    check("it says what to do instead", "wait" in printed.lower())
    check("and warns that forcing it through costs a permanent verdict",
          "NOT_PROVEN" in printed)

    # And the reason that advice was harmful, proven rather than asserted.
    rec = ex.build_record(_baseline(window=30), _after(window=7), "2026-08-30T00:00:00")
    check("a smaller window is indeed an unconditional downgrade",
          rec["confidence"] == "NOT_PROVEN"
          and any("window changed" in r for r in rec["reasons"]))


def test_a_legacy_baseline_can_actually_be_closed():
    """D8. list_open_experiments matched a baseline against the ledger on
    (label, cohort_end_ts), but only admitted a ledger record to `closed` when
    its cohort_before.end was not None. A legacy baseline has no
    cohort_end_ts, so its close record carries end=None, is refused entry to
    `closed`, and the baseline's own (label, None) can never match anything.

    The result: closing it appends a NOT_PROVEN record and it STILL reads as
    open. Every close appends another. And guided_apply refuses to run while
    any experiment is open, so one legacy baseline blocks every guided change
    on the machine, permanently.

    Closing it must be possible. The verdict stays NOT_PROVEN naming the
    missing fields; nothing is invented to fill them."""
    with tempfile.TemporaryDirectory() as d:
        exp_dir = os.path.join(d, "experiments")
        os.makedirs(exp_dir)
        ledger = os.path.join(d, "savings.jsonl")
        # A v1.6 snapshot: no cohort_start_ts, no cohort_end_ts, no
        # fingerprint_start, no treats.
        legacy = {"label": "old", "started": "2026-07-01T00:00:00",
                  "window_days": 30, "schema": mt.SCHEMA,
                  "summary": {"first_request_median": 80000, "parent_sessions": 10}}
        with open(os.path.join(exp_dir, "old.json"), "w") as f:
            json.dump(legacy, f)

        check("the legacy baseline reads as open before any close",
              [b.get("label") for b in ex.list_open_experiments(exp_dir, ledger)] == ["old"])

        rec = ex.build_record(legacy, _after(), "2026-08-30T00:00:00")
        check("closing it is honest about why it cannot be proven",
              rec["confidence"] == "NOT_PROVEN")
        check("...and names the missing fields rather than inventing them",
              any("cohort_end_ts" in r for r in rec["reasons"]))
        with open(ledger, "w") as f:
            f.write(json.dumps(rec) + "\n")

        still_open = [b.get("label") for b in ex.list_open_experiments(exp_dir, ledger)]
        check("after its close record is written it is no longer open", still_open == [])


def test_a_non_numeric_floor_refuses_instead_of_crashing():
    """D21a. The guard three lines above names a non-numeric metric and
    downgrades instead of raising, and then the floor subtraction runs on the
    same unvalidated values guarded only by `is not None`. For the default
    metric those ARE the same two values, so a summary carrying a string where
    the median belongs is named as not comparable and then subtracted anyway:
    TypeError out of build_record, which takes the whole close with it.

    A guard that is undone by the next statement is not a guard."""
    b = _baseline()
    b["summary"]["first_request_median"] = "80000"  # a string, as a hostile or
    a = _after()                                    # half-migrated file gives it
    a["first_request_median"] = 60000

    rec = ex.build_record(b, a, "2026-08-30T00:00:00")
    check("a non-numeric floor downgrades rather than raising",
          rec["confidence"] == "NOT_PROVEN")
    check("the reason names it as not comparable",
          any("non-numeric" in r for r in rec["reasons"]))
    check("no floor reduction is invented from unsubtractable values",
          rec["floor_reduction_tokens"] is None)


if __name__ == "__main__":
    n = 0
    for name in sorted(dir(sys.modules[__name__])):
        if name.startswith("test_"):
            globals()[name]()
            n += 1
    print(f"\n{n} passed")
