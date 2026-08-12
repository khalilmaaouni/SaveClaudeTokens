#!/usr/bin/env python3
"""Self-check for advisor.py. No framework, no fixtures.

    python3 scripts/test_advisor.py

Calibrated tests (defect reinjected during development, confirmed red, then
fixed and confirmed green again): queue cap, RECOMMENDED-in-evidence guard,
suppression filter, NO DATA exclusion, and token-saver's companion-only rank.
"""

import importlib.util
import io
import json
import os
import re
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


adv = _load("advisor")

STRATEGIES_PATH = os.path.join(HERE, "..", "data", "strategies.json")


def leaf(value, label="MEASURED", basis="test basis"):
    return {"value": value, "label": label, "basis": basis}


def nest(flat):
    """Build a nested profile dict from {"a.b.c": leaf(...)} pairs."""
    profile = {}
    for dotted, val in flat.items():
        node = profile
        parts = dotted.split(".")
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = val
    return profile


def strategy(sid, category, metric, op, value, band, evidence="MEASURED", escalate=None):
    trig = {"metric": metric, "op": op, "value": value, "band": band}
    if escalate:
        trig["escalate"] = escalate
    return {
        "id": sid, "category": category, "title": f"title {sid}",
        "trigger": trig, "what_it_changes": "x", "expected_benefit": "x",
        "evidence": evidence, "drawback": "x", "quality_risk": "LOW",
        "reversibility": "x", "how_measured": "x", "if_you_say_no": "x",
        "alternatives": [], "companion": None, "requires_confirmation": False,
        "source": "A1",
    }


def test_queue_never_exceeds_three():
    strategies = [strategy(f"cat{i}.s{i}", "cache", f"usage.m{i}", ">=", 1, "HIGH")
                  for i in range(5)]
    profile = nest({f"usage.m{i}": leaf(5) for i in range(5)})
    result = adv.advise(profile, {}, strategies)
    assert len(result["queue"]) <= 3, result["queue"]
    assert len(result["alternatives"]) <= 2, result["alternatives"]


def test_recommended_never_in_an_evidence_field():
    real = adv.load_strategies(STRATEGIES_PATH)
    for s in real:
        assert s["evidence"] != "RECOMMENDED", s["id"]
    profile = nest({"behavior.model_switch_session_share": leaf(0.5)})
    result = adv.advise(profile, {}, real)
    for c in result["queue"] + ([result["companion"]] if result["companion"] else []):
        assert c["evidence"] != "RECOMMENDED", c["id"]
        assert c["rank"] in ("RECOMMENDED", "ALTERNATIVE", "COMPANION")


def test_suppressed_strategy_absent_before_expiry_and_back_after():
    strategies = [strategy("cache.s1", "cache", "usage.m1", ">=", 1, "HIGH")]
    profile = nest({"usage.m1": leaf(5)})
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    future = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() + 86400))
    past = "2000-01-01T00:00:00"

    still_suppressed = adv.advise(profile, {"cache.s1": {"decision": "suppressed", "until": future}}, strategies)
    assert still_suppressed["best"] is None
    assert still_suppressed["do_nothing"] is True

    expired = adv.advise(profile, {"cache.s1": {"decision": "suppressed", "until": past}}, strategies)
    assert expired["best"] is not None
    assert expired["best"]["id"] == "cache.s1"
    del now  # unused, kept for readability of the past/future contrast above


def test_no_data_metric_excludes_strategy_and_lands_in_insufficient():
    strategies = [strategy("cache.s1", "cache", "usage.m1", ">=", 1, "HIGH")]
    profile = nest({"usage.m1": leaf(None, label="NO DATA")})
    result = adv.advise(profile, {}, strategies)
    assert result["best"] is None
    assert result["insufficient"] == ["cache.s1"]

    missing_key_profile = {}
    result2 = adv.advise(missing_key_profile, {}, strategies)
    assert result2["insufficient"] == ["cache.s1"]


def test_why_selected_contains_the_profiles_own_number():
    strategies = [strategy("cache.s1", "cache", "behavior.model_switch_session_share", ">=", 0.2, "HIGH")]
    profile = nest({"behavior.model_switch_session_share": leaf(0.42)})
    result = adv.advise(profile, {}, strategies)
    assert "42%" in result["best"]["why_selected"], result["best"]["why_selected"]


def test_strategies_json_loads_validates_and_carries_no_dashes():
    strategies = adv.load_strategies(STRATEGIES_PATH)
    assert 10 <= len(strategies) <= 14, len(strategies)
    for s in strategies:
        assert s["source"], s["id"]
    # The dash needles are written as escapes so this source file itself
    # carries no literal em or en dash byte for the push gate to find.
    raw = open(STRATEGIES_PATH, encoding="utf-8").read()
    assert "\u2013" not in raw and "\u2014" not in raw, "em or en dash found in strategies.json"


