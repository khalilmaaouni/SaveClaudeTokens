#!/usr/bin/env python3
"""Self-check for deep_advisor.py. No framework, no fixtures beyond the
small ones built inline below. Never makes a live model call: every test
passes a fake model_call callable.

    python3 scripts/test_deep_advisor.py

Calibrated tests (defect reinjected during development, confirmed red, then
fixed and confirmed green again): the deep path must not run when the
deterministic advisor already decided; an unknown registry id is refused,
never executed; "no confident choice" yields no recommendation, never a
substituted guess; the deep advisor's own cost is subtracted, never added.
"""

import contextlib
import io
import os

import advisor as adv
import deep_advisor as da

HERE = os.path.dirname(os.path.abspath(__file__))
STRATEGIES_PATH = os.path.join(HERE, "..", "data", "strategies.json")


def leaf(value, label="MEASURED", basis="test basis"):
    return {"value": value, "label": label, "basis": basis}


def nest(flat):
    profile = {}
    for dotted, val in flat.items():
        node = profile
        parts = dotted.split(".")
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = val
    return profile


def _healthy_profile():
    """Fires no strategy trigger (same fixture as test_advisor.py's
    do_nothing case), so advisor.advise() returns do_nothing True and the
    deep path is reachable.
    """
    return nest({
        "behavior.model_switch_session_share": leaf(0.0),
        "behavior.idle_gap_shares": leaf(0.0),
        "instruction.startup_floor_share": leaf(0.05),
        "instruction.claude_md_user_bytes": leaf(500),
        "instruction.claude_md_project_bytes": leaf(500),
        "usage.cache_hit_ratio_median": leaf(0.95),
        "usage.output_tokens_total": leaf(1000),
        "environment.plugin_count": leaf(1),
    })


def _fake_model(text, input_tokens=100, output_tokens=50):
    """A model_call stand-in. Records every prompt it was called with, so a
    test can assert it was never invoked, without any network access.
    """
    calls = []

    def call(prompt):
        calls.append(prompt)
        return {"text": text, "input_tokens": input_tokens, "output_tokens": output_tokens}

    call.calls = calls
    return call


def test_valid_registry_id_yields_that_treatment():
    # "companion.caveman" is deliberately not the first entry in
    # strategies.json, so a defect that ignores the model's actual answer
    # and always picks the first registry entry cannot pass this by luck.
    real = adv.load_strategies(STRATEGIES_PATH)
    profile = _healthy_profile()
    model = _fake_model("companion.caveman")
    result = da.deep_advise(profile, {}, real, model_call=model)
    assert result["ran_deep"] is True
    assert result["refused_reason"] is None, result["refused_reason"]
    assert result["selection"] is not None
    assert result["selection"]["id"] == "companion.caveman", result["selection"]


def test_unknown_id_is_refused_with_reason_printed():
    real = adv.load_strategies(STRATEGIES_PATH)
    profile = _healthy_profile()
    model = _fake_model("not.a.real.strategy")
    result = da.deep_advise(profile, {}, real, model_call=model)
    assert result["selection"] is None, result["selection"]
    assert result["refused_reason"] is not None
    assert "not.a.real.strategy" in result["refused_reason"]

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        da.print_result(result)
    out = buf.getvalue()
    assert "REFUSED" in out, out
    assert "not.a.real.strategy" in out, out


def test_no_confident_choice_produces_no_recommendation():
    real = adv.load_strategies(STRATEGIES_PATH)
    profile = _healthy_profile()
    model = _fake_model(da.NO_CHOICE)
    result = da.deep_advise(profile, {}, real, model_call=model)
    assert result["selection"] is None, result["selection"]
    assert result["refused_reason"] is None, result["refused_reason"]
    assert "no confident choice" in result["message"].lower(), result["message"]


def test_deep_path_does_not_run_when_deterministic_decides():
    # This profile fires cache.fixed-parent-model at HIGH band, so the
    # deterministic rules can decide; the deep path, including the model
    # call, must never run, even though a model_call is supplied.
    real = adv.load_strategies(STRATEGIES_PATH)
    profile = nest({"behavior.model_switch_session_share": leaf(0.5)})
    model = _fake_model("companion.caveman")
    result = da.deep_advise(profile, {}, real, model_call=model)
    assert result["ran_deep"] is False, result
    assert model.calls == [], "model_call must not be invoked when the deterministic advisor decided"
    assert result["cost_tokens"] == 0, result["cost_tokens"]
    assert result["deterministic"]["best"]["id"] == "cache.fixed-parent-model"


def test_cost_is_printed_and_subtracted_never_added():
    real = adv.load_strategies(STRATEGIES_PATH)
    profile = _healthy_profile()
    model = _fake_model("companion.caveman", input_tokens=1000, output_tokens=200)
    result = da.deep_advise(profile, {}, real, model_call=model)
    assert result["cost_tokens"] == 1200, result["cost_tokens"]
    assert result["net_tokens"] == -1200, (
        "cost must be subtracted, never added, even with no numeric benefit figure "
        f"to net it against: got {result['net_tokens']}"
    )

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        da.print_result(result)
    out = buf.getvalue()
    assert "1,200" in out, out
    assert "-1,200" in out, out


def test_advise_without_deep_flag_is_unchanged():
    import cli
    import subprocess as sp

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)

        class R:
            returncode = 0
        return R()

    orig = sp.run
    sp.run = fake_run
    try:
        rc = cli.main(["advise"])
    finally:
        sp.run = orig

    assert rc == 0, rc
    assert len(calls) == 1, calls
    assert calls[0][1].endswith("advisor.py"), calls[0]
    assert "--deep" not in calls[0], calls[0]


def test_advise_deep_flag_routes_to_deep_advisor_and_strips_the_flag():
    import cli
    import subprocess as sp

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)

        class R:
            returncode = 0
        return R()

    orig = sp.run
    sp.run = fake_run
    try:
        rc = cli.main(["advise", "--deep"])
    finally:
        sp.run = orig

    assert rc == 0, rc
    assert len(calls) == 1, calls
    assert calls[0][1].endswith("deep_advisor.py"), calls[0]
    assert "--deep" not in calls[0], calls[0]


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
