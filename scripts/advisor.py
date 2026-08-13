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

CAPABILITY-OWNERSHIP SUPPRESSION
A strategy's own "companion" field names the companion plugin that already
owns its capability, when one does. sync_companion_suppressions() writes a
"suppressed" treatment record (reason "companion") for such a strategy the
first time its named companion is seen active, reusing the exact treatments
store above rather than a second one, and stamps the metric value observed
at that moment. It writes AT MOST ONCE per strategy id, ever: any record
already on file for that id, sync's own or the user's, is left untouched,
whatever its decision or expiry. That single rule keeps a user's own choice
(including an accepted one with experiment lineage) safe from being
clobbered, and keeps a lapsed companion suppression from being silently
re-armed with a fresh window on the next run.

A companion suppression is not a permanent muzzle: advise() compares the
current metric reading against the value recorded when the suppression was
written, and if it has grown materially worse (REGRESSION_MARGIN below), the
card returns regardless of the still-open suppression window. A strategy
with no "companion" declared is never touched: NO DATA beats a guess.

USAGE
  python3 advisor.py
  python3 advisor.py --decide <strategy-id> <done|not-now|never>
"""

import calendar
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_STRATEGIES = os.path.join(HERE, "..", "data", "strategies.json")
TREATMENTS_PATH = os.path.expanduser("~/.token-shield/treatments.json")
PROFILE_PATH = os.path.expanduser("~/.token-shield/profile.json")
# discover_companions.py's cached state: {"checked_at": "...Z", "discovered":
# [{"name","enabled",...}], "registry_match": {name: "curated"|"mention"|
# "unknown"}}. Read here, never written here; discovery stays that module's
# job.
COMPANIONS_STATE_PATH = os.path.expanduser("~/.token-shield/companions_state.json")

EVIDENCE_LABELS = {"MEASURED", "ESTIMATED", "VERIFIED", "NATIVE"}
PROFILE_LABELS = {"MEASURED", "SIGNAL", "INFERRED", "NO DATA"}
BANDS = {"HIGH": 3, "MED": 2, "LOW": 1}
OPS = {">=", "<=", "=="}
DECISIONS = {"accepted", "rejected", "suppressed"}

# The plain-word choices offered on a dashboard chip or in the /advisor
# command, mapped onto the decision vocabulary treatment memory already
# understands. No new decision strings are ever invented past DECISIONS.
DECIDE_CHOICES = {"done": "accepted", "not-now": "suppressed", "never": "rejected"}
# "not-now" quiets a card for 90 days; "never" uses the same "rejected"
# decision but far out, so it does not resurface on its own.
DECIDE_DAYS = {"not-now": 90, "never": 36500}

# A companion-ownership suppression gets the same quiet window as a plain
# "not-now": long enough to stop nagging, short enough that the record's
# own expiry is a real, reachable event rather than a formality.
COMPANION_SUPPRESSION_DAYS = 90

# How much worse the current metric reading has to be than the value
# recorded when a companion suppression was written before the card returns
# anyway. 0.5 (50% worse) was chosen over the old "always show on HIGH band"
# rule: enumerating data/strategies.json showed only 2 of 13 strategies can
# ever reach HIGH, so that rule was nearly a no-op. A flat 50% swing is well
# above the run-to-run noise these usage ratios and counts show in practice,
# so it will not flap on an ordinary day, but it is reachable by a genuine
# regression, not just an astronomical one.
REGRESSION_MARGIN = 0.5

# discover_companions.py only runs on demand, never from a hook, so its
# cached state can go stale the moment a companion plugin is uninstalled and
# discovery is never rerun again. 30 days is comfortably longer than
# doctor.py's own 1-day auto-refresh window (STATE_FRESHNESS_SECONDS in
# doctor.py), so a state doctor.py just refreshed is never treated as stale
# here, but far short of the 90-day companion suppression window itself, so
# a suppression this module wrote can never outlive the evidence that
# justified it.
STALE_COMPANION_STATE_DAYS = 30

DASHES = ("\u2013", "\u2014")  # en dash, em dash: never allowed in any strategy text

# Ratified priority order: cache rebuilds > startup floor > output >
# redundancy > boundaries > routing > memory > verbosity > overbuild >
# companion. An unlisted category (should never happen once strategies.json
# validates) sorts last rather than crashing the ranker.
CATEGORY_PRIORITY = ["cache", "startup", "output", "redundancy", "boundaries",
                     "routing", "memory", "verbosity", "overbuild", "companion"]

REQUIRED_FIELDS = ["id", "category", "title", "trigger", "what_it_changes",
                   "expected_benefit", "evidence", "drawback", "quality_risk",
                   "reversibility", "how_measured", "if_you_say_no",
                   "alternatives", "companion", "requires_confirmation", "source",
                   "how"]
REQUIRED_TRIGGER_FIELDS = ["metric", "op", "value", "band"]


def _has_dash(text):
    return any(d in text for d in DASHES)


def _validate_how(sid, how):
    """A strategy's "how" is a concrete, copy-pasteable action list: 2 to 5
    steps, each carrying non-empty text and an optional command. Never a
    literal em or en dash, same rule as every other user-facing field.
    """
    if not isinstance(how, list) or not (2 <= len(how) <= 5):
        raise ValueError(f"strategy {sid}: how must be a list of 2 to 5 steps")
    for j, step in enumerate(how):
        if not isinstance(step, dict) or not step.get("text"):
            raise ValueError(f"strategy {sid}: how step {j} missing non-empty text")
        if _has_dash(step["text"]):
            raise ValueError(f"strategy {sid}: how step {j} text carries an em or en dash")
        command = step.get("command")
        if command is not None and _has_dash(command):
            raise ValueError(f"strategy {sid}: how step {j} command carries an em or en dash")


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
        _validate_how(sid, s["how"])
    return strategies


CLAIMS_DOC = "docs/CLAIMS.md"


def _is_claim_code(text):
    """A docs/CLAIMS.md row id: one letter then digits, such as A6 or D10."""
    return len(text) >= 2 and text[0].isalpha() and text[1:].isdigit()


def _source_claim_codes(source):
    """Every claim code (A6, D5, ...) a strategy's `source` field names.
    These are row ids in docs/CLAIMS.md and, not by accident, the same ids
    data/facts.json uses: a strategy sourced "A4, A6" is citing exactly the
    facts an id-keyed fact registry would call A4 and A6. Returns [] when
    source is not shaped as claim codes (a URL, free text, empty), which
    format_source and the stale-fact check below both read as "no facts to
    check against"."""
    if not source:
        return []
    codes = [c.strip() for c in str(source).strip().split(",") if c.strip()]
    if not codes or not all(_is_claim_code(c) for c in codes):
        return []
    return codes


