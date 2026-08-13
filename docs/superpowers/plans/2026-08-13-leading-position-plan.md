# Leading-position addendum: close every scored gap, integrate the ecosystem, prove savings publicly

Date: 2026-08-13. This plan EXTENDS docs/superpowers/plans/2026-08-13-finish-program-plan.md (merged as PR 22); nothing here replaces that plan's units, sequencing, or standing truths. Founder ask (2026-08-13, daytime): replan the program to finish all remaining tasks and take the leading position; analyze weaknesses; identify what to borrow from the ecosystem as core features; integrate fully and seamlessly with the ecosystem to bring real proven token savings to the Claude community.

The release boundary stays gated on the claude-md-diet verdict (PR 18 amendment): no tag, no publish, no local plugin update, no MCP client registration until VERIFIED or an honest NOT_PROVEN. Building before the verdict is authorized. Nothing in this plan touches the running experiment.

## Weakness analysis (Fable, this session)

Source: the two external benchmark tables recorded verbatim in docs/SCORECARD.md (UNVERIFIED, direction only, never measurement) plus the persona research (docs/research/2026-08-13-personas.md). Every external number below is direction; the yardstick that decides "leading" is docs/SCORECARD.md's evidence-or-nothing rule, target 8.5 plus on every capability per the ratified Solid Core strategy.

| Scored gap (external, UNVERIFIED) | Root cause here | Covering unit |
|---|---|---|
| Companion conflict management 1.0 | doctor sees shared hooks but cannot judge them yet | G1 (compatibility matrix, hook ownership), G2 (suppression) |
| Update resilience 2.5 | no version-drift watch; a companion update can silently invalidate advice and spanning experiments | U1 (new) |
| Personalization 2.5 | scored against 1.6; treatment memory, profile, and per-user math shipped in 1.7.x but carry no scorecard evidence yet | F1 (evidence pass), G2, G3 |
| Companion selection 3.0 | registry is curated but selection is manual | G3 (deep advisor), H1 (adapters), H2 (recipes) |
| Automation 3.5 | zero hooks by default is a trust stance, not a defect; but nothing runs routinely for the user either | C1 (new, observe/assist rungs), A1 (act rung, post-verdict) |
| Actual reduction 5.5 | we measure and advise; we do not natively reduce | R (wave R guided apply: CLAUDE.md diet, plugin prune bundles, memory trim) |
| Onboarding 5.0 | /start journey shipped 1.7.1 and polished in the trust sweep; evidence not yet scored | F1 |
| Continuous optimization 5.0 | monthly report exists; no loop closes advice back into re-measurement | C1 (new) |
| Attribution 6.0 | experiment engine ships; zero VERIFIED records yet; waterfall not rendered | H3, plus the verdict itself |
| Cache intelligence 6.5 | rules corrected against first-party docs in 1.1.0; evidence not yet scored | F1 |

Strengths to defend, not dilute: measurement truth (9.5 external; the meter, calibrated suite, bench kit) and cache plus startup (9.0). No unit may trade honesty labels or the zero-hook default for a score. Stated plainly per review finding M5: the priority ORDER above is derived from unverified external direction; the units themselves are justified independently by the repo's own gaps.

## Wave T: trust repairs (runs FIRST, before F1; from the 2026-08-13 BrotherSBE verification of numbers and methodology)

Two read-only reviewers (evidence audit and data methodology, both opus-tier) attacked the repo's numbers and methodology on 2026-08-13. Verdicts: NUMBERS CONTESTED (0 Critical, 3 Major) and METHODOLOGY CONTESTED (2 Critical, 5 Major); the four load-bearing findings were independently re-confirmed by the orchestrator against the files. The scorecard pass (F1) would inherit every one of these, so repairs run first.

