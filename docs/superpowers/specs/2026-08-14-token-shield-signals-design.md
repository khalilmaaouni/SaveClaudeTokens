# Token Shield Signals: the anonymized waste-intelligence program

Status: DESIGN APPROVED by the founder 2026-08-14 (question windows): aggregates only under a frozen public schema; a minimal owned endpoint; value returned through give-to-get benchmarks, a public quarterly report, and product priors; no direct monetization; maintenance cost kept near zero. Build gated behind the free core's 1.8.0; sequencing alongside Fleet decided at that boundary.

## Goal

Learn, across every consenting instance, WHY tokens get wasted (the classes of mistakes, errors, and overspend that could have been avoided) so the product's defaults, advice rankings, and truth registry improve for everyone. Never learn WHAT any user is doing.

## The promise, stated the way the trust page will state it

- Off by default, forever. The product is fully functional with Signals off.
- What can ever leave the machine is a frozen, public, versioned whitelist schema of coded categories. Anything not in the schema cannot be sent, by construction: the client serializes FROM the whitelist, never filters a larger object down.
- No free text, no prompts, no code, no file paths, no repo names, no user names, no stable machine ids, no timestamps finer than a day.
- You can read every byte before it goes: reports accumulate in a local outbox, and the preview command shows the exact payload. The first send never happens without an explicit recorded consent.
- We do not sell raw data. There is no deeper tier for anyone, at any price. Aggregates published to everyone are the same aggregates we use ourselves.

## What a signals report contains (the whole schema, summarized)

One report per machine per calendar day, aggregates only:

- schema_version.
- waste_shares: share of tokens by waste class (tool_output_noise, duplicate_reads, verbose_output, startup_rent, cache_cold_rebuilds, overbuild, routing_mismatch, unknown), each quantized to 5 percent buckets. unknown stays unknown, never redistributed.
- error_classes: counts by coded class (tool_failure, retry_loop, correction_turn, abandoned_task), quantized to bands (0, 1-5, 6-20, 21+).
- overspend_markers: counts by coded class (model_switch_rebuild, oversized_read, repeated_transcript_scan), same bands.
- environment coarse facts: platform (mac/linux/windows), Claude Code minor version, model family mix as shares (never exact counts), token-shield version.
- treatment_outcomes: for each treatment id from the public registry, an enum (helped, no_change, regressed, rolled_back) when a closed experiment exists for it, with the label (VERIFIED, NOT_PROVEN) and the effect size bucketed. Only registry ids can appear; a private or unknown treatment reports as other.
- a fresh random submission id per report, generated at send time, never stored locally after send, never reused: two reports from the same machine are unlinkable to each other by design.

Deliberately absent: session counts precise enough to fingerprint, timezones, locale, hardware, org names, and any field with unbounded values.

## Consent

- Personal: `signals on` runs the preview first, shows the exact schema and a real sample payload, then records consent (date, schema version) locally. `signals off` stops everything and empties the outbox. Consent is per schema version: a schema change re-asks.
- Fleet: double opt-in. The org profile may enable Signals for the fleet, AND each machine still shows its one-time notice with the payload preview. An org cannot silently enroll a developer.

## Architecture: never overwhelmed, near-zero cost

- Local first: the existing telemetry ledger already aggregates locally. A daily rollup writes one small JSON to ~/.token-shield/signals/outbox/. The outbox is capped (90 files); older unsent reports are dropped oldest-first, stated in the doc, because Signals is sampling, not accounting.
- Send: opt-in machines flush the outbox at most once daily to ONE owned HTTPS endpoint (a Cloudflare Worker writing raw JSON into an R2 bucket; free tier covers any plausible volume). The Worker validates against the schema, enforces a size cap, and refuses anything else. Published server policy: IP addresses are not stored; only the validated JSON body lands in the bucket. Honest limit, stated on the trust page: any HTTPS submission necessarily reveals a network address in transit to the receiving edge; we refuse to store it, and an IP-blinding relay is a roadmap line for the strongest claim.
- Aggregation: a monthly script (run by us, locally, from the bucket) produces public aggregates with a k-anonymity floor: no published cell derived from fewer than 20 distinct submissions. The published file data/signals-aggregates.json ships in the public repo.
- Benchmarks are CLIENT-SIDE: the dashboard compares YOUR local profile against the published aggregates file. No live API, no per-user server state, nothing to scale, nothing to breach. This is how maintenance stays near zero.

## The value loop

- For contributors: the benchmark panel (your waste profile versus the cohort median, computed locally from the public aggregates). Worded honestly: benchmarks are powered by contributors; join to see where you stand.
- For everyone: the public quarterly State of AI Coding Waste report, generated from the same aggregates, k-floor enforced. This is the founder's lead magnet and the community's shared knowledge.
- For the product: waste-class prevalence tunes default advice rankings and prioritizes which treatments get built and vetted next, stated openly in the roadmap.
- For companies using it: their own fleet data stays theirs (Fleet store, org-owned); Signals adds the outside-world comparison their FinOps team cannot get anywhere else.
- Bolt-on futures (roadmap lines only, all from the same k-anonymous pool, never a deeper tier): industry benchmark reports, spend-forecast tooling, enterprise advisory built on the relationship. No raw data product, ever.

## Threat model, and what defeats each threat

- Us turning curious: the schema cannot carry content; submissions are unlinkable to each other; the client is open source, so the claim is auditable, not trusted.
- A breach of our bucket: the attacker gets the stored per-report stream, one row per day per machine, platform and version fields included, not the published k-anonymous aggregates; this is why the reports themselves must carry nothing identifying.
- The org admin spying on developers: fleet Signals is double opt-in and the payload preview is identical for every party; the org's own Fleet store is governed by the org, and Signals adds nothing person-level to it.
- A network observer: sees an HTTPS connection to a known endpoint, contents encrypted; timing reveals at most that a machine runs Token Shield.
- Correlation and fingerprinting: quantized buckets, banded counts, day resolution, no rare free-form values (unbounded fields do not exist in the schema), and the k-floor on anything published.
- Poisoning (someone spamming fake reports to skew benchmarks): size caps and rate limits at the edge; the monthly aggregation trims outliers and states the trimming rule in the published report's method section.

## What Signals is NOT

Not usage analytics, not tracking, not a growth funnel, not required for any feature that works locally, not sellable as raw data, and never a backdoor: no field may be added to the schema without a version bump that re-asks every contributor's consent.

## Testing strategy

Calibrated tests throughout: whitelist serialization (a field outside the schema cannot leave, proven by injecting one and watching the send refuse), quantization boundaries, outbox cap, consent gating (no consent record means the send path refuses, calibrated), schema-version re-ask, fixture Worker (python http.server in tests) validating refusals, and a fingerprinting regression test proving two consecutive reports share no linkable value.

## Rollout

Phase S1 schema plus local rollup, outbox, preview (client-only, zero network). S2 consent flow plus send path against a fixture server. S3 the real Worker and bucket, deployed by the founder from a one-page doc (infra/signals-worker/). S4 published aggregates file plus the client-side benchmark panel. S5 the quarterly report generator. Implementation plan: docs/superpowers/plans/2026-08-14-token-shield-signals-plan.md. S1 and S2 are trust-changing: each gets an independent refuter briefed to REFUTE on privacy grounds specifically, and a cross-family refuter before any public release of the endpoint, per the standing cross-family law for safety claims.
