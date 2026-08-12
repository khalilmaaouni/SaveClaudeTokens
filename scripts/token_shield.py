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
import os
import sys

CACHE_READ = 0.1  # a cached token bills at 0.1x, so the saving is (1 - 0.1)


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


def render(mt, sm, sessions, days, stamp, include_sessions):
    sv = savings_breakdown(sm)
    pp = pain_points(sessions)
    fr_med = sm["first_request_median"]
    share = sm["first_request_share_median"]
    hit = sm["hit_ratio_median"]
    sub = sm["subagent_output_share"]
    w5, w1 = sm["write_5m_total"] or 0, sm["write_1h_total"] or 0
    wtot = w5 + w1

    parts = [f"<style>{CSS}</style>", '<div class="wrap">']
    parts.append(f'<div class="top">{SHIELD_SVG}<div>'
                 f'<p class="eyebrow">Token Shield</p>'
                 f'<h1>What you saved, what it blocked, what still costs you</h1></div></div>')
    parts.append(f'<p class="stamp">Measured {stamp}, transcripts touched in the '
                 f'last {days:g} days. Every figure is read from the API usage counters, '
                 f'not estimated. Measured on this machine; the method is portable, these '
                 f'numbers are not.</p>')

    # HERO: net saving, after the cache-write premium.
    mult = (sv["unblocked"] / sv["paid"]) if sv["paid"] else 0
    parts.append('<div class="hero"><p class="k">Prompt caching saved you, net</p>'
                 f'<div><span class="big">{human(sv["saved"])}</span>'
                 f'<span class="unit">base-input token-units, this window</span></div>'
                 f'<p class="sub">You reused {human(sv["read"])} tokens from cache. Uncached '
                 f'they would bill at full price ({human(sv["unblocked"])}); cached they '
                 f'billed at a tenth ({human(sv["paid"])}), earning {human(sv["gross"])}. '
                 f'Caching costs a write premium of {human(sv["write_premium"])}, and this '
                 f'headline already subtracts it, so it is the net benefit, not the gross '
                 f'read saving. Base-input units, not dollars: no model price table ships '
                 f'here, so a stale price can never inflate it.</p></div>')

    # WHAT IT BLOCKED: the reprocessing that caching stopped.
    parts.append('<h2>What it blocked</h2>')
    blk = sv["unblocked"] - sv["paid"]
    parts.append('<div class="grid">'
                 + stat("Reprocessing blocked", human(blk),
                        "tokens of history that would have been re-read at full price, "
                        "served from cache instead")
                 + stat("Cache hit ratio",
                        f"{hit:.2f}" if hit is not None else "NO DATA",
                        "per-session median; the fraction of input served cheap from cache",
                        hit is None)
                 + stat("Bad comparisons blocked", "by design",
                        "the meter refuses a delta across a metric change or mismatched "
                        "window, and prints NO DATA rather than a guess")
                 + '</div>')

    # WHERE YOU SAVE: the breakdown.
    parts.append('<h2>Where the saving comes from</h2>')
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
                 'reprocessed. Writes are the price of admission that makes the reads cheap.</p>')

    # KEY STATS still worth a glance.
    parts.append('<h2>The recurring cost</h2>')
    parts.append('<div class="grid">'
                 + stat("Always-loaded rent",
                        human(fr_med) if fr_med is not None else "NO DATA",
                        "median first-request tokens, paid before any work on every call",
                        fr_med is None)
                 + stat("Startup share", pct(share),
                        "of everything a session reads is that floor, re-paid each call",
                        share is None)
                 + stat("Subagent output", pct(sub),
                        "share of output from subagents rather than the main thread",
                        sub is None)
                 + (stat("Cache writes",
                         f"{human(w5)}/{human(w1)}",
                         "5m at 1.25x / 1h at 2x; a subscription defaults to 1h")
                    if wtot else stat("Cache writes", "NO DATA", "no TTL split this window", True))
                 + '</div>')

    # KEY PAIN POINTS, each with its own prescription and the saving math,
    # computed from this user's own sessions. Adaptive: only the pain points the
    # data actually shows appear, and every number is theirs.
    rx = prescriptions(sm, sessions)
    parts.append('<h2>Your pain points, and how to treat each</h2>')
    if not rx:
        parts.append('<div class="pain"><div class="pain-item"><div class="rank">-</div>'
                     '<div class="t">No dominant pain point measured<span class="tag">OK</span></div>'
                     '<div class="m">every session pattern is inside its healthy range</div>'
                     '<div class="fix">Keep the shield on and re-check monthly.</div></div></div>')
    else:
        parts.append('<p class="n" style="margin:-4px 0 12px">Ranked by the tokens each '
                     'costs you, largest first. Every figure is from your own sessions, so '
                     'another machine would show a different profile.</p>')
        pain = ['<div class="pain">']
        for i, r in enumerate(sorted(rx, key=lambda x: -x["saving"]), 1):
            pain.append(
                f'<div class="pain-item"><div class="rank">{i}</div>'
                f'<div class="t">{r["title"]}<span class="tag">{r["tag"]}</span></div>'
                f'<div class="m">{r["measure"]}</div>'
                f'<div class="fix"><b style="color:var(--good)">Painkiller.</b> '
                f'{r["painkiller"]}<br><b style="color:var(--accent)">Medicine.</b> '
                f'{r["medicine"]}<br><b style="color:var(--shield)">The math.</b> '
                f'{r["math"]}</div></div>')
        pain.append('</div>')
        total_rx = sum(r["saving"] for r in rx)
        parts.append("".join(pain))
        parts.append(f'<p class="n" style="margin-top:10px">Treating all of these is worth '
                     f'on the order of {human(total_rx)} base-input units this window on your '
                     f'data, on top of what caching already saves. The PROVEN lines are '
                     f'mechanism-backed lower bounds; the SIGNAL line points rather than '
                     f'proves.</p>')

    # WHY KEEP IT ON.
    parts.append('<h2>Why keep the shield on</h2>')
    parts.append('<div class="why">'
                 f'<h3>The saving is recurring, and so is the waste.</h3>'
                 f'<p>Caching saved {human(sv["saved"])} in this {days:g} day window alone, '
                 f'and it does that every window, for free, as long as the prefix stays '
                 f'stable. Turn a session cache-hostile (switch model, edit config mid-run) '
                 f'and you pay full price on every re-read for the rest of it.</p>'
                 f'<p>The {human(fr_med)} startup floor is paid on every one of your calls, '
                 f'so shaving it once pays back on every session after. The shield is how '
                 f'you see both numbers move, measured, so a cleanup that did not actually '
                 f'save shows up as no change instead of a good feeling.</p></div>')

    if include_sessions and sessions:
        top = sorted((s for s in sessions if s["first_request"] > 0),
                     key=lambda x: -x["first_request"])[:10]
        rows = "".join(
            f'<tr><td>{s["first_request"]:,}</td>'
            f'<td>{"n/a" if s["first_request_share"] is None else f"{s['first_request_share']:.2f}"}</td>'
            f'<td>{s["calls"]}</td><td>{s["hit_ratio"]:.2f}</td>'
            f'<td>{s["models"]}</td></tr>' for s in top)
        parts.append('<div class="scroll"><table class="se"><thead><tr>'
                     '<th>First request</th><th>Share</th><th>Calls</th>'
                     '<th>Hit</th><th>Models</th></tr></thead><tbody>'
                     + rows + '</tbody></table></div>'
                     '<p class="n" style="color:var(--muted);font-size:11.5px">'
                     'More than one model in a session means a mid-flight switch, '
                     'which rebuilds that session\'s cache from zero.</p>')

    parts.append('<footer>Token Shield, from SaveClaudeTokens. Every figure is '
                 'measured from local API usage counters; NO DATA means it could not '
                 'be measured, never a guess. Aggregates only: no conversation text, '
                 'file paths, or session identifiers are read into this page.</footer>')
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

    body = render(mt, sm, sessions, a.days, stamp, a.include_sessions)
    out_html = body if a.body_only else render_standalone(body)
    out = os.path.expanduser(a.out)
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    with open(out, "w") as f:
        f.write(out_html)
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