def test_load_strategies_rejects_a_strategy_missing_how():
    # Calibrated: dropping "how" from REQUIRED_FIELDS (or the _validate_how
    # call) lets a strategy without concrete steps load silently and this
    # test goes red; restored, load_strategies raises and names the field.
    import tempfile
    real = adv.load_strategies(STRATEGIES_PATH)
    broken = json.loads(json.dumps({"schema": 2, "strategies": [
        {k: v for k, v in s.items() if k != "how"} for s in real[:1]
    ]}))
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "strategies.json")
        with open(path, "w") as f:
            json.dump(broken, f)
        try:
            adv.load_strategies(path)
            assert False, "expected a ValueError for the missing how field"
        except ValueError as e:
            assert "how" in str(e), str(e)

    # Also reject a "how" that is too short, and one whose step text carries
    # a dash.
    with tempfile.TemporaryDirectory() as d:
        s = json.loads(json.dumps(real[0]))
        s["how"] = [{"text": "one step only"}]
        path = os.path.join(d, "strategies.json")
        with open(path, "w") as f:
            json.dump({"schema": 2, "strategies": [s]}, f)
        try:
            adv.load_strategies(path)
            assert False, "expected a ValueError for a too-short how list"
        except ValueError as e:
            assert "how" in str(e), str(e)

    with tempfile.TemporaryDirectory() as d:
        s = json.loads(json.dumps(real[0]))
        s["how"] = [{"text": "step one"}, {"text": "a step with an em dash " + "\u2014" + " here"}]
        path = os.path.join(d, "strategies.json")
        with open(path, "w") as f:
            json.dump({"schema": 2, "strategies": [s]}, f)
        try:
            adv.load_strategies(path)
            assert False, "expected a ValueError for a dash in a how step"
        except ValueError as e:
            assert "dash" in str(e), str(e)


def test_card_source_is_a_citable_pointer_not_a_bare_code():
    # Calibrated: reverting _card to `"source": strategy["source"]` leaves the
    # bare code A6 on the card and this test goes red; with format_source, green.
    #
    # A6 and D5 are row ids in the tables of docs/CLAIMS.md. On a card they
    # were unlookupable: a reader saw two characters and no way to check the
    # claim behind them.
    real = adv.load_strategies(STRATEGIES_PATH)
    a6 = [s for s in real if s["source"] == "A6"]
    assert a6, "fixture assumption: at least one strategy is sourced A6"

    profile = nest({"behavior.model_switch_session_share": leaf(0.5)})
    result = adv.advise(profile, {}, real)
    card = result["best"]
    assert card["id"] == "cache.fixed-parent-model", card["id"]
    assert card["source"] == "docs/CLAIMS.md row A6", card["source"]

    printed = io.StringIO()
    import contextlib
    with contextlib.redirect_stdout(printed):
        adv._print_card(card)
    assert "docs/CLAIMS.md row A6" in printed.getvalue(), printed.getvalue()

    # Several codes are each named, and anything that is not a claim code (a
    # URL, free text) is left exactly as it was rather than being dressed up
    # as a row id that does not exist.
    assert adv.format_source("A3, A4") == "docs/CLAIMS.md rows A3, A4"
    url = "https://code.claude.com/docs/en/hooks"
    assert adv.format_source(url) == url
    assert adv.format_source("measured on this machine") == "measured on this machine"

    # Every shipped strategy ends up citable: a CLAIMS row, a URL, or a real
    # file in this repo (checked on disk, not just shaped like a path, so a
    # typo'd pointer fails this test the same way a bare code used to).
    for s in real:
        rendered = adv.format_source(s["source"])
        is_claims_row = rendered.startswith("docs/CLAIMS.md row")
        is_url = "://" in rendered
        is_repo_doc = rendered.startswith("docs/") and os.path.exists(
            os.path.join(HERE, "..", rendered))
        assert is_claims_row or is_url or is_repo_doc, (s["id"], rendered)


def test_token_saver_entry_can_never_be_best():
    real = adv.load_strategies(STRATEGIES_PATH)
    # Isolated so ONLY companion.token-saver's trigger (>=200000) fires: below
    # bounded-reads (500000), isolate-huge-logs (1000000) and caveman (300000).
    # If companion cards ever leaked into the main ranking, this is the one
    # profile where token-saver would have nothing else to lose to.
    profile = nest({"usage.output_tokens_total": leaf(250_000)})
    result = adv.advise(profile, {}, real)
    if result["best"]:
        assert result["best"]["id"] != "companion.token-saver"
    for c in result["queue"]:
        assert c["id"] != "companion.token-saver"
    assert result["do_nothing"] is True
    assert result["companion"]["id"] == "companion.token-saver"


