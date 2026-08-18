#!/usr/bin/env python3
"""Self-check for measure_tokens.py. No framework, no fixtures.

    python3 scripts/test_measure_tokens.py

Every assertion here exists because getting it wrong produces a plausible
number rather than an error, which is the failure mode this whole script is
supposed to prevent.
"""

import importlib.util
import json
import os
import re
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("mt", os.path.join(HERE, "measure_tokens.py"))
mt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mt)


def test_split_writes():
    # Nested object present and populated: authoritative.
    assert mt.split_writes({"cache_creation": {"ephemeral_5m_input_tokens": 100,
                                               "ephemeral_1h_input_tokens": 200},
                            "cache_creation_input_tokens": 300}) == (100, 200, 0)

    # Measured on a real machine: the flat counter can read 0 while the nested
    # fields carry the real write. Trusting the flat one loses those tokens.
    assert mt.split_writes({"cache_creation": {"ephemeral_5m_input_tokens": 0,
                                               "ephemeral_1h_input_tokens": 2001},
                            "cache_creation_input_tokens": 0}) == (0, 2001, 0)

    # A genuine zero is a measurement, not missing data.
    assert mt.split_writes({"cache_creation": {"ephemeral_5m_input_tokens": 0,
                                               "ephemeral_1h_input_tokens": 0},
                            "cache_creation_input_tokens": 0}) == (0, 0, 0)

    # No nested object: the total is known but the TTL class is not, so the
    # tokens must land in write_unsplit and poison normalized cost to NO DATA.
    assert mt.split_writes({"cache_creation_input_tokens": 500}) == (0, 0, 500)

    # The contradictory case, and the one that decides whether this function is
    # safe: nested classes account for nothing while the flat counter says 500
    # were written. Those tokens are real and their TTL is unknown, so they
    # must go to unsplit. Returning (0, 0, 0) would lose them; returning them
    # as 5m would price a guess.
    assert mt.split_writes({"cache_creation": {"ephemeral_5m_input_tokens": 0,
                                               "ephemeral_1h_input_tokens": 0},
                            "cache_creation_input_tokens": 500}) == (0, 0, 500)


def test_delta_formatting():
    # A ratio formatted as an integer prints every real move as +0, which reads
    # as "nothing changed" when the hit ratio just fell 4 points.
    assert mt.fmt_delta(0.949, 0.909) == ("-0.040", "-4.2%")
    assert mt.fmt_delta(85021, 85696) == ("+675", "+0.8%")
    # A percent against a zero baseline is undefined, not zero.
    assert mt.fmt_delta(0, 0.625) == ("+0.625", "NO DATA")


def _rec(inp, w5, w1, read, out, sidechain=False, model="claude-x"):
    return json.dumps({
        "isSidechain": sidechain,
        "message": {"model": model, "usage": {
            "input_tokens": inp,
            "cache_creation": {"ephemeral_5m_input_tokens": w5,
                               "ephemeral_1h_input_tokens": w1},
            "cache_creation_input_tokens": w5 + w1,
            "cache_read_input_tokens": read,
            "output_tokens": out}}})


def _write(path, records):
    with open(path, "w") as f:
        f.write("\n".join(records) + "\n")


def test_read_session():
    with tempfile.TemporaryDirectory() as d:
        fp = os.path.join(d, "s.jsonl")
        _write(fp, [
            _rec(10, 100, 0, 0, 5, model="model-a"),      # parent, first call
            _rec(1, 50, 0, 10, 7, sidechain=True),        # subagent
            _rec(2, 0, 200, 1000, 9, model="model-b"),    # parent, after switch
        ])
        s = mt.read_session(fp)

    assert s["calls"] == 3
    # The startup floor is the PARENT's first call. A subagent starts its own
    # context, so counting its first call here understates the real floor.
    assert s["first_request"] == 110, s["first_request"]
    assert (s["write_5m"], s["write_1h"], s["write_unsplit"]) == (150, 200, 0)
    assert s["read"] == 1010 and s["output"] == 21
    assert s["sub_calls"] == 1 and s["sub_output"] == 7
    # Two distinct parent models means a mid-session switch, which rebuilds.
    assert s["models"] == 2
    assert s["normalized_input"] == 13 + 1.25 * 150 + 2.0 * 200 + 0.1 * 1010
    assert s["raw_input"] == 13 + 350 + 1010
    assert abs(s["first_request_share"] - (110 * 3 / 1373)) < 1e-9


