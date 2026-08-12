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
import tempfile

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


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