| Unit | Finding it repairs | What | Agent | Model | Done-check |
|---|---|---|---|---|---|
| T1 | CLAIMS.md B3/B5/B8 claim an "independent second derivation" that exists nowhere on disk (grep over scripts/ and bench/ returns no artifact; both reviewers converged) | build scripts/reconcile.py, a genuinely independent re-derivation of the headline figures from the transcripts with different code, its output recorded beside the claims; UNTIL it lands, those rows relabel CONFIRMED to UNVERIFIED | one builder | sonnet | reconcile output quoted with drift stated; or the relabel diff merged; never both claims at once |
| T2 | VERIFIED has no sign check (experiment.py:346 verified = not reasons; test_tools.py:559 asserts a -8000 regression as VERIFIED); the record carries no per-cohort session count (MIN_SESSIONS = 3 gates but never reaches the record); a model-mix change between cohorts appends no reason; the thin-data downgrade reason does not name the thin side | record gains per-cohort session counts and dispersion; verdict carries direction so a regression can never render as a plain saving (V1 share card inherits this); model-mix mismatch appends a named reason; thin-data reason names the side | one builder plus opus REVIEW (it changes verdict semantics) | sonnet build, opus refute | new tests calibrated red to green including a regression-never-renders-as-saving assertion and a models-differ reason assertion |
| T3 | CLAUDE.md calls the 11-file line "the exact line CI runs" while ci.yml also runs the selftest and mcp-server tests; CLAIMS.md's stability sentence ("drifts by a handful") was refuted by a live re-run (transcripts -8.2 percent day over day); SCORECARD anchors allow two honest reviewers to differ by two points (no tie-break); budget ranges cite "actual unit costs" no file records; companions.json carries two empty reason strings against its own discipline | docs truth sweep: correct the CI-line sentence and wire the uncounted tests into the documented line or say why not; rewrite the stability sentence to the measured churn; add tie-break rules to the anchors (Fable drafts the anchor text, the builder applies); label the budget basis "unrecorded until the WBS ledger ships"; empty reasons become explicit NO DATA | one builder | sonnet | grep confirms each corrected sentence; dash scan empty; suite still green |

Wave T budget: T1 60k to 120k; T2 80k to 150k plus 40k to 80k review; T3 30k to 60k. Findings deliberately NOT auto-fixed this session: they change claim semantics, so they land as reviewed PRs like all code.

## What we borrow from the ecosystem as core features

Borrowing means the capability becomes native where honesty allows, and prescribed where injection is required. The prescribed-never-bundled principle (docs/ROADMAP.md) is not weakened by this plan.

1. From context-mode and token-saver (reduction that actually lands): native guided apply. Wave R already plans it: CLAUDE.md diet, plugin prune bundles, memory index trim, each behind backup, diff, explicit yes, and an auto-opened experiment. This is the reduction score's whole fix and it is native.
2. From caveman, via the pragmatic reviewer finding (andrew.ooo: a one-line brevity instruction captures most of the headline saving): a native minimal-output treatment. Wave R's guided apply gains one more proposal type: a single output-discipline line proposed into the user's CLAUDE.md, measured by its own experiment. Native treatment tried first, exactly as the roadmap orders; the full companion stays the prescribed step up.
3. From token-saver (tool output compression) and the deferred Protect Mode: the act rung, one guard at a time, cold-cache first, opt-in, post-verdict only (A1). The deferred list's flip condition governs.
4. From every companion's failure mode (caveman issue #808 data loss): the never-lose-work contract stays pinned by calibrated test; guided apply inherits it wholesale.
5. What we do NOT borrow: behavioral injection (companions own it; our telemetry stays silent), personality features (ratified passed-on list), and headline percentages (labels cap every number at its evidence).

## Seamless ecosystem integration (the full picture)

- See: registry v2, discovery, doctor (shipped, wave 1). Judge: compatibility matrix, hook ownership, suppression (G1, G2). Select: deep advisor (G3). Work: adapters, recipes, modes (H1, H2). Prove: marginal attribution waterfall (H3), experiments per treatment, companion version change ends spanning experiments (U1 wires the warning).
- I1 (new) promotes the roadmap's "Later: open contract" to a build: token-shield.integration.json, a declaration any optimization plugin can ship (capabilities, modes, state and health commands). Declared data labels DECLARED, never CURATED; curation still requires first-party verification. This is how integration scales past the three hand-verified companions without lowering the evidence bar.
- RS1 (new) applies the first-party discipline to the next candidates (context-mode, Claude DCP) before any registry entry, per the standing caution in docs/ROADMAP.md.
- The MCP server (built, PR 20) is the integration bus outward: any MCP client can read profile, advice, experiments, and the Consumption Report with labels intact. Registration on this machine stays verdict-gated.

## Real proven savings for the community

- The bench kit (PR 15) answers the skeptic: reproduce the meter in two commands, zero real data.
- The claude-md-diet experiment is the first public-grade proof; its verdict (VERIFIED or honest NOT_PROVEN) is itself the product working.
- V1 (new, post-verdict): the share card and README badge generator from the deferred list, whose flip condition (a VERIFIED record exists) will then be met. Cards render only VERIFIED and MEASURED numbers with their labels; nothing shareable can outrun its evidence.
- The release train at the verdict: tag, publish, plugin update here, MCP client registration, live client smoke test, scorecard re-score with the release.

## New units (dispatch table addendum; finish-program table governs F1 through R and REVIEW)

