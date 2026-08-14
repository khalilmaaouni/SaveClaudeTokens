# Token Shield Signals: implementation plan

Source spec: docs/superpowers/specs/2026-08-14-token-shield-signals-design.md (founder-approved 2026-08-14). GATE: nothing starts before the free core ships 1.8.0; ordering against Fleet decided at that boundary. Sizes are ranges, medium confidence, basis the repo's recent unit history.

Standing constraints: Python 3.11 floor, stdlib only, zero hooks by default, command surface stays within the 6-file cap (signals rides the existing CLI), branch plus PR, calibrated tests, no dashes, no attribution, workers never push. The live experiment store is never touched by any Signals code or test.

## S1: schema, rollup, outbox, preview (size M)

Files: data/signals.schema.json (new, the frozen whitelist), scripts/signals.py (new: rollup from the existing telemetry ledger, quantization, outbox, preview), scripts/test_signals.py (new).
- Serialization FROM the whitelist only; quantization (5 percent share buckets, count bands, day resolution); random submission id at send time only; outbox cap 90 with oldest-first drop.
- Done-check: injected out-of-schema field cannot leave (calibrated); quantization boundary tests; two consecutive reports share no linkable value (fingerprint regression test); preview prints the exact payload bytes.

## S2: consent and send (size M, trust-changing)

Files: scripts/signals.py (extend), scripts/test_signals.py (extend), docs/SIGNALS.md (new, the user-facing promise page mirroring the spec's trust wording).
- Consent recorded locally per schema version; fleet double opt-in respected (org profile flag AND machine notice); send refuses without consent (calibrated); flush at most daily; fixture server (http.server) proves schema validation and refusals end to end.
- Review gate: independent opus refuter briefed to REFUTE ON PRIVACY GROUNDS (find a way any field, timing, or sequence identifies a user or links two reports); attacks re-run against fixes.

## S3: the owned endpoint (size S, infra)

Files: infra/signals-worker/worker.js (new), infra/signals-worker/README.md (one-page founder deploy doc), infra/signals-worker/test_worker_contract.py (fixture contract tests runnable without deployment).
- Worker validates schema, size cap, rate limit, writes body to R2, stores no IP; policy text published in docs/SIGNALS.md.
- Founder deploys with one documented command; nothing in the plugin depends on the endpoint existing.
- Review gate before the endpoint goes public: one cross-family refuter on the no-spying claim, per the cross-family law.

## S4: published aggregates and the benchmark panel (size M)

Files: scripts/signals_aggregate.py (new, run by us against the bucket, k-floor 20, outlier trimming with the rule stated), data/signals-aggregates.json (published artifact), scripts/token_shield.py (benchmark panel comparing the local profile to the published file, client-side only), scripts/test_tools.py (extend).
- Done-check: k-floor calibrated (a 19-submission cell refuses to publish); panel renders NO DATA without the aggregates file or without contribution consent; no network call anywhere in the dashboard path (proven by test).

## S5: quarterly report generator (size S)

Files: scripts/signals_report.py (new), template in docs/.
- Generates the State of AI Coding Waste draft from the aggregates with the method section auto-included (k-floor, trimming, cohort sizes). The founder edits and publishes; the generator never publishes.

## What the founder decides, not the session

- The program name (Signals is the working name) and the trust-page wording sign-off.
- When the endpoint goes live, and the relay roadmap timing.
- Each quarterly report's final text.
