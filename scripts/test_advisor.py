#!/usr/bin/env python3
"""Self-check for advisor.py. No framework, no fixtures.

    python3 scripts/test_advisor.py

Calibrated tests (defect reinjected during development, confirmed red, then
fixed and confirmed green again): queue cap, RECOMMENDED-in-evidence guard,
suppression filter, NO DATA exclusion, token-saver's companion-only rank,
aggressive mode's curated-registry gate, and the recipe trust boundary
(disabling cmd_recipe's `result["refused"]` check made
test_recipe_refuses_a_name_not_in_the_curated_registry crash with a
KeyError instead of passing; restoring the check made it pass again).
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


def strategy(sid, category, metric, op, value, band, evidence="MEASURED", escalate=None,
             companion=None, problem_class=None, quality_risk="LOW"):
    trig = {"metric": metric, "op": op, "value": value, "band": band}
    if escalate:
        trig["escalate"] = escalate
    return {
        "id": sid, "category": category, "problem_class": problem_class,
        "title": f"title {sid}",
        "trigger": trig, "what_it_changes": "x", "expected_benefit": "x",
        "evidence": evidence, "drawback": "x", "quality_risk": quality_risk,
        "reversibility": "x", "how_measured": "x", "if_you_say_no": "x",
        "alternatives": [], "companion": companion, "requires_confirmation": False,
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
    # Calibrated (finding C2/M2): before the tournament gated on a real
    # native signal, this profile printed "this profile looks healthy" AND
    # four tournament winners in the same breath (one of them a
    # companion.token-saver crown, even though its own card says it is
    # never offered as a recommended fix), a contradicting second
    # recommendation with no reconciliation in the rendered text. Fixed, a
    # profile with nothing real anywhere renders no tournaments at all: the
    # "do nothing" message stays the only headline.
    assert result["tournaments"] == [], result["tournaments"]

    printed = io.StringIO()
    import contextlib
    with contextlib.redirect_stdout(printed):
        adv._print_tournaments(result["tournaments"])
    assert printed.getvalue() == "", printed.getvalue()


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


def test_companion_ownership_suppresses_duplicate_card():
    # Calibrated: before sync_companion_suppressions/advise() honored a
    # strategy's own "companion" field, this card stayed in the queue no
    # matter which companions were active; fixed, an active owner hides it
    # and stamps the metric value observed at that moment on the record.
    import tempfile
    strategies = [strategy("overbuild.s1", "overbuild", "usage.m1", ">=", 1, "MED",
                            companion="ponytail")]
    profile = nest({"usage.m1": leaf(5)})
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "treatments.json")
        newly = adv.sync_companion_suppressions(strategies, {"ponytail"}, profile, path=path)
        assert newly == ["overbuild.s1"], newly
        treatments = adv.load_treatments(path)
        assert treatments["overbuild.s1"]["decision"] == "suppressed"
        assert treatments["overbuild.s1"]["reason"] == "companion"
        assert treatments["overbuild.s1"]["metric_value_at_suppression"] == 5, treatments
        result = adv.advise(profile, treatments, strategies)
        assert result["best"] is None, result["best"]
        assert result["suppressed_by_companion"] == ["overbuild.s1"], result


def test_strategy_without_declared_companion_is_never_suppressed():
    # NO DATA beats a guess: a strategy that never names a companion must
    # never be suppressed, no matter which companions are active.
    import tempfile
    strategies = [strategy("overbuild.s1", "overbuild", "usage.m1", ">=", 1, "MED",
                            companion=None)]
    profile = nest({"usage.m1": leaf(5)})
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "treatments.json")
        newly = adv.sync_companion_suppressions(strategies, {"ponytail"}, profile, path=path)
        assert newly == [], newly
        assert adv.load_treatments(path) == {}
    result = adv.advise(profile, {}, strategies)
    assert result["best"] is not None and result["best"]["id"] == "overbuild.s1", result


def test_sync_never_re_arms_a_lapsed_companion_suppression():
    # Calibrated to catch the real defect (not the theater the first attempt
    # shipped, which only re-checked advise()'s pre-existing expiry filter):
    # a companion suppression that has already lapsed must never be rewritten
    # with a fresh window on the next sync run, or the card could never come
    # back on its own. This exercises sync_companion_suppressions() itself,
    # not just advise()'s unrelated suppression filter.
    import tempfile
    strategies = [strategy("overbuild.s1", "overbuild", "usage.m1", ">=", 1, "MED",
                            companion="ponytail")]
    profile = nest({"usage.m1": leaf(5)})
    past = "2000-01-01T00:00:00"
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "treatments.json")
        with open(path, "w") as f:
            json.dump({"overbuild.s1": {"decision": "suppressed", "until": past,
                                        "reason": "companion", "at": past,
                                        "metric_value_at_suppression": 5}}, f)

        newly = adv.sync_companion_suppressions(strategies, {"ponytail"}, profile, path=path)
        assert newly == [], newly

        treatments = adv.load_treatments(path)
        assert treatments["overbuild.s1"]["until"] == past, treatments["overbuild.s1"]
        result = adv.advise(profile, treatments, strategies)
        assert result["best"] is not None and result["best"]["id"] == "overbuild.s1", result
        assert result["suppressed_by_companion"] == [], result


def test_sync_never_overwrites_a_user_record_even_an_accepted_one_with_lineage():
    # The reviewer's own repro: an accepted record carrying experiment
    # lineage must survive sync untouched, whatever the strategy's companion
    # field says, because a later experiment may cite that exact lineage.
    import tempfile
    strategies = [strategy("overbuild.s1", "overbuild", "usage.m1", ">=", 1, "MED",
                            companion="ponytail")]
    profile = nest({"usage.m1": leaf(5)})
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "treatments.json")
        user_rec = {"decision": "accepted", "at": "2026-01-01T00:00:00",
                    "lineage": "overbuild.s1-20260101", "note": "did it"}
        with open(path, "w") as f:
            json.dump({"overbuild.s1": dict(user_rec)}, f)

        newly = adv.sync_companion_suppressions(strategies, {"ponytail"}, profile, path=path)
        assert newly == [], newly
        assert adv.load_treatments(path)["overbuild.s1"] == user_rec


def test_load_active_companions_filters_to_enabled_and_curated():
    # A missing state file is NO DATA (empty set, never guessed active); an
    # enabled companion whose name is not registry-matched to "curated" (a
    # same-named lookalike plugin, for example) is left out too.
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "companions_state.json")
        assert adv.load_active_companions(path) == set()
        state = {
            "schema": 1,
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "discovered": [
                {"name": "ponytail", "enabled": True, "source_label": "CLAUDE PROJECTED"},
                {"name": "caveman", "enabled": False, "source_label": "CLAUDE PROJECTED"},
                {"name": "some-fork", "enabled": True, "source_label": "CLAUDE PROJECTED"},
            ],
            "registry_match": {"ponytail": "curated", "caveman": "curated", "some-fork": "unknown"},
        }
        with open(path, "w") as f:
            json.dump(state, f)
        assert adv.load_active_companions(path) == {"ponytail"}, adv.load_active_companions(path)


def test_load_active_companions_stale_state_suppresses_nothing():
    # Calibrated: discover_companions.py stamps checked_at but nothing read
    # it; a state file two years old still counted as active. Uninstalling a
    # companion and never re-running discovery must not silence advice
    # forever, so a state older than STALE_COMPANION_STATE_DAYS is NO DATA.
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "companions_state.json")
        old = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 400 * 86400))
        state = {
            "schema": 1, "checked_at": old,
            "discovered": [{"name": "ponytail", "enabled": True, "source_label": "x"}],
            "registry_match": {"ponytail": "curated"},
        }
        with open(path, "w") as f:
            json.dump(state, f)
        assert adv.load_active_companions(path) == set(), adv.load_active_companions(path)

        fresh = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        state["checked_at"] = fresh
        with open(path, "w") as f:
            json.dump(state, f)
        assert adv.load_active_companions(path) == {"ponytail"}


def test_load_active_companions_never_raises_on_a_malformed_root():
    # load_active_companions's docstring promises it never raises. A JSON
    # root of [], null, "hi", or a dict missing checked_at/registry_match
    # must all degrade to an empty set, never kill the advise command.
    import tempfile
    for bad_root in ([], None, "hi", {"discovered": ["ponytail"]}):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "companions_state.json")
            with open(path, "w") as f:
                json.dump(bad_root, f)
            assert adv.load_active_companions(path) == set(), bad_root


def test_regression_guard_returns_card_when_metric_far_worse_ge_direction():
    # Finding-1 replacement for the old "always show on HIGH band" rule:
    # enumerating strategies.json's real triggers proved that rule was
    # nearly a no-op (11 of 13 strategies can never reach HIGH). Here the
    # fixture is extreme (100000x the recorded value) so the assertion is
    # unambiguous either way the margin is implemented.
    strategies = [strategy("overbuild.s1", "overbuild", "usage.m1", ">=", 1, "MED",
                            companion="ponytail")]
    future = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() + 86400))
    treatments = {"overbuild.s1": {"decision": "suppressed", "until": future,
                                   "reason": "companion", "metric_value_at_suppression": 100}}
    profile = nest({"usage.m1": leaf(100 * 100000)})
    result = adv.advise(profile, treatments, strategies)
    assert result["best"] is not None and result["best"]["id"] == "overbuild.s1", result
    assert result["suppressed_by_companion"] == [], result


def test_regression_guard_returns_card_when_metric_far_worse_le_direction():
    # Same guard, "<=" direction: smaller is worse for a <= trigger.
    strategies = [strategy("memory.s1", "memory", "usage.m1", "<=", 10, "MED",
                            companion="ponytail")]
    future = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() + 86400))
    treatments = {"memory.s1": {"decision": "suppressed", "until": future,
                                "reason": "companion", "metric_value_at_suppression": 100}}
    profile = nest({"usage.m1": leaf(1)})
    result = adv.advise(profile, treatments, strategies)
    assert result["best"] is not None and result["best"]["id"] == "memory.s1", result
    assert result["suppressed_by_companion"] == [], result


def test_regression_guard_margin_not_crossed_keeps_card_suppressed():
    # The margin's own effect: a metric that is worse but by less than
    # REGRESSION_MARGIN must not override the suppression. 100 -> 120 is 20%
    # worse, well under the 50% margin.
    strategies = [strategy("overbuild.s1", "overbuild", "usage.m1", ">=", 1, "MED",
                            companion="ponytail")]
    future = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() + 86400))
    treatments = {"overbuild.s1": {"decision": "suppressed", "until": future,
                                   "reason": "companion", "metric_value_at_suppression": 100}}
    profile = nest({"usage.m1": leaf(120)})
    result = adv.advise(profile, treatments, strategies)
    assert result["best"] is None, result
    assert result["suppressed_by_companion"] == ["overbuild.s1"], result


def test_companion_suppression_expires_and_card_returns():
    # Without expiry, a companion suppression record written once would hide
    # the card forever; the "until" cooldown must let it come back, and it
    # must not carry the old regression-metric baseline forward as a reason
    # to keep hiding it.
    strategies = [strategy("overbuild.s1", "overbuild", "usage.m1", ">=", 1, "MED",
                            companion="ponytail")]
    profile = nest({"usage.m1": leaf(5)})
    past = "2000-01-01T00:00:00"
    treatments = {"overbuild.s1": {"decision": "suppressed", "until": past, "reason": "companion",
                                   "metric_value_at_suppression": 5}}
    result = adv.advise(profile, treatments, strategies)
    assert result["best"] is not None and result["best"]["id"] == "overbuild.s1", result
    assert result["suppressed_by_companion"] == [], result



def test_mode_strategies_nested_deterministic_and_aggressive_equals_full_set():
    # conservative subset of ids <= balanced subset of ids <= aggressive
    # subset of ids, every call returning the exact same list (same ids,
    # same order): a non-technical user picking a "bigger" mode must never
    # lose a card the smaller mode already offered. aggressive == the full,
    # unfiltered strategy list is the proof that a companion strategy is
    # only ever added by the top mode, never silently included earlier.
    real = adv.load_strategies(STRATEGIES_PATH)
    subsets = {m: adv.mode_strategies(real, m) for m in adv.MODES}
    assert subsets["conservative"] == adv.mode_strategies(real, "conservative"), "not deterministic"

    cons_ids = [s["id"] for s in subsets["conservative"]]
    bal_ids = [s["id"] for s in subsets["balanced"]]
    agg_ids = [s["id"] for s in subsets["aggressive"]]
    assert set(cons_ids) <= set(bal_ids) <= set(agg_ids), (cons_ids, bal_ids, agg_ids)
    assert all(s["quality_risk"] == "LOW" and s["category"] != "companion"
               for s in subsets["conservative"]), subsets["conservative"]
    assert all(s["category"] != "companion" for s in subsets["balanced"]), subsets["balanced"]
    assert agg_ids == [s["id"] for s in real], (agg_ids, [s["id"] for s in real])


def test_mode_strategies_rejects_an_unknown_mode():
    try:
        adv.mode_strategies(adv.load_strategies(STRATEGIES_PATH), "reckless")
        assert False, "expected a ValueError for an unknown mode"
    except ValueError as e:
        assert "reckless" in str(e), str(e)


def test_mode_strategies_aggressive_drops_a_companion_not_in_the_curated_registry():
    # Calibrated: an early draft of mode_strategies gated aggressive mode
    # only on category == "companion", with no curated-registry check at
    # all; this test went red (the uncurated strategy stayed in the
    # aggressive subset); restored to checking the id's companion name
    # against curated_names, green again.
    strategies = [
        strategy("companion.widget", "companion", "usage.m1", ">=", 1, "LOW"),
        strategy("cache.s1", "cache", "usage.m2", ">=", 1, "LOW"),
    ]
    kept = adv.mode_strategies(strategies, "aggressive", curated_names={"other-thing"})
    ids = [s["id"] for s in kept]
    assert "companion.widget" not in ids, ids
    assert "cache.s1" in ids, ids
    kept2 = adv.mode_strategies(strategies, "aggressive", curated_names={"widget"})
    assert "companion.widget" in [s["id"] for s in kept2]


def test_main_no_mode_never_filters_and_never_prints_a_mode_line():
    # Calibrated: an early draft always called mode_strategies (defaulting
    # a bare mode to "conservative" instead of None), so the default,
    # no-mode CLI path silently narrowed to a subset; this test went red
    # (mode_strategies raised via the monkeypatch, or "mode:" appeared in
    # the output); restored to only filtering when --mode is actually
    # given, green again: today's behavior, unchanged.
    import contextlib
    import tempfile
    profile = nest({"behavior.model_switch_session_share": leaf(0.5)})
    with tempfile.TemporaryDirectory() as d:
        profile_path = os.path.join(d, "profile.json")
        with open(profile_path, "w") as f:
            json.dump(profile, f)
        treatments_path = os.path.join(d, "treatments.json")
        real_profile_path, real_treatments_path = adv.PROFILE_PATH, adv.TREATMENTS_PATH
        real_mode_strategies = adv.mode_strategies
        adv.PROFILE_PATH, adv.TREATMENTS_PATH = profile_path, treatments_path

        def _boom(*_a, **_k):
            raise AssertionError("mode_strategies must not run when --mode is omitted")

        adv.mode_strategies = _boom
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = adv.main([])
            out = buf.getvalue()
        finally:
            adv.PROFILE_PATH, adv.TREATMENTS_PATH = real_profile_path, real_treatments_path
            adv.mode_strategies = real_mode_strategies
    assert rc == 0
    assert "mode:" not in out, out


def test_main_mode_flag_filters_and_prints_the_mode_line():
    import contextlib
    import tempfile
    profile = nest({"behavior.model_switch_session_share": leaf(0.5)})
    with tempfile.TemporaryDirectory() as d:
        profile_path = os.path.join(d, "profile.json")
        with open(profile_path, "w") as f:
            json.dump(profile, f)
        treatments_path = os.path.join(d, "treatments.json")
        real_profile_path, real_treatments_path = adv.PROFILE_PATH, adv.TREATMENTS_PATH
        adv.PROFILE_PATH, adv.TREATMENTS_PATH = profile_path, treatments_path
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = adv.main(["--mode", "conservative"])
            out = buf.getvalue()
        finally:
            adv.PROFILE_PATH, adv.TREATMENTS_PATH = real_profile_path, real_treatments_path
    assert rc == 0
    assert "mode: conservative" in out, out


def test_main_rejects_an_unknown_mode_before_touching_the_profile():
    # No PROFILE_PATH setup: an unknown --mode is refused before any file
    # is opened, so this runs against whatever PROFILE_PATH is on the box.
    assert adv.main(["--mode", "reckless"]) == 2
    assert adv.main(["--mode"]) == 2


def test_recipe_refuses_a_name_not_in_the_curated_registry():
    # UNVETTED PLUGIN REFUSED: this is the trust boundary the recipe
    # feature exists to enforce. Calibrated (see the module docstring
    # above): disabling cmd_recipe's `result["refused"]` check made this
    # test crash with a KeyError instead of passing; restoring the check
    # makes it pass again.
    buf = io.StringIO()
    import contextlib
    with contextlib.redirect_stdout(buf):
        rc = adv.cmd_recipe("not-a-real-companion-xyz")
    out = buf.getvalue()
    assert rc == 2, rc
    assert "REFUSED" in out, out
    assert "not-a-real-companion-xyz" in out, out


def test_recipe_prints_commands_verbatim_from_the_real_registry():
    with open(os.path.join(HERE, "..", "data", "companions.json")) as f:
        raw = f.read()
    buf = io.StringIO()
    import contextlib
    with contextlib.redirect_stdout(buf):
        rc = adv.cmd_recipe("ponytail")
    out = buf.getvalue()
    assert rc == 0, out
    install_line = [l for l in out.splitlines() if "install:" in l][0]
    rollback_line = [l for l in out.splitlines() if "rollback:" in l][0]
    install_cmd = install_line.split("install:", 1)[1].strip()
    rollback_cmd = rollback_line.split("rollback:", 1)[1].strip()
    assert install_cmd in raw, install_cmd
    assert rollback_cmd in raw, rollback_cmd


def test_recipe_refuses_when_registry_entry_missing_a_required_field():
    # Missing-field refusal: a curated entry that names the companion but
    # is missing "uninstall" must be refused, naming that exact field,
    # never crash and never fall back to inventing a rollback command.
    import tempfile
    real_path = adv.ts.COMPANIONS_PATH
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "companions.json")
        with open(path, "w") as f:
            json.dump({"schema": 2, "mentions": [], "companions": [{
                "name": "widget", "install": "do it",
                "tested_version_range": {"min": "1.0.0", "max": "1.0.0",
                                         "tested_on": "2026-08-13"},
            }]}, f)
        adv.ts.COMPANIONS_PATH = path
        try:
            buf = io.StringIO()
            import contextlib
            with contextlib.redirect_stdout(buf):
                rc = adv.cmd_recipe("widget")
        finally:
            adv.ts.COMPANIONS_PATH = real_path
    out = buf.getvalue()
    assert rc == 2, out
    assert "uninstall" in out, out


def test_sync_refuses_to_suppress_when_the_metric_cannot_be_read():
    # A suppression whose baseline value is unknown can never be lifted by
    # the regression guard, so the card would stay silent for the whole
    # window however badly the metric degraded. Refuse to suppress instead.
    import tempfile
    strategies = [strategy("overbuild.s1", "overbuild", "usage.m1", ">=", 1, "MED",
                            companion="ponytail")]
    path = tempfile.mktemp()
    newly = adv.sync_companion_suppressions(strategies, {"ponytail"}, {"schema": 1}, path=path)
    assert newly == [], newly
    assert adv.load_treatments(path) == {}, adv.load_treatments(path)
    # And the card is still offered, rather than silently withheld.
    result = adv.advise(nest({"usage.m1": leaf(500)}), adv.load_treatments(path), strategies)
    assert result["best"] is not None and result["best"]["id"] == "overbuild.s1", result


def fact(fid, verified, review_interval_days=30, source="test source"):
    return {"id": fid, "statement": "test statement", "source": source,
            "verified": verified, "review_interval_days": review_interval_days}


def test_fresh_fact_renders_without_staleness_text():
    # strategy() sources every fixture strategy "A1" by default.
    strategies = [strategy("cache.s1", "cache", "usage.m1", ">=", 1, "HIGH")]
    profile = nest({"usage.m1": leaf(5)})
    facts = [fact("A1", verified="2026-08-01", review_interval_days=30)]
    result = adv.advise(profile, {}, strategies, facts=facts, today="2026-08-14")
    assert result["best"]["stale_facts"] == [], result["best"]["stale_facts"]

    printed = io.StringIO()
    import contextlib
    with contextlib.redirect_stdout(printed):
        adv._print_card(result["best"])
    assert "FACT STALE" not in printed.getvalue(), printed.getvalue()


def test_stale_fact_carries_staleness_to_the_user():
    # Calibrated: with the propagation removed (_card built without passing
    # facts_by_id/today into _stale_fact_lines, or _print_card not looping
    # over stale_facts), this goes red because the rendered card never
    # mentions the stale fact even though the registry says it is 45 days
    # past its 30 day review interval; restored, it goes green.
    strategies = [strategy("cache.s1", "cache", "usage.m1", ">=", 1, "HIGH")]
    profile = nest({"usage.m1": leaf(5)})
    facts = [fact("A1", verified="2026-06-30", review_interval_days=30)]
    result = adv.advise(profile, {}, strategies, facts=facts, today="2026-08-14")
    assert result["best"]["stale_facts"], result["best"]["stale_facts"]
    assert any("A1" in line for line in result["best"]["stale_facts"])
    assert any("FACT STALE" in line for line in result["best"]["stale_facts"])

    printed = io.StringIO()
    import contextlib
    with contextlib.redirect_stdout(printed):
        adv._print_card(result["best"])
    out = printed.getvalue()
    assert "FACT STALE" in out and "A1" in out, out
    assert "2026-06-30" in out, out


def test_tournament_ranks_two_candidates_winner_and_visible_loser():
    # Two candidates for the same problem, different fit: the higher band
    # wins deterministically and the loser is still visible, one level
    # deeper, with the criterion that decided against it.
    strategies = [
        strategy("cache.a", "cache", "usage.m1", ">=", 1, "HIGH", problem_class="cache_health"),
        strategy("routing.b", "routing", "usage.m1", ">=", 1, "MED", problem_class="cache_health"),
    ]
    profile = nest({"usage.m1": leaf(5)})
    result = adv.advise(profile, {}, strategies)
    tournaments = result["tournaments"]
    assert len(tournaments) == 1, tournaments
    t = tournaments[0]
    assert t["problem_class"] == "cache_health"
    assert t["winner"]["id"] == "cache.a", t["winner"]
    assert "HIGH" in t["why_won"] and "MED" in t["why_won"], t["why_won"]
    assert len(t["also_considered"]) == 1
    loser = t["also_considered"][0]
    assert loser["id"] == "routing.b"
    assert loser["fit"] == "MED"
    assert "MED" in loser["why_lost"], loser["why_lost"]


def test_tournament_native_before_companion_at_equal_fit():
    # Calibrated: with the companion-exclusion removed from the winner pool
    # (build_tournaments picking min() over ALL candidates, companions
    # included), companion.comp wins here instead and this test goes red;
    # restored, the native wins and the companion is a tagged loser, never
    # a winner, at any fit or risk.
    strategies = [
        strategy("output.native", "output", "usage.m1", ">=", 1, "HIGH", problem_class="tool_output"),
        strategy("companion.comp", "companion", "usage.m1", ">=", 1, "HIGH", problem_class="tool_output"),
    ]
    profile = nest({"usage.m1": leaf(5)})
    result = adv.advise(profile, {}, strategies)
    t = result["tournaments"][0]
    assert t["winner"]["id"] == "output.native", t["winner"]
    assert t["also_considered"][0]["id"] == "companion.comp"
    assert t["also_considered"][0]["why_lost"] == "(detect only, never a fix)", t["also_considered"][0]


def test_tournament_missing_signal_renders_no_data_reason():
    # A candidate whose own trigger metric is absent from the profile: its
    # loss is reported as NO DATA, never a guessed comparison.
    strategies = [
        strategy("cache.fired", "cache", "usage.m1", ">=", 1, "HIGH", problem_class="cache_health"),
        strategy("routing.no-signal", "routing", "usage.missing", ">=", 1, "MED",
                  problem_class="cache_health"),
    ]
    profile = nest({"usage.m1": leaf(5)})
    result = adv.advise(profile, {}, strategies)
    t = result["tournaments"][0]
    assert t["winner"]["id"] == "cache.fired"
    loser = t["also_considered"][0]
    assert loser["id"] == "routing.no-signal"
    assert loser["fit"] == "NO DATA", loser["fit"]
    assert loser["why_lost"].startswith("NO DATA:"), loser["why_lost"]
    assert "missing" in loser["why_lost"], loser["why_lost"]


def test_tournament_skips_single_candidate_problem_classes():
    strategies = [strategy("cache.solo", "cache", "usage.m1", ">=", 1, "HIGH",
                            problem_class="cache_health")]
    profile = nest({"usage.m1": leaf(5)})
    result = adv.advise(profile, {}, strategies)
    assert result["tournaments"] == []


def test_real_strategies_json_carries_a_problem_class_and_tournaments():
    real = adv.load_strategies(STRATEGIES_PATH)
    for s in real:
        assert s.get("problem_class"), s["id"]
    profile = nest({"behavior.model_switch_session_share": leaf(0.5)})
    result = adv.advise(profile, {}, real)
    classes = {t["problem_class"] for t in result["tournaments"]}
    assert "cache_health" in classes, classes
    cache_health = next(t for t in result["tournaments"] if t["problem_class"] == "cache_health")
    assert cache_health["winner"]["id"] == "cache.fixed-parent-model"
    assert any(l["id"] == "routing.subagent-not-switch" for l in cache_health["also_considered"])

    printed = io.StringIO()
    import contextlib
    with contextlib.redirect_stdout(printed):
        adv._print_tournaments(result["tournaments"])
    out = printed.getvalue()
    assert "also considered" in out and "cache_health" in out, out


def test_tournament_winner_is_seeded_from_best_even_when_it_would_otherwise_lose():
    # Calibrated (finding C1): before build_tournaments accepted a
    # `best_id` to seed the winner, this exact profile produced a
    # contradiction: result["best"] names cache.a (advise()'s own
    # band-then-category ranking), but the "p" tournament, ranked purely on
    # fit and quality_risk within its own class, crowned memory.b instead
    # (memory.b's LOW quality_risk beats cache.a's HIGH), with no
    # reconciliation between the two in the rendered text. Fixed, the class
    # containing best's own strategy always crowns that exact strategy.
    strategies = [
        strategy("cache.a", "cache", "usage.m1", ">=", 1, "HIGH", problem_class="p", quality_risk="HIGH"),
        strategy("memory.b", "memory", "usage.m2", ">=", 1, "HIGH", problem_class="p", quality_risk="LOW"),
    ]
    profile = nest({"usage.m1": leaf(5), "usage.m2": leaf(5)})
    result = adv.advise(profile, {}, strategies)
    assert result["best"]["id"] == "cache.a", result["best"]
    t = next(t for t in result["tournaments"] if t["problem_class"] == "p")
    assert t["winner"]["id"] == "cache.a", t["winner"]
    assert t["also_considered"][0]["id"] == "memory.b"
    # The seeded case never claims a false comparative reason (memory.b, not
    # cache.a, is the one with lower quality risk here).
    assert "quality risk" not in t["why_won"], t["why_won"]


def test_tournament_never_crowns_a_detect_only_companion_even_when_it_alone_fired():
    # Calibrated (finding C2/M2): the "detect and measure only, never a
    # recommended fix" companion.token-saver used to win the tool_output
    # tournament outright whenever it was the only member of its class with
    # a real signal, exactly mirroring test_token_saver_entry_can_never_be_best's
    # profile but for result["tournaments"] instead of best/queue. Fixed,
    # the same exclusion applies: a companion is never the winner, and the
    # native did-not-trigger candidates are the only eligible winners, so
    # this class renders nothing (neither native ever really fired either).
    real = adv.load_strategies(STRATEGIES_PATH)
    profile = nest({"usage.output_tokens_total": leaf(250_000)})
    result = adv.advise(profile, {}, real)
    for t in result["tournaments"]:
        assert t["winner"]["id"] != "companion.token-saver", t
        for loser in t["also_considered"]:
            if loser["id"] == "companion.token-saver":
                assert loser["why_lost"] == "(detect only, never a fix)", loser


def test_all_no_data_problem_class_renders_no_tournament():
    # The orchestrator's p1_nodata probe: usage.output_tokens_total is
    # explicitly NO DATA, so every tool_output candidate (all three share
    # that one metric) is NO DATA. Before the real-native-signal gate, this
    # rendered a "winner" anyway, printed as "ranked first only by the
    # stable id tiebreak" even when the sort actually used qr_rank; fixed,
    # a class with nothing real anywhere is left out of the report.
    real = adv.load_strategies(STRATEGIES_PATH)
    profile = nest({"usage.output_tokens_total": leaf(None, label="NO DATA")})
    result = adv.advise(profile, {}, real)
    classes = {t["problem_class"] for t in result["tournaments"]}
    assert "tool_output" not in classes, classes


def test_load_strategies_rejects_a_bad_problem_class_value():
    # The orchestrator's p2_typo probe, case A and C: load_strategies must
    # refuse a mistyped or null problem_class by the exact strategy id, the
    # same way it already refuses a bad trigger op or band. Before this
    # check, a typo silently formed its own one-member group (excluded from
    # every tournament with no error) and a null value was skipped the same
    # way (`if not pc: continue` in build_tournaments); the strategy just
    # vanished from the report with nothing telling anyone why.
    import tempfile
    real = adv.load_strategies(STRATEGIES_PATH)

    with tempfile.TemporaryDirectory() as d:
        broken = json.loads(json.dumps({"schema": 2, "strategies": real}))
        broken["strategies"][0]["problem_class"] = "tool_ouput"
        path = os.path.join(d, "strategies.json")
        with open(path, "w") as f:
            json.dump(broken, f)
        try:
            adv.load_strategies(path)
            assert False, "expected a ValueError for a mistyped problem_class"
        except ValueError as e:
            assert broken["strategies"][0]["id"] in str(e), str(e)
            assert "problem_class" in str(e), str(e)

    with tempfile.TemporaryDirectory() as d:
        broken2 = json.loads(json.dumps({"schema": 2, "strategies": real}))
        broken2["strategies"][0]["problem_class"] = None
        path = os.path.join(d, "strategies.json")
        with open(path, "w") as f:
            json.dump(broken2, f)
        try:
            adv.load_strategies(path)
            assert False, "expected a ValueError for a null problem_class"
        except ValueError as e:
            assert broken2["strategies"][0]["id"] in str(e), str(e)


def test_deciding_criterion_always_names_the_first_differing_tuple_field():
    # Finding M1: why_won/why_lost must always derive from the first field
    # of _tournament_key's own tuple that actually differs between the two
    # candidates, never a hardcoded guess (the old bug: an all-NO-DATA
    # winner was always described as "ranked first only by the stable id
    # tiebreak" even when qr_rank was the real decider). Three constructed
    # pairs, each differing on a different tuple field, prove the mapping.
    cand_a = adv._tournament_candidate(
        strategy("cache.a", "cache", "usage.m", ">=", 1, "HIGH", problem_class="p"),
        nest({"usage.m": leaf(5)}))
    cand_b_lower_fit = adv._tournament_candidate(
        strategy("cache.b", "cache", "usage.m", ">=", 1, "MED", problem_class="p"),
        nest({"usage.m": leaf(5)}))
    reason = adv._deciding_criterion(cand_a, cand_b_lower_fit)
    assert "HIGH" in reason and "MED" in reason, reason

    cand_c_worse_risk = adv._tournament_candidate(
        strategy("cache.c", "cache", "usage.m", ">=", 1, "HIGH", problem_class="p", quality_risk="MED"),
        nest({"usage.m": leaf(5)}))
    reason2 = adv._deciding_criterion(cand_a, cand_c_worse_risk)
    assert "quality risk" in reason2, reason2

    cand_d_same_everything_higher_id = adv._tournament_candidate(
        strategy("cache.z", "cache", "usage.m", ">=", 1, "HIGH", problem_class="p"),
        nest({"usage.m": leaf(5)}))
    reason3 = adv._deciding_criterion(cand_a, cand_d_same_everything_higher_id)
    assert "cache.a" in reason3 and "cache.z" in reason3 and "tiebreak" in reason3, reason3


def test_main_mode_narrows_tournament_field_and_notes_it():
    # Finding m1: --mode silently narrowed the tournament's candidate field
    # with no note. Fixed, the printed header names the mode and the exact
    # count narrowed away, so the omission is never silent.
    import contextlib
    import tempfile
    profile = nest({"behavior.model_switch_session_share": leaf(0.5)})
    with tempfile.TemporaryDirectory() as d:
        profile_path = os.path.join(d, "profile.json")
        with open(profile_path, "w") as f:
            json.dump(profile, f)
        treatments_path = os.path.join(d, "treatments.json")
        real_profile_path, real_treatments_path = adv.PROFILE_PATH, adv.TREATMENTS_PATH
        adv.PROFILE_PATH, adv.TREATMENTS_PATH = profile_path, treatments_path
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = adv.main(["--mode", "conservative"])
            out = buf.getvalue()
        finally:
            adv.PROFILE_PATH, adv.TREATMENTS_PATH = real_profile_path, real_treatments_path
    assert rc == 0
    real = adv.load_strategies()
    n = len(adv.mode_strategies(real, "conservative"))
    m = len(real)
    assert n < m, (n, m)  # conservative must actually narrow this fixture, or the test proves nothing
    assert f"field narrowed by mode conservative: {n} of {m} candidates" in out, out


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
