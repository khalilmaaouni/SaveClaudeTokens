# Token Shield Fleet: enterprise edition design

Status: DESIGN APPROVED by the founder 2026-08-14 (question window). Build gated: nothing in this document starts before the free core ships 1.8.0. Founder intent: lead magnet first, sellable later; architecture must stay clean enough to charge for without a rebuild.

## Goal

Give an organization the same honest token-efficiency engine the free core gives one developer, org-wide, with three commands and zero infrastructure. Free core: one developer, one machine, free forever, nothing personal ever paywalled. Fleet: aggregation, policy, budgets, and receipts across machines, instances, and environments.

## The one-sentence promise

Your fleet's token spend, waste, and proven savings on one page, from a store your org already owns, with nothing leaving your organization.

## Non-goals (v1)

- No Token Shield server, no SaaS, no telemetry to any third party. Zero cloud is the differentiator, not a limitation.
- No hard cutoffs: a budget never kills a developer's session mid-task. Alerts only.
- No per-prompt surveillance: fleet records carry counters and labeled experiment results, never prompts, never code, never file paths from private repos.
- No licensing machinery in the lead-magnet phase. A license is a signed org file; enforcement can land later without redesign.
- No new always-on hooks. The zero-hooks-by-default trust posture holds fleet-wide; telemetry stays opt-in per the org profile, visibly.

## Architecture: self-hosted sync, zero cloud

No server anywhere. The org designates a store it already owns and secures:

- Store adapter v1: a private git repository (auth, history, and audit trail come free; works behind firewalls).
- Store adapter v2 (later): any S3-compatible bucket. The adapter seam is a directory of JSON files either way.

Each machine pushes small aggregates; the admin dashboard pulls and renders locally. Token Shield never operates infrastructure.

### Data flow

1. Machine: existing opt-in session-end telemetry (counters only) accumulates locally, exactly as the free core does today.
2. `fleet push` (manual, or the org profile schedules it through the existing launchd monthly-audit pattern): writes one JSON file per machine per day into the store: `fleet/<org>/<machine-id>/<YYYY-MM-DD>.json`.
3. `fleet dashboard` (admin): pulls the store, renders one local HTML page, same Brave-shields design system as the personal dashboard.

### Fleet record schema (per machine, per day)

- machine_id: stable anonymous id (hash of hostname plus a salt the org sets; the org chooses whether ids are readable or pseudonymous).
- team, environment: free tags from the machine's local fleet config (for example team=ios, env=ci).
- counters: input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens, per model, per day. Field names copied verbatim from the transcript usage schema already parsed by the meter.
- experiments: labeled records (VERIFIED, NOT_PROVEN, with fingerprints) exported from the local proof ledger.
- config_fingerprint and token_shield_version: so drift is visible fleet-wide and old evidence renders HISTORICAL, reusing the shipped drift watch.
- schema: integer, versioned from day one; a reader refuses a record from a newer schema rather than guessing (the meter's own refusal discipline).

What is deliberately absent: prompts, file contents, repo names, session transcripts, user names.

## The three commands (the Brave-simple surface)

1. `fleet init` (admin, once): interactive; asks for the store (git URL), org name, salt policy, default mode; writes `org-profile.json` and the store layout; prints exactly what data machines will share, in plain words, before creating anything.
2. `fleet join <store-url>` (each machine, one line; MDM and Jamf ready as a shell one-liner): installs or verifies the plugin, writes local fleet config (machine id, tags, store), runs a first push so the machine appears on the dashboard immediately. Idempotent. `fleet leave` removes the local config and stops pushes; uninstall leaves no trace, same as the core.
3. `fleet dashboard` (admin): one page: spend by team, machine, environment, and model; the waste map; verified savings per label (never summed across labels); budget status; drift alerts. A machine that has not pushed renders NO DATA, never a guess. A regression renders negative.

## Org profile (policy)

`org-profile.json` at the store root, versioned in the store's own git history:

- default_mode: conservative | balanced | aggressive (maps to the H2 intent modes of the free core).
- allowed_companions: subset of the curated registry ids; a machine's advisor will not recommend an optimizer outside it.
- telemetry: what fleet records include (counters_only is the only v1 option, named explicitly so adding levels later is a visible schema change).
- budgets: per team or environment, tokens per period, with alert thresholds (soft only in v1).
- push_cadence: manual | daily.

Machines read the profile at session start through the existing profile plumbing. A machine that cannot reach the store keeps working and reports its staleness on the next dashboard render: availability never gates a developer.

## Budgets and alerts (v1: soft)

Computed at dashboard render time and, on machines, as one advisory line at session start when the local counters cross the org threshold (reusing the existing advisor card surface, no new hook). Hard enforcement is a later, founder-gated decision, same class as the A1 act rung.

## Signed receipts

`fleet receipts` exports the org's labeled experiment records as receipts signed with the org's own ssh key (ssh-keygen -Y sign; present on every macOS and Linux machine, no new dependency). Every receipt carries: label, before, after, net effect, fingerprints, version, and verdict, exactly as the proof ledger stores them. The honesty labels become the audit feature: a NOT_PROVEN receipt is exportable too, because that is the trust story.

## Differentiation table (site-ready)

- Free core: measure yourself, diagnose, prescribe, prove, one machine. Forever free.
- Fleet: everything in core, plus mass install (join one-liner, MDM script), org policy profiles, fleet dashboard, soft budgets with alerts, signed receipts, drift visibility across the fleet. Self-hosted store, zero cloud, nothing leaves the org.

## Error handling and honesty rules

- Store unreachable at push: record queues locally, one plain warning, never blocks a session.
- Malformed or newer-schema record at render: that machine renders NO DATA with the reason; the walk never dies on one bad file (the I1 lesson, applied at design time).
- Clock skew between machines: dashboard buckets by the record's own date field and says so; no cross-machine time reconciliation is attempted or implied.
- Labels never blend fleet-wide: per-label rollups only, no cross-label totals, regressions negative, NO DATA beats a guess. Identical invariants to the core, enforced by reusing the core's reporting code, not by copying it.

## Testing strategy

Every unit ships with calibrated tests (defect reinjected, red, then green), matching the repo standard: fixture stores with hostile records (unhashable names, deep nesting, newer schema, missing fields), budget threshold boundaries, signature verify round-trip, join idempotency (run twice, one registration), and a dashboard render over an empty store (all NO DATA, no crash).

## Rollout

Phase F1 fleet push plus the git store adapter; F2 join, init, MDM script; F3 fleet dashboard; F4 org profile and soft budgets; F5 signed receipts. Each phase is its own PR with its own done-check. Implementation plan: docs/superpowers/plans/2026-08-14-token-shield-fleet-plan.md.