def test_unsplit_writes_give_no_data_not_a_guess():
    with tempfile.TemporaryDirectory() as d:
        fp = os.path.join(d, "old.jsonl")
        with open(fp, "w") as f:
            f.write(json.dumps({"message": {"usage": {
                "input_tokens": 5, "cache_creation_input_tokens": 400,
                "cache_read_input_tokens": 10, "output_tokens": 3}}}) + "\n")
        s = mt.read_session(fp)
    assert s["write_unsplit"] == 400
    assert s["normalized_input"] is None, "must not price an unknown TTL class"
    assert s["output_to_input"] is None


def test_skipped_line_is_counted_and_other_metrics_unchanged():
    # A truncated write leaves a line that contains "usage" but does not parse
    # as JSON. Before this fix that line vanished with no trace; now it must
    # be counted, and the two good records on either side of it must still
    # add up exactly as if the bad line were never there.
    with tempfile.TemporaryDirectory() as d:
        fp = os.path.join(d, "s.jsonl")
        with open(fp, "w") as f:
            f.write(_rec(10, 100, 0, 0, 5, model="model-a") + "\n")
            f.write('{"message": {"usage": {"input_tokens": truncated\n')
            f.write(_rec(2, 0, 200, 1000, 9, model="model-a") + "\n")
        sessions = mt.collect(d, days=9999)
        sm = mt.summarize(sessions)
    assert sm["skipped_lines"] >= 1, sm["skipped_lines"]
    assert sm["skipped_files"] == 0
    assert sm["total_calls"] == 2
    assert sm["output_total"] == 14
    assert sm["input_total"] == 12


def test_subagent_transcript_is_not_a_session():
    with tempfile.TemporaryDirectory() as d:
        parent = os.path.join(d, "p.jsonl")
        sub = os.path.join(d, "sub.jsonl")
        _write(parent, [_rec(10, 100, 0, 0, 5)])
        _write(sub, [_rec(1, 20, 0, 5, 4, sidechain=True)])
        sessions = [mt.read_session(parent), mt.read_session(sub)]

    sm = mt.summarize(sessions)
    assert sm["sessions"] == 2
    assert sm["parent_sessions"] == 1
    assert sm["subagent_transcripts"] == 1
    # The subagent transcript has no startup floor of its own, so it must not
    # drag the median. This is exactly the bug that made an old baseline read
    # 41,898 tokens where the real session median was 85,021.
    assert sm["first_request_median"] == 110
    # Its tokens still count toward the totals: they were really spent.
    assert sm["output_total"] == 9
    assert sm["subagent_output_total"] == 4


def test_legacy_baseline_keys_still_readable():
    assert mt.baseline_get({"preamble_median": 41890}, "first_request_median") == (41890, True)
    assert mt.baseline_get({"first_request_median": 7}, "first_request_median") == (7, False)
    assert mt.baseline_get({}, "hit_ratio_median") == (None, False)
    # The renamed metrics changed population, so they must be refused across
    # the schema boundary rather than compared.
    assert "first_request_median" in mt.INCOMPARABLE_ACROSS_SCHEMA
    assert "hit_ratio_median" not in mt.INCOMPARABLE_ACROSS_SCHEMA


def test_multipliers_match_published_rates():
    assert (mt.CACHE_WRITE_5M, mt.CACHE_WRITE_1H, mt.CACHE_READ) == (1.25, 2.0, 0.1)


def test_dominant_lever_thresholds():
    # One source of truth for the thresholds the dashboard and the note both use.
    assert mt.dominant_lever({"first_request_share_median": 0.36,
                              "hit_ratio_median": 0.95,
                              "subagent_output_share": 0.1}) == "shrink"
    assert mt.dominant_lever({"first_request_share_median": 0.05,
                              "hit_ratio_median": 0.40,
                              "subagent_output_share": 0.1}) == "cache"
    assert mt.dominant_lever({"first_request_share_median": 0.05,
                              "hit_ratio_median": 0.95,
                              "subagent_output_share": 0.5}) == "route"
    assert mt.dominant_lever({"first_request_share_median": 0.05,
                              "hit_ratio_median": 0.95,
                              "subagent_output_share": 0.1}) == "healthy"
    # Nothing measured never yields a confident recommendation.
    assert mt.dominant_lever({"first_request_share_median": None,
                              "hit_ratio_median": None,
                              "subagent_output_share": None}) == "nodata"
    # Shrink outranks cache: the always-loaded floor is the bigger lever.
    assert mt.dominant_lever({"first_request_share_median": 0.5,
                              "hit_ratio_median": 0.4,
                              "subagent_output_share": 0.1}) == "shrink"


