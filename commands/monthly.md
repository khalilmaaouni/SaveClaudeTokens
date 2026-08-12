---
name: monthly
description: Generate and print the Token Shield monthly report -- usage, verified improvements, native caching benefit, top issues, and one addressable opportunity, all measured or clearly labeled estimated. Triggers include monthly report, month in review, last month's report, token shield month.
---

Run the monthly report generator and print its output. Never invent a number that is not in the script's own output.

Steps:

1. Work out which month the user wants. If they named one ("July", "last month", "2026-07"), pass it as `--month YYYY-MM`. If they did not say, leave `--month` off; the script defaults to the previous calendar month.

2. Run it:

   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/report.py` (add `--month YYYY-MM` if the user named a month)

   If the report file for that month is missing, the script writes it fresh on this run: there is nothing extra to do. If a report for that month already exists on disk and the user just wants to see it, running the command again regenerates it from the same measured counters, so re-running is always safe.

3. Print the report exactly as the script wrote it: Usage (MEASURED), Verified improvements (VERIFIED), Native caching benefit (NATIVE), Top issues, Addressable opportunity (ESTIMATED), What did not work, Next month. Keep every section separate the way the script renders them: a VERIFIED figure and an ESTIMATED figure never belong in the same sentence, because they answer different questions (one is proven by a before/after experiment, the other is a pattern-based guess).

4. If the script exits 2 with `NO DATA: no transcripts found under <root>`, say so plainly and suggest running a few sessions first, or checking `--root` if transcripts live somewhere non-default.

5. Tell the user where the file landed (the path the script printed, default `~/.token-shield/reports/YYYY-MM.md`) so they can keep it or paste it elsewhere.

Never present a "Next month" recommendation as if it were already a saving; it is a recommendation, and it only becomes a saving once an experiment proves it (`/token-shield:advisor`, then `experiment.py start`).