| Unit | What | Agent | Model | Why this tier |
|---|---|---|---|---|
| RS1 | First-party verification of context-mode and Claude DCP; registry entries only on CONFIRMED | researcher | sonnet | scoped fact-finding with URLs; Fable triages verdicts |
| U1 | Update resilience: version-drift watch in discovery and doctor; spanning-experiment warning wired to the existing fingerprint | one builder | sonnet | scoped implementation against shipped code, mechanically checkable |
| I1 | Open contract v1: spec, JSON schema, discovery reads declarations as DECLARED | one builder | sonnet | schema plus parsing work, calibrated tests |
| C1 | Continuous optimization: monthly report gains a did-it-work delta section and re-advise; opt-in scheduled-run recipe documented; commands stay at 6 | one builder | sonnet | report rendering from existing data |
| WR+ | Wave R addendum: the one-line output-discipline proposal type inside guided apply | folded into R's builder | sonnet | one more proposal type over the same contract |
| V1 | Share card and README badge from VERIFIED records only (post-verdict) | one builder | sonnet | rendering with label guards, testable |
| A1 | Act rung: cold-cache guard, opt-in, one guard at a time (post-verdict) | one builder plus opus REVIEW | sonnet build, opus refute | it is a hook; the trust posture change demands adversarial review |
| RELEASE | Verdict day: experiment close, scorecard re-score, tag, publish, plugin update, MCP registration, client smoke test | orchestrator | Fable | release gates and judgment never delegate down |

Sequencing: RS1 any time (read-only). U1 after G1. I1 after H1 (the adapter contract informs the schema). C1 after F1. WR+ rides R. V1, A1, RELEASE at the verdict, in that order: RELEASE first, then V1, then A1. Two build lanes maximum, per the caps. REVIEW (opus, briefed to refute) extends to I1 and A1.

## Unit specs (files and done-checks)

RS1: docs/research/<date>-context-mode-first-party.md (and DCP if locatable). Every claim carries the URL or path actually opened, or NO DATA. Done-check: dash and attribution scans empty; no registry edit ships in this unit.

U1: scripts/discover_companions.py compares live versions against ~/.token-shield/companions_state.json and reports drift; scripts/doctor.py renders a VERSION DRIFT section and, when any open experiment's fingerprint spans the change, an explicit spanning-experiment warning. Tests: test_discover_companions.py and test_doctor.py additions, calibrated by injecting a fake version change (red) before the fix (green). Done-check: both test files green; doctor run live prints the section against this machine.

I1: docs/superpowers/specs/integration-contract-v1.md; data/integration.schema.json; discovery reads token-shield.integration.json from installed plugin roots, labels every declared field DECLARED, refuses malformed declarations with the reason printed. Tests: test_discover_companions.py additions against fixture declarations, calibrated. Done-check: tests green; a fixture with a missing capabilities key is refused by name.

