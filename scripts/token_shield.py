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
from datetime import datetime

import config as cfg
import formatting as fmt
import metrics as met

HERE = os.path.dirname(os.path.abspath(__file__))


def native_note(sv):
    """The caveat that travels with a NATIVE figure, or "" when there is none.

    Empty whenever every cache write carried a TTL, so a fully priced headline
    stays clean. When some writes could not be priced, the reader is told on
    the same line as the number rather than in a footnote, because a quietly
    weaker figure prints identically to a solid one otherwise.
    """
    wu = sv.get("write_unsplit") or 0
    if not wu:
        return ""
    return (f" (includes {fmt.human(wu)} of cache writes with no TTL split, "
            f"charged at the most expensive rate, so this is a lower bound)")


def render_waterfall(wf, core_label=met.WATERFALL_CORE_LABEL,
                     companion_label=met.WATERFALL_COMPANION_LABEL):
    parts = ['<h2>Marginal attribution waterfall</h2>']
    if wf is None:
        wf = met.build_waterfall([], core_label, companion_label)
    if wf["core"]["status"] == "NO DATA" and wf["companion"]["status"] == "NO DATA":
        parts.append(
            f'<p class="nodata">NO DATA: no experiment named &quot;{fmt.esc(core_label)}&quot; or '
            f'&quot;{fmt.esc(companion_label)}&quot; in the ledger yet. Run '
            f'<code>experiment start "{fmt.esc(core_label)}"</code>, apply the core change, '
            f'<code>experiment end "{fmt.esc(core_label)}"</code>, then the same around a '
            f'companion change labeled "{fmt.esc(companion_label)}".</p>')
        return "".join(parts)

    if not wf["separable"]:
        parts.append(f'<p class="nodata">{fmt.esc(wf["interaction_note"])} No total is computed; '
                     f'the individual before/after figures below are shown as measured, never '
                     f'split by a guess.</p>')
        for step in (wf["core"], wf["companion"]):
            if step["status"] == "VERIFIED":
                rec = step["record"]
                parts.append(
                    f'<p class="n"><span class="cpill ver">VERIFIED</span> '
                    f'<b>{fmt.esc(step["label"])}</b>: {fmt.human(rec["first_request_before"])} to '
                    f'{fmt.human(rec["first_request_after"])} ({rec["floor_reduction_tokens"]:+,}), '
                    f'source: experiment ledger.</p>')
            elif step["status"] == "NOT_PROVEN":
                parts.append(
                    f'<p class="n"><span class="cpill est">NOT_PROVEN</span> '
                    f'<b>{fmt.esc(step["label"])}</b>: {fmt.esc(step["note"])}</p>')
            else:
                parts.append(
                    f'<p class="n"><b>{fmt.esc(step["label"])}</b>: {fmt.esc(step["note"])}</p>')
        return "".join(parts)

    a, b, c = wf["baseline_a"], wf["point_b"], wf["point_c"]
    parts.append(
        '<div class="compare">'
        f'<div class="col"><p class="lbl">Baseline A</p><div class="amt">{fmt.human(a)}</div></div>'
        f'<div class="col"><p class="lbl">+ Core to B</p>'
        f'<div class="amt">{fmt.human(b)}</div><p class="n">{wf["core_delta"]:+,} '
        f'({fmt.pct(wf["core_delta_pct"])} of A)</p></div>'
        f'<div class="col"><p class="lbl">+ Companion to C</p>'
        f'<div class="amt">{fmt.human(c)}</div><p class="n">{wf["companion_delta"]:+,} '
        f'({fmt.pct(wf["companion_delta_pct"])} of B, not of A)</p></div>'
        '</div>')
    parts.append(
        f'<p class="n"><span class="cpill ver">VERIFIED</span> total A to C: '
        f'{wf["total_delta"]:+,} ({fmt.pct(wf["total_delta_pct"])} of A), computed straight from '
        f'A and C, never from summing the two marginal deltas above. '
        f'{fmt.pct(wf["core_delta_pct"])} is a share of A; {fmt.pct(wf["companion_delta_pct"])} is a '
        f'share of B, a different baseline; the two percentages are never added together. '
        f'Source: experiment ledger, labels "{fmt.esc(core_label)}" and '
        f'"{fmt.esc(companion_label)}".</p>')
    return "".join(parts)


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
        text = fmt.esc(step.get("text", ""))
        command = step.get("command")
        cmd_html = f'<br><code>{fmt.esc(command)}</code>' if command else ''
        items.append(f'<li>{text}{cmd_html}</li>')
    return f'<div class="how"><b>How, exactly.</b><ol>{"".join(items)}</ol></div>'


