#!/usr/bin/env python3
"""
advisor.py: the Quick Advisor. Deterministic rules over a usage profile,
ranked cards with full drawback disclosure, treatment memory, and "do
nothing" as a valid, celebrated output.

No model calls anywhere. Every card is a lookup into data/strategies.json
plus a comparison against the profile dict profile.py produces; nothing
here is generated or inferred by a model. advisor_cost_tokens is always 0,
and main() prints that fact so the honesty is not just in the code.

PROFILE CONTRACT
The profile is a dict of dotted keys, each key's LEAF a
{"value":..., "label": MEASURED|SIGNAL|INFERRED|"NO DATA", "basis": str}
dict. This module never imports profile.py: it reads the dict shape only,
so a missing key or a "NO DATA" label means the trigger cannot fire, never
a crash. See STRATEGY_KEYS below for the exact contract this file assumes.

LABELS, KEPT SEPARATE ON PURPOSE
A profile leaf's label (MEASURED/SIGNAL/INFERRED/NO DATA) says how sure we
are about the USER'S NUMBER. A card's evidence field
(MEASURED/ESTIMATED/VERIFIED/NATIVE) says how sure we are about the CLAIM
the card makes. RECOMMENDED is never an evidence value; it only ever
appears in a card's "rank" field, assigned here at selection time.

TREATMENT MEMORY
~/.token-shield/treatments.json remembers what you did with a card. A
rejected or suppressed strategy is filtered out of consideration until its
until date passes; an accepted one is stamped with a lineage label so a
later experiment can cite the card that caused it.

USAGE
  python3 advisor.py
"""

import json
import os
import shutil
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_STRATEGIES = os.path.join(HERE, "..", "data", "strategies.json")
TREATMENTS_PATH = os.path.expanduser("~/.token-shield/treatments.json")
PROFILE_PATH = os.path.expanduser("~/.token-shield/profile.json")

EVIDENCE_LABELS = {"MEASURED", "ESTIMATED", "VERIFIED", "NATIVE"}
PROFILE_LABELS = {"MEASURED", "SIGNAL", "INFERRED", "NO DATA"}
BANDS = {"HIGH": 3, "MED": 2, "LOW": 1}
OPS = {">=", "<=", "=="}
DECISIONS = {"accepted", "rejected", "suppressed"}

# Ratified priority order: cache rebuilds > startup floor > output >
# redundancy > boundaries > routing > memory > verbosity > overbuild >
# companion. An unlisted category (should never happen once strategies.json
# validates) sorts last rather than crashing the ranker.
CATEGORY_PRIORITY = ["cache", "startup", "output", "redundancy", "boundaries",
                     "routing", "memory", "verbosity", "overbuild", "companion"]

REQUIRED_FIELDS = ["id", "category", "title", "trigger", "what_it_changes",
                   "expected_benefit", "evidence", "drawback", "quality_risk",
                   "reversibility", "how_measured", "if_you_say_no",
                   "alternatives", "companion", "requires_confirmation", "source"]
REQUIRED_TRIGGER_FIELDS = ["metric", "op", "value", "band"]


def load_strategies(path=DEFAULT_STRATEGIES):
    """Load and schema-validate data/strategies.json. Raises ValueError naming
    the exact missing or malformed field, rather than failing deep in advise().
    """
    with open(path) as f:
        doc = json.load(f)
    if "schema" not in doc or "strategies" not in doc:
        raise ValueError("strategies.json missing schema or strategies")
    strategies = doc["strategies"]
    seen_ids = set()
    for i, s in enumerate(strategies):
        sid = s.get("id", f"<entry {i}>")
        for field in REQUIRED_FIELDS:
            if field not in s:
                raise ValueError(f"strategy {sid}: missing required field {field!r}")
        if sid in seen_ids:
            raise ValueError(f"strategy {sid}: duplicate id")
        seen_ids.add(sid)
        trig = s["trigger"]
        if not isinstance(trig, dict):
            raise ValueError(f"strategy {sid}: trigger must be an object")
        for field in REQUIRED_TRIGGER_FIELDS:
            if field not in trig:
                raise ValueError(f"strategy {sid}: trigger missing field {field!r}")
        if trig["op"] not in OPS:
            raise ValueError(f"strategy {sid}: trigger op {trig['op']!r} not in {OPS}")
        if trig["band"] not in BANDS:
            raise ValueError(f"strategy {sid}: trigger band {trig['band']!r} not in {sorted(BANDS)}")
        esc = trig.get("escalate")
        if esc is not None:
            if "value" not in esc or "band" not in esc:
                raise ValueError(f"strategy {sid}: escalate missing value or band")
            if esc["band"] not in BANDS:
                raise ValueError(f"strategy {sid}: escalate band {esc['band']!r} not in {sorted(BANDS)}")
        if s["evidence"] not in EVIDENCE_LABELS:
            raise ValueError(f"strategy {sid}: evidence {s['evidence']!r} not in {sorted(EVIDENCE_LABELS)}")
        if not s.get("source"):
            raise ValueError(f"strategy {sid}: source must be non-empty")
    return strategies