C1: scripts/report.py gains a treatments delta section: for each treatment accepted in the window, the before and after of its target metric with its label, or NO DATA; ends with the current top advice. docs/MAINTENANCE.md documents the opt-in scheduled run (the existing launchd pattern extended to report plus doctor), zero hooks unchanged. Tests: test_report.py additions, calibrated. Done-check: tests green; ls commands/*.md | wc -l prints 6.

WR+: inside wave R's guided_apply contract, proposal type output_discipline: one line, shown verbatim, applied only into the user's CLAUDE.md under backup plus diff plus yes, auto-opens its own experiment. Done-check: wave R's own suite additions cover it calibrated.

V1: scripts/share_card.py rendering a card (text and HTML) from the proof ledger; only VERIFIED and MEASURED rows, label printed on the card face; refuses when the ledger has no qualifying record. Tests calibrated. Done-check: tests green; refusal path prints the reason.

A1: plan file first (its own step naming hook, config, kill switch, and rollback), then build. Not started before RELEASE completes. Done-check for the plan: dash scan empty; the build's done-check lands with its plan.

RELEASE: python3 scripts/cli.py experiment end "claude-md-diet" at the founder's word or the clean window (~2026-09-11); scorecard pass appends to history with the release tag; then the gated steps in PROJECT.md order. Done-check: each step's own command output quoted in the session ledger.

## Budget

Addendum estimates (ranges, medium confidence, priced from the finish-program plan's unit costs): RS1 30k to 60k; U1 60k to 120k; I1 80k to 150k; C1 50k to 100k; WR+ inside R's range; V1 60k to 120k; A1 150k to 300k including its review; RELEASE 40k to 80k. Addendum total 0.47M to 0.93M on top of the finish-program 0.7M to 1.5M: whole program 1.2M to 2.4M output, three to six fresh sessions at standard ceilings. Every session states its ceiling up front, dispatches nothing past 80 percent, hands over on the guard's word.

## Appendix: full allocation, unit by unit (added 2026-08-13 on the founder's detailed-allocation ask)

House laws this appendix applies, so they are not re-derived per unit: guidance and judgment stay on the strongest grade (Fable orchestrates, briefs, verifies, merges); execution routes to the cheapest profile that passes the done-check; every brief names tier and reason; two lanes maximum in parallel; one writer per fence; one suite at a time per tree; parallel writers get their own worktree and branch; every builder brief carries a freshness assertion (quote git log -1 before touching anything) and the orchestrator re-runs each done-check before merge; returns hard-capped near 1500 tokens; an executor failing its done-check twice escalates one grade with the evidence attached; a task shape that succeeded twice on a lower grade defaults there next time. Profile-to-model mapping on this machine today: fast-worker = haiku, builder and researcher = sonnet, reviewer and navigator = opus, orchestrator = Fable (the session model). Effort: builders medium, fast-worker low, reviewers medium with high reserved for the A1 and G3 judgments.

Cross-family refutation law (ratified 2026-08-05): any finding that gates a release or a safety claim gets at least one refuter from a DIFFERENT model family, named in the record. In this program that binds A1 (a hook, a trust-posture change) and the RELEASE claims: one read-only non-Claude refuter (codex exec, output redirected to a file) attacks each before the founder gate.

### Session A (v1.8 wave 2 start; suggested ceiling 500k soft, 800k hard)

| Unit | Executor | Model, effort | Worktree and branch | Writable files (the fence) | Budget | Done-check the orchestrator re-runs |
|---|---|---|---|---|---|---|
| F1 scorecard pass | builder | sonnet, medium | wt-f1, build/scorecard-pass | docs/SCORECARD.md only | 30k to 60k | every scored cell's cited test name greps to a real def; every cited command re-run; history entry present; dash scan empty |
| G1 compatibility | builder | sonnet, medium | wt-g1, build/v18-wave2-g1 | data/compatibility.json, scripts/doctor.py, scripts/test_doctor.py | 60k to 120k | test_doctor.py green with additions calibrated red to green; cli.py doctor prints the ownership section live |
| RS1 research | researcher (read-only, cannot write files) | sonnet, medium | none | none; findings return to Fable, who writes docs/research/ | 30k to 60k | every claim carries an opened URL or NO DATA; dash scan on the written doc empty |
| G2 suppression | builder, opens after G1 merges | sonnet, medium | wt-g2, build/v18-wave2-g2 | scripts/advisor.py, scripts/test_advisor.py | 80k to 150k | suppression, expiry, and suppression-never-hides-a-regression tests calibrated red to green |
| U1 drift watch | builder, opens after G1 merges | sonnet, medium | wt-u1, build/update-resilience | scripts/discover_companions.py, scripts/doctor.py (VERSION DRIFT section), both test files | 60k to 120k | injected fake version change red then green; doctor live print |
| REVIEW of G2 | reviewer, briefed to refute, never edits | opus, high | none (read-only checkout) | none | 40k to 80k | findings severity-split, each naming the falsification executed; Fable triages |
| DOCS sweep per merge | fast-worker | haiku, low | inside the merging branch | CHANGELOG.md, README.md, docs/ROADMAP.md status lines only | 10k to 20k each | grep confirms the new lines; dash scan empty |

Lane discipline: F1 and G1 open together (two lanes). RS1 is read-only and rides beside them without a lane. G2 and U1 open only as F1 and G1 close. Doctor conflict note: G1 and U1 both touch scripts/doctor.py, so they NEVER run concurrently; U1 waits for G1's merge and rebases.

### Session B (deep layer plus adapters; suggested ceiling 500k soft, 800k hard)

| Unit | Executor | Model, effort | Worktree and branch | Writable files | Budget | Done-check |
|---|---|---|---|---|---|---|
| G3 deep advisor | builder for the harness; the deep advisor RUNS on Fable pinned at runtime (ratified product decision) | sonnet, medium | wt-g3, build/deep-advisor | scripts/deep_advisor.py, scripts/test_deep_advisor.py, prompts under skills/token-shield/, scripts/cli.py (advise --deep wiring) | 120k to 250k | tests green against a fake model callable, never a live call; live smoke run only at the founder's explicit yes, cost printed and subtracted |
| H1 adapters | builder | sonnet, medium | wt-h1, build/companion-adapters | scripts/companions/ (ponytail.py, caveman.py, token_saver.py), their test files | 80k to 150k | adapter refuses a registry entry missing evidence fields, calibrated; fixture-registry tests green |
| I1 open contract | builder, opens after H1 merges | sonnet, medium | wt-i1, build/integration-contract | docs/superpowers/specs/integration-contract-v1.md, data/integration.schema.json, scripts/discover_companions.py, its test file | 80k to 150k | fixture missing the capabilities key refused by name; declared data labeled DECLARED |
| C1 optimization loop | builder | sonnet, medium | wt-c1, build/continuous-optimization | scripts/report.py, scripts/test_report.py, docs/MAINTENANCE.md | 50k to 100k | test_report additions calibrated; ls commands/*.md prints 6 |
| REVIEW of G3 | reviewer, refute brief | opus, high | none | none | 40k to 80k | severity-split findings naming the falsification executed |

Lane discipline: G3 and H1 open together. I1 and C1 open as they close. The G3 reviewer runs after G3's tests land red to green.

### Session C (v1.9 finish plus native reduction; suggested ceiling 500k soft, 800k hard)

| Unit | Executor | Model, effort | Worktree and branch | Writable files | Budget | Done-check |
|---|---|---|---|---|---|---|
| R wave R guided apply, WR+ folded in | builder | sonnet, medium | wt-r, build/solid-core-waveR | per the merged wave R plan: scripts/guided_apply.py, scripts/optimize.py extensions, the three new test files, cli wiring; WR+ adds the output_discipline proposal type | 150k to 350k | step 1 experiment interlock commits FIRST (no apply while any experiment is open); every apply behind backup, diff, yes, auto-experiment; suite green |
| H2 modes and recipes | builder | sonnet, medium | wt-h2, build/mode-guidance | advisor card rendering, cli advise recipe surface, test additions | 50k to 100k | unvetted-plugin recipe refused with the reason printed, calibrated |
| H3 attribution waterfall | builder, opens after H2 or R closes a lane | sonnet, medium | wt-h3, build/attribution-waterfall | scripts/token_shield.py, scripts/test_tools.py additions | 80k to 150k | never-sum assertion calibrated; companion version change ends a spanning experiment, wired to the existing fingerprint |
| REVIEW of H3 and I1 | reviewer, refute brief | opus, high | none | none | 40k to 80k | severity-split findings naming the falsification executed |

### Session R (verdict day; founder present; suggested ceiling 500k)

| Unit | Executor | Model, effort | Writable files | Budget | Done-check |
|---|---|---|---|---|---|
| RELEASE train | orchestrator only (Fable); tag and publish behind the founder's explicit confirm, per the standing release gate | Fable, session default | version stamps, CHANGELOG release heading, scorecard history entry | 40k to 80k | experiment end verdict quoted; each release step's own command output quoted; scorecard re-score appends with the tag |
| V1 share card | builder | sonnet, medium | scripts/share_card.py, its test file | 60k to 120k | card refuses without a VERIFIED or MEASURED record, calibrated; label printed on the card face |
| A1 act rung | plan by Fable (navigator posture); build by builder; refute by reviewer PLUS one non-Claude-family refuter; enable only at a founder gate | plan Fable; build sonnet medium; reviews opus high plus codex read-only | plan file first; then the hook, config, kill switch, rollback | 150k to 300k including reviews | plan lands before any hook code; both refuters' reports on file; founder yes before the hook ever registers |

### Why each executor is the right one (the five assignment questions, answered once per class)

- Builders (sonnet): every build unit above works from a merged plan that names files and done-checks, which is exactly scoped implementation from a precise spec; routing it higher is the OVERTHOUGHT failure mode. Checked by: calibrated tests re-run by Fable. Accepted by: Fable at merge, founder at the page.
- Researcher (sonnet, read-only): RS1 is external evidence gathering with URLs; it cannot write, so Fable lands the doc, which also keeps the registry-edit boundary clean.
- Reviewers (opus, refute briefs, never edit): G2, G3, H3, I1, A1 are the judgment-heavy or trust-sensitive units; verification never routes below the guide's grade, and an executor never verifies its own work.
- Fast-worker (haiku): changelog and status-line sweeps are mechanical bulk with grep-checkable outcomes.
- Orchestrator (Fable): briefs, fences, merges, gate scans, done-check re-runs, scorecard judgment, release train, and every founder conversation. Verification and judging never delegate down; mechanical loops never run on Fable.

Escalation and de-escalation: a builder failing its done-check twice hands the unit one grade up (to opus) with the failure evidence; a unit class that lands twice clean on sonnet stays there; if the haiku sweeps miscount once, they move to sonnet and the ledger records why.
