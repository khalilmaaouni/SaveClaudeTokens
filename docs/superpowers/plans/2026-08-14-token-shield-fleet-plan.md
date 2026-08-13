# Token Shield Fleet: implementation plan

Source spec: docs/superpowers/specs/2026-08-14-token-shield-fleet-design.md (founder-approved 2026-08-14). GATE: no phase starts before the free core ships 1.8.0. Sizes are ranges with medium confidence; the basis is the repo's own recent unit history (S roughly one builder session, M two, L three or more), stated because no WBS ledger exists yet.

Standing constraints for every phase: Python 3.11 floor, standard library only, no new dependency, zero hooks by default, command surface stays within the 6-file cap (fleet is ONE command file with subcommands), branch plus PR, calibrated tests red to green, no em or en dashes, no AI attribution, workers never push.

## F1: fleet record and the git store adapter (size S to M)

Files: scripts/fleet.py (new: record build, push, store adapter seam), scripts/test_fleet.py (new), data/fleet.schema.json (new).
- Build the per-machine per-day record from the existing telemetry ledger and proof ledger; field names verbatim from the transcript usage schema.
- Git store adapter: push writes `fleet/<org>/<machine-id>/<date>.json`, commits, pushes to the org store remote; every subprocess call checks its exit code; unreachable store queues locally with one warning.
- Done-check: `cd scripts && python3 test_fleet.py` green after reinjection calibration (break the record builder, red; restore, green); a push against a local bare repo fixture lands the file; unreachable-store fixture queues and warns without raising.

## F2: join, init, leave, MDM script (size M)

Files: scripts/fleet.py (extend), scripts/test_fleet.py (extend), docs/FLEET.md (new, admin guide), scripts/fleet-join.sh (new, MDM one-liner wrapper).
- `fleet init` interactive store and profile creation, printing in plain words what data machines will share BEFORE creating anything.
- `fleet join` idempotent (second run changes nothing, proven by test), `fleet leave` removes local config; uninstall leaves no trace.
- Done-check: join twice on a fixture store produces one registration (calibrated); leave then join re-registers; shellcheck-clean join script; docs dash scan empty.

## F3: fleet dashboard (size M)

Files: scripts/fleet.py (extend: pull and render), scripts/test_fleet.py (extend), reusing the core dashboard's design system and label rules by import, never by copy.
- Render spend by team, machine, environment, model; waste map; per-label savings; drift alerts (reuse the shipped drift watch); silent machine renders NO DATA.
- Hostile-store fixtures: unhashable name, 200k-deep JSON, newer schema, missing fields; the walk never dies on one bad file.
- Done-check: render over empty store all NO DATA no crash (calibrated); hostile fixtures each isolated to their own row; label-blend test proves no cross-label total appears.

## F4: org profile and soft budgets (size M)

Files: scripts/fleet.py (extend), scripts/advisor.py (one advisory card when local counters cross the org threshold), scripts/test_fleet.py and scripts/test_advisor.py (extend), data/fleet.schema.json (extend).
- Profile read at session start through existing profile plumbing; unreachable store never gates the developer (calibrated: store gone, session advises from last known profile and says stale).
- Budgets soft only; the advisory line renders through the existing card surface, no new hook.
- Done-check: threshold boundary tests (under, at, over) calibrated; allowed_companions subset suppresses out-of-catalog recommendations (calibrated against the shipped suppression logic).

## F5: signed receipts (size S)

Files: scripts/fleet.py (extend), scripts/test_fleet.py (extend).
- Export labeled records as receipts; sign with ssh-keygen -Y sign using the org key; verify round-trip in tests with a throwaway key; NOT_PROVEN receipts export too.
- Done-check: sign and verify round-trip green; a tampered receipt fails verification (calibrated by tampering one byte).

## Review gates

F1 and F5 merge on calibrated tests plus the orchestrator's own reinjection. F2, F3, F4 (trust-changing surfaces: install path, org-wide rendering, policy) each get an independent opus refuter briefed to REFUTE, and the refuter's attacks are re-run against the fix before merge, per the standing lesson that two units passed their own tests and were still wrong.

## What the founder decides, not the session

- The product name (Fleet is the working name).
- When the lead-magnet phase becomes a sold product, and pricing.
- Any move from soft budgets to enforcement (same founder-gate class as the A1 hook).