def _get_leaf(profile, dotted_key):
    """Walk a dotted key into the profile dict. Returns the leaf dict, or None
    if any part of the path is missing or the leaf is not the expected shape.
    A path may continue past a {value,label} leaf into a composite value (for
    example behavior.idle_gap_shares.5m_to_15m); the component inherits the
    leaf's label. Never raises: a malformed profile is NO DATA, not a crash.
    """
    node = profile
    label = None
    for part in dotted_key.split("."):
        if isinstance(node, dict) and "value" in node and "label" in node and part not in node:
            label = node["label"]
            node = node["value"]
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    if isinstance(node, dict) and "value" in node and "label" in node:
        return node
    if label is not None:
        return {"value": node, "label": label, "basis": "component of " + dotted_key}
    return None


def _evaluate_trigger(profile, trigger):
    """Returns the fired band (str) if the trigger fires, False if it does not,
    or None if the metric could not be evaluated (missing key, NO DATA label,
    or a null value) -- the "insufficient" state.
    """
    leaf = _get_leaf(profile, trigger["metric"])
    if leaf is None or leaf.get("label") == "NO DATA" or leaf.get("value") is None:
        return None
    v = leaf["value"]
    op, tv = trigger["op"], trigger["value"]
    if isinstance(tv, (int, float)) and not isinstance(v, (int, float)):
        return None
    if op == ">=":
        hit = v >= tv
    elif op == "<=":
        hit = v <= tv
    else:
        hit = v == tv
    if not hit:
        return False
    band = trigger["band"]
    esc = trigger.get("escalate")
    if esc and op == ">=" and v >= esc["value"]:
        band = esc["band"]
    return band


def _fmt_value(v):
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, float) and 0.0 <= v <= 1.0:
        return f"{v:.0%}"
    if isinstance(v, (int, float)):
        return f"{v:,.0f}" if float(v).is_integer() else f"{v:,.2f}"
    return str(v)


def _why_selected(strategy, leaf, trigger):
    metric_name = trigger["metric"].split(".")[-1].replace("_", " ")
    basis = leaf.get("basis") or "no basis recorded"
    return (f"Your {metric_name} is {_fmt_value(leaf['value'])} ({basis}), "
            f"which meets this card's trigger ({trigger['op']} {_fmt_value(trigger['value'])}).")


def _card(strategy, rank, profile):
    leaf = _get_leaf(profile, strategy["trigger"]["metric"])
    return {
        "id": strategy["id"],
        "title": strategy["title"],
        "rank": rank,
        "what_it_changes": strategy["what_it_changes"],
        "why_selected": _why_selected(strategy, leaf, strategy["trigger"]),
        "expected_benefit": strategy["expected_benefit"],
        "evidence": strategy["evidence"],
        "drawback": strategy["drawback"],
        "quality_risk": strategy["quality_risk"],
        "reversibility": strategy["reversibility"],
        "how_measured": strategy["how_measured"],
        "if_you_say_no": strategy["if_you_say_no"],
        "source": strategy["source"],
        "requires_confirmation": strategy["requires_confirmation"],
    }


def _is_suppressed(strategy_id, treatments, now_iso):
    rec = (treatments or {}).get(strategy_id)
    if not rec:
        return False
    if rec.get("decision") not in ("rejected", "suppressed"):
        return False
    until = rec.get("until")
    return bool(until) and until > now_iso


def _sort_key(entry):
    _sid, strategy, band = entry
    try:
        cat_rank = CATEGORY_PRIORITY.index(strategy["category"])
    except ValueError:
        cat_rank = len(CATEGORY_PRIORITY)
    return (-BANDS[band], cat_rank)


