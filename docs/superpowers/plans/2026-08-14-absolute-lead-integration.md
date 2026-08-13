# Absolute-lead integration: what the blueprint changes, and what it does not

Date: 2026-08-14. Judged by Fable against the merged program, on the founder's order: "add this to the roadmap in an integrated fashion so we take the lead. Do not try to beat every optimizer at its own technique. Become the product that knows when each optimizer deserves to run."

Source: TOKEN_SHIELD_ABSOLUTE_LEAD_BLUEPRINT.md (2,261 lines, founder-supplied). This plan EXTENDS docs/superpowers/plans/2026-08-13-finish-program-plan.md and 2026-08-13-leading-position-plan.md; it replaces neither. The release boundary stays gated on the claude-md-diet verdict. Building is authorized.

## The position, in one sentence

Token Shield measures where your tokens actually go, decides which optimizer (including none) deserves to run on your machine, and proves the result with labeled evidence. Your tool is a treatment. Token Shield is the diagnosis and the verdict.

It must be best at exactly three things: measurement truth (the reconciled meter, the scorecard's only 9.0), personalized diagnosis and selection (this machine's waste profile mapped to one capability then one treatment, with do-nothing valid), and causal proof with revalidation (before and after, marginal attribution, version-drift honesty).

It deliberately does NOT compete on: compression and brevity technique (caveman's game), minimal-code behavioral coaching (ponytail's game), context isolation and proxying (context-mode's and Tokenade's game), live dedup blocking (DCP's game), or behavioral injection of any kind, because our telemetry stays silent.

## Adopted, ranked by service to the position

1. PRO2, behavioral profiler v2 scoped to transcript-derivable MEASURED signals: tool-output share by tool, exact duplicate reads and commands, output verbosity, structured-input share. Without these, prescribing caveman versus RTK versus context-mode is generic guesswork. Moves Personalization.
2. TOUR1, treatment tournament: strategies gain a problem_class, the advisor ranks all candidates for one problem with native first, shows one winner and the losers one level deeper. Shrinks the deep advisor's domain, so stronger deterministic rules mean fewer paid calls.
3. METR1, treatment-specific primary metrics: each treatment judged on the metric it targets. Additive to the shipped experiment engine, and it must carry a calibrated test proving the OPEN claude-md-diet records and fingerprint are byte-identical, because a schema change refuses comparison by design.
4. FACTS1, truth registry plus stale-fact circuit breaker: data/facts.json holding dated sourced platform facts, a doctor staleness section, strategies referencing fact ids instead of hardcoding platform behavior. Operationalizes the self-correction principle already adopted.
5. HIST1, HISTORICAL marking on version change: when the shipped drift watch fires, evidence recorded under the old version renders HISTORICAL at read time rather than being silently inherited. Completes the shipped U1.
6. DASH1, dashboard top strip: verified improvement, current stack, largest remaining problem, next best move.
7. LAB1, Token Shield Lab (post-verdict): reproducible workload profiles where the deliverable is "Token Shield picked the right winner", never "Token Shield won". Curated companions only; it never publishes numbers for tools that failed first-party curation.
8. Receipt formats fold into the already-planned V1 share card. No new unit.

Confirmed as already shipped, so NOT re-planned: capability-first selection, hook arbitration, suppression, the open protocol (shipped as I1), the deep advisor's constraints, the onboarding order, and one-next-best-move.

## Rejected, and why (this list is as load-bearing as the adoptions)

1. A native minimal-implementation ladder. Competing with ponytail at ponytail's game, and it needs behavioral injection, which telemetry silence forbids. The ratified WR+ one-line output-discipline treatment stays capped at one static line and never grows into a brevity engine.
2. Shadow-mode duplicate protection. Needs a live PreToolUse hook, a trust-posture change. PRO2's transcript-derived duplicate counting gives the same diagnosis with zero hooks. Live blocking stays behind A1, post-verdict, adversarially reviewed.
3. A recommendation card standard. Already shipped: the cards carry expected benefit, evidence, drawback, quality risk, reversibility, how measured, and what happens if you say no.
4. Accepted-result as the north star metric now. No reliable acceptance signal exists, and a weak heuristic acceptance is a guess wearing a label. NO DATA beats a guess.
5. Bootstrap confidence intervals and effect sizes. The VERIFIED ledger is empty. Statistical machinery before one closed experiment is decoration.
6. The 15-dimension self-score table and its "current 7.9" figure. Self-assigned scores with no evidence chain, superseded by the scorecard's anchors. Adopting it would trade an honesty label for a score.
7. Enterprise, Teams and governance tiers. The blueprint's own avoid-list rejects it; not the position.
8. Cross-agent schemas now. Speculative abstraction over a meter that is legitimately transcript-shaped. Keep a "do not hardwire gratuitously" note, build nothing.
9. Distribution phases and marketing copy. Not code; growth work was already passed on.
10. Per-session routine checks. Needs default hooks. C1's documented opt-in scheduled run is the honest version.
11. "Fully vet ten companions" as a block. Repriced, not rejected: even cooperative candidates fail curation for lack of a documented uninstall path. Vet one at a time, demand-driven; the shipped DECLARED path scales the rest without lowering the bar.

## Sequenced work (extends the existing waves, two lanes maximum)

| Id | Scope | Deps | Size | Done-check |
|---|---|---|---|---|
| H3 | Marginal attribution waterfall on the dashboard | shipped fingerprints | M | never-sum assertion calibrated red to green |
| PRO2 | Transcript pressure signals in the profile | shipped meter | M | profile tests calibrated; cli profile prints the section live; reconcile still RECONCILED |
| FACTS1 | data/facts.json plus doctor staleness section | none | S | calibrated stale-fact fixture; doctor prints the section live |
| H2 | Modes as intent plus guided recipes, curated registry only | shipped H1 | M | unvetted-plugin recipe refused with its reason |
| C1 | Report treatments-delta and re-advise, opt-in schedule doc | shipped F1 | S | report tests calibrated; commands count prints 6 |
| TOUR1 | problem_class, tournament ranking, one next best move | PRO2, H2 | M | two candidates one problem, deterministic winner, losers listed deeper |
| METR1 | Treatment-specific primary metric, additive | PRO2 | M | calibrated test that open-experiment records and fingerprint are byte-identical |
| HIST1 | Drift marks old-version evidence HISTORICAL at render | shipped U1 | S | injected fake drift renders HISTORICAL, red to green |
| DASH1 | Dashboard top strip | H3 | S | strip renders with labels; empty ledger renders NO DATA |
| R plus WR+ | Wave R guided apply plus the output-discipline line | interlock commits first | L | per the merged wave R plan |

Post-verdict, in order: RELEASE, then V1 (share card, now also emitting the receipt formats), then A1 (act rung, adversarial review), then LAB1, then rolling first-party vetting units.

Changes to ALREADY-MERGED units, stated so nobody rediscovers them: TOUR1 and H2 modify the shipped advisor; FACTS1 and HIST1 extend the shipped doctor and discovery; METR1 extends the shipped experiment engine additively.

## Honest gaps in the blueprint itself

- Every competitor capability list in it is single-sourced and UNVERIFIED here until a first-party check. Tonight's research showed the friction is real: both checked tools were confirmed first-party and still blocked from curation for lacking a documented uninstall path, and one has had no commit in four months while the blueprint treats it as a live borrow source.
- All its worked numbers are illustrative mockups. None may ever render in the product as data.
- Its self-score has no derivation and is superseded by the scorecard.
- Its market claims are unverifiable first-party and are direction only.

## Stated uncertainty

Whether TOUR1's ranking can stay deterministic once problem classes multiply is unproven. If ranking starts needing judgment per case, that is the deep advisor's job rather than more rules. Flip condition: the first tournament test where two honest builders would rank differently.