def format_source(source):
    """Render a strategy's `source` as something a reader can go and check.

    strategies.json stores claim codes (A6, D5, "A3, A4"), which are row ids
    in the tables of docs/CLAIMS.md. Printed bare they are opaque: the reader
    cannot tell what A6 is or where to look it up, which is what made 12 of
    the 13 shipped sources uncitable. Only the exact code shape is rewritten,
    so a URL source, or any other free text, passes through untouched rather
    than being dressed up as a row id that does not exist.
    """
    if not source:
        return source
    text = str(source).strip()
    codes = _source_claim_codes(source)
    if not codes:
        return text
    word = "row" if len(codes) == 1 else "rows"
    return f"{CLAIMS_DOC} {word} {', '.join(codes)}"


def _load_facts_by_id():
    """data/facts.json indexed by id, via doctor.py's own loader, the only
    fact loader in this repo (this module never re-implements it). Imported
    locally, not at module top, so a plain `import advisor` never drags in
    doctor.py's own dependency chain (discover_companions, experiment,
    profile, token_shield) unless a card actually needs a staleness check.
    A missing or malformed registry degrades to an empty dict, same NO DATA
    posture as every other read in this file, never a crash."""
    import doctor
    facts, _refused, _error = doctor._load_facts()
    return {f["id"]: f for f in facts if f.get("id")}