def test_a_hostile_usage_value_is_skipped_not_a_crash_and_not_a_fake_zero():
    """os.walk recurses into every .jsonl under the root, and --root is a
    documented flag, so a foreign tool's transcript or a schema variant is
    reachable input. RED before the fix, each ending a stranger's first run:

      nan       ValueError: cannot convert float NaN to integer
      str       TypeError: unsupported operand type(s) for +=: 'int' and 'str'
      list      TypeError: unsupported operand type(s) for +=: 'int' and 'list'
      deepnest  RecursionError: maximum recursion depth exceeded

    Infinity was worse than any of those because it did NOT raise: every
    ratio divided by infinity and the tool printed 0.000 share and 0.000
    cache hit ratio as MEASURED facts."""
    hostile = [
        ('{"message":{"usage":{"input_tokens":NaN,"output_tokens":1}}}', "nan"),
        ('{"message":{"usage":{"input_tokens":Infinity,"output_tokens":1}}}', "infinity"),
        ('{"message":{"usage":{"input_tokens":"1200","output_tokens":1}}}', "string"),
        ('{"message":{"usage":{"input_tokens":[1],"output_tokens":1}}}', "list"),
        ('{"usage":' + "[" * 50000 + "]" * 50000 + "}", "deepnest"),
    ]
    good = json.dumps({"message": {"usage": {
        "input_tokens": 1000, "cache_read_input_tokens": 500,
        "output_tokens": 10,
        "cache_creation": {"ephemeral_5m_input_tokens": 100,
                           "ephemeral_1h_input_tokens": 0}}}})
    for payload, name in hostile:
        with tempfile.TemporaryDirectory() as d:
            fp = os.path.join(d, "s.jsonl")
            with open(fp, "w") as f:
                f.write("\n".join([good] * 3) + "\n" + payload + "\n")
            sess = mt.read_session(fp)
            assert sess is not None, f"{name}: the three good records were lost"
            # The three good records must survive intact: the hostile value is
            # skipped, never counted as a token and never poisoning the total.
            assert sess["input"] == 3000, f"{name}: input total is {sess['input']}"
            assert sess["read"] == 1500, f"{name}: read total is {sess['read']}"


def _assistant_rec(usage):
    return json.dumps({"type": "assistant", "message": {"usage": usage}})


def test_no_transcripts_is_no_data_exit_zero():
    """Zero transcripts is not an error: a new user has no history yet."""
    with tempfile.TemporaryDirectory() as d:
        result = mt.format_canary(d, days=9999)
    assert result["transcripts"] == 0, result
    assert result["state"] == "NO DATA", result
    assert result["parse_health"] is None, result
    assert result["exit_code"] == 0, result


def test_renamed_usage_field_is_unrecognised_not_zero():
    """The section 2a hole: a renamed field must not silently read as a
    measured zero. It must be caught and named as FORMAT UNRECOGNISED,
    which is exactly what pricing.py, experiment.py and profile.py cannot
    do, because they only skip on the shape they do not recognise."""
    with tempfile.TemporaryDirectory() as d:
        fp = os.path.join(d, "s.jsonl")
        _write(fp, [
            _assistant_rec({"prompt_tokens": 100, "completion_tokens": 5,
                            "cached_tokens": 10}),
            _assistant_rec({"prompt_tokens": 200, "completion_tokens": 8}),
        ])
        result = mt.format_canary(d, days=9999)
    assert result["transcripts"] == 1, result
    assert result["messages"] == 2, result
    assert result["recognised"] == 0, result
    assert result["state"] == "FORMAT UNRECOGNISED", result
    assert result["parse_health"] == "UNRECOGNISED", result
    assert result["exit_code"] != 0, result


def test_healthy_corpus_reports_healthy():
    with tempfile.TemporaryDirectory() as d:
        fp = os.path.join(d, "s.jsonl")
        _write(fp, [
            _assistant_rec({"input_tokens": 100, "output_tokens": 5,
                            "cache_read_input_tokens": 10}),
            _assistant_rec({"input_tokens": 200, "output_tokens": 8}),
        ])
        result = mt.format_canary(d, days=9999)
    assert result["transcripts"] == 1, result
    assert result["messages"] == 2, result
    assert result["recognised"] == 2, result
    assert result["state"] == "OK", result
    assert result["parse_health"] is None, result
    assert result["exit_code"] == 0, result


