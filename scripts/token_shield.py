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
import importlib.util
import json
import os
import sys

CACHE_READ = 0.1  # a cached token bills at 0.1x, so the saving is (1 - 0.1)

HERE = os.path.dirname(os.path.abspath(__file__))
COMPANIONS_PATH = os.path.join(HERE, "..", "data", "companions.json")


def load_measure():
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location(
        "measure_tokens", os.path.join(here, "measure_tokens.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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
    if not treatments:
        return 0
    with_t = adv_mod.advise(profile, treatments, strategies)
    without_t = adv_mod.advise(profile, None, strategies)

    def ids(res):
        s = {c["id"] for c in res["queue"]}
        if res["companion"]:
            s.add(res["companion"]["id"])
        return s

    return len(ids(without_t) - ids(with_t))


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
            f'<div class="rec"><p class="k">{best["evidence"]} recommendation</p>'
            f'<h3>{best["title"]}</h3>'
            f'<p><b>Why:</b> {best["why_selected"]}</p>'
            f'<p><b>Expected benefit:</b> {best["expected_benefit"]}</p>'
            f'<p><b>Drawback:</b> {best["drawback"]}</p>'
            f'<p><b>Quality risk:</b> {best["quality_risk"]}</p>'
            f'<p><b>Reversibility:</b> {best["reversibility"]}</p>'
            f'<p><b>If you say no:</b> {best["if_you_say_no"]}</p>'
            f'</div>')
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
        parts.append(f'<p class="n">{label} (from <code>{metric_name}</code>).</p>')
    fr = _leaf(profile, "usage", "first_request_median_tokens")
    hit = _leaf(profile, "usage", "cache_hit_ratio_median")
    sw = _leaf(profile, "behavior", "model_switch_session_share")
    parts.append('<div class="grid">'
                 + stat("First-request median", human(fr), "tokens paid before any work", fr is None)
                 + stat("Cache hit ratio median", pct(hit), "share of reads served from cache", hit is None)
                 + stat("Model-switch share", pct(sw), "sessions that ran more than one model", sw is None)
                 + '</div>')
    return "".join(parts)


def render_recommendation_queue(advise_result, suppressed_n):
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
                f'<div class="t">{c["title"]}'
                f'<span class="cpill est" style="margin:0 0 0 8px">{c["evidence"]}</span></div>'
                f'<div class="fix">{c["drawback"]}</div></div>')
        parts.append('<div class="pain">' + "".join(rows) + '</div>')
    if suppressed_n:
        parts.append(f'<p class="n">{suppressed_n} recommendation(s) suppressed by your '
                     f'earlier choices.</p>')
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
                f'<div class="t">{name}<span class="tag">installed</span></div>'
                f'<div class="fix">Installed, measure it. {c["benefit"]}</div></div>')
        elif _companion_plausible(name, profile):
            rows.append(
                f'<div class="pain-item"><div class="rank">?</div>'
                f'<div class="t">{name}<span class="tag">consider</span></div>'
                f'<div class="fix">When: {c["when"]}<br>Drawback: {c["drawback"]}</div></div>')
        else:
            collapsed.append(name)
    parts.append('<div class="pain">' + "".join(rows) + '</div>' if rows
                 else '<p class="n">No companion is indicated by your profile right now.</p>')
    if collapsed:
        parts.append(f'<p class="n">Not indicated by your profile: {", ".join(collapsed)}.</p>')
    mentions = companions_data.get("mentions") or []
    if mentions:
        parts.append('<div class="legend">'
                     + "".join(f'<span>{m["name"]} ({m["repo"]}), {m["status"]}</span>'
                              for m in mentions)
                     + '</div>')
    return "".join(parts)


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
        date = (r.get("timestamp") or "n/a")[:10]
        rowlist.append(f'<tr><td>{label}</td><td>{conf}</td><td>{delta_txt}</td><td>{date}</td></tr>')
    parts.append('<div class="scroll"><table class="se"><thead><tr>'
                 '<th>Label</th><th>Verdict</th><th>Floor delta</th><th>Date</th>'
                 '</tr></thead><tbody>' + "".join(rowlist) + '</tbody></table></div>')
    parts.append('<p class="n">One row per experiment. Floor deltas are never summed '
                 'across labels.</p>')
    return "".join(parts)


