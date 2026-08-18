# Cloud Cost Shield: a usage chart is not an invoice

Token Shield exists because Claude Code spend is invisible until measured. This chapter covers the sibling trap: a cloud provider's metered-usage page that LOOKS like a bill and is not one. It was written after a real incident on 2026-08-16 and every number in the incident section was read off the provider's own pages that morning.

## The incident, one paragraph

A GitHub personal account on the Free plan showed a "Metered usage" chart climbing past $850 for the first half of August 2026. The account owner, who had never added a payment method, read it as a surprise bill and prepared to dispute it. The verified truth, from GitHub's own billing Overview page: gross metered usage $864.61, included-usage discounts $864.61, next payment due: none, payment history: "You have not made any payments." Billed amount: $0.00. The chart plots the list-price VALUE of compute the free tier gave away (public-repository Actions runs plus 2,000 included private-repo minutes), then discounts all of it. Nothing was owed, and with no payment method and $0 stop-usage budgets on every product, nothing could ever have been charged.

## Why the misread happens to anyone

- The chart has a dollar axis and the word "usage", and the billed-versus-gross split only appears in a hover tooltip.
- The warning emails count MINUTES, not money ("You have used 90% of the Actions minutes"), so there is no dollar anywhere until the chart shocks you.
- Quota alerts can arrive while you sleep; in the incident the 90% and 100% alerts landed in the same minute, at 1:17 AM local time.
- The 100% email says you WILL be billed for overage "unless a $0 budget is set", which reads as an existing debt even when the $0 budget is already in place and blocking everything.
- Runs failing with a message about having no money left means the free quota is exhausted and usage is BLOCKED, which is the opposite of being charged.

## The reading order, before any panic

1. Billing Overview, the "Next payment due" card. A dash or $0 with no date means nobody is charging you. This single card outranks every chart.
2. Payment history. "You have not made any payments" plus no card on file means nothing was ever collected and nothing can be.
3. Hover one day on the usage chart. Read the three lines: Gross, Billed, Discount. Billed is the only line that is money.
4. Budgets and alerts. A $0 budget with "Stop usage: Yes" per product means overage is structurally blocked, not accruing.
5. Only if Billed is nonzero or a payment exists: now it is a real billing question. Politely request a one-time adjustment through the provider's support for unintended automated usage; first-time runaway CI requests are routinely granted. Accusations reduce the success rate; evidence raises it.

## The preventive posture for a free account

- Never add a payment method to an account meant to stay free. It is the load-bearing wall: with no card, overage cannot collect.
- Set a $0 budget with stop-usage on every billable product (Actions, Codespaces, Packages, Git LFS, AI credits). On card-less accounts these may already exist; verify rather than assume.
- Disable Actions per repository unless a repository has a deliberate, named reason to build in the cloud. Re-enabled workflows should trigger manually (workflow_dispatch), never on every push.
- Pushing code is free on every plan. Backups, checkpoint pushes, and history live on the free tier untouched. What costs money is compute triggered BY pushes, so kill the trigger, keep the push.
- Verification belongs in local, host-neutral scripts the repository carries. A cloud CI run then merely confirms what a local run already proved, on deliberate occasions (release candidates, host-adapter changes), not on every commit.
- Automation multiplies triggers. Overnight agent sessions that push at every green checkpoint are exactly how 1,193 workflow runs happen in 15 days without a human noticing. The push cadence is healthy; the per-push cloud trigger is the defect.

## The audit

`scripts/github_cost_guard.py` audits the posture drift this chapter exists to prevent:

```bash
python3 scripts/github_cost_guard.py
```

It lists every repository visible to the authenticated `gh` CLI and reports whether Actions is disabled (OK) or has come back on (WARN), then attempts the month's billed-versus-gross summary from the billing API. Absent evidence is printed as NO-DATA with the command that would produce it, and NO-DATA is never a pass. Exit codes: 0 all OK, 1 any WARN, 2 NO-DATA at the top level.

## What this chapter does not claim

The page layouts, email wording, and default budget behavior described here were read on 2026-08-16 and can change on the provider's side without notice. The reading order and the posture are the durable content: the money question is answered by "amount due" and "payments made", never by a usage chart. Other providers (cloud compute, LLM APIs, storage) present the same trap with different words; the same reading order applies.