def test_partially_recognised_corpus_does_not_report_unrecognised():
    """Some messages recognised, some not: this must never fire the alarm.
    A single genuinely bad message is expected noise, not a format break."""
    with tempfile.TemporaryDirectory() as d:
        fp = os.path.join(d, "s.jsonl")
        _write(fp, [
            _assistant_rec({"prompt_tokens": 100}),           # unrecognised
            _assistant_rec({"input_tokens": 200, "output_tokens": 8}),  # recognised
        ])
        result = mt.format_canary(d, days=9999)
    assert result["messages"] == 2, result
    assert result["recognised"] == 1, result
    assert result["state"] == "OK", result
    assert result["parse_health"] is None, result


def test_format_canary_survives_hostile_lines_without_crashing_or_miscounting():
    """RED before the fix, each ending a stranger's first run:

      not-json      json.JSONDecodeError
      json-not-dict a top level list, e.g. `["assistant"]`
      message-str   `message` holds a string instead of an object

    None of the three may crash the walk, and none may be counted as a
    recognised message: they carry no usable usage block at all."""
    with tempfile.TemporaryDirectory() as d:
        fp = os.path.join(d, "s.jsonl")
        with open(fp, "w") as f:
            f.write(_assistant_rec({"input_tokens": 1, "output_tokens": 1}) + "\n")
            f.write('{"type": "assistant", "message": truncated\n')
            f.write(json.dumps(["assistant", "not", "an", "object"]) + "\n")
            f.write(json.dumps({"type": "assistant", "message": "not an object"}) + "\n")
            f.write(_assistant_rec({"input_tokens": 2, "output_tokens": 2}) + "\n")
        result = mt.format_canary(d, days=9999)
    assert result["transcripts"] == 1, result
    # Only the two genuine records with a message object are counted.
    assert result["messages"] == 2, result
    assert result["recognised"] == 2, result
    assert result["state"] == "OK", result


def test_format_canary_survives_an_unreadable_file():
    with tempfile.TemporaryDirectory() as d:
        fp = os.path.join(d, "locked.jsonl")
        _write(fp, [_assistant_rec({"input_tokens": 1, "output_tokens": 1})])
        os.chmod(fp, 0o000)
        try:
            result = mt.format_canary(d, days=9999)
        finally:
            os.chmod(fp, 0o644)
    # The file is a candidate transcript even though it could not be opened;
    # unreadable is not the same claim as "format unrecognised", so this
    # must not silently become messages == 0 turning into a crash.
    assert result["transcripts"] == 1, result
    assert result["messages"] == 0, result
    assert result["state"] == "NO DATA", result


def test_an_unreadable_directory_is_counted_rather_than_silently_dropped():
    """RED before the fix: skip_counts stayed at 0 while a whole directory of
    transcripts vanished, so the honest 'some files were skipped' line never
    printed and the user saw a confident undercount. os.walk swallows
    directory errors unless onerror is passed."""
    with tempfile.TemporaryDirectory() as d:
        locked = os.path.join(d, "locked")
        os.makedirs(locked)
        with open(os.path.join(locked, "s.jsonl"), "w") as f:
            f.write("{}\n")
        os.chmod(locked, 0o000)
        try:
            mt.SKIP_COUNTS["files"] = 0
            list(mt.iter_session_files(d, 0))
            assert mt.SKIP_COUNTS["files"] > 0, (
                "an unreadable directory was dropped without being counted")
        finally:
            os.chmod(locked, 0o755)


def test_total_type_rename_is_format_unrecognised_not_no_data():
    """Section 2a case A, the fatal one: renaming the outer `type` field
    (assistant -> assistant_message) alongside the usage field names must
    not drive the denominator to zero. Before the structural-probe fix this
    reported NO DATA, the worst outcome a detector can produce: nothing to
    see, precisely when the parser is most thoroughly dead."""
    with tempfile.TemporaryDirectory() as d:
        fp = os.path.join(d, "s.jsonl")
        _write(fp, [json.dumps({"type": "assistant_message",
                                 "message": {"usage": {"prompt_tokens": 10,
                                                        "completion_tokens": 5}}})] * 50)
        result = mt.format_canary(d, days=9999)
    assert result["transcripts"] == 1, result
    assert result["messages"] == 50, result
    assert result["recognised"] == 0, result
    assert result["state"] == "FORMAT UNRECOGNISED", result
    assert result["parse_health"] == "UNRECOGNISED", result
    assert result["exit_code"] != 0, result