def _stale_fact_lines(source, facts_by_id, today=None):
    """One "FACT STALE" line per claim code a strategy's source cites that
    is past its own review interval in data/facts.json, so a card built on
    an aging platform claim visibly carries that staleness to the reader
    instead of presenting it with the same confidence as a fresh one.
    Reuses doctor.py's own staleness rule (_is_fact_stale) rather than a
    second definition of "stale" here. A code with no matching fact, or a
    fact that is still fresh, contributes nothing."""
    if not facts_by_id:
        return []
    import doctor
    lines = []
    for code in _source_claim_codes(source):
        fact = facts_by_id.get(code)
        if fact is None or not doctor._is_fact_stale(fact, today):
            continue
        interval = fact.get("review_interval_days", doctor.DEFAULT_FACT_REVIEW_DAYS)
        lines.append(
            f"FACT STALE, verify before acting: {code} "
            f"(verified {fact.get('verified')}, review interval {interval} days)")
    return lines


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


def _card(strategy, rank, profile, facts_by_id, today=None):
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
        # Citable at the point every surface reads it (CLI, dashboard, report),
        # so no consumer has to know that A6 is a docs/CLAIMS.md row id.
        "source": format_source(strategy["source"]),
        # Carries the fact's own staleness to the reader when the platform
        # claim this card leans on has gone past its review interval.
        "stale_facts": _stale_fact_lines(strategy["source"], facts_by_id, today),
        "requires_confirmation": strategy["requires_confirmation"],
        "how": strategy.get("how", []),
    }


def _is_suppressed(strategy_id, treatments, now_iso):
    rec = (treatments or {}).get(strategy_id)
    if not rec:
        return False
    if rec.get("decision") not in ("rejected", "suppressed"):
        return False
    until = rec.get("until")
    return bool(until) and until > now_iso


def _regression_override(strategy, profile, rec):
    """True when the metric a companion suppression (reason "companion")
    covers has grown materially (REGRESSION_MARGIN) worse than the value
    recorded the moment that suppression was written, in the direction the
    strategy's own trigger op defines as worse: bigger for ">="/"==",
    smaller for "<=". A record with no recorded value, or a profile that
    cannot currently be read, never overrides: NO DATA beats a guess.
    """
    recorded = rec.get("metric_value_at_suppression")
    if not isinstance(recorded, (int, float)):
        return False
    leaf = _get_leaf(profile, strategy["trigger"]["metric"])
    if leaf is None or leaf.get("value") is None:
        return False
    current = leaf["value"]
    if not isinstance(current, (int, float)):
        return False
    if strategy["trigger"]["op"] == "<=":
        if recorded == 0:
            return current < 0
        return current <= recorded * (1 - REGRESSION_MARGIN)
    if recorded == 0:
        return current > 0
    return current >= recorded * (1 + REGRESSION_MARGIN)


def _sort_key(entry):
    _sid, strategy, band = entry
    try:
        cat_rank = CATEGORY_PRIORITY.index(strategy["category"])
    except ValueError:
        cat_rank = len(CATEGORY_PRIORITY)
    return (-BANDS[band], cat_rank)


