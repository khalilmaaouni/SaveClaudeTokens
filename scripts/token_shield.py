#!/usr/bin/env python3
"""
token_shield.py: render a Token Shield dashboard as a self-contained HTML file.

The visual language is Brave's shields panel, a shield and a few big numbers
saying what it saved you. The difference from a gimmick is that every number
here is read from the API `usage` counters in your own transcripts, and any
number that cannot be measured says NO DATA instead of inventing a figure.

WHAT COUNTS AS A SAVING, HONESTLY
Brave's "bandwidth saved" is real bytes not downloaded. The token analog that
is genuinely a saving is prompt caching: a cache read bills at 0.1x base input
instead of 1x, so every cached token is a 0.9x saving against the uncached
price. That is the hero number. It is a relative figure in base-input units,
not a dollar amount, because no model price table ships here (a stale price
would corrupt the number silently).

The dashboard also shows the cost the shield helps you attack: the first-request
floor, paid on every call before any work happens. That is a cost to cut, shown
as such, not dressed up as a saving.

PRIVACY
Aggregates only. No conversation text, no file paths, no session identifiers
reach the page. Per-session rows are off unless you pass --include-sessions.

USAGE
  python3 token_shield.py --out ~/token-shield.html
  python3 token_shield.py --out shield.html --days 30
  python3 token_shield.py --out shield.html --stamp "2026-08-12 15:07"
"""

import argparse
import html
import importlib.util
import json
import os
import sys

CACHE_READ = 0.1  # a cached token bills at 0.1x, so the saving is (1 - 0.1)

HERE = os.path.dirname(os.path.abspath(__file__))
COMPANIONS_PATH = os.path.join(HERE, "..", "data", "companions.json")

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


def esc(s):
    """HTML-escape anything that came from outside this file before it enters
    the page. Experiment labels are typed by the user, profile bases carry
    file paths, and the companion registry is an editable JSON file, so all
    three are attacker-shaped text as far as the renderer is concerned. None
    renders as an empty string rather than the word None."""
    return html.escape("" if s is None else str(s))


def human(n):
    """Compact a token count: 1_532_000 -> 1.5M."""
    if n is None:
        return "NO DATA"
    n = float(n)
    for unit, div in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if abs(n) >= div:
            return f"{n / div:.1f}{unit}"
    return f"{int(n):,}"


