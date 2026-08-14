# The Claude domination plan: Token Shield as the standard token layer for Claude Code

Date: 2026-08-14. Author: Khalil Maaouni. Status: ratified direction (founder's words in session 816c4828: specialize solely on Claude and Anthropic, take the best practices from the others, integrate the right solutions, independently be the number one token saving solution for Claude, everyone who uses Claude uses this plugin).

FOUNDER DECISION RECORDED: this SUPERSEDES the 2026-08-14 roadmap decision naming OpenAI Codex CLI and Cursor as the next platforms. Cross-platform work is PARKED, not deleted: the adapter seam stays in the design so the decision is reversible. Flip condition: the founder names a second platform again.

## 1. The field, as verified today (every claim labeled)

Four kinds of players compete for the same budget of attention, none of them holding our ground:

A. COUNTERS (ccusage, Claude-Code-Usage-Monitor, claude-usage local dashboard and VS Code extension, claude-hud live overlay, SessionWatcher, menu bar apps; enterprise: Torii per-seat spend, Faros token classification). They display spend. The strongest (Faros) classifies tokens as productive, inefficient, or wasteful, which overlaps our attribution ambition, but as central SaaS: no local proof, no experiments, no treatment loop. Source: fresh web sweep 2026-08-14 (links in the session record). Label: MEASURED landscape, sources opened.

B. TREATMENTS (ponytail, caveman, token-saver, context-mode, Claude DCP). Each one behavior change, first-party verified by us on this machine (docs/research/2026-08-13-context-mode-and-dcp-first-party.md, companion registry evidence). None of them measures its own effect. Their claims are testimonial, not proven. Label: VERIFIED first-party facts on disk.

C. CONTENT (the 19-changes, 12-ways, 60 to 90 percent posts). Headline percentages with no method section. Their volume proves demand for exactly what we refuse to fake. Label: MEASURED landscape.

D. ANTHROPIC NATIVE, the only force that matters long term: /usage as the source of truth for plan limits, /recap, auto compaction, prompt caching, and from Claude Code v2.1.x a plugin browse pane showing PROJECTED context cost per plugin. Native transparency is arriving, and it validates the category. Critically, the native numbers are projections and pool meters, not audited waste attribution. Label: MEASURED landscape, /usage semantics confirmed against current docs.

## 2. Why this path wins (the argument, in one page)

The trust position is EMPTY and we already hold the deed. Counters count, treatments treat, content asserts. Nobody proves. Token Shield is the only player whose numbers carry a second independent derivation (reconcile.py, 0.000 percent drift on 3,619 real sessions), whose claims carry labels that never blend, whose experiments return honest NOT_PROVEN and publish it, and whose reduction engine refuses to touch a config while a measurement is running. In a market drowning in 60 to 90 percent claims, the one tool that says NO DATA beats a guess is not a competitor among many; it is the referee. Referees become standards.

Anthropic is not our competitor; it is our terrain. Their native meters answer how much you used against your plan. We answer what you wasted, why, what to change, and whether the change actually worked, proven on your own transcripts, locally, with their native contribution attributed under the NATIVE label and never claimed. When native features grow (and they will), the independent auditor position strengthens: an auditor that reconciles against the house counters is worth more, not less, the bigger the house gets.

The competitors in category B are not enemies; they are our inventory. The control plane strategy (adapters, the DECLARED integration contract, the treatment tournament, guided applies) turns every behavior plugin into a treatment we prescribe, measure, and rank. Their best practices become our recipes: ponytail's minimalism, caveman's output discipline (already ours as WR+, one static line, experiment-backed), token-saver's output compression. Users arrive through them and stay for the proof. That is how you take the best from everyone and still stand alone at number one.

Specializing on Claude is what makes depth possible: cache keys that include model and effort, the five hour and weekly window economics where saved tokens literally equal more Claude hours, subagent cost structure, plugin context rent, MCP schema weight. Generic SaaS cannot follow us down; content cannot keep up with versions; and we self-correct on a 30 day fact review clock.

## 3. Gaps the sweep exposed (ours, named honestly)

1. LIVE visibility: claude-hud shows cost during the session; we render after. A user feels pain mid-session.
2. LIMIT RUNWAY: nobody converts waste into plan-window language (you lose N minutes of your 5 hour window to duplicate reads). Under subscription caps this is the single most visceral framing, and it is unclaimed.
3. Our own context rent: the v2.1.x browse pane will price every plugin. We must be the cheapest tool on the shelf and say so: zero hooks, near zero context cost, measured by our own meter.
4. Discoverability: the content wave outranks us; the marketplace is our home turf and the website is not live yet.

## 3b. Borrowed from beyond Claude (founder directive, session 816c4828: take the winning moves from successful solutions outside Claude Code and bring them to the Claude world)

Researched 2026-08-14 with every claim tied to an opened page (sweep record in the session; UNVERIFIED items labeled in the research file). The eight subjects: Langfuse and Helicone (open source LLM observability), Google Lighthouse, Bundlephobia PR bots, ESLint plus Prettier, Sentry release health, Dependabot, ccusage plus the Aider leaderboard, tokencost plus OpenRouter's public usage analytics. The five moves worth stealing, ranked, each already mapped to a unit below:

1. ZERO FRICTION TRIAL (ccusage won 17.9k stars on `npx ccusage@latest`, no install, reads local files; Helicone's funnel is a one line base URL swap). We already ARE zero integration (local transcripts, zero hooks); we have never led with it. Unit BX1: a zero install invocation (`uvx` or `npx` equivalent) that prints your waste numbers in one command with no plugin install, plus marketing copy that leads with it.
2. COST DELTA INSIDE THE REVIEW SURFACE (Bundlephobia style PR bots put the size delta in the PR comment at decision time). Nobody sees token waste at the moment they add a hook, an MCP server, or 300 lines of CLAUDE.md. Unit BX2: a GitHub Action that comments the measured context cost delta of CLAUDE.md, hook, and plugin manifest changes on the PR, before merge.
3. ONE PUBLIC FIXED FORMULA SCORE (Lighthouse became a CI gate because one 0 to 100 number, open algorithm, means the same thing everywhere). Unit BX3: the Waste Score: one headline number from a PUBLISHED formula over MEASURED inputs, honestly labeled, comparable across machines, usable as a CI budget the way teams ship at Lighthouse 90 plus.
4. REPRODUCIBLE PUBLIC BENCHMARK WITH AN OPEN CONTRIBUTION PATH (Aider's leaderboard is credible because outsiders can rerun and submit). Our bench/ kit already reproduces the meter in two commands. Unit BX4 shapes LAB1 as exactly this: a published corpus, a runnable scorer, a contribution path, so companion plugins get scored on the same board (this is also how the tournament gets public teeth). Timing unchanged: post verdict, per the founder's LAB1 decision.
5. AUTOMATED FIX PLUS A TRUST SCORE (Dependabot's compatibility badge: crowd evidence attached to the automated PR; scarcity of the score is its known weakness). Unit BX5: every guided apply proposal carries its own history line: how many times this treatment ran here, what the experiments returned, labeled MEASURED with the sample size, NO DATA when thin, never a fabricated confidence.

Also adopted from the sweep without new units: Sentry's release health pattern (our experiment engine gains a regression flag whenever a label's new result is worse than its last record: folds into the existing report delta); Prettier's config as a dependency (strategy presets as versioned installable files: folds into the existing strategy registry); OpenRouter's public aggregates as content (that is Signals S4 and the quarterly report, already planned, now with the positioning language: the data page IS the marketing).

## 4. The end to end plan

Phase 0, CLOSED (checked against origin/main 5b57935 at write time: scripts/guided_apply.py and scripts/signals.py both present on main, PRs 56, 54, 57, 58 in its log, zero open PRs): V1 is feature complete: measure, advise, reduce, prove, all shipped. The merged suite line names all 20 test files. Suite figure 339 checks green is the overnight session's quoted run, attributed, not re-run here.

Phase 1, THE WEEKEND (running now in the overnight session): Fleet F1 MERGED (PR 58); Fleet F2 in its refute and fix cycle behind a live fence; F3 to F5 and Signals S2 (consent and send, client only, per founder hold) follow; website assembly support. ADDED UNITS, each serving the north star objective "best for Claude" (sized, founder can veto on the page): LR1 limit runway (size S: profile and dashboard rows converting measured waste to five hour window minutes, sourced from /usage semantics, labeled ESTIMATED); HUD1 opt in statusline (size M: Claude Code statusline hook exposing session tokens and top waste class live; opt in, zero by default, its own cost measured and printed).

Phase 2, DISTRIBUTION (last week of August): website live (the founder builds from WEBSITE-BRIEF; sessions support with screenshots and fact checks); marketplace positioning (plugin description leads with its own measured context cost); the honest playbook page (our answer to the 19 changes content: every recommendation carrying its evidence label, NO DATA where we have none: content that converts skeptics); share card loop live in README; BX1 zero install trial (size S) and BX3 the Waste Score (size M, formula published before the first score ships) land here because both compound every later phase; BX2 the PR cost delta action (size M) starts here and matures in phase 4.

Phase 3, PROOF (mid September): diet-v2 verdict at its clean window near 2026-09-13; LAB1 unparked the moment the verdict lands (founder decision 2026-08-14) and built in the BX4 shape: published corpus, runnable scorer, open contribution path, companions scored on the same board; the first VERIFIED record or the second honest NOT_PROVEN published either way. Proof before megaphone: distribution assets are built during phase 2 but the loud push waits for the verdict, because our whole brand is that the number arrives with its evidence.

Phase 4, STANDARD (Q4): integration contract v2 with a certification mark (Measured by Token Shield: a companion may carry the badge only with a published experiment against our ledger format); BX5 trust scored guided fixes and the matured BX2 CI budget (a Waste Score threshold a repo can enforce, the Lighthouse budget pattern); Fleet pilots for teams (the Torii and Faros counter positioning: local first, private by construction, Signals aggregates only with double opt in); the first State of AI Coding Waste quarterly, method section first, published from signals_report.py the moment Signals volume exists, positioned the OpenRouter way: the public data page is the marketing.

## 5. What we deliberately do NOT do (unchanged house law)

No behavioral injection, no personality features, no universal percentage claims, no hooks by default, no cross label totals, no dollar claims on native caching, no building on another platform until the founder reopens that decision. The gate discipline stays: nothing ships a claim without its evidence, and the release boundary honors every open experiment.

## 6. Measures of domination (counted, never felt)

- Install count on the public marketplace (the one external number that defines "everyone uses it").
- Share of the documented suite green on every merge (internal quality floor, currently 100 percent).
- Time from verdict to published proof (target: same day).
- Number of companions carrying the DECLARED contract, then the certification mark.
- Signals opt in volume (the quarterly report's fuel), never bought with dark patterns: double opt in stays.

## 7. Immediate next actions (already in motion)

1. Fresh session closes wave R per the handover runbook (V1 complete).
2. Weekend program runs with LR1 and HUD1 appended to its backlog, lowest priority behind the ratified units.
3. Roadmap edit: this plan supersedes the multi platform paragraph; parked, not deleted.
