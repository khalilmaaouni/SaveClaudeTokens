# Roadmap

We built the smallest honest set that delivers the mission: measure token use and prove the saving. A Fable-tier judge ranked a product blueprint for value and mathematical soundness, and we passed on the sprawl. The test for any feature is one question: does it help Token Shield prevent, measure, attribute, or communicate a real token saving? If not, we do not build it.

## The leadership roadmap (2026-08-14, founder direction)

North star: the best free token-efficiency product for AI coding. Find the waste. Fix the right waste. Prove the result. Core stays free and complete: we offer for free what others charge for, we win standalone in our own way (measurement truth, personalized diagnosis and selection, causal proof with revalidation), then integrate natively with every specialist to cement the position. Internal law: every optimization pays rent, every saving needs evidence, every version change can invalidate old proof, and the best next move can always be nothing.

Gate status 2026-08-14: the claude-md-diet experiment was closed early on the founder's explicit word; verdict honest NOT_PROVEN (window changed, config changed during window, model mix not comparable). Under the ratified amendment either verdict opens the release boundary, so the release boundary is OPEN. A successor experiment, claude-md-diet-v2, opened the same day and runs untouched.

### Short term (this weekend: 1.8.0)

- Finish the remaining build units: FACTS2, PRO2, H2, TOUR1, METR1, HIST1, DASH1, each with calibrated tests, refute reviews on the judgment-heavy ones, and docs lines per merge. R and WR+ are done, see the guided-apply status line below.
- **R and WR+ (guided apply), status 2026-08-14:** built under the founder's build-before-verdict amendment (release still gated). `scripts/guided_apply.py` ships the shared refuse-then-mutate-then-verify-then-open-one-experiment contract; `scripts/optimize.py` gains the CLAUDE.md diet's `--guided-apply` path plus WR+'s one-static-line `output_discipline` proposal type (`--propose-output-discipline` / `--apply-output-discipline`); `scripts/plugin_prune.py` and `scripts/memory_trim.py` are the two other guided-apply producers, wired into `cli.py prune`/`cli.py trim`. Every apply refuses while any experiment is open and auto-opens its own on success. The plugin-prune bare-name-vs-full-id ambiguity stays UNVERIFIED, see docs/CLAIMS.md.
- **R fix round, status 2026-08-14:** an independent review of wave R found 3 Critical and 7 Major findings before release; all are fixed on `build/wave-r-fix`. Critical: a guided apply's mutate step now returns an honest int rc that `guided_apply.apply` propagates, so a NO DATA no-op never opens an experiment for a change that never happened; every guided-apply entry point refuses, naming both paths, when the file named at apply time differs from the proposal's own stored target; every propose now records a sha256 of the source text, and apply refuses a stale proposal (the source changed since propose) instead of silently rolling it back. Major: `memory_trim.py` and `optimize.py` back up an existing archive/history file before ever writing to it and append rather than overwrite, and `memory_trim.py`'s trim now moves bullet lines only, so frontmatter and block HTML comments never leave the index; `experiment.list_open_experiments` fails CLOSED on an unreadable or unparseable baseline (a marker naming the file, not a skip); `plugin_prune.verify_bundle` no longer reads an absent plugin id as confirmed disabled; `plugin_prune`'s bundle file stores plugin names only, never argv, with every name checked against a strict charset both at propose and apply time; a guided apply's success message now names the earliest clean close date. Full documented test suite done-check (CLAUDE.md line 8) exits 0: `test_guided_apply.py` 8 passed, `test_plugin_prune.py` 6 passed, `test_memory_trim.py` 7 passed, `test_optimize.py` 15 passed, `test_experiment.py` 37 passed. Every review repro re-run confirms the safe outcome.
- Ship 1.8.0: tag, publish, plugin update on this machine, MCP client registration, live smoke test. Founder confirms the tag and the publish.
- The Token Shield command center: one page a non-technical user reads in ten seconds. How efficient am I, what is running, what is my biggest issue, what is the next best move, and why. No knowledge of hooks, TTL, or MCP required.
- Simplicity: a one-command start, modes phrased as intent (conservative, balanced, aggressive), guided install and rollback recipes, do-nothing as a first-class answer.
- Website handoff: hero copy, the proof story, and this roadmap, ready for the founder's site.