def render_alerts(profile):
    parts = ['<h2>Alerts</h2>']
    if not profile:
        parts.append('<p class="nodata">NO DATA: no profile.json found.</p>')
        return "".join(parts)
    alerts = []
    sw = _leaf(profile, "behavior", "model_switch_session_share")
    if sw is not None and sw >= 0.20:
        alerts.append(f'{sw * 100:.0f}% of your sessions switched model mid-session and '
                      f'rebuilt their cache.')
    floor = _leaf(profile, "instruction", "startup_floor_share")
    if floor is not None and floor >= 0.30:
        alerts.append(f'Startup floor is {floor * 100:.0f}% of everything a session reads.')
    hit = _leaf(profile, "usage", "cache_hit_ratio_median")
    if hit is not None and hit < 0.5:
        alerts.append(f'Cache hit ratio median is {hit * 100:.0f}%, below the healthy range.')
    alerts = alerts[:3]
    if not alerts:
        parts.append('<div class="wins"><span class="win ok">&#10003; no active alerts</span></div>')
    else:
        parts.append('<div class="wins">'
                     + "".join(f'<span class="win bad">! {a}</span>' for a in alerts) + '</div>')
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
.hero3{display:grid;grid-template-columns:repeat(3,1fr);gap:13px;margin:16px 0 6px;}
@media(max-width:640px){.hero3{grid-template-columns:1fr;}}
.h3c{background:var(--panel);border:1px solid var(--line);border-radius:15px;padding:19px 19px 17px;}
.h3c.lead{background:linear-gradient(135deg,var(--panel2),var(--panel));}
.h3c .big{font-size:clamp(28px,6vw,44px);font-weight:750;line-height:1;letter-spacing:-.02em;}
.h3c .big.g{color:var(--good);} .h3c .big.a{color:var(--accent);} .h3c .big.w{color:var(--warn);}
.h3c .big.muted{color:var(--muted);font-size:20px;font-weight:640;}
.h3c .u{font-size:12.5px;color:var(--muted);margin-top:8px;line-height:1.5;}
.cpill{display:inline-block;font-family:var(--mono);font-size:9px;letter-spacing:.1em;text-transform:uppercase;padding:2px 8px;border-radius:20px;border:1px solid var(--line);margin-bottom:10px;color:var(--muted);}
.cpill.ver{color:var(--good);border-color:var(--good);}
.cpill.nat{color:var(--accent);border-color:var(--accent);}
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
           experiment_rows=None, plugin_cache_root=None):
    sv = savings_breakdown(sm)
    pp = pain_points(sessions)
    rx = prescriptions(sm, sessions)
    total_rx = sum(r["saving"] for r in rx)
    share = sm["first_request_share_median"]
    hit = sm["hit_ratio_median"]
    sub = sm["subagent_output_share"]
    usd = usd_res if (usd_res and usd_res.get("status") == "OK") else None

    parts = [f"<style>{CSS}</style>", '<div class="wrap">']
    parts.append(f'<div class="top">{SHIELD_SVG}<div>'
                 f'<p class="eyebrow">Token Shield</p>'
                 f'<h1>Save Claude Code tokens. Prove every saving.</h1></div></div>')
    parts.append(f'<p class="stamp">Measured {stamp}, over transcripts touched in the last '
                 f'{days:g} days. Every figure is read from the API usage counters, never '
                 f'estimated. Measured on this machine; the method is portable, these numbers '
                 f'are not.</p>')

    # THREE HONEST COLUMNS, never merged: what Token Shield PROVED (verified
    # before/after), what Claude Code's caching did NATIVELY, and what is still
    # OPPORTUNITY (estimated). Merging these is the exact dishonesty this exists
    # to avoid, so they sit side by side, each with its own confidence label.
    if verified and verified.get("experiments"):
        vbig = f'<span class="big g">{human(verified["floor_reduction"])}</span>'
        vu = (f'fewer startup tokens per call, proven across {verified["experiments"]} '
              f'before/after experiment(s)')
    else:
        vbig = '<span class="big muted">NONE YET</span>'
        vu = ('No verified saving yet. Apply one recommendation, then run an experiment '
              'to measure the before and after.')
    nat_usd = f' &nbsp;&middot;&nbsp; about ${usd["usd"]:,.0f} API-equivalent' if usd else ''
    parts.append(
        '<div class="hero3">'
        '<div class="h3c lead"><span class="cpill ver">Verified &middot; Token Shield</span>'
        f'<div>{vbig}</div><p class="u">{vu}</p></div>'
        '<div class="h3c"><span class="cpill nat">Native &middot; Claude Code</span>'
        f'<div><span class="big a">{human(sv["saved"])}</span></div>'
        f'<p class="u">token-units saved by Anthropic\'s automatic caching{nat_usd}. Not this '
        f'tool\'s doing, and it does not claim it.</p></div>'
        '<div class="h3c"><span class="cpill est">Opportunity &middot; estimated</span>'
        f'<div><span class="big w">{human(total_rx)}</span></div>'
        '<p class="u">token-units still addressable in your own sessions, estimated from the '
        'issues below.</p></div>'
        '</div>')

    # USD honesty line.
    if usd:
        unp = (f' {human(usd["unpriced_units"])} units ran on models not in the snapshot and '
               f'are left unpriced.' if usd.get("unpriced_units") else '')
        parts.append(f'<p class="usdline"><b>Dollars, honestly.</b> The native caching saving '
                     f'is about <b>${usd["usd"]:,.0f}</b> API-equivalent at list prices '
                     f'(snapshot {usd["snapshot"]}), priced at each model\'s own rate.{unp} On '
                     f'a subscription your bill did not drop by this; it is what the same '
                     f'tokens would cost at API prices.</p>')
    elif usd_res and usd_res.get("status") == "NO_PRICE_DATA":
        parts.append('<p class="usdline"><b>Dollars: NO PRICE DATA.</b> The pricing snapshot '
                     'is stale, so no dollar figure is shown. The token saving still stands.</p>')

    # v1.7 advisor surfaces. Each degrades to its own NO DATA state, never a
    # crash, when its source (profile.json, the experiment ledger, or
    # data/companions.json) is missing.
    cache_root = plugin_cache_root or os.path.expanduser("~/.claude/plugins/cache")
    parts.append(render_next_best_move(advise_result))
    parts.append(render_observed_pattern(profile))
    parts.append(render_recommendation_queue(advise_result, suppressed_n))
    parts.append(render_companions(companions_data, profile, cache_root))
    parts.append(render_experiment_history(experiment_rows or []))
    parts.append(render_alerts(profile))

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
    parts.append('<h2>Your top issues, ranked</h2>')
    if not rx:
        parts.append('<div class="pain"><div class="pain-item"><div class="rank">&#10003;</div>'
                     '<div class="t">No dominant issue measured<span class="tag">OK</span></div>'
                     '<div class="m">every session pattern is inside its healthy range</div>'
                     '<div class="fix">Keep the shield on and re-check monthly.</div></div></div>')
    else:
        pain = ['<div class="pain">']
        for i, r in enumerate(sorted(rx, key=lambda x: -x["saving"]), 1):
            impact = 'HIGH' if i == 1 else 'MEDIUM'
            lt = r.get("longterm", "")
            lt_html = f'<br><b class="lt">Long-term fix.</b> {lt}' if lt else ''
            pain.append(
                f'<div class="pain-item"><div class="rank">{i}</div>'
                f'<div class="t">{r["title"]}<span class="tag">{impact} impact</span>'
                f'<span class="cpill est" style="margin:0 0 0 8px">Estimated</span></div>'
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

    # NATIVE DETAIL, secondary: where the native saving comes from, so the hero
    # number is checkable rather than asserted.
    parts.append('<h2>Where the native saving comes from</h2>')
    umax = sv["unblocked"] or 1
    parts.append('<div class="compare">'
                 '<div class="col"><div class="barc"><div class="fill" '
                 f'style="width:100%;background:var(--shield)"></div></div>'
                 f'<div class="amt">{human(sv["unblocked"])}</div>'
                 '<div class="lbl">reads, uncached price</div></div>'
                 '<div class="col"><div class="barc"><div class="fill" '
                 f'style="width:{sv["paid"] / umax * 100:.1f}%;background:var(--good)"></div></div>'
                 f'<div class="amt">{human(sv["paid"])}</div>'
                 '<div class="lbl">reads, actually paid (0.1x)</div></div>'
                 '<div class="col"><div class="barc"><div class="fill" '
                 f'style="width:{sv["write_cost"] / umax * 100:.1f}%;background:var(--accent)"></div></div>'
                 f'<div class="amt">{human(sv["write_cost"])}</div>'
                 '<div class="lbl">cache writes (1.25x / 2x)</div></div></div>'
                 '<p class="n" style="margin-top:10px">Almost all of the saving is the gap '
                 'between the first two bars: history re-read from cache instead of '
                 'reprocessed. This is Anthropic\'s caching, shown so the hero number is '
                 'checkable, not so the tool can claim it.</p>')

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

    verified = None
    ledger = os.path.expanduser("~/.claude/token-shield/savings.jsonl")
    if os.path.exists(ledger):
        n = 0
        floor = 0
        with open(ledger, errors="ignore") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if r.get("confidence") == "VERIFIED" and r.get("floor_reduction_tokens"):
                    n += 1
                    floor += max(0, r["floor_reduction_tokens"])
        verified = {"experiments": n, "floor_reduction": floor}
    experiment_rows = load_experiment_rows(ledger)

    # v1.7 advisor surfaces: profile, advice, and the companion registry. Each
    # degrades to None on any failure, rather than take the whole render down.
    profile = None
    advise_result = None
    suppressed_n = 0
    try:
        import advisor as adv
        profile = load_profile(adv.PROFILE_PATH)
        if profile is not None:
            strategies = adv.load_strategies()
            treatments = adv.load_treatments()
            advise_result = adv.advise(profile, treatments, strategies)
            suppressed_n = suppressed_recommendation_count(adv, profile, treatments, strategies)
    except (OSError, ValueError, ImportError) as e:
        print(f"note: advisor skipped ({e})", file=sys.stderr)
    companions_data = load_companions(COMPANIONS_PATH)

    body = render(mt, sm, sessions, a.days, stamp, a.include_sessions, usd_res, verified,
                  profile=profile, advise_result=advise_result, suppressed_n=suppressed_n,
                  companions_data=companions_data, experiment_rows=experiment_rows)
    out_html = body if a.body_only else render_standalone(body)
    out = os.path.expanduser(a.out)
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    with open(out, "w") as f:
        f.write(out_html)
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