def test_do_nothing_on_a_healthy_profile():
    real = adv.load_strategies(STRATEGIES_PATH)
    profile = nest({
        "behavior.model_switch_session_share": leaf(0.0),
        "behavior.idle_gap_shares": leaf(0.0),
        "instruction.startup_floor_share": leaf(0.05),
        "instruction.claude_md_user_bytes": leaf(500),
        "instruction.claude_md_project_bytes": leaf(500),
        "usage.cache_hit_ratio_median": leaf(0.95),
        "usage.output_tokens_total": leaf(1000),
        "environment.plugin_count": leaf(1),
    })
    result = adv.advise(profile, {}, real)
    assert result["best"] is None
    assert result["do_nothing"] is True
    assert "95%" in result["message"] and "5%" in result["message"], result["message"]


def test_load_treatments_recovers_from_a_corrupt_file(tmp_path=None):
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "treatments.json")
        with open(path, "w") as f:
            f.write("{not valid json")
        buf = io.StringIO()
        import contextlib
        with contextlib.redirect_stdout(buf):
            result = adv.load_treatments(path)
        assert result == {}
        backups = [n for n in os.listdir(d) if n.startswith("treatments.json.corrupt-")]
        assert backups, os.listdir(d)


def test_record_decision_round_trips_and_expires_correctly():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "treatments.json")
        adv.record_decision("cache.s1", "rejected", days=1, note="not now", path=path)
        loaded = adv.load_treatments(path)
        assert loaded["cache.s1"]["decision"] == "rejected"
        assert loaded["cache.s1"]["until"] > time.strftime("%Y-%m-%dT%H:%M:%S")

        adv.record_decision("cache.s2", "accepted", path=path)
        loaded2 = adv.load_treatments(path)
        assert loaded2["cache.s2"]["lineage"].startswith("cache.s2-")
        assert "until" not in loaded2["cache.s2"]


def test_decide_flag_round_trips_into_treatment_memory_and_the_queue():
    # Calibrated: dropping the `--decide` branch from main() (or having
    # cmd_decide write through record_decision's own stale default path
    # instead of the live TREATMENTS_PATH global) makes this go red because
    # nothing lands in the temp file; restored, the decision round-trips and
    # the suppressed strategy is gone from the very next queue.
    import tempfile
    real_path = adv.TREATMENTS_PATH
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "treatments.json")
        adv.TREATMENTS_PATH = path
        try:
            rc = adv.main(["--decide", "cache.fixed-parent-model", "not-now"])
            loaded = adv.load_treatments(path)
            assert rc == 0
            assert loaded["cache.fixed-parent-model"]["decision"] == "suppressed"
            assert loaded["cache.fixed-parent-model"]["until"] > time.strftime("%Y-%m-%dT%H:%M:%S")

            strategies = adv.load_strategies()
            profile = nest({"behavior.model_switch_session_share": leaf(0.5)})
            result = adv.advise(profile, loaded, strategies)
            ids = [c["id"] for c in result["queue"]]
            assert "cache.fixed-parent-model" not in ids, ids

            # "never" maps onto the same "rejected" decision, just far out, and
            # "done" onto "accepted"; no new decision string is ever invented.
            rc2 = adv.main(["--decide", "startup.floor-ladder", "never"])
            rc3 = adv.main(["--decide", "companion.ponytail", "done"])
            assert rc2 == 0 and rc3 == 0
            loaded2 = adv.load_treatments(path)
            assert loaded2["startup.floor-ladder"]["decision"] == "rejected"
            assert loaded2["companion.ponytail"]["decision"] == "accepted"
            assert "lineage" in loaded2["companion.ponytail"]

            rc4 = adv.main(["--decide", "cache.fixed-parent-model", "bogus-choice"])
            assert rc4 == 2
        finally:
            adv.TREATMENTS_PATH = real_path


def test_trigger_descends_into_a_composite_leaf_value():
    """A metric like behavior.idle_gap_shares.5m_to_15m must reach inside the
    leaf's own dict value, inheriting the leaf's label."""
    profile = nest({"behavior.idle_gap_shares": leaf(
        {"under_5m": 0.5, "5m_to_15m": 0.4, "15m_to_60m": 0.1, "over_60m": 0.0},
        label="SIGNAL")})
    strategies = [strategy("cache.ttl", "cache", "behavior.idle_gap_shares.5m_to_15m", ">=", 0.15, "MED")]
    result = adv.advise(profile, {}, strategies)
    assert result["best"] is not None and result["best"]["id"] == "cache.ttl", result


def test_composite_leaf_without_descent_is_insufficient_not_a_crash():
    """Comparing a whole composite value to a number is a real profile shape
    (the live crash of 2026-08-12): it must land in insufficient, never raise."""
    profile = nest({"behavior.idle_gap_shares": leaf({"under_5m": 1.0}, label="SIGNAL")})
    strategies = [strategy("cache.ttl", "cache", "behavior.idle_gap_shares", ">=", 0.2, "MED")]
    result = adv.advise(profile, {}, strategies)
    assert result["best"] is None
    assert "cache.ttl" in result["insufficient"], result


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