def test_mid_history_rename_is_caught_by_newest_slice():
    """Section 2a case B, the most likely real shape: a rename lands today
    and would otherwise hide behind up to CANARY_DAYS of unaffected history,
    because the whole-corpus recognised count stays above zero. All 510
    records live in one file, oldest first (append order is chronological
    order in this format): 10 healthy calls, then 500 renamed ones. The
    newest NEWEST_SLICE_MESSAGES are entirely renamed, so the recency check
    must fire even though the whole window's recognised count is 10, not 0."""
    with tempfile.TemporaryDirectory() as d:
        fp = os.path.join(d, "s.jsonl")
        records = ([_assistant_rec({"input_tokens": 10, "output_tokens": 5})] * 10 +
                   [_assistant_rec({"prompt_tokens": 1})] * 500)
        _write(fp, records)
        result = mt.format_canary(d, days=9999)
    assert result["messages"] == 510, result
    assert result["recognised"] == 10, result
    assert result["state"] == "FORMAT UNRECOGNISED", result
    assert result["parse_health"] == "UNRECOGNISED", result
    assert result["exit_code"] != 0, result
    assert "newest" in result["reason"].lower(), result


def test_newest_slice_recognised_does_not_alarm_even_with_older_unrecognised_records():
    """The mirror of the mid-history rename: OLD records (first in the file)
    are unrecognised, the NEWEST ones (last in the file) are fine. This must
    read as OK, not fire the recency alarm: the format is healthy right now,
    and old noise or a since-fixed rename is not today's problem."""
    with tempfile.TemporaryDirectory() as d:
        fp = os.path.join(d, "s.jsonl")
        records = ([_assistant_rec({"prompt_tokens": 1})] * 300 +
                   [_assistant_rec({"input_tokens": 10, "output_tokens": 5})] * 250)
        _write(fp, records)
        result = mt.format_canary(d, days=9999)
    assert result["messages"] == 550, result
    assert result["recognised"] == 250, result
    assert result["state"] == "OK", result
    assert result["parse_health"] is None, result


def test_assistant_records_with_no_usage_block_do_not_alarm():
    """Section 2a case C: profile.py:332 already expects assistant records
    that legitimately carry no usage block at all, and cries wolf is not
    the alarm this canary exists to raise. No usage-shaped container exists
    anywhere in these records, so there is nothing to judge the parsers'
    recognition against: NO DATA (an absence of evidence to check), never
    the alarm, and never a guessed OK either."""
    with tempfile.TemporaryDirectory() as d:
        fp = os.path.join(d, "s.jsonl")
        _write(fp, [json.dumps({"type": "assistant",
                                 "message": {"content": "hello, no usage block here"}})] * 20)
        result = mt.format_canary(d, days=9999)
    assert result["transcripts"] == 1, result
    assert result["messages"] == 0, result
    assert result["state"] == "NO DATA", result
    assert result["parse_health"] is None, result
    assert result["exit_code"] == 0, result


def test_type_field_is_not_required_for_message_counting():
    """Locks the removal of the old `rec.get("type") != "assistant"` gate: a
    record whose type is not the literal "assistant" at all must still be
    counted and judged on its usage container alone. Reintroducing a type
    check here would silently zero out `messages` again for any transcript
    format that renames or omits `type`, which is exactly the section 2a
    failure this whole task exists to close."""
    with tempfile.TemporaryDirectory() as d:
        fp = os.path.join(d, "s.jsonl")
        _write(fp, [json.dumps({"type": "something_else",
                                 "message": {"usage": {"input_tokens": 5,
                                                        "output_tokens": 2}}})])
        result = mt.format_canary(d, days=9999)
    assert result["messages"] == 1, result
    assert result["recognised"] == 1, result
    assert result["state"] == "OK", result


def test_top_level_usage_without_message_wrapper_is_found():
    """Locks the structural-probe equivalent of the `rec.get("usage")`
    fallback the other parsers use: a usage block living directly on the
    record, with no `message` object at all, must still be found."""
    with tempfile.TemporaryDirectory() as d:
        fp = os.path.join(d, "s.jsonl")
        _write(fp, [json.dumps({"type": "assistant",
                                 "usage": {"input_tokens": 5, "output_tokens": 2}})])
        result = mt.format_canary(d, days=9999)
    assert result["messages"] == 1, result
    assert result["recognised"] == 1, result
    assert result["state"] == "OK", result


