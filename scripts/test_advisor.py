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
    raw = open(STRATEGIES_PATH, encoding="utf-8").read()
    assert "–" not in raw and "—" not in raw, "em or en dash found in strategies.json"


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