def _render_chips(card_id):
    """The decision chips row. The dashboard is static HTML, so a chip is not
    a button, it is its own ready-to-copy command; the command IS the
    action. Choices mirror advisor.DECIDE_CHOICES exactly (done/not-now/
    never), never a vocabulary the treatment memory would not recognize.
    """
    cid = fmt.esc(card_id)
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
            f'<div class="rec"><p class="k">{fmt.esc(best["evidence"])} recommendation</p>'
            f'<h3>{fmt.esc(best["title"])}</h3>'
            f'<p><b>Why:</b> {fmt.esc(best["why_selected"])}</p>'
            f'<p><b>Expected benefit:</b> {fmt.esc(best["expected_benefit"])}</p>'
            f'<p><b>Drawback:</b> {fmt.esc(best["drawback"])}</p>'
            f'<p><b>Quality risk:</b> {fmt.esc(best["quality_risk"])}</p>'
            f'<p><b>Reversibility:</b> {fmt.esc(best["reversibility"])}</p>'
            f'<p><b>If you say no:</b> {fmt.esc(best["if_you_say_no"])}</p>'
            # advisor._card already renders `source` as a citable pointer (a
            # docs/CLAIMS.md row, or a URL), so the page never shows a bare
            # internal code a reader cannot look up.
            + (f'<p><b>Source:</b> {fmt.esc(best["source"])}</p>' if best.get("source") else '')
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
    label, metric_name = met.dominant_pattern(profile)
    if label is None:
        parts.append('<p class="n">No dominant pattern measured; every tracked band is low.</p>')
    else:
        parts.append(f'<p class="n">{fmt.esc(label)} (from <code>{fmt.esc(metric_name)}</code>).</p>')
    fr = met._leaf(profile, "usage", "first_request_median_tokens")
    hit = met._leaf(profile, "usage", "cache_hit_ratio_median")
    sw = met._leaf(profile, "behavior", "model_switch_session_share")
    # Same pill helper, same shape as the top strip: a number never travels
    # without its label, and an absent leaf says NO DATA rather than wearing
    # MEASURED over a blank.
    parts.append('<div class="grid">'
                 + stat(f'First-request median {_cpill("MEASURED" if fr is not None else "NO DATA")}',
                        fmt.human(fr), "tokens paid before any work", fr is None)
                 + stat(f'Cache hit ratio median {_cpill("MEASURED" if hit is not None else "NO DATA")}',
                        fmt.pct(hit), "share of reads served from cache", hit is None)
                 + stat(f'Model-switch share {_cpill("MEASURED" if sw is not None else "NO DATA")}',
                        fmt.pct(sw), "sessions that ran more than one model", sw is None)
                 + '</div>')
    return "".join(parts)