def advise(profile, treatments=None, strategies=None, facts=None, today=None):
    """Deterministic advice from a profile. Pure function apart from two
    reads: the ISO string used to compare treatment expiry against, and (when
    `facts` is not supplied) data/facts.json via doctor.py's loader, so it
    stays directly testable with synthetic profiles and a synthetic facts
    list alike. `facts` is the same shape as data/facts.json's "facts" array;
    pass one, with `today`, to control staleness in a test without touching
    the real registry or the clock.
    """
    if strategies is None:
        strategies = load_strategies()
    facts_by_id = ({f["id"]: f for f in facts if f.get("id")}
                   if facts is not None else _load_facts_by_id())
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%S")

    insufficient = []
    main_fired = []
    companion_fired = []
    suppressed_by_companion = []
    for s in strategies:
        rec = (treatments or {}).get(s["id"])
        is_companion_rec = bool(rec) and rec.get("reason") == "companion"
        suppressed = _is_suppressed(s["id"], treatments, now_iso)
        band = _evaluate_trigger(profile, s["trigger"])

        if suppressed:
            if is_companion_rec and _regression_override(s, profile, rec):
                pass  # regression guard: worse than when suppressed, card returns
            else:
                if is_companion_rec and band not in (None, False):
                    suppressed_by_companion.append(s["id"])
                continue

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
        best_card = _card(main_fired[0][1], "RECOMMENDED", profile, facts_by_id, today)
        alt_cards = [_card(s, "ALTERNATIVE", profile, facts_by_id, today) for _sid, s, _b in main_fired[1:3]]

    companion_card = None
    if companion_fired:
        companion_card = _card(companion_fired[0][1], "COMPANION", profile, facts_by_id, today)

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
        "suppressed_by_companion": suppressed_by_companion,
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


def record_decision(strategy_id, decision, days=90, note="", reason=None, metric_value=None,
                     path=TREATMENTS_PATH):
    """Record a decision on a card. rejected/suppressed carry an expiry
    `days` out; accepted carries a lineage label instead, for a later
    experiment to cite as the card that caused it. `reason`, when given, is
    stamped onto the record so a later reader (advise()'s own suppression
    check) can tell this was not the user's own choice; the only reason this
    file writes today is "companion", from sync_companion_suppressions.
    `metric_value`, when given, is the profile reading observed at the
    moment of this decision, stamped as "metric_value_at_suppression" so
    advise()'s regression guard has a baseline to compare a later, worse
    reading against.
    """
    if decision not in DECISIONS:
        raise ValueError(f"decision {decision!r} not in {sorted(DECISIONS)}")
    treatments = load_treatments(path)
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    rec = {"decision": decision, "at": now, "note": note}
    if reason:
        rec["reason"] = reason
    if metric_value is not None:
        rec["metric_value_at_suppression"] = metric_value
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


def sync_companion_suppressions(strategies, active_companions, profile, days=COMPANION_SUPPRESSION_DAYS,
                                 path=TREATMENTS_PATH):
    """For every strategy whose own "companion" field names a companion in
    `active_companions`, write a "suppressed" treatment record (reason
    "companion") through record_decision, stamping the metric value observed
    right now so advise()'s regression guard has a baseline.

    Writes AT MOST ONCE per strategy id, ever: any record already on file
    for that id, whether sync wrote it earlier or the user did (including an
    "accepted" record carrying experiment lineage), is left completely
    untouched, no matter its decision or whether its window has already
    lapsed. That one rule is deliberate, not an oversight: a lapsed
    companion suppression must never be silently re-armed with a fresh
    window on the next run, or the card could never come back on its own,
    and a user's own choice is never sync's to overwrite.

    A strategy with no "companion" declared is left alone entirely (NO DATA
    beats a guess). So is a strategy whose trigger metric cannot be read
    right now: with no baseline value the regression guard could never fire,
    so suppressing would silence that card for the whole window with no way
    back. If the safety net cannot be armed, nothing is suppressed.

    Returns the list of strategy ids newly suppressed by this call.
    """
    active = set(active_companions or ())
    if not active:
        return []
    treatments = load_treatments(path)
    newly = []
    for s in strategies:
        owner = s.get("companion")
        if not owner or owner not in active:
            continue
        if s["id"] in treatments:
            continue
        leaf = _get_leaf(profile, s["trigger"]["metric"])
        metric_value = leaf["value"] if leaf and isinstance(leaf.get("value"), (int, float)) else None
        if metric_value is None:
            # The regression guard needs a baseline value to compare against
            # later. Without one it can never fire, so suppressing here would
            # silence this card for the whole window with no way back. If the
            # safety net cannot be armed, do not suppress at all.
            continue
        record_decision(s["id"], "suppressed", days=days,
                         note=f"companion {owner} already owns this capability",
                         reason="companion", metric_value=metric_value, path=path)
        newly.append(s["id"])
    return newly


