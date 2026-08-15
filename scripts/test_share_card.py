#!/usr/bin/env python3
"""Calibrated checks for share_card.py, the proof-ledger share card.

    python3 scripts/test_share_card.py

Calibrated (defect reinjected, confirmed red, then reverted to green):
  - refusal bypass: widened QUALIFYING_CONFIDENCE to also accept NOT_PROVEN,
    which rendered a card off a NOT_PROVEN-only fixture instead of refusing;
    the NOT_PROVEN-only test caught it.
"""

import tempfile

import share_card as sc


def check(name, cond):
    print(("ok  " if cond else "FAIL ") + name)
    assert cond, name


def test_qualifying_verified_row_renders_with_label_on_the_face():
    rows = [{"label": "shrink-claude-md", "confidence": "VERIFIED",
             "timestamp": "2026-08-05T00:00:00+00:00",
             "floor_reduction_tokens": 5000}]
    row, reason = sc.select_card_row(rows)
    check("a qualifying VERIFIED row is selected, not refused", row is not None and reason is None)

    text = sc.render_text_card(row)
    html = sc.render_html_card(row)
    check("the label prints on the text card face", "shrink-claude-md" in text)
    check("the confidence label prints on the text card face", "VERIFIED" in text)
    check("the label prints on the html card face", "shrink-claude-md" in html)
    check("the confidence label prints on the html card face", "VERIFIED" in html)


def test_qualifying_measured_row_renders_with_label_on_the_face():
    rows = [{"label": "prune-plugins", "confidence": "MEASURED",
             "timestamp": "2026-08-05T00:00:00+00:00",
             "floor_reduction_tokens": 1200}]
    row, reason = sc.select_card_row(rows)
    check("a qualifying MEASURED row is selected, not refused", row is not None and reason is None)
    text = sc.render_text_card(row)
    check("the label prints on the face", "prune-plugins" in text)
    check("the MEASURED label itself prints on the face", "MEASURED" in text)


def test_empty_ledger_refuses_with_a_reason():
    row, reason = sc.select_card_row([])
    check("no row is selected from an empty ledger", row is None)
    check("a reason string is printed, not a silent failure", bool(reason))


def test_not_proven_only_refuses_with_reason_and_never_renders():
    rows = [{"label": "claude-md-diet", "confidence": "NOT_PROVEN",
             "timestamp": "2026-08-13T20:54:46+00:00",
             "floor_reduction_tokens": 3000,
             "reasons": ["only 2 sessions after the change, need 5"]}]
    row, reason = sc.select_card_row(rows)
    check("a NOT_PROVEN-only ledger never selects a row", row is None)
    check("the refusal names NOT_PROVEN as the reason", "NOT_PROVEN" in reason)
    check("the refused label is never mentioned in the reason as if it qualified",
          "claude-md-diet" not in reason)


def test_mixed_ledger_never_lets_not_proven_reach_the_card():
    rows = [
        {"label": "claude-md-diet", "confidence": "NOT_PROVEN",
         "timestamp": "2026-08-13T20:54:46+00:00", "floor_reduction_tokens": 9999},
        {"label": "shrink-claude-md", "confidence": "VERIFIED",
         "timestamp": "2026-08-05T00:00:00+00:00", "floor_reduction_tokens": 5000},
    ]
    row, reason = sc.select_card_row(rows)
    check("the VERIFIED row is the one selected", row is not None and row["label"] == "shrink-claude-md")
    text = sc.render_text_card(row)
    check("the NOT_PROVEN label never appears on the rendered card", "claude-md-diet" not in text)


def test_best_qualifying_row_wins_when_no_label_given():
    rows = [
        {"label": "small-win", "confidence": "VERIFIED",
         "timestamp": "2026-08-01T00:00:00+00:00", "floor_reduction_tokens": 500},
        {"label": "big-win", "confidence": "VERIFIED",
         "timestamp": "2026-08-02T00:00:00+00:00", "floor_reduction_tokens": 8000},
    ]
    row, reason = sc.select_card_row(rows)
    check("the larger floor reduction wins the card by default", row["label"] == "big-win")


def test_explicit_label_selects_that_labels_latest_record():
    rows = [
        {"label": "shrink-claude-md", "confidence": "VERIFIED",
         "timestamp": "2026-08-01T00:00:00+00:00", "floor_reduction_tokens": 1000},
        {"label": "shrink-claude-md", "confidence": "VERIFIED",
         "timestamp": "2026-08-10T00:00:00+00:00", "floor_reduction_tokens": 4000},
    ]
    row, reason = sc.select_card_row(rows, label="shrink-claude-md")
    check("the latest record for the label wins, not the first", row["floor_reduction_tokens"] == 4000)


def test_cli_refuses_on_a_fixture_ledger_with_only_not_proven():
    with tempfile.TemporaryDirectory() as d:
        ledger = f"{d}/savings.jsonl"
        with open(ledger, "w") as f:
            f.write('{"label": "x", "confidence": "NOT_PROVEN", '
                    '"timestamp": "2026-08-13T00:00:00+00:00", '
                    '"floor_reduction_tokens": 100}\n')
        import sys
        argv = sys.argv
        sys.argv = ["share_card.py", "--ledger", ledger]
        try:
            rc = sc.main()
        finally:
            sys.argv = argv
    check("main() exits nonzero when nothing qualifies", rc != 0)


def test_a_later_not_proven_supersedes_an_earlier_verified():
    """The card is the artifact designed to LEAVE THIS MACHINE, so a claim a
    re-run could not reproduce must never travel on it.

    RED before the fix: the card rendered "+24,000 startup tokens/call,
    fewer, proven 2026-07-01" even though the newest record for that label
    is a NOT_PROVEN from six weeks later. The cause was ordering: every
    reader filtered to VERIFIED BEFORE picking the latest row, so a failed
    re-run simply vanished instead of superseding.

    The pre-existing latest-wins test could not catch this because both of
    its rows were VERIFIED, which is the shape the defect hides behind."""
    rows = [{"label": "claude-md-diet", "confidence": "VERIFIED",
             "timestamp": "2026-07-01T00:00:00+00:00",
             "floor_reduction_tokens": 24000},
            {"label": "claude-md-diet", "confidence": "NOT_PROVEN",
             "timestamp": "2026-08-14T00:00:00+00:00",
             "floor_reduction_tokens": None}]
    row, reason = sc.select_card_row(rows)
    check("a superseded VERIFIED claim is refused, not published",
          row is None and reason is not None)

    # The mirror case: a genuine newer VERIFIED must still publish, so the
    # fix cannot be "refuse whenever any NOT_PROVEN exists".
    rows_ok = [{"label": "x", "confidence": "NOT_PROVEN",
                "timestamp": "2026-07-01T00:00:00+00:00",
                "floor_reduction_tokens": None},
               {"label": "x", "confidence": "VERIFIED",
                "timestamp": "2026-08-14T00:00:00+00:00",
                "floor_reduction_tokens": 9000}]
    row_ok, reason_ok = sc.select_card_row(rows_ok)
    check("a newer VERIFIED still publishes", row_ok is not None and reason_ok is None)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
