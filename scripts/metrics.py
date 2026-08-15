#!/usr/bin/env python3
"""
metrics.py: what this project COMPUTES, with nothing that renders.

Split out of token_shield, which was simultaneously the presentation layer,
a metrics module and a file loader, and which nine modules therefore had to
import to reach a number. That shape is the one every honesty defect in this
project traces back to: two surfaces onto one quantity, drifting apart with
nothing able to notice. Keeping the computation in one place below the
renderer means a second surface has to go THROUGH it rather than around it.

Layer 1. It may import the foundation and nothing above it. In particular it
never imports the renderer, and scripts/test_architecture.py refuses the
edit that would make it.

What belongs here: a function that reads counters or ledger records and
returns a number, a verdict, or a structure. What does not: anything that
emits HTML, chooses a colour, or writes a sentence for a person to read.
"""

import importlib.util
import json
import os

import formatting as fmt


CACHE_READ = 0.1  # a cached token bills at 0.1x, so the saving is (1 - 0.1)

# Default experiment labels the marginal attribution waterfall chains: the
# user runs `experiment start "core"` / `end "core"` around a Token Shield
# native change, then the same around a companion plugin change labeled
# "companion" (docs/ROADMAP.md: "baseline A, plus Core to B, plus companion
# to C"). Overridable via --waterfall-core/--waterfall-companion for anyone
# who picked their own label names.
WATERFALL_CORE_LABEL = "core"
WATERFALL_COMPANION_LABEL = "companion"