def render_recommendation_queue(advise_result, suppressed_n, companion_suppressed_n=0):
    parts = ['<h2>Recommendation queue</h2>']
    if not advise_result:
        parts.append('<p class="nodata">NO DATA: no profile to advise on.</p>')
        return "".join(parts)
    # The best card owns the Next best move section above, chips and all.
    # Repeating it here printed the same recommendation three times on one
    # page, so the queue lists only what is NOT already shown.
    best_id = (advise_result.get("best") or {}).get("id")
    full_queue = advise_result.get("queue") or []
    queue = [c for c in full_queue if c.get("id") != best_id][:3]
    if not queue:
        # Two different empty states, and they must never share a sentence:
        # a queue emptied by the card above is not a healthy profile.
        if full_queue:
            parts.append('<p class="n">Nothing else queued: the only recommendation that '
                         'fired is the card above.</p>')
        else:
            parts.append('<p class="n">Queue is empty: profile is healthy right now '
                         '(see Next best move).</p>')
    else:
        rows = []
        for i, c in enumerate(queue, 1):
            rows.append(
                f'<div class="pain-item"><div class="rank">{i}</div>'
                f'<div class="t">{fmt.esc(c["title"])}'
                f'<span class="cpill est" style="margin:0 0 0 8px">{fmt.esc(c["evidence"])}</span></div>'
                f'<div class="fix">{fmt.esc(c["drawback"])}</div>'
                f'{_render_how(c.get("how"))}</div>')
        parts.append('<div class="pain">' + "".join(rows) + '</div>')
        # The copy-paste chips live on the Next best move card only, so this
        # one line keeps the queue actionable without reprinting them.
        parts.append('<p class="n">Decide on any of these in '
                     '<code>/token-shield:advisor</code>.</p>')
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
        if met._installed_companion(name, cache_root):
            rows.append(
                f'<div class="pain-item"><div class="rank">&#10003;</div>'
                f'<div class="t">{fmt.esc(name)}<span class="tag">installed</span></div>'
                f'<div class="fix">Installed, measure it. {fmt.esc(c["benefit"])}</div></div>')
        elif met._companion_plausible(name, profile):
            rows.append(
                f'<div class="pain-item"><div class="rank">?</div>'
                f'<div class="t">{fmt.esc(name)}<span class="tag">consider</span></div>'
                f'<div class="fix">When: {fmt.esc(c["when"])}<br>'
                f'Drawback: {fmt.esc(c["drawback"])}</div></div>')
        else:
            collapsed.append(name)
    parts.append('<div class="pain">' + "".join(rows) + '</div>' if rows
                 else '<p class="n">No companion is indicated by your profile right now.</p>')
    if collapsed:
        parts.append('<p class="n">Not indicated by your profile: '
                     + ", ".join(fmt.esc(n) for n in collapsed) + '.</p>')
    mentions = companions_data.get("mentions") or []
    if mentions:
        parts.append('<div class="legend">'
                     + "".join(f'<span>{fmt.esc(m["name"])} ({fmt.esc(m["repo"])}), '
                               f'{fmt.esc(m["status"])}</span>'
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
        f'{fmt.esc(r["label"])} {r["floor_reduction"]:+,}' + (' [HISTORICAL]' if r.get("historical") else '')
        for r in verified_rows)
    if len(verified_rows) == 1:
        r = verified_rows[0]
        if r.get("historical"):
            big = f'<span class="big muted">HISTORICAL</span>'
            under = (f'{fmt.human(r["floor_reduction"])} fewer startup tokens per call was '
                     f'verified on <b>{fmt.esc(r["label"])}</b>, but {fmt.esc(r["historical_reason"])}. '
                     f'Re-run the experiment to confirm it still holds.')
            return big, under
        # A regression carries its own colour AND its own word. Colour alone
        # would leave a colour-blind reader unable to tell it from a saving
        # (WCAG 2.2 SC 1.4.1), and the figure is never clipped either way.
        if r["floor_reduction"] < 0:
            big = f'<span class="big w">{fmt.human(r["floor_reduction"])} REGRESSION</span>'
            under = (f'the startup floor GREW by {fmt.human(abs(r["floor_reduction"]))} tokens per '
                     f'call on <b>{fmt.esc(r["label"])}</b>: this experiment measured a regression, '
                     f'not a saving. Shown as it measured, never clipped.')
            return big, under
        big = f'<span class="big g">{fmt.human(r["floor_reduction"])}</span>'
        under = (f'fewer startup tokens per call on <b>{fmt.esc(r["label"])}</b>, proven by a '
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
        rowlist.append(f'<tr><td>{fmt.esc(label)}</td><td>{fmt.esc(conf)}</td>'
                       f'<td>{delta_txt}</td><td>{fmt.esc(date)}</td></tr>')
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
    just moved since), nat (accent) for NATIVE so the pill matches the colour
    the label key paints that word, and the bare muted cpill for everything
    else (MEASURED, NO DATA)."""
    cls = {"VERIFIED": "cpill ver", "ESTIMATED": "cpill est",
          "HISTORICAL": "cpill est", "NATIVE": "cpill nat"}.get(label, "cpill")
    return f'<span class="{cls}">{fmt.esc(label)}</span>'


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
            v_note = f'on {fmt.esc(r["label"])}: {fmt.esc(r["historical_reason"])}'
        else:
            v_label = "VERIFIED"
            v_val = f'{r["floor_reduction"]:+,}'
            v_note = f'startup-floor tokens on {fmt.esc(r["label"])}'
    else:
        hist_n = sum(1 for r in verified if r.get("historical"))
        v_label = "HISTORICAL" if hist_n == len(verified) else "VERIFIED"
        v_val = f'{len(verified)} labels'
        v_note = "each label's own figure, never summed"
        if hist_n:
            v_note += f'; {hist_n} of {len(verified)} historical'
    parts.append(stat(f'Verified improvement {_cpill(v_label)}', fmt.esc(v_val), fmt.esc(v_note),
                      v_label == "NO DATA"))

    # 2. Current stack: installed companion plugins, the same cheap directory
    # read render_companions() already runs per companion.
    names = (companions_data or {}).get("companions") or []
    if not names:
        s_label, s_val, s_note = "NO DATA", "NO DATA", "data/companions.json not found or empty"
    else:
        installed = sum(1 for c in names if met._installed_companion(c["name"], cache_root))
        s_label = "MEASURED"
        s_val = f'{installed}/{len(names)}'
        s_note = "companion plugins installed on this machine"
    parts.append(stat(f'Current stack {_cpill(s_label)}', fmt.esc(s_val), fmt.esc(s_note),
                      s_label == "NO DATA"))

    # 3. Largest remaining problem: the dashboard's own top-ranked issue card.
    if not ranked_rx:
        p_label, p_val, p_note = ("MEASURED", "None ranked",
                                  "every measured pattern is inside its healthy range")
    else:
        top = ranked_rx[0]
        p_label, p_val, p_note = "ESTIMATED", top["title"], top["measure"]
    parts.append(stat(f'Largest remaining problem {_cpill(p_label)}', fmt.esc(p_val), fmt.esc(p_note),
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
    parts.append(stat(f'Next best move {_cpill(m_label)}', fmt.esc(m_val), fmt.esc(m_note),
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
        v = met._leaf(profile, rule["section"], key)
        if v is None:
            continue
        hit = v < rule["value"] if rule["op"] == "below" else v > rule["value"]
        if hit:
            fired.append((rule["what"].format(v=fmt.pct(v)), rule["why"], rule["action"], rule["when"]))

    if not fired:
        parts.append('<div class="wins"><span class="win ok">&#10003; no active alerts</span></div>')
    else:
        for what, why, action, when in fired:
            parts.append(
                f'<div class="alert"><p class="a-what">! {fmt.esc(what)}</p>'
                f'<p class="a-why"><b>Why it matters.</b> {fmt.esc(why)}</p>'
                f'<p class="a-action"><b>Action.</b> {fmt.esc(action)}</p>'
                f'<p class="a-when"><b>When.</b> {fmt.esc(when)}</p></div>')
    return "".join(parts)


# THE COMMAND CENTER STATE, docs/plan/2026-08-15-STATE-MODEL.md. metrics.py's
# command_center_state() is the single source of truth for which of the four
# states (PROVING, OPPORTUNITY, VERIFIED, HEALTHY) or NO DATA renders; this
# module only renders the (state, reason) pair it returns, never recomputes
# the priority order.
#
# VERIFIED is a name shared with a different axis entirely: the five
# confidence labels (VERIFIED, MEASURED, ESTIMATED, NATIVE, RECOMMENDED) that
# the cpills carry on every figure elsewhere on this page. Confusing them
# would read as if a fresh proof had just landed when in fact the state means
# "healthy, and something is proven" (a steady state, not news). Kept apart
# three ways, so a reader loses the thread on none of them alone: (1) the
# word "VERIFIED" here always carries an explicit "(a steady state...)"
# clarifier the confidence pill never does; (2) the state band uses its own
# colour, --accent, never the confidence pill's --good green (see .cc-band.
# cc-verified in CSS below and test_verified_state_is_visually_and_textually_
# distinct_from_verified_label); (3) the two live in physically separate
# containers with different shapes (a rectangular banner vs. a small pill)
# and the band is titled "Command center status", a phrase that appears
# nowhere near a confidence pill.
_CC_STATE_CLASS = {"PROVING": "cc-proving", "OPPORTUNITY": "cc-opportunity",
                   "VERIFIED": "cc-verified", "HEALTHY": "cc-healthy"}


def render_command_center(state, reason):
    """The four-state header, rendered exactly as command_center_state()
    returns it: state and reason verbatim, no re-deriving either one."""
    cls = _CC_STATE_CLASS.get(state, "cc-nodata")
    clarifier = (" (a steady state: healthy and already proven, not a fresh "
                "result)" if state == "VERIFIED" else "")
    return (f'<div class="cc-band {cls}">'
           f'<p class="cc-eyebrow">Command center status</p>'
           f'<p class="cc-state">{fmt.esc(state)}</p>'
           f'<p class="cc-reason">{fmt.esc(reason)}{fmt.esc(clarifier)}</p></div>')


def _proving_day_count(started, window_days, today_str):
    """(n, m) for the PROVING panel, n counting the start date as day 1.
    n can exceed m: the window is n days long only up to and including day
    m, so n > m means the window has closed and the caller (render_proving_
    panel) renders that as "closed", never as an impossible "day n of m"
    fraction. Returns None when started, window_days or today_str is
    missing or unparsable, rather than guess a day count: this is panel
    text, not a computed state, and the memo's own refusal to guess (section
    2) applies here too. Never raises. today_str is a plain "YYYY-MM-DD" (or
    fuller ISO) string, always supplied by the caller (render()'s own `today`
    parameter, itself derived once from the CLI's --stamp / clock read, per
    "no Date.now in library code paths" above): nothing in this function
    reads the clock, which is what keeps it testable with a fixed date."""
    if not started or not window_days or not today_str:
        return None
    try:
        start_date = datetime.fromisoformat(str(started).replace("Z", "+00:00")).date()
        today_date = datetime.fromisoformat(str(today_str).replace("Z", "+00:00")).date()
    except ValueError:
        return None  # sbe: allow-silent an unparsable date becomes "day NO DATA" in the panel, never a guessed day count
    return (today_date - start_date).days + 1, window_days


def _keep_stable_list(exp_mod, baseline):
    """The config surface this open experiment's fingerprint watches, minus
    whatever the record's own treats/fingerprint_excluded fields say the
    treatment is allowed to touch (experiment.py's excluded_by_treats, run
    once at experiment start and stored on the baseline). Named from the
    static path constants experiment.py already defines, never a live
    filesystem glob of SKILLS_DIR: that would make the list depend on
    whichever skills happen to be installed on the machine rendering the
    page, which is neither a fact recorded on the experiment itself nor
    reproducible from a test fixture."""
    if exp_mod is None or not baseline:
        return []
    watched = [
        ("CLAUDE.md", getattr(exp_mod, "CLAUDE_MD_PATH", None)),
        ("settings.json", getattr(exp_mod, "SETTINGS_PATH", None)),
        (".claude.json", getattr(exp_mod, "CLAUDE_JSON_PATH", None)),
        ("installed skills (every SKILL.md)", getattr(exp_mod, "SKILLS_DIR", None)),
    ]
    excluded = set(baseline.get("fingerprint_excluded") or [])
    treats = baseline.get("treats")
    if treats:
        excluded.add(os.path.abspath(os.path.expanduser(str(treats))))
    return [name for name, path in watched
           if path is not None and os.path.abspath(path) not in excluded]


def render_proving_panel(open_experiments, exp_mod, today_str):
    """The PROVING panel: which open experiment, how far through its window,
    and what must hold still for the result to stay honest. Shown only when
    the command center state is PROVING (render() gates the call). Mirrors
    metrics._proving_reason's own handling of an "_unreadable" marker
    (list_open_experiments fails CLOSED per its own docstring): names the
    file path, never invents a label, never raises."""
    if not open_experiments:
        return ""
    first = open_experiments[0] or {}
    more = len(open_experiments) - 1
    parts = ['<div class="proving-panel">', '<h2>Proving</h2>']
    path = first.get("_unreadable")
    if path:
        parts.append(f'<p class="pv-label">Baseline unreadable: <code>{fmt.esc(path)}</code></p>')
        parts.append('<p class="n">This baseline file could not be read, so an open trial '
                     'cannot be ruled out. No label, day count or stable list can be shown '
                     'for it.</p>')
    else:
        label = first.get("label") or "(unlabeled)"
        parts.append(f'<p class="pv-label">{fmt.esc(label)}</p>')
        day = _proving_day_count(first.get("started"), first.get("window_days"), today_str)
        if day:
            n, m = day
            if n > m:
                closed_days = n - m
                day_word = "day" if closed_days == 1 else "days"
                close_cmd = f'python3 scripts/cli.py experiment end "{label}"'
                parts.append(f'<p class="pv-day pv-closed">Window closed {closed_days} '
                             f'{day_word} ago. Run <code>{fmt.esc(close_cmd)}</code> for a '
                             f'verdict.</p>')
            else:
                parts.append(f'<p class="pv-day">day {n} of {m}</p>')
        else:
            parts.append('<p class="pv-day nodata">day NO DATA</p>')
        keep = _keep_stable_list(exp_mod, first)
        if keep:
            parts.append('<p class="n">Keep this stable until the window closes:</p>')
            parts.append('<ul class="pv-keep">'
                         + "".join(f'<li>{fmt.esc(k)}</li>' for k in keep) + '</ul>')
        else:
            parts.append('<p class="n nodata">NO DATA: could not determine what to keep '
                         'stable for this experiment.</p>')
    if more:
        parts.append(f'<p class="n">and {more} more open experiment(s)</p>')
    parts.append('</div>')
    return "".join(parts)


CSS = """
:root{
  --bg:#16131f; --panel:#1e1a2b; --panel2:#251f36; --line:#332a47;
  --ink:#efeaf7; --muted:#a99fc0; --shield:#ff6a3d; --good:#5ad19a;
  --warn:#ffcf5c; --accent:#8b7be8;
  --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;
  --mono:"SF Mono",Menlo,Consolas,monospace;
}
/* Light theme. --good and --warn are darker than their dark-theme twins on
   purpose: they carry the confidence pills and the evidence lines at 9px, so
   WCAG 2.2 SC 1.4.3 asks 4.5:1, not the 3:1 large-text exception. Measured
   against every surface they sit on (--bg, --panel, --panel2): --good #0f7a4e
   is 4.84 / 5.37 / 4.96, --warn #8a6508 is 4.80 / 5.32 / 4.92. The old
   #1f9d68 and #b8860b were 3.11 and 2.93 on --bg. Dark mode already passes
   (11.58 and 9.61) and is untouched. */