### Mid term (two to six weeks)

- The diet-v2 verdict: the first public VERIFIED or honest NOT_PROVEN cycle, shown on the dashboard as the product working, never as an embarrassment.
- V1 share card (VERIFIED and MEASURED rows only, label on the card face). LAB1 selection benchmark: the deliverable is "Token Shield picked the right winner", reproducible on a second machine. A1 act rung, founder-gated: zero hooks stays the default posture.
- Rolling first-party companion vetting, one at a time, demand-driven.
- Optimizer self-overhead on the dashboard: Token Shield reports its own cost and recommends nothing when the next treatment is not worth it.

### Long term (a quarter and beyond)

- Adapter layer for other agent surfaces: OpenAI Codex CLI first, then Cursor. Same meter honesty, same labels, a per-platform truth registry. Claude Code finishes first.
- The category is Agent FinOps: one local product that measures any coding agent's spend, prescribes the cheapest high-quality stack, and proves the result.
- Free core forever. Anything paid later (team fleet views, organization receipts) never paywalls personal token efficiency.

### Rejected stays rejected

Compression proxies, behavioral injection, self-scored capability tables, universal-percentage marketing. Each carries a flip condition in the absolute-lead section below; none reopens without new evidence.

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

## Adopted direction: the companion ecosystem (blueprint reviewed 2026-08-12)

A product blueprint (Token Shield Native Companion Ecosystem, research snapshot 2026-08-12) was reviewed and its thesis is ADOPTED: Token Shield is the control plane, measurement layer, and verdict owner; specialist companions (ponytail, caveman, context isolation tools, dedupe tools) are treatments that Token Shield prescribes, measures, and keeps or rolls back. Token Shield decides what is worth changing, a companion executes the treatment, Token Shield proves whether it worked. The strongest position is not replacing every optimizer; it is making every optimizer measurable, personal, compatible, and reversible. Positioning sentence (founder, 2026-08-13): Token Shield continuously finds the cheapest high-quality way for you to use Claude Code, using native capabilities first and specialist plugins only when they prove their value.

Adopted principles, binding on all waves below:

- **Prescribed, never bundled.** No companion becomes a plugin dependency. Recommendation, preview, explicit user choice, then activation at a clean session boundary for attribution.
- **Capability first, brand second.** Recommendations name the missing capability (minimal_code, output_compression, tool_output_isolation, deterministic_deduplication), then map it to the safest available provider, with Token Shield Core native treatment tried first.
- **Telemetry hooks stay silent.** Token Shield observes and never injects behavioral context; companions own behavioral injection. An optimizer that prints advice every turn becomes the waste it measures.
- **Marginal attribution, canonical baseline.** Stack effects report as a waterfall (baseline A, plus Core to B, plus companion to C); marginal deltas never sum as naive percentages, interaction effects are declared not separable, and a companion version change is a treatment change that ends any spanning experiment.
- **External evidence never populates the user's savings.** A public benchmark is a reason to test, displayed apart from YOUR EVIDENCE, which starts at NOT PROVEN.
- **The deep selector never executes.** Fable-tier selection picks one treatment from the curated registry when deterministic rules cannot decide; it never invents install commands, never alters labels, never touches files.
- **Self-correction is routine, not an exception.** Founder directive 2026-08-13, after a re-benchmark found Token Shield's own optimization advice stale: the tool's advice is data with a shelf life. Every strategy carries its source and a last_reviewed date, the ecosystem doctor flags advice past its review window, and a re-benchmark that overturns the tool's own guidance is recorded like any other finding: the system working, never an embarrassment. This capability ranks with the meter itself.

Sequencing, bent to the ratified gate (unchanged: no v1.8 implementation file before one VERIFIED experiment exists):