def pct(x):
    return "NO DATA" if x is None else f"{x * 100:.0f}%"


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
    """
    read = sm["read_total"] or 0
    paid = CACHE_READ * read          # what reads actually cost, at 0.1x
    unblocked = 1.0 * read            # what they would cost uncached
    gross = unblocked - paid          # the 0.9x earned on reads
    w5, w1 = sm["write_5m_total"] or 0, sm["write_1h_total"] or 0
    write_premium = 0.25 * w5 + 1.0 * w1   # extra paid over uncached input
    return {
        "read": read, "paid": paid, "unblocked": unblocked,
        "gross": gross, "write_premium": write_premium,
        "saved": gross - write_premium,     # NET
        "write_cost": 1.25 * w5 + 2.0 * w1,
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
                    f"{len(switched)} switches x 0.9 x {human(fr)} floor = "
                    f"{human(saving)} base-input units saved this window. The real figure "
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
            "measure": f"your median session pays {human(fr)} before any work, "
                       f"{share:.0%} of everything it reads, on every one of "
                       f"{total_calls:,} calls this window",
            "painkiller": "Run context_lint.py to see exactly where the rent is, then "
                          "diet CLAUDE.md under 200 lines.",
            "medicine": "Prune plugins and MCP servers you do not use, quiet "
                        "session-start hooks, and move rarely-relevant rules into "
                        "path-scoped .claude/rules/ so they load only when they apply.",
            "math": f"The floor is re-read at 0.1x on every call. Cutting it 20 percent "
                    f"saves 0.2 x {human(fr)} x 0.1 across your {total_calls:,} calls = "
                    f"{human(saving)} base-input units this window. Cut it in half and "
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
                    f"{human(excess)} base-input units across these sessions. Treat it as "
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
        return None


def load_companions(path):
    """data/companions.json, or None if missing/corrupt. Never raises."""
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


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
                continue
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
    newest = {}
    for i, r in enumerate(rows or []):
        if r.get("confidence") != "VERIFIED":
            continue
        delta = r.get("floor_reduction_tokens")
        if isinstance(delta, bool) or not isinstance(delta, (int, float)):
            continue
        label = r.get("label") or "(unlabeled)"
        ts = r.get("timestamp") if isinstance(r.get("timestamp"), str) else ""
        if label in newest and (ts, i) < newest[label]:
            continue
        newest[label] = (ts, i)
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


def render_waterfall(wf, core_label=WATERFALL_CORE_LABEL,
                     companion_label=WATERFALL_COMPANION_LABEL):
    parts = ['<h2>Marginal attribution waterfall</h2>']
    if wf is None:
        wf = build_waterfall([], core_label, companion_label)
    if wf["core"]["status"] == "NO DATA" and wf["companion"]["status"] == "NO DATA":
        parts.append(
            f'<p class="nodata">NO DATA: no experiment named &quot;{esc(core_label)}&quot; or '
            f'&quot;{esc(companion_label)}&quot; in the ledger yet. Run '
            f'<code>experiment start "{esc(core_label)}"</code>, apply the core change, '
            f'<code>experiment end "{esc(core_label)}"</code>, then the same around a '
            f'companion change labeled "{esc(companion_label)}".</p>')
        return "".join(parts)

    if not wf["separable"]:
        parts.append(f'<p class="nodata">{esc(wf["interaction_note"])} No total is computed; '
                     f'the individual before/after figures below are shown as measured, never '
                     f'split by a guess.</p>')
        for step in (wf["core"], wf["companion"]):
            if step["status"] == "VERIFIED":
                rec = step["record"]
                parts.append(
                    f'<p class="n"><span class="cpill ver">VERIFIED</span> '
                    f'<b>{esc(step["label"])}</b>: {human(rec["first_request_before"])} to '
                    f'{human(rec["first_request_after"])} ({rec["floor_reduction_tokens"]:+,}), '
                    f'source: experiment ledger.</p>')
            elif step["status"] == "NOT_PROVEN":
                parts.append(
                    f'<p class="n"><span class="cpill est">NOT_PROVEN</span> '
                    f'<b>{esc(step["label"])}</b>: {esc(step["note"])}</p>')
            else:
                parts.append(
                    f'<p class="n"><b>{esc(step["label"])}</b>: {esc(step["note"])}</p>')
        return "".join(parts)

    a, b, c = wf["baseline_a"], wf["point_b"], wf["point_c"]
    parts.append(
        '<div class="compare">'
        f'<div class="col"><p class="lbl">Baseline A</p><div class="amt">{human(a)}</div></div>'
        f'<div class="col"><p class="lbl">+ Core to B</p>'
        f'<div class="amt">{human(b)}</div><p class="n">{wf["core_delta"]:+,} '
        f'({pct(wf["core_delta_pct"])} of A)</p></div>'
        f'<div class="col"><p class="lbl">+ Companion to C</p>'
        f'<div class="amt">{human(c)}</div><p class="n">{wf["companion_delta"]:+,} '
        f'({pct(wf["companion_delta_pct"])} of B, not of A)</p></div>'
        '</div>')
    parts.append(
        f'<p class="n"><span class="cpill ver">VERIFIED</span> total A to C: '
        f'{wf["total_delta"]:+,} ({pct(wf["total_delta_pct"])} of A), computed straight from '
        f'A and C, never from summing the two marginal deltas above. '
        f'{pct(wf["core_delta_pct"])} is a share of A; {pct(wf["companion_delta_pct"])} is a '
        f'share of B, a different baseline; the two percentages are never added together. '
        f'Source: experiment ledger, labels "{esc(core_label)}" and '
        f'"{esc(companion_label)}".</p>')
    return "".join(parts)


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


def _render_how(how_steps):
    """The "How, exactly" block: numbered steps from a strategy's own "how"
    field (data/strategies.json), commands in monospace so they are
    copy-pasteable straight off a static page. Missing or empty renders
    nothing, so the fixture cards in test_tools.py that predate the "how"
    field still render cleanly.
    """
    if not how_steps:
        return ''
    items = []
    for step in how_steps:
        text = esc(step.get("text", ""))
        command = step.get("command")
        cmd_html = f'<br><code>{esc(command)}</code>' if command else ''
        items.append(f'<li>{text}{cmd_html}</li>')
    return f'<div class="how"><b>How, exactly.</b><ol>{"".join(items)}</ol></div>'


def _render_chips(card_id):
    """The decision chips row. The dashboard is static HTML, so a chip is not
    a button, it is its own ready-to-copy command; the command IS the
    action. Choices mirror advisor.DECIDE_CHOICES exactly (done/not-now/
    never), never a vocabulary the treatment memory would not recognize.
    """
    cid = esc(card_id)
    return (
        '<div class="chips">'
        f'<div class="chip"><b>Did it</b>'
        f'<code>python3 scripts/cli.py advise --decide {cid} done</code></div>'
        f'<div class="chip"><b>Not now (90 days quiet)</b>'
        f'<code>python3 scripts/cli.py advise --decide {cid} not-now</code></div>'
        f'<div class="chip"><b>Never recommend</b>'
        f'<code>python3 scripts/cli.py advise --decide {cid} never</code></div>'
        '</div>'
        '<p class="n">Prefer to be walked through it? Run '
        '<code>/token-shield:advisor</code> in any Claude session.</p>'
    )


def render_next_best_move(advise_result):
    parts = ['<h2>Next best move</h2>']
    if not advise_result:
        parts.append('<p class="nodata">NO DATA: no profile to advise on. Run '
                     '<code>python3 profile.py</code> first.</p>')
        return "".join(parts)
    if advise_result.get("do_nothing"):
        msg = advise_result.get("message", "Nothing to recommend right now.")
        parts.append(f'<div class="rec"><p class="k">Healthy profile</p>'
                     f'<h3>Nothing crossed a trigger</h3><p>{msg}</p></div>')
    else:
        best = advise_result["best"]
        parts.append(
            f'<div class="rec"><p class="k">{esc(best["evidence"])} recommendation</p>'
            f'<h3>{esc(best["title"])}</h3>'
            f'<p><b>Why:</b> {esc(best["why_selected"])}</p>'
            f'<p><b>Expected benefit:</b> {esc(best["expected_benefit"])}</p>'
            f'<p><b>Drawback:</b> {esc(best["drawback"])}</p>'
            f'<p><b>Quality risk:</b> {esc(best["quality_risk"])}</p>'
            f'<p><b>Reversibility:</b> {esc(best["reversibility"])}</p>'
            f'<p><b>If you say no:</b> {esc(best["if_you_say_no"])}</p>'
            # advisor._card already renders `source` as a citable pointer (a
            # docs/CLAIMS.md row, or a URL), so the page never shows a bare
            # internal code a reader cannot look up.
            + (f'<p><b>Source:</b> {esc(best["source"])}</p>' if best.get("source") else '')
            + _render_how(best.get("how"))
            + '</div>')
        parts.append(_render_chips(best["id"]))
    cost = advise_result.get("advisor_cost_tokens", 0)
    parts.append(f'<p class="n">Advisor cost: {cost} tokens (deterministic)</p>')
    return "".join(parts)


def render_observed_pattern(profile):
    parts = ['<h2>Observed pattern</h2>']
    if not profile:
        parts.append('<p class="nodata">NO DATA: no profile.json found. Run '
                     '<code>python3 profile.py</code> first.</p>')
        return "".join(parts)
    label, metric_name = dominant_pattern(profile)
    if label is None:
        parts.append('<p class="n">No dominant pattern measured; every tracked band is low.</p>')
    else:
        parts.append(f'<p class="n">{esc(label)} (from <code>{esc(metric_name)}</code>).</p>')
    fr = _leaf(profile, "usage", "first_request_median_tokens")
    hit = _leaf(profile, "usage", "cache_hit_ratio_median")
    sw = _leaf(profile, "behavior", "model_switch_session_share")
    parts.append('<div class="grid">'
                 + stat("First-request median", human(fr), "tokens paid before any work", fr is None)
                 + stat("Cache hit ratio median", pct(hit), "share of reads served from cache", hit is None)
                 + stat("Model-switch share", pct(sw), "sessions that ran more than one model", sw is None)
                 + '</div>')
    return "".join(parts)


def render_recommendation_queue(advise_result, suppressed_n, companion_suppressed_n=0):
    parts = ['<h2>Recommendation queue</h2>']
    if not advise_result:
        parts.append('<p class="nodata">NO DATA: no profile to advise on.</p>')
        return "".join(parts)
    queue = (advise_result.get("queue") or [])[:3]
    if not queue:
        parts.append('<p class="n">Queue is empty: profile is healthy right now '
                     '(see Next best move).</p>')
    else:
        rows = []
        for i, c in enumerate(queue, 1):
            rows.append(
                f'<div class="pain-item"><div class="rank">{i}</div>'
                f'<div class="t">{esc(c["title"])}'
                f'<span class="cpill est" style="margin:0 0 0 8px">{esc(c["evidence"])}</span></div>'
                f'<div class="fix">{esc(c["drawback"])}</div>'
                f'{_render_how(c.get("how"))}{_render_chips(c["id"])}</div>')
        parts.append('<div class="pain">' + "".join(rows) + '</div>')
    # A companion-caused suppression is never the user's own choice, so it
    # gets its own honest line rather than being folded into "your earlier
    # choices": that phrase used to render after a companion-only sync, with
    # nothing the user ever decided behind it.
    if suppressed_n:
        parts.append(f'<p class="n">{suppressed_n} recommendation(s) suppressed by your '
                     f'earlier choices.</p>')
    if companion_suppressed_n:
        parts.append(f'<p class="n">{companion_suppressed_n} recommendation(s) suppressed '
                     f'because an already installed companion plugin owns that capability '
                     f'(not your choice).</p>')
    return "".join(parts)


def render_companions(companions_data, profile, cache_root):
    parts = ['<h2>Companions</h2>']
    if not companions_data:
        parts.append('<p class="nodata">NO DATA: data/companions.json not found or '
                     'unreadable.</p>')
        return "".join(parts)
    rows = []
    collapsed = []
    for c in companions_data.get("companions", []):
        name = c["name"]
        if _installed_companion(name, cache_root):
            rows.append(
                f'<div class="pain-item"><div class="rank">&#10003;</div>'
                f'<div class="t">{esc(name)}<span class="tag">installed</span></div>'
                f'<div class="fix">Installed, measure it. {esc(c["benefit"])}</div></div>')
        elif _companion_plausible(name, profile):
            rows.append(
                f'<div class="pain-item"><div class="rank">?</div>'
                f'<div class="t">{esc(name)}<span class="tag">consider</span></div>'
                f'<div class="fix">When: {esc(c["when"])}<br>'
                f'Drawback: {esc(c["drawback"])}</div></div>')
        else:
            collapsed.append(name)
    parts.append('<div class="pain">' + "".join(rows) + '</div>' if rows
                 else '<p class="n">No companion is indicated by your profile right now.</p>')
    if collapsed:
        parts.append('<p class="n">Not indicated by your profile: '
                     + ", ".join(esc(n) for n in collapsed) + '.</p>')
    mentions = companions_data.get("mentions") or []
    if mentions:
        parts.append('<div class="legend">'
                     + "".join(f'<span>{esc(m["name"])} ({esc(m["repo"])}), '
                               f'{esc(m["status"])}</span>'
                              for m in mentions)
                     + '</div>')
    return "".join(parts)


def render_verified_hero(verified_rows):
    """The VERIFIED column of the hero, per label and never summed.

    Returns (big_html, under_text_html). With one label the big number is
    that label's own signed delta. With several, the big slot says how many
    labels there are and every label is listed with its own figure, because
    a single headline number across labels would be exactly the cross-label
    total the rest of this page refuses to compute.

    A row whose "historical" flag is set (verified_by_label /
    _historical_check: its config fingerprint or ledger schema no longer
    matches the environment right now) renders HISTORICAL with its one-line
    reason instead of a bare VERIFIED number. The ledger record itself is
    never rewritten; this is rendering only.
    """
    if not verified_rows:
        return ('<span class="big muted">NONE YET</span>',
                'No verified saving yet. Apply one recommendation, then run an experiment '
                'to measure the before and after.')
    items = "; ".join(
        f'{esc(r["label"])} {r["floor_reduction"]:+,}' + (' [HISTORICAL]' if r.get("historical") else '')
        for r in verified_rows)
    if len(verified_rows) == 1:
        r = verified_rows[0]
        if r.get("historical"):
            big = f'<span class="big muted">HISTORICAL</span>'
            under = (f'{human(r["floor_reduction"])} fewer startup tokens per call was '
                     f'verified on <b>{esc(r["label"])}</b>, but {esc(r["historical_reason"])}. '
                     f'Re-run the experiment to confirm it still holds.')
            return big, under
        cls = "g" if r["floor_reduction"] >= 0 else "w"
        big = f'<span class="big {cls}">{human(r["floor_reduction"])}</span>'
        under = (f'fewer startup tokens per call on <b>{esc(r["label"])}</b>, proven by a '
                 f'before/after experiment. Regressions are shown as they measured, '
                 f'never clipped.')
        return big, under
    big = f'<span class="big muted">{len(verified_rows)} LABELS</span>'
    hist_n = sum(1 for r in verified_rows if r.get("historical"))
    hist_note = (f' {hist_n} of {len(verified_rows)} are HISTORICAL: their evidence no '
                f'longer matches the environment.' if hist_n else '')
    under = (f'proven per experiment label, never summed across them: {items}. '
             f'A repeated label shows its latest run, and a regression stays negative.'
             f'{hist_note}')
    return big, under


def render_experiment_history(rows):
    parts = ['<h2>Experiment history</h2>']
    if not rows:
        parts.append('<p class="n">No experiments yet. Your first: '
                     '/token-shield:start names one.</p>')
        return "".join(parts)
    rowlist = []
    for r in rows:
        label = r.get("label") or "(unlabeled)"
        conf = r.get("confidence") or "NO DATA"
        delta = r.get("floor_reduction_tokens")
        delta_txt = f'{delta:+,}' if isinstance(delta, (int, float)) else "n/a"
        date = str(r.get("timestamp") or "n/a")[:10]
        rowlist.append(f'<tr><td>{esc(label)}</td><td>{esc(conf)}</td>'
                       f'<td>{delta_txt}</td><td>{esc(date)}</td></tr>')
    parts.append('<div class="scroll"><table class="se"><thead><tr>'
                 '<th>Label</th><th>Verdict</th><th>Floor delta</th><th>Date</th>'
                 '</tr></thead><tbody>' + "".join(rowlist) + '</tbody></table></div>')
    parts.append('<p class="n">One row per experiment. Floor deltas are never summed '
                 'across labels.</p>')
    return "".join(parts)


def _cpill(label):
    """A confidence badge, reusing the cpill classes already styled in CSS:
    ver (good/green) for VERIFIED, est (warn) for ESTIMATED and HISTORICAL
    (a warning, not a proof failure: it was proven once, the environment
    just moved since), and the bare muted cpill for everything else
    (MEASURED, NO DATA)."""
    cls = {"VERIFIED": "cpill ver", "ESTIMATED": "cpill est",
          "HISTORICAL": "cpill est"}.get(label, "cpill")
    return f'<span class="{cls}">{esc(label)}</span>'


def render_top_strip(verified, companions_data, cache_root, ranked_rx, advise_result):
    """Four things a non-technical reader can take in in ten seconds. Every
    cell reuses a number this render already computed elsewhere on the page
    (verified_by_label rows, the companion install check render_companions
    already runs, the ranked prescriptions list, the advisor's own pick);
    nothing here is re-derived. Confidence label always accompanies the
    value; an empty proof ledger says NO DATA, never zero.
    """
    parts = ['<h2>At a glance</h2>', '<div class="grid topstrip">']

    # 1. Verified improvement: latest VERIFIED record per label, never summed.
    # A HISTORICAL label (verified_by_label's own check) means the config
    # fingerprint or ledger schema moved since that record was verified: the
    # figure was true once, not necessarily now.
    if not verified:
        v_label, v_val, v_note = ("NO DATA", "NO DATA",
                                  "no closed experiment in the proof ledger yet")
    elif len(verified) == 1:
        r = verified[0]
        if r.get("historical"):
            v_label = "HISTORICAL"
            v_val = f'{r["floor_reduction"]:+,}'
            v_note = f'on {esc(r["label"])}: {esc(r["historical_reason"])}'
        else:
            v_label = "VERIFIED"
            v_val = f'{r["floor_reduction"]:+,}'
            v_note = f'startup-floor tokens on {esc(r["label"])}'
    else:
        hist_n = sum(1 for r in verified if r.get("historical"))
        v_label = "HISTORICAL" if hist_n == len(verified) else "VERIFIED"
        v_val = f'{len(verified)} labels'
        v_note = "each label's own figure, never summed"
        if hist_n:
            v_note += f'; {hist_n} of {len(verified)} historical'
    parts.append(stat(f'Verified improvement {_cpill(v_label)}', esc(v_val), esc(v_note),
                      v_label == "NO DATA"))

    # 2. Current stack: installed companion plugins, the same cheap directory
    # read render_companions() already runs per companion.
    names = (companions_data or {}).get("companions") or []
    if not names:
        s_label, s_val, s_note = "NO DATA", "NO DATA", "data/companions.json not found or empty"
    else:
        installed = sum(1 for c in names if _installed_companion(c["name"], cache_root))
        s_label = "MEASURED"
        s_val = f'{installed}/{len(names)}'
        s_note = "companion plugins installed on this machine"
    parts.append(stat(f'Current stack {_cpill(s_label)}', esc(s_val), esc(s_note),
                      s_label == "NO DATA"))

    # 3. Largest remaining problem: the dashboard's own top-ranked issue card.
    if not ranked_rx:
        p_label, p_val, p_note = ("MEASURED", "None ranked",
                                  "every measured pattern is inside its healthy range")
    else:
        top = ranked_rx[0]
        p_label, p_val, p_note = "ESTIMATED", top["title"], top["measure"]
    parts.append(stat(f'Largest remaining problem {_cpill(p_label)}', esc(p_val), esc(p_note),
                      False))

    # 4. Next best move: the advisor's own top pick when one fired, else the
    # top issue card's own painkiller line.
    if advise_result and not advise_result.get("do_nothing") and advise_result.get("best"):
        best = advise_result["best"]
        m_label = best.get("evidence") or "ESTIMATED"
        m_val, m_note = best["title"], best.get("why_selected", "")
    elif ranked_rx:
        m_label = "ESTIMATED"
        m_val, m_note = ranked_rx[0]["painkiller"], f'from "{ranked_rx[0]["title"]}"'
    else:
        m_label, m_val, m_note = "NO DATA", "NO DATA", "no profile and no ranked issue to advise on"
    parts.append(stat(f'Next best move {_cpill(m_label)}', esc(m_val), esc(m_note),
                      m_label == "NO DATA"))

    parts.append('</div>')
    return "".join(parts)


# ALERTS BAND thresholds. MEASURED triggers: crossing one of these means
# something is actively costing tokens right now, so they are deliberately
# stricter than the advisor's own ranking thresholds in data/strategies.json
# (a card can rank without alarming; an alert always means "look now").
# Each entry names the profile leaf to read, the direction that fires, the
# strategy card the action line points to, and when to act.
ALERT_THRESHOLDS = {
    "cache_hit_ratio_median": {
        "section": "usage", "op": "below", "value": 0.5,
        "what": "Cache hit ratio median is {v}, below the healthy range.",
        "why": "A low hit ratio means the cached prefix keeps getting rebuilt, so most "
               "calls pay full price instead of the 0.1x cache-read rate.",
        "action": 'See the "Prefer a fresh session at real phase boundaries" card below.',
        "when": "Before your next long session.",
    },
    "startup_floor_share": {
        "section": "instruction", "op": "above", "value": 0.5,
        "what": "Startup floor is {v} of everything a session reads.",
        "why": "That floor is paid again, at cache-read price, on every call for the "
               "life of the session.",
        "action": 'See the "Shrink the always-loaded startup floor" card below.',
        "when": "Next time you touch CLAUDE.md or plugin config.",
    },
    "model_switch_session_share": {
        "section": "behavior", "op": "above", "value": 0.5,
        "what": "{v} of your sessions switched model or effort mid-session.",
        "why": "Each switch rebuilds the cached prefix from zero at full price.",
        "action": 'See the "Fix your model and effort at session start" card below.',
        "when": "At the start of your next session.",
    },
}


def render_alerts(profile):
    """The alerts band. Fires only on a deterministic threshold crossing from
    ALERT_THRESHOLDS, or when the meter itself reports NO DATA (no
    profile.json to read at all). No alert ever fires on healthy data.
    """
    parts = ['<h2>Alerts</h2>']
    if not profile:
        parts.append(
            '<div class="alert"><p class="a-what">NO DATA: no profile has been measured yet.</p>'
            '<p class="a-why"><b>Why it matters.</b> Without a profile, nothing below can be '
            'checked against a real threshold.</p>'
            '<p class="a-action"><b>Action.</b> Run <code>python3 scripts/cli.py profile</code> '
            'to generate one.</p>'
            '<p class="a-when"><b>When.</b> Now, before relying on any section below.</p></div>')
        return "".join(parts)

    fired = []
    for key, rule in ALERT_THRESHOLDS.items():
        v = _leaf(profile, rule["section"], key)
        if v is None:
            continue
        hit = v < rule["value"] if rule["op"] == "below" else v > rule["value"]
        if hit:
            fired.append((rule["what"].format(v=pct(v)), rule["why"], rule["action"], rule["when"]))

    if not fired:
        parts.append('<div class="wins"><span class="win ok">&#10003; no active alerts</span></div>')
    else:
        for what, why, action, when in fired:
            parts.append(
                f'<div class="alert"><p class="a-what">! {esc(what)}</p>'
                f'<p class="a-why"><b>Why it matters.</b> {esc(why)}</p>'
                f'<p class="a-action"><b>Action.</b> {esc(action)}</p>'
                f'<p class="a-when"><b>When.</b> {esc(when)}</p></div>')
    return "".join(parts)


CSS = """
:root{
  --bg:#16131f; --panel:#1e1a2b; --panel2:#251f36; --line:#332a47;
  --ink:#efeaf7; --muted:#a99fc0; --shield:#ff6a3d; --good:#5ad19a;
  --warn:#ffcf5c; --accent:#8b7be8;
  --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;
  --mono:"SF Mono",Menlo,Consolas,monospace;
}
@media (prefers-color-scheme: light){
  :root{--bg:#f4f2fa;--panel:#ffffff;--panel2:#f7f5fc;--line:#e4dff0;
        --ink:#211b30;--muted:#6b6284;--shield:#e2542a;--good:#1f9d68;
        --warn:#b8860b;--accent:#6a5ad0;}
}
:root[data-theme="light"]{--bg:#f4f2fa;--panel:#ffffff;--panel2:#f7f5fc;--line:#e4dff0;
      --ink:#211b30;--muted:#6b6284;--shield:#e2542a;--good:#1f9d68;--warn:#b8860b;--accent:#6a5ad0;}
:root[data-theme="dark"]{--bg:#16131f;--panel:#1e1a2b;--panel2:#251f36;--line:#332a47;
      --ink:#efeaf7;--muted:#a99fc0;--shield:#ff6a3d;--good:#5ad19a;--warn:#ffcf5c;--accent:#8b7be8;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);line-height:1.5;}
.wrap{max-width:920px;margin:0 auto;padding:34px 20px 70px;}
.top{display:flex;align-items:center;gap:14px;margin-bottom:6px;}
.shield{width:46px;height:46px;flex:none;}
.eyebrow{font-family:var(--mono);font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--shield);margin:0;}
h1{font-size:26px;margin:2px 0 0;font-weight:650;letter-spacing:-.01em;}
.stamp{font-family:var(--mono);font-size:11.5px;color:var(--muted);margin:14px 0 26px;border-left:2px solid var(--line);padding-left:11px;}
.hero{background:linear-gradient(135deg,var(--panel2),var(--panel));border:1px solid var(--line);border-radius:16px;padding:26px 26px 22px;margin-bottom:16px;}
.hero .k{font-family:var(--mono);font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin:0 0 6px;}
.hero .big{font-size:clamp(40px,9vw,68px);font-weight:750;line-height:1;letter-spacing:-.02em;color:var(--good);}
.hero .unit{font-size:16px;color:var(--muted);font-weight:500;margin-left:6px;}
.hero .sub{margin:12px 0 0;font-size:14px;color:var(--muted);max-width:60ch;}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:13px;margin:16px 0;}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:13px;padding:16px 17px;}
.stat .k{font-family:var(--mono);font-size:10px;letter-spacing:.11em;text-transform:uppercase;color:var(--muted);margin:0 0 7px;}
.stat .v{font-size:29px;font-weight:680;line-height:1;letter-spacing:-.01em;}
.stat .n{font-size:12.5px;color:var(--muted);margin:7px 0 0;}
.split{height:9px;border-radius:5px;overflow:hidden;display:flex;margin:9px 0 0;background:var(--line);}
.split .a{background:var(--accent);} .split .b{background:var(--shield);}
.rec{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--shield);border-radius:0 13px 13px 0;padding:16px 18px;margin:16px 0;}
.rec .k{font-family:var(--mono);font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--shield);margin:0 0 6px;}
.rec h3{margin:0 0 5px;font-size:17px;}
.rec p{margin:0;font-size:14px;color:var(--muted);}
footer{margin-top:30px;border-top:1px solid var(--line);padding-top:15px;font-family:var(--mono);font-size:11px;color:var(--muted);line-height:1.7;}
.nodata{color:var(--muted);font-weight:500;}
h2{font-size:14px;font-family:var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:30px 0 12px;font-weight:600;}
.compare{display:flex;align-items:flex-end;gap:16px;flex-wrap:wrap;margin-top:14px;}
.compare .col{flex:1;min-width:120px;}
.compare .barc{height:10px;border-radius:5px;background:var(--line);overflow:hidden;margin-bottom:6px;}
.compare .fill{height:100%;}
.compare .lbl{font-family:var(--mono);font-size:10px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);}
.compare .amt{font-size:19px;font-weight:680;letter-spacing:-.01em;}
.pain{display:flex;flex-direction:column;gap:11px;}
.pain-item{background:var(--panel);border:1px solid var(--line);border-radius:13px;padding:15px 17px;display:grid;grid-template-columns:auto 1fr;gap:4px 14px;align-items:baseline;}
.pain-item .rank{font-family:var(--mono);font-size:22px;font-weight:730;color:var(--shield);line-height:1;grid-row:span 3;align-self:center;}
.pain-item .t{font-size:16px;font-weight:640;}
.pain-item .m{font-family:var(--mono);font-size:12px;color:var(--warn);}
.pain-item .fix{font-size:13.5px;color:var(--muted);}
.pain-item .tag{display:inline-block;font-family:var(--mono);font-size:9px;letter-spacing:.1em;text-transform:uppercase;padding:1px 7px;border-radius:10px;border:1px solid var(--line);color:var(--muted);margin-left:8px;vertical-align:middle;}
.why{background:var(--panel2);border:1px solid var(--line);border-radius:14px;padding:18px 20px;margin-top:16px;}
.why h3{margin:0 0 8px;font-size:16px;}
.why p{margin:0 0 8px;font-size:14px;color:var(--muted);}
.why p:last-child{margin-bottom:0;}
table.se{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:8px;}
table.se th{text-align:left;font-family:var(--mono);font-size:9.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);padding:5px 7px;border-bottom:1px solid var(--line);}
table.se td{padding:5px 7px;border-bottom:1px solid var(--line);font-variant-numeric:tabular-nums;}
.scroll{overflow-x:auto;}
.cpill{display:inline-block;font-family:var(--mono);font-size:9px;letter-spacing:.1em;text-transform:uppercase;padding:2px 8px;border-radius:20px;border:1px solid var(--line);margin-bottom:10px;color:var(--muted);}
.cpill.ver{color:var(--good);border-color:var(--good);}
.cpill.est{color:var(--warn);border-color:var(--warn);}
.usdline{font-size:13.5px;color:var(--muted);margin:2px 0 8px;max-width:66ch;}
.usdline b{color:var(--ink);}
.wins{display:flex;flex-wrap:wrap;gap:8px;margin:6px 0 4px;}
.win{font-size:12px;font-family:var(--mono);padding:6px 11px;border-radius:20px;border:1px solid var(--line);color:var(--muted);}
.win.ok{color:var(--good);border-color:var(--line);}
.win.bad{color:var(--warn);border-color:var(--line);}
.pain-item .fix .lt{color:var(--warn);}
.legend{display:flex;flex-wrap:wrap;gap:12px;margin:2px 0 10px;font-family:var(--mono);font-size:10.5px;color:var(--muted);}
.legend b{font-weight:600;}
.alert{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--warn);border-radius:0 13px 13px 0;padding:14px 16px;margin:10px 0;}
.alert .a-what{margin:0 0 6px;font-size:14.5px;font-weight:640;color:var(--ink);}
.alert p{margin:0 0 4px;font-size:13px;color:var(--muted);}
.alert p:last-child{margin-bottom:0;}
.how{margin-top:10px;font-size:13px;color:var(--muted);}
.how ol{margin:5px 0 0 18px;padding:0;}
.how li{margin:3px 0;}
.how code{font-family:var(--mono);font-size:11.5px;color:var(--ink);background:var(--panel2);padding:1px 5px;border-radius:5px;}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px;}
.chip{font-size:11.5px;background:var(--panel2);border:1px solid var(--line);border-radius:9px;padding:6px 9px;}
.chip b{display:block;font-size:9.5px;letter-spacing:.04em;text-transform:uppercase;color:var(--muted);margin-bottom:3px;}
.chip code{font-family:var(--mono);font-size:11px;color:var(--ink);}
"""

SHIELD_SVG = (
    '<svg class="shield" viewBox="0 0 24 24" fill="none" '
    'xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
    '<path d="M12 2l7 3v6c0 4.5-3 8-7 9-4-1-7-4.5-7-9V5l7-3z" '
    'fill="var(--shield)" opacity="0.16"/>'
    '<path d="M12 2l7 3v6c0 4.5-3 8-7 9-4-1-7-4.5-7-9V5l7-3z" '
    'stroke="var(--shield)" stroke-width="1.4"/>'
    '<path d="M8.5 12l2.2 2.2L15.6 9.3" stroke="var(--good)" '
    'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>'
)


def stat(k, v, note, is_nodata=False):
    cls = ' class="v nodata"' if is_nodata else ' class="v"'
    return (f'<div class="stat"><p class="k">{k}</p>'
            f'<div{cls}>{v}</div><p class="n">{note}</p></div>')


def render(mt, sm, sessions, days, stamp, include_sessions, usd_res=None, verified=None,
           profile=None, advise_result=None, suppressed_n=0, companions_data=None,
           experiment_rows=None, plugin_cache_root=None, companion_suppressed_n=0,
           waterfall_core_label=WATERFALL_CORE_LABEL,
           waterfall_companion_label=WATERFALL_COMPANION_LABEL):
    # usd_res is accepted for signature compatibility with callers (main()
    # still measures it for the separate `prices` command's use elsewhere)
    # but is never rendered here: the dashboard shows only figures the user
    # can act on, not a dollar estimate of Anthropic's own caching.
    pp = pain_points(sessions)
    rx = prescriptions(sm, sessions)
    ranked_rx = sorted(rx, key=lambda x: -x["saving"])
    total_rx = sum(r["saving"] for r in rx)
    share = sm["first_request_share_median"]
    hit = sm["hit_ratio_median"]
    sub = sm["subagent_output_share"]
    cache_root = plugin_cache_root or os.path.expanduser("~/.claude/plugins/cache")

    parts = [f"<style>{CSS}</style>", '<div class="wrap">']
    parts.append(f'<div class="top">{SHIELD_SVG}<div>'
                 f'<p class="eyebrow">Token Shield</p>'
                 f'<h1>Save Claude Code tokens. Prove every saving.</h1></div></div>')
    parts.append(f'<p class="stamp">Measured {stamp}, over transcripts touched in the last '
                 f'{days:g} days. Every figure is read from the API usage counters, never '
                 f'estimated. Measured on this machine; the method is portable, these numbers '
                 f'are not.</p>')

    # TOP STRIP, above even the alerts band: four things a non-technical
    # reader can take in in ten seconds. Every cell reuses a number this
    # render already computed, never a re-derived figure.
    parts.append(render_top_strip(verified, companions_data, cache_root, ranked_rx, advise_result))

    # ALERTS BAND, at the top on purpose: a deterministic threshold crossing
    # is the one thing worth seeing before anything else on the page.
    parts.append(render_alerts(profile))

    # WHAT TOKEN SHIELD VERIFIED, the lead and only hero number. `verified`
    # is a list of per-label rows from verified_by_label(), never a
    # cross-label total: the same refusal the experiment history states below.
    vbig, vu = render_verified_hero(verified)
    parts.append(
        '<div class="hero"><span class="cpill ver">Verified &middot; Token Shield</span>'
        f'<p class="k">What Token Shield verified</p>'
        f'<div>{vbig}</div><p class="sub">{vu}</p></div>')

    # v1.7 advisor surfaces, grouped under one banner: everything from here
    # down is something the user can move by acting (a habit, a config edit,
    # a card decision), never a cache mechanic they cannot touch.
    parts.append('<h2>What you can still influence</h2>')
    parts.append(render_next_best_move(advise_result))
    parts.append(render_observed_pattern(profile))
    parts.append(render_recommendation_queue(advise_result, suppressed_n, companion_suppressed_n))
    parts.append(render_companions(companions_data, profile, cache_root))
    parts.append(render_experiment_history(experiment_rows or []))
    wf = build_waterfall(experiment_rows or [], waterfall_core_label, waterfall_companion_label)
    parts.append(render_waterfall(wf, waterfall_core_label, waterfall_companion_label))

    # WINS AND ISSUES at a glance, Brave-style reassurance.
    wins = []
    wins.append(('ok', '&#10003; Cache reuse healthy') if (hit is not None and hit >= 0.7)
                else ('bad', '! Cache running cold') if hit is not None
                else ('ok', 'cache: NO DATA'))
    wins.append(('ok', '&#10003; No model switching') if not pp['switch_n']
                else ('bad', f'! Model switching {pp["switch_share"]:.0%}'))
    wins.append(('ok', '&#10003; Output routing ok') if (sub is not None and sub < 0.40)
                else ('bad', f'! Subagent output {pct(sub)}') if sub is not None
                else ('ok', 'routing: NO DATA'))
    wins.append(('bad', f'! Startup context {pct(share)}') if (share is not None and share >= 0.30)
                else ('ok', '&#10003; Startup context lean') if share is not None
                else ('ok', 'startup: NO DATA'))
    parts.append('<h2>Wins and issues</h2>')
    parts.append('<div class="wins">'
                 + ''.join(f'<span class="win {c}">{t}</span>' for c, t in wins) + '</div>')

    # ISSUE CARDS, ranked. OPPORTUNITY, so labeled ESTIMATED: measured waste plus
    # an estimated saving from fixing it. Only Experiment Mode makes it VERIFIED.
    # Every card here is a behavior the user can change (a switch, a floor, a
    # rebuild pattern), never a cache mechanic they cannot act on.
    parts.append('<h2>Your top issues, ranked</h2>')
    if not rx:
        parts.append('<div class="pain"><div class="pain-item"><div class="rank">&#10003;</div>'
                     '<div class="t">No dominant issue measured<span class="tag">OK</span></div>'
                     '<div class="m">every session pattern is inside its healthy range</div>'
                     '<div class="fix">Keep the shield on and re-check monthly.</div></div></div>')
    else:
        pain = ['<div class="pain">']
        for i, r in enumerate(ranked_rx, 1):
            impact = 'HIGH' if i == 1 else 'MEDIUM'
            lt = r.get("longterm", "")
            lt_html = f'<br><b class="lt">Long-term fix.</b> {lt}' if lt else ''
            pain.append(
                f'<div class="pain-item"><div class="rank">{i}</div>'
                f'<div class="t">{r["title"]}<span class="tag">{impact} impact</span>'
                f'<span class="cpill est" style="margin:0 0 0 8px">Opportunity, estimated</span></div>'
                f'<div class="m">{r["measure"]}</div>'
                f'<div class="fix"><b style="color:var(--good)">Painkiller.</b> '
                f'{r["painkiller"]}<br><b style="color:var(--accent)">Medicine.</b> '
                f'{r["medicine"]}{lt_html}<br><b style="color:var(--shield)">The math.</b> '
                f'{r["math"]}</div></div>')
        pain.append('</div>')
        parts.append("".join(pain))
        parts.append(f'<p class="n" style="margin-top:8px">Treating all of these is worth on '
                     f'the order of {human(total_rx)} base-input units this window on your data, '
                     f'estimated, and it is the tool\'s own contribution, separate from the '
                     f'native caching. To turn an estimate into a VERIFIED number, run '
                     f'<code>experiment start</code>, apply one fix, then '
                     f'<code>experiment end</code>.</p>')

    if include_sessions and sessions:
        top = sorted((s for s in sessions if s["first_request"] > 0),
                     key=lambda x: -x["first_request"])[:10]
        rowlist = []
        for s in top:
            sh = ("n/a" if s["first_request_share"] is None
                  else f'{s["first_request_share"]:.2f}')
            rowlist.append(
                f'<tr><td>{s["first_request"]:,}</td><td>{sh}</td>'
                f'<td>{s["calls"]}</td><td>{s["hit_ratio"]:.2f}</td>'
                f'<td>{s["models"]}</td></tr>')
        rows = "".join(rowlist)
        parts.append('<div class="scroll"><table class="se"><thead><tr>'
                     '<th>First request</th><th>Share</th><th>Calls</th>'
                     '<th>Hit</th><th>Models</th></tr></thead><tbody>'
                     + rows + '</tbody></table></div>')

    # YOUR ROUTINE, static: no new machinery, just naming what already runs
    # by itself and what to run by hand after a real change.
    parts.append('<h2>Your routine</h2>')
    parts.append(
        '<p class="n">Monthly, the <code>com.tokenshield.monthly-audit</code> launchd job '
        're-renders this page by itself, and <code>/token-shield:monthly</code> compares it '
        'against the prior month. After any config change, run '
        '<code>python3 scripts/cli.py profile</code> to re-measure. Before and after an '
        'experiment, run <code>python3 scripts/cli.py experiment start &lt;label&gt;</code> '
        'and <code>python3 scripts/cli.py experiment end &lt;label&gt;</code>.</p>')

    # METHODOLOGY POINTER, the only mention of native caching left on this
    # page: one sentence, no numbers, no bars, no dollars. The full accounting
    # (0.1x reads, 1.25x/2x write premiums) lives in docs/METHODOLOGY.md, not
    # here, because every number on this page is one the user can move by
    # acting; the native saving is not this tool's, and it does not claim it.
    parts.append(
        '<p class="usdline">Anthropic\'s own caching also works underneath every session; '
        'that saving is not this tool\'s, and it does not claim it. The accounting lives in '
        '<code>docs/METHODOLOGY.md</code>, not on this page.</p>')

    parts.append('<h2>What the labels mean</h2>')
    parts.append('<div class="legend">'
                 '<span><b style="color:var(--good)">VERIFIED</b> before/after, proven</span>'
                 '<span><b style="color:var(--muted)">MEASURED</b> from counters, cause not proven</span>'
                 '<span><b style="color:var(--warn)">ESTIMATED</b> a transparent projection</span>'
                 '<span><b style="color:var(--accent)">NATIVE</b> Claude Code\'s own saving</span>'
                 '</div>')
    parts.append('<footer>Token Shield. Every figure is measured from local API usage '
                 'counters; NO DATA means it could not be measured, never a guess. Aggregates '
                 'only: no conversation text, file paths, or session identifiers reach this '
                 'page. Nothing is uploaded.</footer>')
    parts.append("</div>")
    return "\n".join(parts) + "\n"


def render_standalone(body, title="Token Shield"):
    return (f'<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f'<title>{title}</title>\n</head>\n<body>\n{body}</body>\n</html>\n')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--out", required=True, help="HTML file to write")
    ap.add_argument("--root", default=os.path.expanduser("~/.claude/projects"))
    ap.add_argument("--days", type=float, default=30)
    ap.add_argument("--stamp", default=None,
                    help="snapshot label for the header (Date.now is not used)")
    ap.add_argument("--include-sessions", action="store_true",
                    help="add a per-session table (transcript rows carry no names)")
    ap.add_argument("--body-only", action="store_true",
                    help="emit body content without the html wrapper (for artifact publish)")
    ap.add_argument("--waterfall-core", default=WATERFALL_CORE_LABEL,
                    help="experiment label for the waterfall's Core step (default: core)")
    ap.add_argument("--waterfall-companion", default=WATERFALL_COMPANION_LABEL,
                    help="experiment label for the waterfall's companion step "
                         "(default: companion)")
    a = ap.parse_args()

    if not os.path.isdir(a.root):
        print(f"NO DATA: {a.root} does not exist.", file=sys.stderr)
        return 2

    mt = load_measure()
    sessions = mt.collect(a.root, a.days)
    sm = mt.summarize(sessions)
    if not sm:
        print("NO DATA: no transcripts carried usage counters.", file=sys.stderr)
        return 2

    # No Date.now in library code paths; the caller supplies the stamp, or we
    # read the OS clock only here, at the CLI edge.
    stamp = a.stamp
    if stamp is None:
        import time
        stamp = time.strftime("%Y-%m-%d %H:%M")

    # Optional honest enrichment: per-model USD from the pricing snapshot, and
    # the VERIFIED total from the experiment ledger. Both degrade to None without
    # breaking the render, and a failure is surfaced, not swallowed.
    usd_res = None
    try:
        import pricing as pr
        today = stamp.split()[0]
        usd_res = pr.price_saving(pr.saving_by_model(a.root, a.days),
                                  pr.load_pricing(), today)
    except (OSError, ValueError, ImportError) as e:
        print(f"note: USD skipped ({e})", file=sys.stderr)

    ledger = os.path.expanduser("~/.claude/token-shield/savings.jsonl")
    experiment_rows = load_experiment_rows(ledger)
    try:
        exp_mod = load_experiment()
    except (OSError, ValueError, ImportError) as e:
        exp_mod = None
        print(f"note: historical-drift check skipped ({e})", file=sys.stderr)
    verified = verified_by_label(experiment_rows, exp_mod)

    # v1.7 advisor surfaces: profile, advice, and the companion registry. Each
    # degrades to None on any failure, rather than take the whole render down.
    profile = None
    advise_result = None
    suppressed_n = 0
    companion_suppressed_n = 0
    try:
        import advisor as adv
        profile = load_profile(adv.PROFILE_PATH)
        if profile is not None:
            strategies = adv.load_strategies()
            treatments = adv.load_treatments()
            advise_result = adv.advise(profile, treatments, strategies)
            suppressed_n, companion_suppressed_n = suppressed_recommendation_counts(
                adv, profile, treatments, strategies)
    except (OSError, ValueError, ImportError) as e:
        print(f"note: advisor skipped ({e})", file=sys.stderr)
    companions_data = load_companions(COMPANIONS_PATH)

    body = render(mt, sm, sessions, a.days, stamp, a.include_sessions, usd_res, verified,
                  profile=profile, advise_result=advise_result, suppressed_n=suppressed_n,
                  companions_data=companions_data, experiment_rows=experiment_rows,
                  companion_suppressed_n=companion_suppressed_n,
                  waterfall_core_label=a.waterfall_core,
                  waterfall_companion_label=a.waterfall_companion)
    out_html = body if a.body_only else render_standalone(body)
    out = os.path.expanduser(a.out)
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    with open(out, "w") as f:
        f.write(out_html)
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