@media (prefers-color-scheme: light){
  :root{--bg:#f4f2fa;--panel:#ffffff;--panel2:#f7f5fc;--line:#e4dff0;
        --ink:#211b30;--muted:#6b6284;--shield:#e2542a;--good:#0f7a4e;
        --warn:#8a6508;--accent:#6a5ad0;}
}
:root[data-theme="light"]{--bg:#f4f2fa;--panel:#ffffff;--panel2:#f7f5fc;--line:#e4dff0;
      --ink:#211b30;--muted:#6b6284;--shield:#e2542a;--good:#0f7a4e;--warn:#8a6508;--accent:#6a5ad0;}
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
.hero .big{font-size:clamp(40px,9vw,68px);font-weight:750;line-height:1;letter-spacing:-.02em;color:var(--ink);}
/* One colour per hero state. The base above is deliberately neutral: a hero
   that forgets its modifier must never inherit success green, which is how a
   regression, a HISTORICAL caveat and NONE YET all used to read as a win. The
   words differ too (see render_verified_hero), because WCAG 2.2 SC 1.4.1
   forbids colour as the only carrier of a distinction. */
.hero .big.g{color:var(--good);}
.hero .big.w{color:var(--warn);}
.hero .big.muted{color:var(--muted);}
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
.cpill.nat{color:var(--accent);border-color:var(--accent);}
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
.cc-band{border:1px solid var(--line);border-left:4px solid var(--muted);border-radius:10px;padding:16px 18px;margin:16px 0 22px;background:var(--panel);}
.cc-eyebrow{font-family:var(--mono);font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);margin:0 0 6px;}
.cc-state{font-size:22px;font-weight:750;letter-spacing:.01em;margin:0 0 6px;}
.cc-reason{font-size:13.5px;color:var(--muted);margin:0;max-width:70ch;}
.cc-band.cc-proving{border-left-color:var(--shield);}
.cc-band.cc-proving .cc-state{color:var(--shield);}
.cc-band.cc-opportunity{border-left-color:var(--warn);}
.cc-band.cc-opportunity .cc-state{color:var(--warn);}
.cc-band.cc-verified{border-left-color:var(--accent);}
.cc-band.cc-verified .cc-state{color:var(--accent);}
.cc-band.cc-healthy{border-left-color:var(--good);}
.cc-band.cc-healthy .cc-state{color:var(--good);}
.cc-band.cc-nodata{border-left-color:var(--muted);}
.cc-band.cc-nodata .cc-state{color:var(--muted);}
.proving-panel{background:var(--panel2);border:1px solid var(--line);border-radius:13px;padding:16px 18px;margin:0 0 22px;}
.pv-label{font-size:16px;font-weight:650;margin:0 0 4px;}
.pv-day{font-family:var(--mono);font-size:12px;color:var(--muted);margin:0 0 10px;}
.pv-day.pv-closed{color:var(--warn);}
.pv-keep{margin:6px 0 0;padding-left:18px;font-size:13.5px;color:var(--ink);}
.pv-keep li{margin:2px 0;}
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
           waterfall_core_label=met.WATERFALL_CORE_LABEL,
           waterfall_companion_label=met.WATERFALL_COMPANION_LABEL,
           open_experiments=None, strategy_count=0, parse_health=None, today=None,
           exp_mod=None):
    # usd_res is accepted for signature compatibility with callers (main()
    # still measures it for the separate `prices` command's use elsewhere)
    # but is never rendered here: the dashboard shows only figures the user
    # can act on, not a dollar estimate of Anthropic's own caching.
    #
    # open_experiments/strategy_count/parse_health feed command_center_state()
    # unchanged (T2.1's one function, the single source of truth per
    # docs/plan/2026-08-15-STATE-MODEL.md); exp_mod and today are used only
    # here, to render the PROVING panel's keep-stable list and day count, and
    # are never passed into command_center_state itself.
    state, cc_reason = met.command_center_state(open_experiments or [], advise_result,
                                                 verified, strategy_count, parse_health)
    pp = met.pain_points(sessions)
    rx = met.prescriptions(sm, sessions)
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

    # THE FOUR-STATE HEADER, above the confidence-label key on purpose: the
    # state answers "what do I do right now", the key below answers "what do
    # these words mean", and the two must never sit close enough to blur
    # together (see render_command_center's docstring on keeping the VERIFIED
    # state apart from the VERIFIED confidence label).
    parts.append(render_command_center(state, cc_reason))
    if state == "PROVING":
        parts.append(render_proving_panel(open_experiments or [], exp_mod, today))

    # THE KEY, here and not at the foot of the page: it explains the four
    # words every figure below is labelled with, so it has to arrive before
    # the first pill does, not thirteen screens after it.
    parts.append('<h2>What the labels mean</h2>')
    parts.append('<div class="legend">'
                 '<span><b style="color:var(--good)">VERIFIED</b> before/after, proven</span>'
                 '<span><b style="color:var(--muted)">MEASURED</b> from counters, cause not proven</span>'
                 '<span><b style="color:var(--warn)">ESTIMATED</b> a transparent projection</span>'
                 '<span><b style="color:var(--accent)">NATIVE</b> Claude Code\'s own saving</span>'
                 '</div>')

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
    wf = met.build_waterfall(experiment_rows or [], waterfall_core_label, waterfall_companion_label)
    parts.append(render_waterfall(wf, waterfall_core_label, waterfall_companion_label))

    # WINS AND ISSUES at a glance, Brave-style reassurance.
    wins = []
    wins.append(('ok', '&#10003; Cache reuse healthy') if (hit is not None and hit >= 0.7)
                else ('bad', '! Cache running cold') if hit is not None
                else ('ok', 'cache: NO DATA'))
    wins.append(('ok', '&#10003; No model switching') if not pp['switch_n']
                else ('bad', f'! Model switching {pp["switch_share"]:.0%}'))
    wins.append(('ok', '&#10003; Output routing ok') if (sub is not None and sub < 0.40)
                else ('bad', f'! Subagent output {fmt.pct(sub)}') if sub is not None
                else ('ok', 'routing: NO DATA'))
    wins.append(('bad', f'! Startup context {fmt.pct(share)}') if (share is not None and share >= 0.30)
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
        # The unit the card math is about to quote, defined once, right where
        # a reader first meets it. Without it the closing figure is unreadable
        # as either big or small.
        pain = ['<p class="n">One base-input unit is one token at the ordinary input '
                'price, so a cached read costs a tenth of one.</p>',
                '<div class="pain">']
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
                     f'the order of {fmt.human(total_rx)} base-input units this window on your data, '
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
    # This sentence is the page's one NATIVE instance, so it carries the pill:
    # the key defines the word, and here is the thing it names.
    parts.append(
        f'<p class="usdline">{_cpill("NATIVE")} Anthropic\'s own caching also works underneath '
        'every session; that saving is not this tool\'s, and it does not claim it. The '
        'accounting lives in <code>docs/METHODOLOGY.md</code>, not on this page.</p>')

    parts.append('<footer>Token Shield. Every figure is measured from local API usage '
                 'counters; NO DATA means it could not be measured, never a guess. Aggregates '
                 'only: no conversation text, file paths, or session identifiers reach this '
                 'page. Nothing is uploaded.</footer>')
    parts.append("</div>")
    return "\n".join(parts) + "\n"


def render_standalone(body, title="Token Shield"):
    # esc() here, not raw interpolation: title is caller-supplied text (the
    # fleet dashboard builds it from an org name a machine set at join time),
    # so an unescaped title lets a value like
    # "acme</title><script>alert(1)</script>" break out of the <title> tag
    # and inject a live script into the page. `body` is not escaped here on
    # purpose: every caller already escapes its own body content before
    # handing it to this function.
    return (f'<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f'<title>{fmt.esc(title)}</title>\n</head>\n<body>\n{body}</body>\n</html>\n')


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
    ap.add_argument("--waterfall-core", default=met.WATERFALL_CORE_LABEL,
                    help="experiment label for the waterfall's Core step (default: core)")
    ap.add_argument("--waterfall-companion", default=met.WATERFALL_COMPANION_LABEL,
                    help="experiment label for the waterfall's companion step "
                         "(default: companion)")
    a = ap.parse_args()

    if not os.path.isdir(a.root):
        print(f"NO DATA: {a.root} does not exist.", file=sys.stderr)
        return 2

    mt = met.load_measure()
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

    # "today" for the PROVING panel's day count (docs/plan/2026-08-15-STATE-
    # MODEL.md section 2a: command_center_state is deliberately clock free,
    # so the day count is computed here, at the CLI edge, from the same
    # stamp the pricing lookup below already derives a date from) rather than
    # a fresh clock read inside the renderer.
    today = stamp.split()[0] if stamp else None

    # Optional honest enrichment: per-model USD from the pricing snapshot, and
    # the VERIFIED total from the experiment ledger. Both degrade to None without
    # breaking the render, and a failure is surfaced, not swallowed.
    usd_res = None
    try:
        import pricing as pr
        usd_res = pr.price_saving(pr.saving_by_model(a.root, a.days),
                                  pr.load_pricing(), today)
    except (OSError, ValueError, ImportError) as e:
        print(f"note: USD skipped ({e})", file=sys.stderr)

    ledger = os.path.expanduser("~/.claude/token-shield/savings.jsonl")
    experiment_rows = met.load_experiment_rows(ledger)
    try:
        exp_mod = met.load_experiment()
    except (OSError, ValueError, ImportError) as e:
        exp_mod = None
        print(f"note: historical-drift check skipped ({e})", file=sys.stderr)
    verified = met.verified_by_label(experiment_rows, exp_mod)

    # Open experiments: the PROVING primitive (docs/plan/2026-08-15-STATE-
    # MODEL.md). list_open_experiments() itself never raises on a missing
    # directory (it degrades to []), but the read still goes through the same
    # degrade-to-empty-and-say-so pattern as every other optional surface
    # here, in case the module failed to load at all above.
    open_experiments = []
    if exp_mod is not None:
        try:
            open_experiments = exp_mod.list_open_experiments()
        except OSError as e:
            print(f"note: open experiment check skipped ({e})", file=sys.stderr)

    # v1.7 advisor surfaces: profile, advice, and the companion registry. Each
    # degrades to None on any failure, rather than take the whole render down.
    profile = None
    advise_result = None
    suppressed_n = 0
    companion_suppressed_n = 0
    strategy_count = 0
    try:
        import advisor as adv
        profile = met.load_profile(adv.PROFILE_PATH)
        if profile is not None:
            strategies = adv.load_strategies()
            strategy_count = len(strategies)
            treatments = adv.load_treatments()
            advise_result = adv.advise(profile, treatments, strategies)
            suppressed_n, companion_suppressed_n = met.suppressed_recommendation_counts(
                adv, profile, treatments, strategies)
    except (OSError, ValueError, ImportError) as e:
        print(f"note: advisor skipped ({e})", file=sys.stderr)
    companions_data = cfg.load_companions(cfg.COMPANIONS_PATH)

    body = render(mt, sm, sessions, a.days, stamp, a.include_sessions, usd_res, verified,
                  profile=profile, advise_result=advise_result, suppressed_n=suppressed_n,
                  companions_data=companions_data, experiment_rows=experiment_rows,
                  companion_suppressed_n=companion_suppressed_n,
                  waterfall_core_label=a.waterfall_core,
                  waterfall_companion_label=a.waterfall_companion,
                  open_experiments=open_experiments, strategy_count=strategy_count,
                  today=today, exp_mod=exp_mod)
    out_html = body if a.body_only else render_standalone(body)
    out = os.path.expanduser(a.out)
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    with open(out, "w") as f:
        f.write(out_html)
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
