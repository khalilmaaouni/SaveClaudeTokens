#!/usr/bin/env python3
"""
share_card.py: a share card for one proven Token Shield result.

WHY A SEPARATE CARD AND NOT A DASHBOARD SCREENSHOT
The dashboard shows the whole picture, warts included. A share card is a
single claim meant to leave this machine, so it holds itself to a higher
bar: only VERIFIED (a closed experiment proved it) and MEASURED (counted on
this machine) rows ever reach the card face, and the label that earned the
row prints ON the card, never stripped off. NOT_PROVEN is a real finding,
but it is not a claim, so it never appears on a card. With nothing
qualifying, the command REFUSES and prints why, rather than rendering an
empty or misleading card.

No model calls. The card is built from one record already sitting in the
proof ledger (experiment.py's LEDGER, ~/.claude/token-shield/savings.jsonl
by default); nothing here re-derives a number that ledger did not already
measure.

USAGE
  python3 share_card.py                  # best qualifying record, if any
  python3 share_card.py --label <label>  # a specific label's record
  python3 share_card.py --ledger PATH    # a fixture ledger, for testing
  python3 share_card.py --out card.html  # also write the HTML card to disk
"""

import argparse
import json
import os
import sys

import experiment as ex
import token_shield as ts

import metrics as met
import formatting as fmt
QUALIFYING_CONFIDENCE = {"VERIFIED", "MEASURED"}


def _read_ledger(path):
    if not os.path.exists(path):
        return []
    records = []
    with open(path, errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # sbe: allow-silent a corrupt ledger line is skipped so one bad line cannot blank the card
    return records


def select_card_row(rows, label=None):
    """Pick the one ledger row a share card renders, or refuse with a
    reason. Returns (row, None) or (None, reason).

    Only VERIFIED and MEASURED rows qualify; this project's own confidence
    taxonomy treats NOT_PROVEN as a real, honest finding, not a claim, so it
    is never card material. Among qualifying rows, a repeated label
    collapses to the latest by timestamp: the same "latest record per label
    wins" rule this project applies everywhere else a ledger label is read
    (experiment.aggregate_by_label, token_shield.verified_by_label).

    With no `label`, the row with the largest floor_reduction_tokens wins
    (the card's whole point is to show the best proven result on file).
    """
    # Newest row per label FIRST (the shared rule in token_shield), THEN the
    # confidence filter. The order used to be reversed here, which meant a
    # later NOT_PROVEN run did not supersede an earlier VERIFIED one and this
    # card kept printing "proven" for a claim the newest run could not
    # reproduce. This card is the artifact designed to leave the machine, so
    # that was the worst place in the codebase for this defect to live.
    latest = {}
    for lbl, r in met.latest_row_per_label(rows).items():
        if r.get("confidence") not in QUALIFYING_CONFIDENCE:
            continue
        fr = r.get("floor_reduction_tokens")
        if isinstance(fr, bool) or not isinstance(fr, (int, float)):
            continue
        latest[lbl] = ((r.get("timestamp") or "", 0), r)

    if not latest:
        if not rows:
            return None, "no readable ledger record"
        not_proven = sum(1 for r in rows if r.get("confidence") == "NOT_PROVEN")
        if not_proven == len(rows):
            return None, (f"ledger holds only NOT_PROVEN record(s) ({not_proven}); "
                          f"nothing VERIFIED or MEASURED to show")
        return None, "no VERIFIED or MEASURED record in the ledger"

    if label is not None:
        if label not in latest:
            return None, f"no VERIFIED or MEASURED record for label {label!r}"
        return latest[label][1], None

    best = max(latest.values(), key=lambda kv: kv[1]["floor_reduction_tokens"])[1]
    return best, None


def render_text_card(row):
    lbl = row.get("label") or "(unlabeled)"
    conf = row["confidence"]
    fr = row["floor_reduction_tokens"]
    tail = "fewer" if fr >= 0 else "MORE (regression)"
    date = str(row.get("timestamp") or "n/a")[:10]
    return "\n".join([
        f"TOKEN SHIELD -- {conf}",
        lbl,
        f"{fr:+,} startup tokens/call, {tail}",
        f"proven {date}",
    ])


def render_html_card(row):
    lbl = fmt.esc(row.get("label") or "(unlabeled)")
    conf = row["confidence"]
    fr = row["floor_reduction_tokens"]
    color = "var(--good)" if fr >= 0 else "var(--warn)"
    tail = "fewer" if fr >= 0 else "MORE (regression)"
    date = fmt.esc(str(row.get("timestamp") or "n/a")[:10])
    return (
        f'<!doctype html><html><head><meta charset="utf-8">'
        f'<title>Token Shield share card</title><style>{ts.CSS}'
        f'.card{{max-width:420px;margin:40px auto;background:var(--panel);'
        f'border:1px solid var(--line);border-radius:16px;padding:28px;'
        f'text-align:center;}}'
        f'.card .big{{font-size:46px;font-weight:750;color:{color};margin:10px 0 0;}}'
        f'.card .sub{{font-size:13px;color:var(--muted);margin-top:6px;}}'
        f'</style></head><body><div class="card">'
        f'{ts.SHIELD_SVG}{ts._cpill(conf)}'
        f'<div class="big">{fr:+,}</div>'
        f'<div class="sub">startup tokens/call, {tail}</div>'
        f'<h3>{lbl}</h3>'
        f'<p class="sub">proven {date}</p>'
        f'</div></body></html>'
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--ledger", default=ex.LEDGER)
    ap.add_argument("--label", default=None, help="a specific ledger label; default: the best")
    ap.add_argument("--out", default=None, help="write the HTML card here too")
    a = ap.parse_args()

    rows = _read_ledger(a.ledger)
    row, reason = select_card_row(rows, label=a.label)
    if row is None:
        print(f"REFUSED: {reason}", file=sys.stderr)
        return 2

    print(render_text_card(row))
    if a.out:
        with open(a.out, "w") as f:
            f.write(render_html_card(row))
        print(f"html card written: {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