def advise(profile, treatments=None, strategies=None):
    """Deterministic advice from a profile. Pure function: no file I/O, no
    clock reads except the ISO string used to compare treatment expiry
    against, so it stays directly testable with synthetic profiles.
    """
    if strategies is None:
        strategies = load_strategies()
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%S")

    insufficient = []
    main_fired = []
    companion_fired = []
    for s in strategies:
        if _is_suppressed(s["id"], treatments, now_iso):
            continue
        band = _evaluate_trigger(profile, s["trigger"])
        if band is None:
            insufficient.append(s["id"])
            continue
        if band is False:
            continue
        entry = (s["id"], s, band)
        if s["category"] == "companion":
            companion_fired.append(entry)
        else:
            main_fired.append(entry)

    main_fired.sort(key=_sort_key)
    companion_fired.sort(key=_sort_key)

    best_card = None
    alt_cards = []
    if main_fired:
        best_card = _card(main_fired[0][1], "RECOMMENDED", profile)
        alt_cards = [_card(s, "ALTERNATIVE", profile) for _sid, s, _b in main_fired[1:3]]

    companion_card = None
    if companion_fired:
        companion_card = _card(companion_fired[0][1], "COMPANION", profile)

    queue = ([best_card] if best_card else []) + alt_cards
    do_nothing = best_card is None

    result = {
        "best": best_card,
        "alternatives": alt_cards,
        "companion": companion_card,
        "queue": queue[:3],
        "do_nothing": do_nothing,
        "advisor_cost_tokens": 0,
        "insufficient": insufficient,
    }
    if do_nothing:
        hit = _get_leaf(profile, "usage.cache_hit_ratio_median")
        share = _get_leaf(profile, "instruction.startup_floor_share")
        hit_txt = _fmt_value(hit["value"]) if hit and hit.get("value") is not None else "NO DATA"
        share_txt = _fmt_value(share["value"]) if share and share.get("value") is not None else "NO DATA"
        result["message"] = (
            "Nothing crossed a trigger threshold, so this profile looks healthy right now. "
            f"Your two strongest metrics: cache hit ratio {hit_txt}, startup floor share {share_txt}."
        )
    return result


def load_treatments(path=TREATMENTS_PATH):
    """Load the treatment memory dict {strategy_id: decision record}. A
    corrupt file is backed up with a timestamp suffix and replaced with an
    empty store; this never raises, so a bad file can't take the advisor down.
    """
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("treatments.json root must be an object")
        return data
    except (json.JSONDecodeError, ValueError, OSError) as e:
        backup = f"{path}.corrupt-{time.strftime('%Y%m%dT%H%M%S')}"
        try:
            shutil.copy(path, backup)
        except OSError:
            backup = None
        print(f"note: {path} was corrupt ({e}); backed up to {backup}; starting fresh")
        return {}


def record_decision(strategy_id, decision, days=90, note="", path=TREATMENTS_PATH):
    """Record a decision on a card. rejected/suppressed carry an expiry
    `days` out; accepted carries a lineage label instead, for a later
    experiment to cite as the card that caused it.
    """
    if decision not in DECISIONS:
        raise ValueError(f"decision {decision!r} not in {sorted(DECISIONS)}")
    treatments = load_treatments(path)
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    rec = {"decision": decision, "at": now, "note": note}
    if decision == "accepted":
        rec["lineage"] = f"{strategy_id}-{time.strftime('%Y%m%d')}"
    else:
        until_epoch = time.time() + days * 86400
        rec["until"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(until_epoch))
        rec["days"] = days
    treatments[strategy_id] = rec
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(treatments, f, indent=2)
    return rec


def _print_card(card):
    print(f"[{card['rank']}] {card['title']}  (id: {card['id']})")
    print(f"  what it changes:     {card['what_it_changes']}")
    print(f"  why selected:        {card['why_selected']}")
    print(f"  expected benefit:    {card['expected_benefit']}")
    print(f"  evidence:            {card['evidence']}")
    print(f"  drawback:            {card['drawback']}")
    print(f"  quality risk:        {card['quality_risk']}")
    print(f"  reversibility:       {card['reversibility']}")
    print(f"  how measured:        {card['how_measured']}")
    print(f"  if you say no:       {card['if_you_say_no']}")
    print(f"  source:              {card['source']}")
    print(f"  requires confirmation: {card['requires_confirmation']}")
    print()


def main():
    if not os.path.exists(PROFILE_PATH):
        print("NO DATA: run profile.py first")
        return 2
    try:
        with open(PROFILE_PATH) as f:
            profile = json.load(f)
    except json.JSONDecodeError as e:
        print(f"NO DATA: {PROFILE_PATH} is corrupt ({e})")
        return 2

    strategies = load_strategies()
    treatments = load_treatments()
    result = advise(profile, treatments, strategies)

    print("=== Token Shield: Quick Advisor ===")
    if result["do_nothing"]:
        print(result["message"])
    else:
        _print_card(result["best"])
        for c in result["alternatives"]:
            _print_card(c)
    if result["companion"]:
        print("--- companion ---")
        _print_card(result["companion"])
    if result["insufficient"]:
        print(f"NO DATA on {len(result['insufficient'])} strategy trigger(s): "
              + ", ".join(result["insufficient"]))
    print("Advisor cost: 0 tokens (deterministic)")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
