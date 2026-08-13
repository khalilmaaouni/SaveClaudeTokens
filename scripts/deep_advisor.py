#!/usr/bin/env python3
"""
deep_advisor.py: the deep advisor.

Runs ON FABLE, pinned: a ratified product decision, not a default this
module may change. It runs ON DEMAND only (`cli.py advise --deep`), never
automatically, and only when the deterministic Quick Advisor (advisor.py)
could not decide; deterministic first is house law, so the cheap mechanical
check always runs before a model is asked to judge. It JUDGES, never
EXECUTES: it selects exactly one treatment id from data/strategies.json and
nothing else, never an install command, a changed label, or a file write. A
selection naming anything outside the registry is REFUSED with the reason
printed. "No confident choice" is a correct, expected answer: it is never
replaced by a guess, a default, or a second-best pick.

MODEL SEAM
The model call is injected: model_call(prompt) -> {"text", "input_tokens",
"output_tokens"}. Tests always pass a fake callable; this module never
makes a live call itself. live_fable_call, the real default, is a
placeholder the orchestrator replaces with its own callable to run the one
pre-authorized Fable invocation; calling the default directly is a
build-time mistake, so it raises rather than reaching for a network this
repo does not otherwise touch.

COST
Its cost (input plus output tokens spent on the call) is always printed,
and net_tokens is always the cost, negated: nothing here invents a numeric
benefit figure to net the spend against, so the cost is subtracted, never
folded in as if it were free or added as if it were more saving.

USAGE
  python3 deep_advisor.py
"""

import json
import os
import sys

import advisor as adv

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PROMPT_PATH = os.path.join(HERE, "..", "skills", "token-shield", "deep-advisor-prompt.md")

NO_CHOICE = "no confident choice"


def live_fable_call(prompt):
    """Placeholder seam, not a live integration. The orchestrator injects its
    own model_call callable to run the one pre-authorized, pinned Fable
    invocation; this module never calls a model on its own.
    """
    raise NotImplementedError(
        "live_fable_call is a placeholder seam; the orchestrator must inject "
        "its own model_call callable to run the pinned Fable invocation."
    )


def build_prompt(profile, strategies, prompt_path=DEFAULT_PROMPT_PATH):
    """The deep advisor's prompt: fixed instructions from prompt_path, plus
    the exact registry ids it may choose from and the profile it is judging,
    so the model never guesses at either.
    """
    with open(prompt_path) as f:
        instructions = f.read()
    ids = sorted(s["id"] for s in strategies)
    return (
        instructions
        + "\n\nRegistry ids you may choose from:\n"
        + "\n".join(f"- {i}" for i in ids)
        + "\n\nProfile under review:\n"
        + json.dumps(profile, indent=2)
    )


def deep_advise(profile, treatments=None, strategies=None, model_call=live_fable_call,
                 prompt_path=DEFAULT_PROMPT_PATH):
    """Deterministic-first: runs advisor.advise() and only calls model_call
    when it found nothing (do_nothing is True), the "deterministic rules
    cannot decide" state. Never raises on a bad model response: an
    unrecognized answer is REFUSED, and "no confident choice" is passed
    through as a real recommendation of nothing, never replaced by a guess.
    """
    if strategies is None:
        strategies = adv.load_strategies()
    deterministic = adv.advise(profile, treatments, strategies)

    if not deterministic["do_nothing"]:
        return {
            "ran_deep": False,
            "deterministic": deterministic,
            "selection": None,
            "refused_reason": None,
            "cost_tokens": 0,
            "net_tokens": 0,
            "message": "Deterministic rules already decided; the deep advisor did not run.",
        }

    prompt = build_prompt(profile, strategies, prompt_path)
    response = model_call(prompt)
    cost_tokens = int(response.get("input_tokens", 0)) + int(response.get("output_tokens", 0))
    text = (response.get("text") or "").strip()

    result = {
        "ran_deep": True,
        "deterministic": deterministic,
        "selection": None,
        "refused_reason": None,
        "cost_tokens": cost_tokens,
        # No numeric benefit figure is invented to net the spend against, so
        # the cost is always subtracted here, never added or dropped.
        "net_tokens": -cost_tokens,
        "message": None,
    }

    if text.lower() == NO_CHOICE:
        result["message"] = "The deep advisor found no confident choice; recommending nothing."
        return result

    valid_ids = {s["id"] for s in strategies}
    if text not in valid_ids:
        result["refused_reason"] = (
            f"deep advisor returned {text!r}, which is not a registry id in "
            "data/strategies.json; refused rather than executed."
        )
        return result

    strategy = next(s for s in strategies if s["id"] == text)
    result["selection"] = strategy
    result["message"] = f"Deep selection: {text}"
    return result


def _print_selection(strategy):
    print(f"[RECOMMENDED, deep] {strategy['title']}  (id: {strategy['id']})")
    print(f"  what it changes:     {strategy['what_it_changes']}")
    print(f"  expected benefit:    {strategy['expected_benefit']}")
    print(f"  evidence:            {strategy['evidence']}")
    print(f"  drawback:            {strategy['drawback']}")
    print(f"  quality risk:        {strategy['quality_risk']}")
    print(f"  reversibility:       {strategy['reversibility']}")
    print(f"  if you say no:       {strategy['if_you_say_no']}")
    print(f"  source:              {adv.format_source(strategy['source'])}")
    print(f"  requires confirmation: {strategy['requires_confirmation']}")
    print()


def print_result(result):
    """Print a deep_advise() result. Pure with respect to stdout only, no
    file I/O, so it is testable directly on a result dict.
    """
    if not result["ran_deep"]:
        det = result["deterministic"]
        print("Deterministic rules already decided; the deep advisor did not run.")
        if det["do_nothing"]:
            print(det["message"])
        else:
            print(f"Best: {det['best']['title']}  (id: {det['best']['id']})")
        print("Deep advisor cost: 0 tokens (not invoked)")
        return

    if result["refused_reason"]:
        print(f"REFUSED: {result['refused_reason']}")
    elif result["selection"]:
        _print_selection(result["selection"])
    else:
        print(result["message"])

    print(f"Deep advisor cost: {result['cost_tokens']:,} tokens (Fable, pinned)")
    print(f"Net tokens after cost (subtracted, never inflated): {result['net_tokens']:,}")


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    if not os.path.exists(adv.PROFILE_PATH):
        print("NO DATA: run profile.py first")
        return 2
    try:
        with open(adv.PROFILE_PATH) as f:
            profile = json.load(f)
    except json.JSONDecodeError as e:
        print(f"NO DATA: {adv.PROFILE_PATH} is corrupt ({e})")
        return 2

    strategies = adv.load_strategies()
    treatments = adv.load_treatments()
    print("=== Token Shield: Deep Advisor ===")
    result = deep_advise(profile, treatments, strategies)
    print_result(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