- **v1.8 wave 1: see the ecosystem.** Registry schema v2 (tested version ranges, hook footprints, curated activation and rollback commands, last_reviewed dates), native discovery through Claude Code's own plugin inventory (claude plugin list, plugin details footprint captured as CLAUDE PROJECTED, never as a saving), local companion state file, and an ecosystem doctor (read-only health, overlap, and conflict report). Status 2026-08-13: built under the founder's build-before-verdict amendment (release still gated); data/companions.json is schema v2, scripts/discover_companions.py and scripts/doctor.py ship, `python3 scripts/cli.py doctor` is wired in. CI wiring and the README/ATTRIBUTION doc updates are a separate builder's file fence tonight, not yet reconciled here.
- **v1.8 wave 2: judge the stack.** Machine-readable compatibility matrix (data/compatibility.json), hook ownership table, overlap detection with suppression of Token Shield's own duplicate advice when an active companion owns the capability, suppression memory and cooldowns for rejected or failed treatments.
- **v1.9: work the treatments.** Companion adapter layer (scripts/companions/, one adapter per verified companion), mode guidance phrased as intent (conservative, balanced, aggressive), guided install and rollback recipes from the curated registry only, marginal attribution waterfall on the dashboard.
- **Later: the open contract.** An optional token-shield.integration.json any optimization plugin can ship to declare capabilities, modes, state and health commands; Token Shield keeps supporting companions that never adopt it.
- **Later: MCP as a distribution channel (founder direction, 2026-08-12 night).** A separate, opt-in Token Shield MCP server exposing the deterministic surface (profile, advise, experiment, report) to any MCP client: Claude Desktop, editors, other agents. Shipped as its own package, never bundled into the plugin, because an always-loaded MCP server would tax the very startup floor this tool exists to shrink and would break the plugin's cache-safe, zero-hook posture. Same gate as the rest of this section.

Cautions recorded at adoption, so they are not rediscovered the hard way:

- The blueprint is single-sourced research. Its descriptions of specific companion internals (context-mode, Claude DCP, Caveman 2 proxy modes) are UNVERIFIED here; no registry entry ships until the companion's real source, hooks, and modes are confirmed first-party, the same discipline that caught the token-saver identity mixup recorded in docs/CLAIMS.md section D.
- Blueprint P0 to P10 ordering is superseded by the gate above: its Experiment Engine V2 items largely shipped in 1.7, and its Fable Deep Selector is the gated 1.8 deep advisor, not a new track.

## Passed on

- **Status line, the 7-Day Diet, Show Your Shield community, case studies.** Growth and marketing, not code. Discussions is a checkbox, not a build.
- **AI analysis of the dashboard.** Spending model tokens to explain how to save model tokens breaks the product's whole point. The skill already handles deeper reasoning on demand.

## The one decision we recorded

We reversed the deliberate "ship no price table" stance. It is sound only with four guards, all now in place: a dated snapshot, a staleness cutoff that degrades to NO PRICE DATA, per-model rows with an unpriced bucket, and API-equivalent wording for subscription usage. Missing any one, we keep the no-price stance.

## Absolute-lead integration (founder order, 2026-08-14)

The position, ratified: Token Shield measures where your tokens actually go, decides which optimizer (including none) deserves to run, and proves the result with labeled evidence. Your tool is a treatment; this is the diagnosis and the verdict. It must be best at measurement truth, at personalized diagnosis and selection, and at causal proof with revalidation. It deliberately does NOT compete on compression technique, behavioral coaching, context isolation, live dedup blocking, or behavioral injection of any kind.

Full judgment, adoptions, rejections and sequencing: docs/superpowers/plans/2026-08-14-absolute-lead-integration.md. Adopted in priority order: PRO2 pressure signals, TOUR1 treatment tournament, METR1 treatment-specific metrics, FACTS1 truth registry with a stale-fact circuit breaker, HIST1 historical marking on version change, DASH1 dashboard strip, LAB1 selection benchmark (post-verdict).

Eleven proposals were REJECTED, and the reasons matter as much as the adoptions: a native brevity ladder and shadow-mode dedup would put us in a straight fight with ponytail and DCP at their own techniques, both need behavioral injection or a default hook, and the blueprint's self-scored capability table would trade an honesty label for a score. The accepted-result north star stays deferred until a reliable acceptance signal exists, because a weak heuristic acceptance is a guess wearing a label.

Gate update 2026-08-14: the experiment closed with an honest NOT_PROVEN on the founder's explicit early-close decision, which opens the release boundary under the ratified amendment. Release steps still require the founder's confirmation of the tag and the publish.
