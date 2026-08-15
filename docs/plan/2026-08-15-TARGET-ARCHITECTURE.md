# Token Shield: target architecture, 2026-08-15

Governing document for the next month of engineering. Written against: the
architecture brief of 2026-08-15, docs/ARCHITECTURE.md, scripts/test_architecture.py
(the LAYERS dict is the authority), docs/ATTRIBUTION.md, data/fleet.schema.json,
data/signals.schema.json, scripts/experiment.py, scripts/guided_apply.py,
scripts/signals.py, scripts/session_end_telemetry.py, scripts/fleet.py (structure),
scripts/advisor.py (structure), scripts/trial.py, scripts/cli.py,
scripts/measure_tokens.py, and a research pass over the official Claude Code docs
(hooks.md, statusline.md, plugins-reference.md, costs.md, changelog.md,
discover-plugins.md, all opened 2026-08-15). Platform facts below cite those pages.
No em or en dashes anywhere in this file, per repo law.

## 1. The one-paragraph shape

Token Shield is a layered, stdlib-only Python pipeline that runs the loop MEASURE,
DIAGNOSE, TREAT, PROVE, LEARN over files that already exist on the user's disk,
spending zero model tokens and registering zero hooks by default. The floor (L0)
reads Anthropic's own transcript counters; L1 turns them into the quantities the
product talks about (metrics, prices, experiments, signals); L2 and L3 propose and
rank changes; L4 is the one advisor; L5 is the one renderer where every label,
caveat and colour is decided; L6 aggregates machines; L7 is one entry point per
thing a person can run. Every honesty defect this project has shipped had one
shape, two surfaces onto one number, so the architecture's single organizing rule
is that every number has exactly one producer and every surface reaches it through
that producer: imports point down, KNOWN_UPWARD is empty, computing layers may not
emit markup, and the additions in this document (an export producer, a status line,
an observation bundle) are each designed as one more door onto the same room, never
a second room.

## 2. The five core contracts (six named, four folded, two pinned)

The WBS names Fact, Observation, Problem, Treatment, Trial, Verdict. Verdict and
Trial already exist in experiment.py; Observation exists in signals.py; Problem and
Treatment exist across advisor.py, data/strategies.json and guided_apply.py. The
decisions below fold wherever a thing exists. Two new data files total.

### 2.1 Fact: JSON on disk, contract pinned by a NEW schema file

What it is: one measured session row, appended by scripts/session_end_telemetry.py
(L0) to ~/.claude/token-ledger.jsonl (its DEFAULT_LEDGER). The row already exists;
what does not exist is a written contract, and docs/ARCHITECTURE.md names "runtime
coupling through files" as a check blind spot held only by the two existing
schemas. signals.py (L1) and fleet.py (L6) both read this file today.

Decision: keep the row as-is; add NEW data/ledger.schema.json documenting it,
following the signals/fleet schema style (versioned, additionalProperties false,
descriptions carrying the honesty semantics). Writer stays L0. The schema file is
documentation-grade first; a reader-side conformance check lands with the export
work.

Fields, verbatim from session_end_telemetry.record():

| field | required | absence means |
|---|---|---|
| recorded_at | yes | row is unusable, skipped as NO DATA, never guessed |
| session_id | no | hook payload carried none (manual --transcript run) |
| transcript | yes | basename only, never a full path; absence = unusable row |
| schema | yes | meter schema unknown; cross-schema comparison refused |
| calls | yes | no call count, session contributes NO DATA |
| first_request | yes | no startup floor for this session |
| first_request_share | yes | derived; absent when first_request absent |
| input | yes | counter not present in transcript: NO DATA, never zero |
| cache_read | yes | same rule |
| cache_write_5m | no | transcript lacked split write classes |
| cache_write_1h | no | same |
| cache_write_unsplit | no | present exactly when the split was unavailable |
| normalized_input | no | NO DATA when split classes were unavailable |
| output | yes | counter rule as above |
| hit_ratio | no | denominator empty: NO DATA |
| rewrite_ratio | no | same |
| models | no | distinct-model count; absence = model tracking predates row |
| subagent_calls | no | no subagent data observed |
| subagent_output | no | same |

