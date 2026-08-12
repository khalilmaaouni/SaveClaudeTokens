# Roadmap

We built the smallest honest set that delivers the mission: measure token use and prove the saving. A Fable-tier judge ranked a product blueprint for value and mathematical soundness, and we passed on the sprawl. The test for any feature is one question: does it help Token Shield prevent, measure, attribute, or communicate a real token saving? If not, we do not build it.

## Shipped (1.5.0)

- **Experiment Mode.** A real before and after over the same window is the only thing that earns VERIFIED. It refuses the comparison across a schema change, a window mismatch, or thin data, and writes one record to a local proof ledger.
- **Honest per-model USD.** Dollars come from a dated snapshot in `data/pricing.json`, priced at each model's own rate. A model not in the snapshot is left unpriced, never priced at another model's rate. A stale snapshot degrades to NO PRICE DATA. Subscription usage is phrased as API-equivalent value, never "you saved $X".
- **Three-column dashboard.** VERIFIED, NATIVE, and OPPORTUNITY sit side by side and never merge, each with its own confidence label. Issue cards carry a painkiller, a medicine, a long-term fix, and the math.
- **One CLI.** `python3 scripts/cli.py` with four subcommands: summary, dashboard, experiment, prices. The scripts stay internal.
- **Distribution basics.** CI over the self-checks with a badge, an outcome-first README, a repository description and topics.

## Shipped (1.7.0)

- **Deterministic profiler and confidence labels.** MEASURED signals (cache rebuilds, startup floor, model switches) split from INFERRED patterns. Every finding now carries its confidence so you know what is proven versus pattern-based.
- **Quick Advisor.** Ranked action cards with full drawback disclosure, treatment memory for learned patterns on your machine, and do-nothing as a valid answer when the gain is marginal.
- **Companion registry.** Curated verified sources for tools that pair well with Token Shield (caveman, ponytail, token-saver, and mentions of related tools).
- **Monthly report and onboarding.** Session-end telemetry hook (opt-in only, no hooks by default) feeds the advisor and monthly report. No traces left on uninstall.
- **Experiment Mode v2.** Message-timestamp cohorts and config fingerprints for tighter before/after matching; NOT_PROVEN downgrade when data is thin; no cross-label summing.
- **Meter honesty.** Skipped files and lines are now counted and reported, so you see what the meter actually observed.

## Deferred, with the reason

- **Protect Mode and its four blocking hooks** (cold-cache, oversized-read, duplicate, output). The biggest build and the biggest risk. It reverses the no-hooks-by-default trust position before the measurement story has shipped, and its attribution math as blueprinted was unsound: a prevented event is a counterfactual, so it is estimated, never verified. Flip condition: revisit only after the first real VERIFIED experiment, and then one guard at a time, cold-cache first.
- **Tokens per accepted result.** Needs an acceptance-signal subsystem (tests pass, PR merged, user marks accepted) with weak signal availability. Flip condition: a reliable acceptance signal exists.
- **Share card and README badge generator.** Worth building once there is a VERIFIED number to share. Flip condition: Experiment Mode has produced real verified results.
- **Full intervention ledger.** Folded into Experiment Mode, which is its only honest producer today.
- **v1.8 deep layer (Fable advisor subagent, semantic optimizer v2).** Gated on the first VERIFIED experiment on this machine, per the ratified acceptance gate.

## Passed on

- **Status line, the 7-Day Diet, Show Your Shield community, case studies.** Growth and marketing, not code. Discussions is a checkbox, not a build.
- **AI analysis of the dashboard.** Spending model tokens to explain how to save model tokens breaks the product's whole point. The skill already handles deeper reasoning on demand.

## The one decision we recorded

We reversed the deliberate "ship no price table" stance. It is sound only with four guards, all now in place: a dated snapshot, a staleness cutoff that degrades to NO PRICE DATA, per-model rows with an unpriced bucket, and API-equivalent wording for subscription usage. Missing any one, we keep the no-price stance.