def test_recognised_via_nested_cache_creation_only():
    """Locks the nested cache_creation check inside _usage_recognised: a
    usage block with none of the four flat keys, only a recognised nested
    ephemeral_*_input_tokens field, must still count as recognised."""
    with tempfile.TemporaryDirectory() as d:
        fp = os.path.join(d, "s.jsonl")
        _write(fp, [_assistant_rec({"cache_creation": {"ephemeral_5m_input_tokens": 50}})])
        result = mt.format_canary(d, days=9999)
    assert result["messages"] == 1, result
    assert result["recognised"] == 1, result
    assert result["state"] == "OK", result


def test_format_canary_respects_the_days_window():
    """Locks the `days` argument actually being used as the cutoff rather
    than ignored in favor of the default: a transcript modified before the
    requested window must not be counted at all."""
    with tempfile.TemporaryDirectory() as d:
        fp = os.path.join(d, "s.jsonl")
        _write(fp, [_assistant_rec({"input_tokens": 5, "output_tokens": 2})])
        old = time.time() - 5 * 86400
        os.utime(fp, (old, old))
        result = mt.format_canary(d, days=1)
    assert result["transcripts"] == 0, result
    assert result["state"] == "NO DATA", result


def test_no_data_reason_wording_distinguishes_zero_transcripts_from_zero_messages():
    """Locks the two NO DATA reason strings against being swapped: the
    zero-transcripts case (a new user) must say so, and the
    transcripts-found-but-no-usage-shaped-record case must say so too, in
    distinct wording, so the two absences of evidence are never confused."""
    with tempfile.TemporaryDirectory() as d:
        empty_result = mt.format_canary(d, days=9999)
    assert "no transcripts found" in empty_result["reason"].lower(), empty_result

    with tempfile.TemporaryDirectory() as d:
        fp = os.path.join(d, "s.jsonl")
        _write(fp, [json.dumps({"type": "assistant", "message": {"content": "hi"}})])
        found_result = mt.format_canary(d, days=9999)
    assert "no transcripts found" not in found_result["reason"].lower(), found_result
    assert "transcript(s) found" in found_result["reason"], found_result


def test_recognised_usage_keys_pinned_exactly():
    """Ten mutations from the review stayed green with zero coverage on this
    set. Deleting any one of the four recognised usage keys, or either of
    the two nested cache_creation keys, must go red here."""
    assert mt.RECOGNISED_USAGE_KEYS == frozenset({
        "input_tokens", "output_tokens", "cache_read_input_tokens",
        "cache_creation_input_tokens"}), mt.RECOGNISED_USAGE_KEYS
    assert mt.RECOGNISED_CACHE_CREATION_KEYS == frozenset({
        "ephemeral_5m_input_tokens", "ephemeral_1h_input_tokens"}), \
        mt.RECOGNISED_CACHE_CREATION_KEYS


def test_recognised_usage_keys_match_what_the_five_parsers_actually_read():
    """Greps pricing.py, experiment.py, profile.py, reconcile.py and this
    file's own read_session for every literal usage.get("KEY") and
    cc.get("KEY") they branch on, and asserts the pinned sets above are
    exactly that union: neither a stale key nobody reads nor a live key the
    canary does not know about can drift apart from the real parsers again."""
    key_re = re.compile(r'usage\.get\("([a-zA-Z0-9_]+)"\)')
    cc_re = re.compile(r'cc\.get\("([a-zA-Z0-9_]+)"\)')
    found_usage_keys = set()
    found_cc_keys = set()
    for name in ("pricing.py", "experiment.py", "profile.py", "reconcile.py",
                 "measure_tokens.py"):
        with open(os.path.join(HERE, name)) as f:
            text = f.read()
        found_usage_keys |= set(key_re.findall(text))
        found_cc_keys |= set(cc_re.findall(text))
    # "cache_creation" is the nested-object key itself, read via usage.get,
    # not a leaf counter; it is deliberately excluded from the pinned set.
    found_usage_keys.discard("cache_creation")
    assert found_usage_keys == set(mt.RECOGNISED_USAGE_KEYS), found_usage_keys
    assert found_cc_keys == set(mt.RECOGNISED_CACHE_CREATION_KEYS), found_cc_keys


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