The load-bearing rule the schema text must carry: an absent counter is NO DATA
for that quantity and is never zero-filled. The 5m/1h/unsplit triple exists
precisely so an unsplit write is never priced as a 5 minute one
(measure_tokens.py, "Transcripts that do not carry the split write classes get
NO DATA").

### 2.2 Observation: FOLD into the signals report

Already exists: data/signals.schema.json (schema_version 1) plus scripts/signals.py
(L1), which builds a candidate and then walks the schema (_project) copying only
named fields. That IS the observation contract: day grain, quantized shares,
banded counts, absent-over-fabricated everywhere. No new file, no dataclass.
Fields are the schema's: schema_version (required), report_date (required),
submission_id (S2 send-time only), environment (platform,
claude_code_minor_version, model_family_mix, token_shield_version), waste_shares
(eight classes), error_classes (four), overspend_markers (three),
treatment_outcomes. Absence of any optional field means "not measured", by the
schema's own descriptions; S1 populates only startup_rent, cache_cold_rebuilds
and unknown because only those have an honest ledger basis (signals.py docstring).

### 2.3 Problem: FOLD into the advisor's card machinery

Already exists, in three cooperating pieces: profile.py (L1) writes the labeled
evidence (~/.token-shield/profile.json, labels MEASURED, SIGNAL, INFERRED, NO
DATA per advisor.py's PROFILE_LABELS); data/strategies.json declares triggers
(REQUIRED_TRIGGER_FIELDS: metric, op, value, band); advisor.py (L4) evaluates
triggers and raises a card with a problem_class (PROBLEM_CLASSES set in
advisor.py). A Problem is therefore a strategy trigger firing on a labeled
profile leaf. Decision: no new artifact of any kind. The one addition is prose:
docs/ARCHITECTURE.md's layer table gains one line saying L4 is where a Problem
becomes a rankable object, so nobody reinvents it at L2. A trigger whose metric
is absent from the profile raises no card: NO DATA suppresses, it never guesses.

### 2.4 Treatment: FOLD into data/strategies.json plus the guided_apply contract

Two halves already exist. The declarative half is a data/strategies.json entry
(advisor.py REQUIRED_FIELDS begin: id, category, problem_class, title, trigger,
what_it_changes). The executable half is guided_apply.apply(label, treats,
mutate_fn, verify_fn) at L2: refuse if any experiment is open, mutate, verify,
auto-open exactly one experiment (read in full; this is the mutation contract).
Decision: no new proposal format; the three producers keep their own review
directories as designed (guided_apply.py docstring, design decision 2).

One promotion, no new file: data/strategies.json ids are DECLARED the public
treatment registry that data/signals.schema.json's treatment_outcomes field
anticipates ("keyed by public treatment registry id... No public treatment
registry exists yet"). One list, one owner, at the layer the schema can reach.
NEW conformance check in test_signals.py: every strategies.json id matches the
schema's key pattern ^[a-z0-9_.-]+$, so a future S2 send never meets an id it
must degrade to "other". (Current ids UNVERIFIED against that pattern; the check
settles it.)

### 2.5 Trial: FOLD into the experiment baseline, unchanged

Already exists: one JSON baseline per open experiment under
~/.claude/token-shield/experiments/ (experiment.py EXP_DIR), pinned by cmd_start,
consumed by build_record. Fields, as build_record and V2_BASELINE_KEYS read them:
label (required), schema (required; mismatch downgrades), window_days (required),
summary (required; the before cohort), cohort_start_ts and cohort_end_ts
(required for v2; absence marks a legacy baseline that can never reach VERIFIED,
only NOT_PROVEN with the reason named), fingerprint_start, fingerprint_method
(absence or mismatch means the fingerprints are not comparable: NO DATA by name,
never "changed" or "unchanged"), treats, fingerprint_excluded, target_metric
(absence reads as DEFAULT_METRIC, first_request_median). Decision: no schema
file. Exactly one writer and one reader exist, both in experiment.py, so a
schema file would be a second description of a single-owner contract, which is
the drift shape this repo exists to prevent. The moment a second writer appears,
that decision flips.

### 2.6 Verdict: FOLD into the savings ledger record; pin an export whitelist

Already exists: one record per ended experiment, appended to
~/.claude/token-shield/savings.jsonl by experiment.build_record (read in full),
EXP_SCHEMA 2. The full field list is build_record's return: schema, timestamp,
label, confidence (VERIFIED or NOT_PROVEN), reasons, window_days, cohort_before,
cohort_after, fingerprint_start, fingerprint_end, fingerprint_excluded, treats,
first_request_before, first_request_after, floor_reduction_tokens, direction,
target_metric, metric_before, metric_after, metric_delta, sessions_before,
sessions_after, dispersion_before, dispersion_after, normalized_input_before,
normalized_input_after, models_before, models_after, evidence. Required core:
schema, timestamp, label, confidence, reasons; a null metric_delta means the two
sides were not numerically comparable and the record says why in reasons.

This file has MULTIPLE direct readers today (cli._verified_by_label,
metrics.latest_row_per_label consumers, fleet._day_experiments), which is the
exact condition under which a code-only contract drifts. Decision: build_record
stays the sole authority for MEANING; add NEW data/savings.schema.json as the
frozen field whitelist that the export layer (section 7) walks via
signals._project, the same construction fleet.py already uses against its own
schema. The schema file exists for the exporter and for readers outside this
repo (a warehouse), not as a competing definition: its description says so, and
a test asserts the schema's property set equals build_record's key set, so the
two cannot drift silently.

### Contract-to-file summary (the done-check row)

| Contract | Disposition | File path | Layer |
|---|---|---|---|
| Fact | JSON on disk (exists); NEW schema pin | data/ledger.schema.json (NEW); writer scripts/session_end_telemetry.py | 0 |
| Observation | FOLD | data/signals.schema.json + scripts/signals.py | 1 |
| Problem | FOLD | data/strategies.json + scripts/advisor.py (evidence from scripts/profile.py) | 4 (evidence at 1) |
| Treatment | FOLD | data/strategies.json + scripts/guided_apply.py | 2 (registry data at repo data/) |
| Trial | FOLD | ~/.claude/token-shield/experiments/*.json via scripts/experiment.py | 1 |
| Verdict | FOLD + NEW export whitelist | ~/.claude/token-shield/savings.jsonl via scripts/experiment.py; data/savings.schema.json (NEW) | 1 |

## 3. The layer map, revised

Target table. Unchanged rows compressed; LAYERS in scripts/test_architecture.py
remains the single authority and changes in the same commit as any module below.

| L | Name | Modules (target) | Change |
|---|---|---|---|
| 0 | foundation | config, formatting, measure_tokens, context_lint, session_end_telemetry, check_py311 | _harden(path, mode) moves INTO config.py; fleet.py and signals.py delete their byte-identical copies. This is the exact "foundation module" fix docs/ARCHITECTURE.md already names for that duplication. config.py also gains the consent reader (section 4). |
| 1 | metrics | metrics, pricing, experiment, profile, signals | unchanged |
| 2 | proposal | guided_apply, optimize, discover_companions | unchanged |
| 3 | advice and ecosystem | companions, plugin_prune, memory_trim, doctor | unchanged |
| 4 | advisors | advisor, deep_advisor | unchanged |
| 5 | presentation | token_shield | unchanged |
| 6 | fleet | fleet, export (NEW) | export.py: the one export producer. Reason: it must read the single-machine ledgers (L1 and below) AND the fleet store reader (fleet.py, sideways at L6, legal: a module may import its own layer), and it must sit BELOW every surface so no format can disagree with another. |
| 7 | surfaces | cli, trial, report, detail_report, share_card, fleet_dashboard, reconcile, obsidian_export, statusline (NEW) | statusline.py: one entry point Claude Code invokes per render (section 8). A surface by definition. |

New upward-import risks this design creates, and the avoidance for each:

1. export.py wanting presentation labels from token_shield (L5). Not upward
   (6 imports 5 is downward) but it IS the two-doors risk: export must take its
   confidence labels from the same constants surfaces use. Avoidance: labels are
   data, not markup; the enum lives at L1 or below (advisor.py's
   EVIDENCE_LABELS shows the set already exists in code), and export carries
   label strings only, never rendering.
2. fleet_dashboard.py (L7) and export.py (L6) sharing suppression logic.
   If suppression stayed in the dashboard, export would need L6 to L7, a real
   upward import. Avoidance: the k-anonymity gate moves DOWN into fleet.py
   (section 5) before export ships. This ordering is mandatory.
3. statusline.py tempted to import cli helpers (L7 sideways, legal but wrong:
   cli is a leaf by decision, docs/ARCHITECTURE.md). Avoidance: statusline
   phase 1 imports formatting (L0) at most; it renders pass-through platform
   numbers (section 8).
4. session_end_telemetry (L0) gaining observer-bundle events and wanting
   metrics (L1). Avoidance: the observer writes raw rows only; interpretation
   stays at L1. L0 stays the floor.

KNOWN_UPWARD stays empty. Any design change that would require an entry is a
wrong design by definition, per docs/ARCHITECTURE.md "Adding something new" rule 2.

Housekeeping found while reading: the docstring of
test_the_frozen_list_is_exactly_the_five_known_today (scripts/test_architecture.py
line 158) still narrates "the five known today" while correctly asserting zero.
Update the docstring in the same commit that next touches LAYERS.

Directories: NOT yet. The imports are flat by name ("import metrics"), the hook
loader resolves measure_tokens.py by file path (session_end_telemetry.load_measure
uses importlib.util.spec_from_file_location), and the LAYERS dict already gives
the enforcement a directory layout cannot add. What would have to be true first:
module count crossing about 40 (30 today, counted from LAYERS), or plugin
packaging demanding package-qualified imports, or a second regular contributor.
Until one of those is true a directory move is churn across every import, every
test, and the hook loader, for zero enforcement gain: docs/ARCHITECTURE.md's own
rejected alternative 2, still correct.

## 4. The observation plane

Constraint stack: zero hooks by default, zero model tokens, zero context
injection, and the design assumption that MOST users never enable a hook.

What the transcripts alone tell us (no hook, no consent needed, on demand):
everything measure_tokens.py reads today: per-message usage counters (the
billing counters), split cache write classes, first-request floor, hit ratio,
normalized input, distinct models, subagent split, message timestamps (which is
why experiment cohorts work with no hook at all: experiment.py v2 builds cohorts
from each record's own message timestamp). The transcript format is
UNDOCUMENTED: path pattern ~/.claude/projects/<escaped-cwd>/<session-uuid>.jsonl
with message.usage fields confirmed only by reading a real local file (research
pass 2026-08-15; no spec page exists). Section 9 treats this as the number one
break risk. The transcripts also contain tool-call records the meter currently
ignores; error and retry classes (signals.schema.json's empty error_classes)
are in principle recoverable from transcripts after the fact, without any hook,
by a deeper parse that still reads counters and structure, never content.

What only a hook can tell us: the moment a session ends (timely ledger append),
config changes as they happen (versus the fingerprint knowing only THAT
something moved between start and end), compaction events and whether they were
manual or auto, and subagent lifecycle in real time. Per the hooks reference
(code.claude.com/docs/en/hooks.md, opened 2026-08-15): 31 hook events exist and
27 are silent to the model, injecting nothing and costing zero tokens; only
UserPromptSubmit, UserPromptExpansion, PostToolUse and PostToolUseFailure can
inject. Silent events include SessionStart, SessionEnd, ConfigChange (matchers
user_settings, project_settings, local_settings, policy_settings, skills),
PreCompact and PostCompact (matchers manual, auto), SubagentStart, SubagentStop.
Every hook receives session_id and transcript_path on stdin.

Which events are worth the opt-in:

- WORTH IT, as one bundle: SessionEnd (exists today), ConfigChange, PreCompact,
  PostCompact, SubagentStop. All silent, all rare (once per session or per
  event, never per tool call), all writing to local disk only. ConfigChange is
  the standout: it timestamps exactly the confounders the experiment
  fingerprint can only detect after the fact, so a NOT_PROVEN verdict can say
  WHEN and WHICH config moved. PreCompact and PostCompact give compaction a
  measured basis (a waste class signals cannot honestly fill today).
- NOT WORTH IT: PreToolUse and PostToolUse for observation. Per-tool-call
  process spawns on every action, and the facts are recoverable from the
  transcript afterwards. The ONLY reason to touch the per-call path is
  enforcement (a budget guard), which is founder decision 1, not observation.
- NEVER, regardless of consent: the four injecting events for any observational
  purpose. Zero context injection is law 4.

How the opt-in is asked exactly once and honoured forever: the plugin ships NO
hooks/hooks.json. The plugins reference confirms a plugin can declare all 31
events there, which is precisely why we must not: a declared hook is a
registered hook, and law 2 says zero by default. Instead /token-shield:start
(commands/start.md, one of the six existing command files) asks once, shows the
exact event list and the exact fields written (the ledger schema of section
2.1), and on yes writes the hook entries into the USER'S own settings and
records the decision in NEW ~/.token-shield/consent.json: {decided_at, answer,
schema_version, events}. Reader lives in config.py (L0). Any later surface that
would benefit from the hook checks consent.json and stays silent if a decision
of either kind exists: asked once means never nagged, and a recorded "no" is
honoured exactly as long as a recorded "yes". The one re-ask trigger is a
schema_version bump, the same consent rule data/signals.schema.json already
states for itself.

What happens to every downstream number when the user says no (the majority
case, designed for rather than tolerated):

- summary, dashboard, trial, profile, advise, report: unchanged. All read
  transcripts on demand.
- experiments and verdicts: unchanged. Cohorts never needed the hook.
- signals rollup: NO DATA (no ledger). cmd_rollup says so; nothing fabricates.
- fleet record: still valid (schema requires only schema and date), with
  counters absent, not zeroed. An org sees participation without telemetry.
- statusline: UNCHANGED AND LIVE, because the status line is not a hook:
  Claude Code pushes the numbers to it per render (section 8). This is the
  design's answer to "most users never enable a hook": the always-visible
  surface works for them anyway.

## 5. The privacy boundary, as an auditable rule

The rule, checkable by a data protection officer, per mode:

Mode 1, single machine, no network (the default). Nothing crosses the machine
boundary. Auditable as: signals.py contains no socket, urllib, or http.client
code (its docstring states this; grep verifies it); the only network-capable
module is fleet.py, which runs git by subprocess only inside explicit fleet
commands; no hook is registered by default (no hooks/hooks.json exists in the
plugin). Field inventory crossing the boundary: none.

Mode 2, opt-in local telemetry. Crosses a process boundary into one local file,
~/.claude/token-ledger.jsonl. Exactly the ledger fields of section 2.1: counters,
recorded_at, session_id, transcript basename, schema, distinct-model count.
Never conversation text, never a full path, never a repo or user name
(session_end_telemetry.py, "WHAT IT DOES NOT DO"). Auditable as: the writer is
one function (record) whose returned keys are the whole row, plus NEW
data/ledger.schema.json to check it against.

Mode 3, org fleet store. Crosses the machine boundary into a git repository the
org owns. Exactly the data/fleet.schema.json fields: schema, date, machine_id
(sha256 of hostname plus org salt), team, environment, counters (per model
bucket: input_tokens, output_tokens, cache_read_input_tokens,
cache_creation_input_tokens), experiments (label, confidence, timestamp,
target_metric, metric_delta, direction, fingerprint_start, fingerprint_end),
config_fingerprint, token_shield_version. Enforced by construction: the record
is built by walking the schema (signals._project reused, per the schema's own
description) with additionalProperties false everywhere, never by deleting bad
parts from a larger object.

The k-anonymity rule and its single enforcement point. The rule: no view
publishes an aggregate standing on fewer than five distinct machines, AND the
withheld remainder must itself stand on five, because a five-machine group
beside a six-machine total handed back the sixth by subtraction (the shipped
defect, brief and docs/ARCHITECTURE.md). Today the complement logic lives
inside fleet_dashboard.py's render path (its render_tag_totals docstring, lines
798 to 812, narrates the five-plus-one case). That is one surface owning a
privacy invariant, which is exactly how a second surface reimplements it
differently. TARGET: the suppression moves DOWN into fleet.py (L6) as one
function, NEW fleet.suppress_small_groups(groups, k=5), enforcing both the
group floor and the complement floor, with fleet_dashboard.py and export.py
both required to call it and a test that greps for any other module computing a
machine-count threshold. Export work does not start until this move lands.

Residual risks that cannot be designed away, with the honest disclosure each:

1. The org salt reaches every joined machine, so any salt holder can hash
   candidate hostnames and unmask machine_id. Disclosure: the store is
   INTERNAL data, not anonymised data (already stated in the brief and
   docs/ARCHITECTURE.md; keep saying it in docs/FLEET.md and the join
   disclosure text fleet.py writes).
2. Experiment labels are user-chosen free text up to 200 characters
   (fleet.schema.json) and ride into the store. A label can name a private
   project. Disclosure: say it at push time; mitigation candidate is a
   warn-and-confirm on first push of a new label, never silent rewriting.
3. Git history is not erasure. Deleting a record leaves it in history; real
   erasure is a history rewrite (docs/ARCHITECTURE.md says this plainly; keep
   it plain).
4. Commit metadata leaks activity timing. Records are day-grain by schema, but
   every push creates a commit whose timestamp is second-grain, so the store's
   log is a presence trail per machine. Cannot be removed while git is the
   transport. Disclosure: state it in docs/FLEET.md; mitigation candidate is
   batched or queued pushes (the local queue in fleet.py already exists), which
   blurs but does not remove the trail.
5. Works-council exposure attaches to CAPABILITY, not intent (German Works
   Constitution Act section 87(1) no. 6, cited in the brief and docs/FLEET.md).
   The honest statement: this system is CAPABLE of per-machine measurement at
   the store layer even though no view publishes it; adoption in a German shop
   needs the council's involvement regardless of our suppression.

## 6. Trust for org records, given zero dependencies

The gap: records are unsigned; anyone with push access can forge any machine's
record. The previously decided design (machine key at join, public half in the
record) is unbuildable as decided: no crypto library is allowed, stdlib HMAC
needs a shared secret, and a public key stored inside the record is rewritten
with the record. Three options, ranked.

Option A, RECOMMENDED: stay unsigned, say it loudly, and add tamper EVIDENCE
plus host-side controls. Three parts: (1) keep the plain statement in
docs/FLEET.md and the join disclosure that any push holder can forge any
record; (2) NEW field prev_record_sha256 in the fleet record (schema bump to 2,
which per the schema's own rule re-asks consent): each machine's record carries
the hash of its previous record, making a machine's lane a hash chain, so
silent edits and deletions break the chain and are DETECTED, though not
prevented; (3) documented deployment requirement that the store repo enables
the host's branch protection and force-push refusal, so rewrites are loud and
the host's push audit log attributes every write to an authenticated account.
Costs: a schema bump, about a day of code and tests, one docs section. Defends
against: silent tampering, accidental corruption, deniable forgery (the host
log names the pusher). Does not defend against: a push holder openly appending
a forged record for another machine (the chain break names the victim lane, not
the author; the host log names the author). What would make it insufficient: an
adopter whose threat model includes malicious insiders with admin rights on the
store; that adopter needs option B.
Flip condition: the first enterprise security review that refuses unsigned
records in writing flips this to option B.

Option B, the viable upgrade: OpenSSH signatures by subprocess. ssh-keygen -Y
sign at push, ssh-keygen -Y verify at read, against an allowed_signers file
committed at join, first write wins, protected by the same branch rules as
option A. No new Python dependency; a new RUNTIME dependency on OpenSSH 8.0 or
newer being on PATH, stated plainly rather than smuggled (git over SSH already
implies OpenSSH on most fleet machines; Windows presence UNMEASURED, and the
design must degrade to "record unsigned, reason: no ssh-keygen" rather than
fail). Costs: a join ceremony (keygen, publish, pin), per-machine key custody,
a verify pass in fleet_dashboard and export, and the hard truth that whoever
can rewrite allowed_signers can re-pin, so the anchor is still the host's
branch protection. Defends against: forgery by any push holder who is not a
store admin, with per-record non-repudiation. Does not defend against: a store
admin, or a compromised machine key. What would have to change to make it
viable: nothing technical; it is buildable today. It is not recommended FIRST
because it roughly doubles fleet complexity to defend against an insider the
org already trusts with the repo, before any org has asked.

Option C, listed to be rejected honestly: org-wide shared-secret HMAC (stdlib
hmac). Every joined machine holds the same secret, so every legitimate member
can forge every other member, and a leaked secret converts the whole store's
history to unverifiable. It defends only against an outsider who somehow gained
push access but not the secret, a threat the host's authentication already
covers. This is the half signature the brief warns about: it LOOKS signed and
proves almost nothing. Rejected.

Recommendation: A now, B on the flip condition, C never. The honest sentence
that ships either way: "authenticity of a fleet record rests on your git host's
access control and audit log; Token Shield adds tamper evidence, not
tamper proof."

## 7. The connector and export layer for analytics and FinOps

The seam. ONE export producer: NEW scripts/export.py at layer 6. Every format
is a serializer over one internal row stream; no format computes anything. It
reads single-machine numbers through metrics/experiment/signals (L1) and org
records through fleet.load_record (L6 sideways), applies
fleet.suppress_small_groups for any org scope, and walks data/savings.schema.json
(NEW, section 2.6) for verdict fields via signals._project. Surfaces (cli at
L7) invoke it; nothing invokes a format directly. A second surface that wants a
number in a new shape adds a serializer here or does not ship.

Formats, ranked by what a real team asks for first:

1. CSV (first, because every FinOps tool ingests it; CodeBurn's own export
   defaults to it, per the brief). Stdlib csv module.
2. JSON / JSONL (same rows, machine-readable; also the collector-tail vehicle
   below). Stdlib json.
3. Warehouse table shape: the CSV columns below ARE the table shape, one
   documented grain, loadable into BigQuery or Snowflake as-is; we ship the
   column documentation, not a loader.
4. OpenTelemetry: we do NOT duplicate what Anthropic emits.
   claude_code.token.usage and claude_code.cost.usd already exist first party
   (docs/ATTRIBUTION.md). What we ADD is the proof stream: verdict records
   (VERIFIED and NOT_PROVEN, with metric_delta and direction) and labeled
   waste shares, which no first-party metric carries. Honest zero-dependency
   verdict: hand-rolling OTLP over HTTP encoding is spec mimicry against a
   moving protobuf mapping and is refused; the zero-dependency path is JSONL
   on disk that an org's existing collector tails (filelog-style receivers are
   standard collector equipment), and the WITH-dependency path is founder
   decision 3. Said plainly: native OTLP push needs a dependency; we do not
   pretend otherwise.
5. Webhook: POST of the JSON export to one configured URL. Stdlib
   urllib.request. Opt-in, explicit invocation only, never in the default
   path (law 5); the URL comes from the invocation or local config, never
   hardcoded.
6. Slack or chat summary: a plain-text digest (top verdict, top opportunity,
   day totals with labels) posted through the same webhook sender. One sender,
   two payload shapes.
7. Prometheus scrape: honest zero-dependency answer is the textfile pattern,
   not a server: export.py writes a .prom text exposition file
   (token_shield_verified_delta{label=...}, token_shield_tokens_total{...});
   the org's node exporter textfile collector picks it up. No daemon, no
   port, no library. A live metrics HTTP endpoint would mean a resident
   http.server process, refused in section 10.

What a FinOps person actually needs that nobody in this field ships: not
another spend counter (Anthropic's dashboard and /usage own spend, and /usage
now attributes by skill, subagent, plugin and MCP server first party, per
costs.md opened 2026-08-15). The unshipped thing is COST OF WASTE BY CAUSE WITH
A CONFIDENCE LABEL, and PROOF-ADJUSTED SAVINGS PER TREATMENT: which change was
made, on how many machines, and the verified delta, so a platform team can
report "this rollout is proven, this one is not" instead of "spend moved".
Grain: per machine per day per model bucket for usage rows; per experiment
label for proof rows; per org per day for k-gated aggregate rows.

The exact column design (one narrow layout; every number carries its own label,
which is how the VERIFIED, MEASURED, ESTIMATED and NATIVE distinction survives
any spreadsheet):

export_schema, generated_at, scope, org, team, machine_id, record_date,
window_days, metric, model_bucket, value, unit, confidence, basis,
experiment_label, treatment_id, machine_count, plugin_version

Rules, enforced in export.py and tested: confidence is exactly one of VERIFIED,
MEASURED, ESTIMATED, NATIVE, RECOMMENDED; unit is one of tokens, ratio, count,
share_pct_bucket, usd_api_equivalent; a NATIVE row never carries unit
usd_api_equivalent (law 7 exported); there is NO total row and no cross-label
sum anywhere in any file (a consumer may sum, the artifact never does);
machine_id is populated only at scope=machine on that machine's own export;
scope=org rows carry machine_count, and machine_count is at least 5 or the row
does not exist, with the complement rule applied before rows are emitted. basis
carries the evidence sentence (for verdicts, the record's own evidence field).

How an export cannot become a privacy leak, given the subtraction precedent:
org rows pass through fleet.suppress_small_groups, the SAME function the
dashboard uses (section 5), so the export can never publish a slice the
dashboard would withhold; the machine_count column makes the guarantee
auditable inside the artifact itself; and no org export ever contains
machine_id at all, so no join key exists to reverse the aggregation. A
machine-scope export is the user exporting their own data and is not suppressed.

## 8. The surface and UX architecture

Context: CodeBurn ships a terminal interface, a macOS menu bar app, desktop
apps, and a localhost dashboard. The platform facts that decide our answer
(research pass 2026-08-15): plugins cannot render an interactive panel inside
Claude Code (confirmed absent, not unfound; experimental monitors inject context
and therefore cost tokens, refused); plugins CANNOT register a status line
(plugin.json has no statusLine field), but a user can add one line to
settings.json pointing at any command, and Claude Code then invokes it per
render with a JSON payload on stdin carrying, among documented fields,
context_window.used_percentage, context_window.remaining_percentage,
cost.total_cost_usd, model.display_name, effort.level, and for Pro and Max
subscribers rate_limits.five_hour and rate_limits.seven_day used_percentage
and resets_at (statusline.md).

The surface set, decided:

1. The HTML dashboard (exists, token_shield.py L5 rendered via cli dashboard,
   written to ~/.token-shield/token-shield.html). Stays the rich surface: a
   file the user opens, zero process cost, zero tokens. No web server.
2. The status line, NEW scripts/statusline.py (L7). Technically: a stdlib
   Python script reading one JSON object on stdin per render and printing one
   line. This is the honest answer to the menu bar app: an ALWAYS-VISIBLE
   LIVE NUMBER, pushed by Claude Code itself, zero hooks, zero model tokens,
   zero daemon, works for the majority who never opt into anything. So the
   explicit question has an explicit answer: yes, a stdlib-only plugin can
   give a Claude Code user an always-visible live number, via the user-added
   statusLine command. Render content, phase 1: context percentage used,
   remaining percentage worded (not coloured; text), five-hour and
   seven-day rate limit percentages when present, model name. Degradation:
   rate_limits is absent for non-subscribers and before the first response in
   a session; the script prints what exists and omits what does not (NO DATA
   discipline at one-line scale), never a placeholder zero. Latency budget:
   the render path reads stdin and prints; it opens NO transcript and runs NO
   scan; Python interpreter startup is the whole cost (UNMEASURED; measure
   with the bench harness before shipping, and if it is felt, the script is
   small enough to rewrite the hot path as read-parse-print only). Second-door
   rule: phase 1 renders ONLY platform pass-through numbers, attributed as
   Claude Code's own, and no Token Shield metric, so it cannot disagree with
   the dashboard because it shares no number with it. Any phase 2 Token Shield
   figure must come through metrics (L1), decided at that point, not smuggled.
   Founder decision 4 governs. Cost to build: small (one script, one test).
   Cost to user: one settings line they paste themselves; the setup flow
   prints the exact line, never writes settings.
3. The MCP server (exists: mcp-server/, tests in mcp-server/test_mcp_server.py,
   repointed at metrics in commit 8acf5ad). Stays the agent-facing surface,
   the analogue of codeburn mcp. Its numbers already route through metrics,
   which is the one-door rule holding.
4. The CLI (exists, cli.py, one entry point, subcommands). All new capability
   (export, consent, statusline setup snippet) lands as cli subcommands. The
   COMMAND FILE cap of 6 is already fully spent (commands/: token-audit,
   stats, monthly, advisor, start, optimize), so no new slash command exists
   without a founder decision to retire one. Not requested here: the cap
   holds.
5. NO terminal interface, NO menu bar app, NO desktop app, NO localhost web
   server. Reasons in section 10.

The answer to npx codeburn. Two prongs, both distribution rather than code:
(1) the official plugin marketplace: a listed plugin installs in ONE command,
and archive sources (zip over HTTPS, no git, no npm) landed 2026-08-13
(changelog.md, discover-plugins.md), so the install story reaches CodeBurn
parity without Node; (2) for the no-install stranger, scripts/trial.py already
runs from a checkout, and the gap to npx is the checkout itself: close it with
a stdlib zipapp, a single token-shield.pyz built with python3 -m zipapp at
release, downloaded and run as two copy-paste lines with no install and no
dependencies. Both prongs are RELEASE ACTS and therefore sit behind the
ratified gate (no tag, no release, no publish until the claude-md-diet
experiment reaches VERIFIED or NOT_PROVEN, per the founder amendment of
2026-08-13): build now, publish at gate-clear. Founder decision 5.

## 9. Scale-up path

Three scale points, and what changes at each:

1 machine (today): nothing changes. Everything is on-demand file reading; the
only standing artifacts are opt-in.

About 5 to 1,000 machines (fleet): the shape already holds: one record per
machine per day, pushed to a git store, day-partitioned by path
(fleet/<org>/<machine-id>/<date>.json per data/fleet.schema.json). At 1,000
machines the store accrues 365,000 files per year. What changes: pushes should
use shallow or sparse clones (a git capability, no dependency) and the
dashboard scan should read a bounded window rather than the full history.
Nothing in the record shape or the layer map changes.

Org with a warehouse: the git store remains the system of record for org
records; export.py's documented grain becomes the interface; the warehouse is a
derived copy loaded from the CSV or JSONL export. No rewrite, because the
exporter was built as the one producer from day one; the org's BI tools take
over presentation above the privacy gate.

Data ownership, stated once: transcripts are Anthropic's files and the system
of record for Facts; the ledger is a derived cache of them; savings.jsonl is
the system of record for this machine's Verdicts; the fleet store is the system
of record for org records; a warehouse is derived from the export. When two
disagree, the one closer to the counters wins and the derived copy is rebuilt;
nothing ever flows downhill from store to machine.

The thing that breaks first, named specifically: not the git store. It is the
TRANSCRIPT FORMAT, at every scale including one machine: the single most
load-bearing input (message.usage fields under ~/.claude/projects) is
undocumented and confirmed only by reading real local files (research pass
2026-08-15); Anthropic can change it without notice, and a silent mis-parse
would corrupt every number above L0. The design's defense is already partly
built (mt.SCHEMA versioning, refusal across schema changes, skipped-file
downgrades in build_record) and must extend to a loud NO DATA when expected
usage keys go missing at scale, never a quiet zero. Second breakage, growth
driven: the per-push full clone and the dashboard's full-store scan as machine
count and history grow. The number at which it breaks: UNMEASURED. The
measurement that settles it: extend the bench kit (bench/generate_corpus.py,
bench/run_benchmark.py) to synthesize a store of 1,000 machines by 365 days
and time fleet push_record and fleet_dashboard render against it; set the
mitigation threshold from those two timings, not from feeling.

## 10. What this design refuses to build, and why

1. hooks/hooks.json in the plugin. The hooks reference makes all 31 events one
   file away, which is exactly the temptation: a declared hook is a registered
   hook, and zero hooks by default is law 2. Observation stays a consented
   write into the USER'S settings.
2. A resident process of any kind: menu bar app, terminal-interface daemon,
   localhost web server, live Prometheus endpoint. The status line gives the
   always-visible number with Claude Code doing the scheduling; the HTML file
   gives the rich view; a daemon is a support surface, a battery cost, and a
   second door.
3. A hand-rolled OTLP encoder. Spec mimicry without the spec's library breaks
   silently on protocol evolution; the collector-tail JSONL path delivers the
   same data with zero dependencies, and native OTLP is founder decision 3.
4. Rebuilding per-plugin attribution. /usage now ships attribution by skill,
   subagent, plugin and MCP server first party (costs.md, 2026-08-15). This
   partially fires the flip condition docs/ATTRIBUTION.md wrote for itself
   ("if Anthropic ships per-cause attribution... the overlapping part stops
   being worth maintaining and this document says so at that point"), so
   ATTRIBUTION.md owes an update naming what stands down (any plan to compute
   per-plugin shares ourselves) and what remains ours (the proof loop,
   history beyond the 7 day window /usage covers, and the fact that NO
   standalone API exists to poll it).
5. An org-wide shared-secret HMAC dressed as signing. Half a signature is
   worse than an honest absence: it defends against nobody in the actual
   threat model while claiming cryptographic weight (section 6, option C).
6. sqlite (or any second store) for the ledger. Stdlib or not, a second store
   is a second door onto the same rows, plus a migration; JSONL is greppable,
   append-only, and NO-DATA-friendly. Flip only on measured parse-time pain
   at real scale, through the bench kit.
7. Model-token-powered diagnosis (an LLM classifying waste or writing the
   advice). Law 3, ratified WONTFIX, and CodeBurn's disputed classifier
   (one planning turn in 30 days for a heavy planner, per the brief's Hacker
   News citation) is the cautionary tale: a classifier without ground truth
   gets disputed, and NO DATA beats a guess.
8. Any total row, cross-label sum, or org league table in any surface or
   export. The invariant that never merges, extended to every artifact that
   leaves the machine; per-person performance views are refused at the
   privacy gate itself.
9. A Node or npm shim to imitate npx. Marketplace one-command install plus
   the zipapp reach the same friction with our own toolchain; shipping Node
   artifacts to imitate a competitor's installer buys nothing but a second
   toolchain to maintain.

## 11. The decisions only the founder can take

1. The hard budget guard. CodeBurn stops a session at a hard cap; we report
   and advise, and our own field map falsely said nobody enforces. Enforcement
   would need an opt-in hook on the per-call path and changes our posture from
   meter to actor.
   Options: (a) RECOMMENDED: build an opt-in guard behind its own separate
   consent, fail-open like CodeBurn's and say so plainly; (b) stay
   report-only and correct the field map row (the correction is owed under
   every option); (c) build fail-closed (a broken guard can then block
   sessions, an MDM incident waiting).
   Default if silent: (b): no guard is built, the field map correction lands
   anyway.
2. Fleet record trust. Records are forgeable by any push holder; the decided
   crypto design is unbuildable under zero dependencies.
   Options: (a) RECOMMENDED: unsigned and loud, plus hash-chain tamper
   evidence and documented branch protection (section 6 option A, schema bump
   to 2); (b) OpenSSH signing via ssh-keygen subprocess with pinned
   allowed_signers (option B, a runtime dependency stated plainly); (c) leave
   exactly as today, gap documented, no chain.
   Default if silent: (c) today's state persists; (a) is the prepared next
   step.
3. OpenTelemetry. Native OTLP push needs a dependency; the law says stdlib
   only.
   Options: (a) RECOMMENDED: no dependency: ship CSV, JSONL for collector
   tailing, and the Prometheus textfile; attribute Anthropic's own OTel for
   usage and cost; (b) accept one vetted dependency for OTLP in an OPTIONAL
   connector never imported by the core; (c) no OTel story at all.
   Default if silent: (a).
4. Statusline scope. The platform lets a user wire our script into an
   always-visible line, but a plugin cannot self-register it, and what it
   shows is a product posture question.
   Options: (a) RECOMMENDED: build phase 1 pass-through (context pressure,
   rate limits, model), setup prints the settings line for the user to paste,
   we never write their settings; (b) also surface one Token Shield number
   (today's tokens via metrics), accepting the two-doors review burden now;
   (c) do not ship a statusline.
   Default if silent: (a).
5. Distribution under the ratified gate. Marketplace listing and the
   token-shield.pyz zipapp are release acts; the amended gate forbids any
   release or publish until the claude-md-diet experiment reaches VERIFIED or
   NOT_PROVEN.
   Options: (a) RECOMMENDED: build both now, publish automatically at
   gate-clear; (b) build now, publish only on a second explicit go; (c) defer
   both entirely.
   Default if silent: (b): nothing publishes without his word; the gate
   already says so.
6. Observer bundle extent. Today's opt-in is SessionEnd only; the silent-hook
   facts make ConfigChange, PreCompact, PostCompact and SubagentStop cheap and
   valuable, but works-council law attaches to what a system is CAPABLE of,
   so widening collection is not an engineering call.
   Options: (a) RECOMMENDED: one bundle, one consent screen naming every
   event and field, schema bump re-asks; (b) SessionEnd stays alone,
   ConfigChange added by itself for experiment confounder witnessing; (c)
   status quo, SessionEnd only.
   Default if silent: (c).

## 12. Founder decisions already taken, 2026-08-15

Four were put to the founder through question windows on 2026-08-15 evening and
answered. They are recorded here because this document is written under them.

1. **Enterprise scope: design now, build individual only.** The enterprise and
   connector architecture is written this week (this document) and the seams are
   real in code, but the fourteen days of building go to the individual product.
   Rejected: building the first connector too (cost, two days from the command
   center and install experience, which is where the competitive gap is);
   leading with enterprise; keeping the freeze absolute so architecture gets
   retrofitted later.
   Flip condition: a named organisation asking for an export, in writing.

2. **The release gate holds; build to a ready branch.** Everything lands on main
   through pull requests, fully tested, and sits unreleased until the
   claude-md-diet-v2 verdict near 2026-09-13. Rejected: a pre-release for
   testers (still a publish, and a deliberate partial lift of the founder's own
   gate); lifting the gate now (shipping a release whose headline claim is that
   we prove things, while our first experiment is still open).
   Flip condition: the experiment closing early with a verdict of either kind.

3. **Always-on is a one-time consented setup.** Zero hooks by default stays. The
   install flow asks once, in plain words, showing exactly what gets written and
   how to undo it, then wires the observer bundle and prints the status line to
   paste. Rejected: silent-by-default with opt-out (reverses the founding
   promise, and a user reading the settings diff afterwards would feel it was
   done to them); staying fully passive (cannot deliver "always there").
   This decision governs section 4's consent design and founder decision 6.

4. **Path A now, Path B seams only.** Fourteen days on the native product. The
   companion machinery that exists (the registry, discovery, the tournament that
   already ranks native above companion) stays working and gets its data model
   finished, but nothing installs, activates or trials another plugin. Rejected:
   both with Path B narrow (three days, and it puts an install and rollback path
   for somebody else's software into a release we cannot yet ship); leading with
   Path B (the plan's own warning is that orchestration must never compensate
   for weak fundamentals, and ours have five unfinished front doors).
   Flip condition: Path A reaching its gate.

A second round of four followed the same evening, resolving founder decisions 1
to 4 of section 11. Section 11 keeps the full option text; the answers are here.

5. **The hard budget guard: build it, opt-in, fail open, and say so.**
   Resolves section 11 decision 1, against its stated default. Enforcement gets
   built behind its OWN consent, separate from the observer bundle consent of
   section 4, because agreeing to be measured is not agreeing to be stopped. It
   fails open exactly as CodeBurn's does, and that limitation is printed in the
   setup screen rather than left in a document. This is the first thing Token
   Shield ships that touches the per-call path, which section 4 had ruled out
   for OBSERVATION and which this decision opens only for ENFORCEMENT: the
   distinction is load bearing and must survive into the code, so a guard hook
   never becomes an observation hook by accretion. Rejected: staying report only
   (concedes the one capability gap where a competitor genuinely beats us);
   fail closed (a broken guard blocks real sessions, an incident waiting on any
   machine pushed by a management tool).
   Flip condition on the fail-open half: a user reporting a guard that failed
   open on a run that then overspent, which would make the honest disclosure
   insufficient and force the fail-closed conversation with real evidence behind
   it.

6. **Fleet trust: unsigned and loud, plus a hash chain.**
   Resolves section 11 decision 2, taking option A over its stated default of
   no change. Section 6 option A is now the plan: keep the plain statement that
   any push holder can forge a record, add prev_record_sha256 so each machine's
   lane is a chain whose breaks are detectable, and document the branch
   protection requirement so the host's audit log names the writer. Rejected:
   ssh-keygen signing now (roughly doubles fleet complexity to defend against an
   insider the org already trusts with the repository, before any org has
   asked); leaving it as today (it stays the largest open hole in the enterprise
   story). The sentence that ships either way is unchanged: authenticity rests
   on your git host's access control and audit log; Token Shield adds tamper
   evidence, not tamper proof.
   Flip condition to option B is unchanged: the first enterprise security review
   that refuses unsigned records in writing.

7. **OpenTelemetry: no dependency, three formats.**
   Resolves section 11 decision 3, confirming its default. CSV, JSON lines for
   an existing collector to tail, and a Prometheus text file. Anthropic's own
   exporter is attributed for usage and cost; we add only the proof stream,
   which is the thing no first-party metric carries. Rejected: one isolated
   dependency (the zero dependency claim gains an asterisk, and an asterisk on
   an absolute claim is how trust erodes); no OpenTelemetry story at all
   (observability is the language a FinOps buyer speaks).
   Flip condition: a named organisation that cannot consume any of the three
   formats and can say why.

8. **Status line: phase one shows Claude's own numbers only.**
   Resolves section 11 decision 4, confirming its default. The line carries
   context fullness, five-hour and seven-day limit consumption, model and
   effort, all attributed as Claude Code's own, and no Token Shield metric. The
   reason is the defect family this whole architecture exists to make harder:
   the status line is the surface a user looks at most often, and a Token Shield
   number there would be a second door onto a figure the dashboard already owns.
   It cannot disagree with the dashboard because it shares no number with it.
   Rejected: adding one of our figures now (accepts the two-doors review burden
   on the most-looked-at surface); shipping no status line (declines the single
   best thing the platform hands us for free, and concedes the always-visible
   ground).
   Flip condition: phase one shipped and stable, at which point a Token Shield
   figure may be added THROUGH metrics (L1), decided then rather than smuggled.