def load_measure():
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location(
        "measure_tokens", os.path.join(here, "measure_tokens.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_experiment():
    """experiment.py, loaded by explicit path like load_measure() loads
    measure_tokens.py, so it works regardless of the caller's cwd. Used only
    for its compute_fingerprint()/EXP_SCHEMA, to check whether a VERIFIED
    record's evidence still matches the environment right now (see
    _historical_check). A load failure is the caller's to catch; this
    function never swallows one, so it never hides a real bug behind a
    silent NO DATA."""
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location(
        "experiment", os.path.join(here, "experiment.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def lever(sm, mt):
    """Map the shared classification key to shield-flavored wording."""
    key = mt.dominant_lever(sm)
    share = sm.get("first_request_share_median")
    hit = sm.get("hit_ratio_median")
    sub = sm.get("subagent_output_share")
    if key == "nodata":
        return ("Not enough measured sessions yet",
                "Run a few more sessions, then re-render. The shield reports what it "
                "can measure and nothing more.")
    if key == "shrink":
        return ("Shrink the always-loaded context",
                f"The startup floor is {share * 100:.0f}% of everything a session reads, "
                f"paid again on every call. Pruning what loads at session start beats "
                f"every other lever.")
    if key == "cache":
        return ("Keep the cache hot",
                f"A {hit:.2f} median hit ratio means the prefix is being rebuilt. Look "
                f"for model or effort switches, a changed toolset, or idle gaps past the "
                f"cache TTL.")
    if key == "route":
        return ("Route work deliberately",
                f"Subagents produced {sub * 100:.0f}% of output. Worth it when they keep "
                f"exploration out of the parent context, waste when a script would have "
                f"done the job.")
    return ("Healthy",
            "Every measured signal is inside its healthy range. Spend effort on the work, "
            "not the meter.")


def pain_points(sessions):
    """Measured waste patterns, worst first. Every count is from the transcripts.

    Two confidence levels, kept distinct on purpose:
    - PROVEN: a model switch mid-session rebuilds the cache from zero, because
      each model has its own cache (documented). models > 1 is a fact.
    - SIGNAL: a high rewrite ratio suggests the prefix kept rebuilding, but
      ordinary growth writes cache too, so it points rather than proves.
    """
    parent = [s for s in sessions if s["first_request"] > 0]
    n = len(parent) or 1
    switched = [s for s in parent if s["models"] > 1]
    rebuilt = [s for s in parent
               if s["rewrite_ratio"] and s["rewrite_ratio"] > 0.15 and s["calls"] >= 10]
    return {
        "n": len(parent),
        "switch_n": len(switched),
        "switch_share": len(switched) / n,
        "rebuild_n": len(rebuilt),
        "rebuild_share": len(rebuilt) / n,
    }


def savings_breakdown(sm):
    """Where the caching saving comes from, in base-input units.

    Honest accounting: caching earns 0.9x on every read token, and pays a
    premium on every write token (0.25x extra at the 5 minute TTL, 1.0x extra
    at the 1 hour TTL). The NET saving subtracts that premium, so the headline
    is not the gross read saving dressed up as the net benefit.

    Writes whose TTL the transcript never split are charged at the MOST
    expensive rate (1.0x), not skipped. Skipping them made this headline
    largest exactly where the evidence was weakest. NATIVE is attributed to
    Anthropic rather than claimed by this tool, so it has to be a lower bound:
    understating their benefit is a caveat, overstating it is the dishonesty
    this whole product exists against. The unsplit volume is returned beside
    the number so a surface can disclose it instead of printing a quietly
    weaker figure that looks identical to a fully priced one.
    """
    read = sm["read_total"] or 0
    paid = CACHE_READ * read          # what reads actually cost, at 0.1x
    unblocked = 1.0 * read            # what they would cost uncached
    gross = unblocked - paid          # the 0.9x earned on reads
    w5, w1 = sm["write_5m_total"] or 0, sm["write_1h_total"] or 0
    # .get: an older schema's summary, and the partial dicts callers build,
    # carry no unsplit key at all. A missing key is zero, never a crash.
    wu = sm.get("write_unsplit_total") or 0
    write_premium = 0.25 * w5 + 1.0 * w1 + 1.0 * wu   # extra over uncached
    return {
        "read": read, "paid": paid, "unblocked": unblocked,
        "gross": gross, "write_premium": write_premium,
        "saved": gross - write_premium,     # NET
        "write_cost": 1.25 * w5 + 2.0 * w1 + 2.0 * wu,
        "write_unsplit": wu,
        "raw_input": sm["input_total"] or 0,
    }


def prescriptions(sm, sessions):
    """One prescription per detected pain point, with the token-saving math
    computed from THIS user's own sessions. Adaptive: a user whose data shows
    no model switching gets no model-switch card. Every number is theirs.
    """
    parent = [s for s in sessions if s["first_request"] > 0]
    n = len(parent) or 1
    fr = sm["first_request_median"] or 0
    share = sm["first_request_share_median"]
    total_calls = sum(s["calls"] for s in parent)
    out = []

    switched = [s for s in parent if s["models"] > 1]
    if switched:
        saving = len(switched) * 0.9 * fr   # lower bound: floor re-read at full
        out.append({
            "tag": "PROVEN",
            "title": "Switching model mid-session",
            "longterm": "Make subagent routing the default: fix the parent model and "
                        "effort at session start as policy, and send any cheaper sub-task "
                        "to a subagent, so the main loop's cache is never rebuilt.",
            "measure": f"{len(switched)} of {n} of your sessions "
                       f"({len(switched) / n:.0%}) ran more than one model",
            "painkiller": "Pick your model and effort once, at the top of a session, "
                          "and leave them for the rest of it.",
            "medicine": "When a sub-task wants a cheaper model, spawn a subagent on it "
                        "instead of switching the main loop. Effort is in the cache key "
                        "too, so /effort rebuilds the prefix exactly like /model.",
            "math": f"Each switch re-reads the conversation at full 1x instead of cached "
                    f"0.1x. Lower bound, counting only the startup floor: "
                    f"{len(switched)} switches x 0.9 x {fmt.human(fr)} floor = "
                    f"{fmt.human(saving)} base-input units saved this window. The real figure "
                    f"is larger, because a switch re-reads the whole context at that "
                    f"point, not just the floor.",
            "saving": saving,
        })

    if share is not None and share >= 0.30:
        cut = 0.20
        # The floor is re-read at 0.1x on every call after the first. Cutting it
        # by 20% saves, per session, 0.2 x floor x 0.1 x calls. Summed over the
        # user's own sessions. The one-time write saving is minor, left out to
        # keep the estimate conservative.
        saving = fr * cut * CACHE_READ * total_calls
        out.append({
            "tag": "PROVEN",
            "title": "The always-loaded startup floor",
            "longterm": "Shrink the always-loaded core for good: keep CLAUDE.md to hard "
                        "rules only, move rarely-relevant rules into path-scoped "
                        ".claude/rules/ that load only when a matching file is read, and "
                        "disable plugins and MCP servers you do not use. A small core is "
                        "paid once; a bloated one is paid on every call forever.",
            "measure": f"your median session pays {fmt.human(fr)} before any work, "
                       f"{share:.0%} of everything it reads, on every one of "
                       f"{total_calls:,} calls this window",
            "painkiller": "Run context_lint.py to see exactly where the rent is, then "
                          "diet CLAUDE.md under 200 lines.",
            "medicine": "Prune plugins and MCP servers you do not use, quiet "
                        "session-start hooks, and move rarely-relevant rules into "
                        "path-scoped .claude/rules/ so they load only when they apply.",
            "math": f"The floor is re-read at 0.1x on every call. Cutting it 20 percent "
                    f"saves 0.2 x {fmt.human(fr)} x 0.1 across your {total_calls:,} calls = "
                    f"{fmt.human(saving)} base-input units this window. Cut it in half and "
                    f"the saving scales with it.",
            "saving": saving,
        })

    rebuilt = [s for s in parent
               if s["rewrite_ratio"] and s["rewrite_ratio"] > 0.15 and s["calls"] >= 10]
    if rebuilt:
        # Excess writes over a light-rewrite baseline of 0.05, at the write rate.
        excess = sum(max(0.0, (s["rewrite_ratio"] - 0.05)) * s["read"] * 1.25
                     for s in rebuilt)
        out.append({
            "tag": "SIGNAL",
            "title": "Prefix rebuilt mid-session",
            "longterm": "Adopt a fixed config window: do settings, hook and MCP edits "
                        "between sessions, and background every long wait with a completion "
                        "callback so a session never goes cold past the cache TTL.",
            "measure": f"{len(rebuilt)} of {n} of your sessions "
                       f"({len(rebuilt) / n:.0%}) wrote cache heavily relative to reads",
            "painkiller": "Do config edits between sessions, not during one. Editing "
                          "settings, hooks or MCP config mid-run changes the prefix.",
            "medicine": "Avoid idle gaps past the cache TTL (5 minutes on an API key, "
                        "1 hour on a subscription); background long waits so the session "
                        "re-wakes rather than going cold.",
            "math": f"A signal, not a proof: excess writes above a light-rewrite baseline "
                    f"of 0.05, priced at the 1.25x write rate, come to about "
                    f"{fmt.human(excess)} base-input units across these sessions. Treat it as "
                    f"a place to look, since ordinary growth also writes cache.",
            "saving": excess,
        })
    return out


# --- v1.7 advisor surfaces --------------------------------------------------
# Every function below degrades to a NO DATA render when its source (profile,
# ledger, companions.json) is absent; none of them ever invent a number.

def load_profile(path):
    """profile.json, or None if missing/corrupt. Never raises."""
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None  # sbe: allow-silent an unreadable JSON source becomes NO DATA in the section that needed it; the rest of the dashboard still renders


def load_experiment_rows(path):
    """One row per experiment ledger record, tolerant of corrupt lines. Rows
    are never aggregated here: a floor reduction measured for one experiment
    is not the same quantity as one measured for another, so the renderer
    keeps them per-label all the way down.
    """
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # sbe: allow-silent a corrupt ledger line is skipped so one bad line cannot empty the dashboard's experiment table
    return rows


def _historical_check(record, exp_mod):
    """(is_historical, reason) for one VERIFIED ledger record, checked
    against the environment right now, not the ledger: the record itself is
    never rewritten, this only decides how a render labels it.

    Absence of evidence is not evidence of drift: a record with no
    fingerprint_end (a hand-built fixture, or one predating the v2
    fingerprint guard) always comes back (False, None), never a guessed
    HISTORICAL. Same when exp_mod is None (experiment.py could not be
    loaded): there is nothing to compare against, so the check is skipped
    rather than assumed either way.

    fingerprint_end is recomputed with the SAME --treats exclusion the
    record itself used (record["treats"]), so the one file the experiment
    edited stays excluded on both sides of the comparison, exactly as it was
    when the record was verified. compute_fingerprint() is a sha256 over a
    handful of local files plus a plugin-dir listing, no network, so this is
    cheap to run on every render.

    Also checked: the ledger schema the record was written under
    (record["schema"]) against experiment.EXP_SCHEMA, the schema this
    install writes today. That is the "token-shield version context" half
    of drift; there is no separate Claude Code version field on a record to
    check, so this is the only version-shaped signal grounded in real code.
    """
    fp_end = record.get("fingerprint_end")
    if fp_end is None or exp_mod is None:
        return False, None
    try:
        current_fp = exp_mod.compute_fingerprint(record.get("treats"))
    except OSError:
        return False, None
    if current_fp != fp_end:
        return True, ("the config fingerprint has moved since this record was "
                      "verified (CLAUDE.md, settings.json, ~/.claude.json, a "
                      "skill, or an installed plugin changed)")
    schema = record.get("schema")
    current_schema = getattr(exp_mod, "EXP_SCHEMA", None)
    if schema is not None and current_schema is not None and schema != current_schema:
        return True, (f"the token-shield ledger schema moved from {schema} to "
                      f"{current_schema} since this record was verified")
    return False, None


def latest_row_per_label(rows):
    """The newest ledger row per label, across EVERY confidence.

    One function because this rule had three copies (here, share_card.py and
    cli.py), and all three made the same mistake: they filtered to VERIFIED
    BEFORE picking the latest row, so a re-run that FAILED to prove a claim
    did not supersede the older VERIFIED one. The share card is the artifact
    designed to leave this machine, so that published "proven" for a claim
    the newest run could not reproduce, which inverts the one thing this
    project sells. Filtering by confidence is the CALLER's job and happens
    after this returns, never before.

    Ties on timestamp keep the LAST row in file order, matching the
    append-only ledger's own meaning of "latest".
    """
    newest = {}
    for i, r in enumerate(rows or []):
        if not isinstance(r, dict):
            continue
        label = r.get("label") or "(unlabeled)"
        ts = r.get("timestamp") if isinstance(r.get("timestamp"), str) else ""
        if label in newest and (ts, i) < newest[label][0]:
            continue
        newest[label] = ((ts, i), r)
    return {label: r for label, (_key, r) in newest.items()}


def verified_by_label(rows, exp_mod=None):
    """One VERIFIED row per experiment label, newest record wins.

    The contract, shared with the CLI summary and with
    experiment.aggregate_by_label:
      - never sum across labels. A floor reduction measured for one label is
        a different quantity from one measured for another, so a total of the
        two is a number about nothing;
      - repeated runs of the SAME label do not add up either. The latest
        record is the current state of that label, so it replaces the earlier
        one instead of being counted twice;
      - a regression stays negative. Clipping it to zero would let a change
        that made the floor worse read as neutral.

    Ledger order is the tiebreak (the file is append-only), and a parsable
    timestamp beats file order when both records carry one.

    Each row also carries "historical" and "historical_reason" (see
    _historical_check): True plus a one-line reason when the record's own
    config fingerprint or ledger schema no longer matches the environment
    right now, so a render can say HISTORICAL instead of a bare VERIFIED.
    exp_mod is the loaded experiment module (load_experiment()); pass None
    to skip the check entirely, which callers do when they have no real
    environment to check against (tests pass a fixture double instead, so
    the check never depends on this machine's actual ~/.claude files).
    """
    by_label = {}
    for label, r in latest_row_per_label(rows).items():
        if r.get("confidence") != "VERIFIED":
            continue
        delta = r.get("floor_reduction_tokens")
        if isinstance(delta, bool) or not isinstance(delta, (int, float)):
            continue
        historical, reason = _historical_check(r, exp_mod)
        by_label[label] = {"label": label, "floor_reduction": delta,
                           "timestamp": r.get("timestamp"),
                           "direction": r.get("direction"),
                           "historical": historical,
                           "historical_reason": reason}
    return [by_label[k] for k in sorted(by_label)]


def _latest_record(rows, label):
    """The newest ledger record for one label, any confidence (unlike
    verified_by_label, which keeps VERIFIED rows only). The waterfall needs
    to say WHY a step failed, not just that it did, so a NOT_PROVEN record
    is kept here and its reasons are what gets rendered.

    Tie-break mirrors verified_by_label: a parsable timestamp beats ledger
    order, ledger order (append-only) is the fallback.
    """
    best, best_key = None, None
    for i, r in enumerate(rows or []):
        if (r.get("label") or "(unlabeled)") != label:
            continue
        ts = r.get("timestamp") if isinstance(r.get("timestamp"), str) else ""
        key = (ts, i)
        if best_key is None or key > best_key:
            best, best_key = r, key
    return best


def build_waterfall(rows, core_label=WATERFALL_CORE_LABEL,
                    companion_label=WATERFALL_COMPANION_LABEL):
    """The marginal attribution waterfall from docs/ROADMAP.md: baseline A,
    plus Core's own before/after experiment to B, plus the companion's own
    before/after experiment to C.

    Each experiment.py record is already ONE treatment's before/after (one
    label, one fingerprint-pinned comparison; docs/superpowers/specs/
    2026-08-13-solid-core-design.md: "single-treatment attribution is
    core"). This function only COMPOSES the two existing records; it never
    re-derives a confidence verdict and never computes a second fingerprint.
    A companion version change already ends the experiment that spans it
    inside experiment.build_record's own fingerprint_start/fingerprint_end
    guard (that record downgrades to NOT_PROVEN there); this function reads
    that verdict and the two fingerprint fields already written to the
    record, and refuses to chain across a break rather than invent its own
    version check.

    HARD RULES this function exists to hold:
      - core_delta_pct is a percentage of A, companion_delta_pct is a
        percentage of B: different baselines, so they are NEVER added.
        total_delta_pct is computed straight from (A - C) / A.
      - total_delta is computed straight from A and C too, not from
        core_delta + companion_delta: B is measured twice (once as core's
        own after-cohort, once as companion's own before-cohort), and those
        two measurements are not guaranteed to agree exactly even when the
        chain is otherwise clean, so summing the marginal deltas would
        silently paper over that gap.
      - when the two experiments cannot be chained cleanly (a fingerprint
        break between them, or overlapping cohort windows), separable is
        False and no total is computed at all: the interaction is declared
        NOT SEPARABLE rather than credited to one side by a guess.
    """
    core = _latest_record(rows, core_label)
    companion = _latest_record(rows, companion_label)

    def step(rec, label):
        if rec is None:
            return {"label": label, "status": "NO DATA",
                    "note": f"no experiment record labeled \"{label}\" in the ledger"}
        if rec.get("confidence") != "VERIFIED":
            reasons = rec.get("reasons") or ["not verified"]
            return {"label": label, "status": "NOT_PROVEN",
                    "note": "; ".join(str(x) for x in reasons)}
        return {"label": label, "status": "VERIFIED", "record": rec}

    core_step, companion_step = step(core, core_label), step(companion, companion_label)
    result = {"core": core_step, "companion": companion_step, "separable": False,
             "interaction_note": None, "baseline_a": None, "point_b": None,
             "point_c": None, "core_delta": None, "core_delta_pct": None,
             "companion_delta": None, "companion_delta_pct": None,
             "total_delta": None, "total_delta_pct": None}

    if core_step["status"] != "VERIFIED" or companion_step["status"] != "VERIFIED":
        missing = [s["label"] for s in (core_step, companion_step) if s["status"] != "VERIFIED"]
        result["interaction_note"] = (
            f"NOT SEPARABLE: {' and '.join(missing)} has no VERIFIED experiment to "
            f"chain from")
        return result

    a, b, c = (core["first_request_before"], core["first_request_after"],
              companion["first_request_after"])
    result["baseline_a"], result["point_b"], result["point_c"] = a, b, c
    result["core_delta"] = core["floor_reduction_tokens"]
    result["companion_delta"] = companion["floor_reduction_tokens"]

    # Separable only when nothing moved between the two experiments: the
    # fingerprint core ended on must be the exact fingerprint companion
    # started from (read, never re-derived), and companion's before-cohort
    # window must not overlap core's after-cohort window in time, or the
    # same session would be double-counted on both sides of the chain.
    fp_end, fp_start = core.get("fingerprint_end"), companion.get("fingerprint_start")
    fp_continuous = fp_end is not None and fp_end == fp_start
    ca, cb = core.get("cohort_after") or {}, companion.get("cohort_before") or {}
    windows_clean = (ca.get("end") is not None and cb.get("start") is not None
                     and cb["start"] >= ca["end"])

    if not (fp_continuous and windows_clean):
        reasons = []
        if not fp_continuous:
            reasons.append(
                "the config fingerprint moved between the core and companion "
                "experiments (for example a companion version change), so B is not "
                "the same state on both sides")
        if not windows_clean:
            reasons.append(
                "the companion's before-cohort window overlaps the core's "
                "after-cohort window in time")
        result["interaction_note"] = "NOT SEPARABLE: " + "; ".join(reasons)
        return result

    result["separable"] = True
    if a:
        result["core_delta_pct"] = result["core_delta"] / a
    # companion_delta_pct is a share of companion's OWN before-value (its own
    # experiment record), not of core's after-value b: the two are separate
    # measurements of nominally the same state B and are not guaranteed to
    # agree, so mixing them here would make the percentage inconsistent with
    # companion["floor_reduction_tokens"], the number the experiment ledger
    # itself already reports for this label.
    companion_before = companion["first_request_before"]
    if companion_before:
        result["companion_delta_pct"] = result["companion_delta"] / companion_before
    result["total_delta"] = a - c
    if a:
        result["total_delta_pct"] = result["total_delta"] / a
    return result


def _leaf(profile, section, key):
    """Read profile[section][key]["value"], honoring the NO DATA label.
    Returns None on any missing path or a NO DATA leaf, never raises."""
    node = ((profile or {}).get(section) or {}).get(key) or {}
    if not isinstance(node, dict) or node.get("label") == "NO DATA" or node.get("value") is None:
        return None
    return node["value"]


def suppressed_recommendation_count(adv_mod, profile, treatments, strategies):
    """advise() filters suppressed/rejected treatments before ranking and does
    not expose what it filtered. Computed here by diffing the queue and
    companion ids with treatments applied against the same call without them.
    The queue caps at 3, so this can undercount when more than 3 cards would
    otherwise fire, but it never invents a figure.
    """
    return sum(suppressed_recommendation_counts(adv_mod, profile, treatments, strategies))


def suppressed_recommendation_counts(adv_mod, profile, treatments, strategies):
    """Same diff as suppressed_recommendation_count, split into what the
    user chose (a rejected/suppressed record with no "reason") and what
    sync_companion_suppressions wrote (reason "companion"), so a machine
    suppression is never rendered as "your earlier choices": that used to
    happen after a companion-only sync, attributing a decision to the user
    that the user never made.

    Returns (user_n, companion_n).
    """
    if not treatments:
        return 0, 0
    with_t = adv_mod.advise(profile, treatments, strategies)
    without_t = adv_mod.advise(profile, None, strategies)

    def ids(res):
        s = {c["id"] for c in res["queue"]}
        if res["companion"]:
            s.add(res["companion"]["id"])
        return s

    hidden = ids(without_t) - ids(with_t)
    companion_n = sum(1 for sid in hidden if (treatments.get(sid) or {}).get("reason") == "companion")
    return len(hidden) - companion_n, companion_n


def _band_rank(value, low, med, high):
    """0/1/2/3 band for a metric against three rising thresholds; -1 for an
    unmeasured value, so it never wins a max() over a real 0."""
    if value is None:
        return -1
    if value >= high:
        return 3
    if value >= med:
        return 2
    if value >= low:
        return 1
    return 0


def dominant_pattern(profile):
    """The single loudest signal in a profile: whichever of the startup floor
    share, the model-switch share, or total output volume sits in the
    highest band. Ties keep the fixed priority order below (floor first),
    mirroring advisor.py's own cache > startup > output ranking. Returns
    (label, metric_name), or (None, None) when nothing is measured or every
    tracked band is at its lowest.
    """
    fv = _leaf(profile, "instruction", "startup_floor_share")
    sv = _leaf(profile, "behavior", "model_switch_session_share")
    ov = _leaf(profile, "usage", "output_tokens_total")
    candidates = [
        ("The always-loaded startup floor is heavy",
         "instruction.startup_floor_share", _band_rank(fv, 0.10, 0.15, 0.30)),
        ("Sessions keep switching model mid-session",
         "behavior.model_switch_session_share", _band_rank(sv, 0.10, 0.20, 0.40)),
        ("Output volume is high",
         "usage.output_tokens_total", _band_rank(ov, 300_000, 1_000_000, 3_000_000)),
    ]
    candidates = [c for c in candidates if c[2] > 0]
    if not candidates:
        return None, None
    best = max(candidates, key=lambda c: c[2])
    return best[0], best[1]


def _installed_companion(name, cache_root):
    """True if <cache_root>/*/<name> is a directory, mirroring how profile.py
    counts installed plugins two levels under the plugin cache root."""
    try:
        marketplaces = os.listdir(cache_root)
    except OSError:
        return False
    return any(os.path.isdir(os.path.join(cache_root, m, name)) for m in marketplaces)


def _companion_plausible(name, profile):
    """Whether a non-installed companion's own "when" text maps onto a metric
    profile.py actually measures. Only token-saver's when (a huge
    shell-output profile) does; ponytail's (large diffs per accepted change)
    and caveman's (corrective turns not rising) name signals profile.py does
    not carry, so they are never claimed plausible here: they collapse
    instead of turning into a guess.
    """
    if name != "token-saver":
        return False
    v = _leaf(profile, "usage", "output_tokens_total")
    return v is not None and v >= 1_000_000


def _proving_reason(open_experiments):
    """One line naming what is proving right now, for the first entry in
    list_open_experiments()'s own sort order (oldest first). A marker with
    no readable baseline (see list_open_experiments's docstring on
    "_unreadable") names the file path instead of guessing a label it does
    not have, per docs/plan/2026-08-15-STATE-MODEL.md section 3."""
    first = open_experiments[0] or {}
    more = f" (and {len(open_experiments) - 1} more open)" if len(open_experiments) > 1 else ""
    path = first.get("_unreadable")
    if path:
        return (f"a baseline at {path} could not be read, so an open trial "
                 f"cannot be ruled out{more}")
    label = first.get("label") or "(unlabeled)"
    window = first.get("window_days")
    window_txt = f", {window} day window" if window else ""
    return f"proving {label}{window_txt}{more}"


def _opportunity_reason(advise_result):
    """The best card's own one line summary, per section 3. do_nothing is
    the negation of best_card is None (advisor.py:751), so best is always
    present when this is called with do_nothing False."""
    best = advise_result.get("best") or {}
    return best.get("why_selected") or best.get("title") or "a new recommendation is available"


def _verified_reason(non_historical_rows):
    """Names the label and its floor reduction for the first non historical
    VERIFIED row (verified_by_label already sorts by label)."""
    row = non_historical_rows[0]
    delta = row.get("floor_reduction")
    delta_txt = f"{delta:+,}" if isinstance(delta, (int, float)) and not isinstance(delta, bool) else "NO DATA"
    return f"{row.get('label')}: floor reduction {delta_txt} tokens"


def command_center_state(open_experiments, advise_result, verified, strategy_count, parse_health=None):
    """The one top line state every surface renders, per
    docs/plan/2026-08-15-STATE-MODEL.md sections 2, 2a, 3 and 4. Every
    surface (token_shield.py, cli.py) calls this rather than recomputing the
    state, so it is the single source of truth for what the user sees.

    Pure: every argument is the already computed output of an existing
    primitive (list_open_experiments(), advise(), verified_by_label(), and
    the count of loaded strategies), so a test hands it fixtures and this
    never reads the real machine's files.

    Returns (state, reason). state is one of "PROVING", "OPPORTUNITY",
    "VERIFIED", "HEALTHY", or the string "NO DATA". reason is one line of
    plain text, never markup: this is layer 1 and test_architecture.py
    refuses a computing layer that renders.

    parse_health defaults to None, meaning unknown, which preserves
    behaviour exactly as it was before this argument existed (memo section
    2a). The string "UNRECOGNISED" means the transcript parsers stopped
    recognising the format: every counter they feed reads as zero rather
    than absent, so every trigger looks evaluable and the NO DATA
    precondition below can never catch it. UNRECOGNISED fires NO DATA ahead
    of every other rule, PROVING included, because a state computed from a
    meter that cannot read its own input is not a state at all. Nothing in
    this codebase passes anything but None yet: the format canary that would
    supply UNRECOGNISED is a separate task, not built here.

    advise_result may be None (token_shield.py sets it to None when the
    advisor fails to load); that renders NO DATA rather than raising.

    The NO DATA precondition's denominator is advise_result["evaluated"] (the
    count of strategies that actually reached trigger evaluation, i.e. were
    not skipped by a suppression) when that key is present; otherwise it is
    the strategy_count argument, exactly as before this key existed, so
    older callers and fixtures keep their existing behaviour. A denominator
    of 0 means every strategy was suppressed, so nothing at all could be
    evaluated; that also renders NO DATA, distinct in wording from the
    original "insufficient triggers" case.
    """
    if parse_health == "UNRECOGNISED":
        return ("NO DATA",
                "the transcript format is not recognised by the parsers, so "
                "every measurement below may read as zero rather than absent: "
                "no state is trustworthy until the format is fixed")

    if advise_result is None:
        return ("NO DATA",
                "the advisor could not be read, so no state can be computed. "
                "Run token-shield profile to gather data.")

    insufficient = advise_result.get("insufficient") or []
    evaluated = advise_result.get("evaluated")
    denominator = evaluated if evaluated is not None else strategy_count
    if denominator and len(insufficient) == denominator:
        return ("NO DATA",
                f"NO DATA on {len(insufficient)} strategy trigger(s): "
                + ", ".join(insufficient) + ". Run token-shield profile to gather data.")

    if open_experiments:
        return ("PROVING", _proving_reason(open_experiments))

    # The all suppressed case sits BELOW PROVING, and the two NO DATA rules
    # above sit on top of it, deliberately. They are not the same kind of
    # thing. An unrecognised format and an unreadable advisor are MEASUREMENT
    # failures: the numbers a running trial would report cannot be trusted, so
    # hiding PROVING is the honest move. A denominator of zero is a
    # CONFIGURATION choice: the user muted every strategy, which says nothing
    # about whether the meter works. An open experiment is read from a file on
    # disk rather than computed from the profile, so it is still a fact, and
    # burying a running trial under NO DATA would lose real information and
    # cost the user the stability warning that PROVING exists to give.
    # Note the two are mutually exclusive above: `denominator and ...` is False
    # when the denominator is zero, so the insufficient triggers rule cannot
    # fire on an empty list here.
    if denominator == 0:
        return ("NO DATA",
                "every strategy is suppressed, so nothing could be evaluated "
                "right now. Run token-shield profile to gather data.")

    if not advise_result.get("do_nothing"):
        return ("OPPORTUNITY", _opportunity_reason(advise_result))

    non_historical = [r for r in (verified or []) if not r.get("historical")]
    if non_historical:
        return ("VERIFIED", _verified_reason(non_historical))

    return ("HEALTHY", advise_result.get("message")
            or "Nothing crossed a trigger threshold, so this profile looks healthy right now.")