def load_active_companions(path=COMPANIONS_STATE_PATH):
    """Companions treated as active for capability-ownership suppression:
    discover_companions.py's cached state, filtered to entries that are both
    enabled and registry-matched to "curated" (never a "mention" or
    "unknown" name, which could be an unvetted lookalike plugin). A state
    file older than STALE_COMPANION_STATE_DAYS is NO DATA: an uninstalled
    companion whose discovery was never rerun must not go on silencing
    advice forever.

    Mirrors load_treatments's guard pattern (an isinstance check on the
    loaded root, corrupt-file handling) rather than inventing a second one:
    a missing or malformed state file (a JSON root that is not an object, a
    bad or missing checked_at, a "discovered" that is not a list) is NO
    DATA, an empty set, never a crash.
    """
    if not os.path.exists(path):
        return set()
    try:
        with open(path) as f:
            state = json.load(f)
    except (json.JSONDecodeError, OSError):
        return set()
    if not isinstance(state, dict):
        return set()
    try:
        checked = time.strptime(state.get("checked_at"), "%Y-%m-%dT%H:%M:%SZ")
        age_days = (time.time() - calendar.timegm(checked)) / 86400
    except (TypeError, ValueError):
        return set()
    if age_days > STALE_COMPANION_STATE_DAYS:
        return set()
    discovered = state.get("discovered")
    if not isinstance(discovered, list):
        return set()
    match = state.get("registry_match")
    if not isinstance(match, dict):
        match = {}
    active = set()
    for d in discovered:
        if not isinstance(d, dict):
            continue
        name = d.get("name")
        if name and d.get("enabled") and match.get(name) == "curated":
            active.add(name)
    return active


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
    for line in card.get("stale_facts", []):
        print(f"  {line}")
    print(f"  requires confirmation: {card['requires_confirmation']}")
    print()


def cmd_decide(strategy_id, choice):
    """Handle `advisor.py --decide <strategy-id> <done|not-now|never>`. Maps
    the plain-word dashboard/CLI choice onto the existing accepted/rejected/
    suppressed vocabulary; no new decision string is ever invented.
    """
    if choice not in DECIDE_CHOICES:
        print(f"unknown decision {choice!r}; use one of {sorted(DECIDE_CHOICES)}")
        return 2
    decision = DECIDE_CHOICES[choice]
    days = DECIDE_DAYS.get(choice, 90)
    # TREATMENTS_PATH read live (not via record_decision's own default
    # argument, bound once at definition time) so a test can point it at a
    # temp file the same way it already does for PROFILE_PATH in main().
    rec = record_decision(strategy_id, decision, days=days, path=TREATMENTS_PATH)
    until = rec.get("until")
    tail = f"quiet until {until}" if until else f"lineage {rec.get('lineage')}"
    print(f"recorded: {strategy_id} -> {decision} ({tail})")
    return 0


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] == "--decide":
        if len(argv) != 3:
            print("usage: advisor.py --decide <strategy-id> <done|not-now|never>")
            return 2
        return cmd_decide(argv[1], argv[2])

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
    sync_companion_suppressions(strategies, load_active_companions(), profile)
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
    if result["suppressed_by_companion"]:
        print(f"suppressed {len(result['suppressed_by_companion'])} duplicate card(s): "
              "an installed, active companion already owns that capability")
    print("Advisor cost: 0 tokens (deterministic)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
