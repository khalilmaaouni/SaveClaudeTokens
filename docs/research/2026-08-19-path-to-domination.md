# The path to domination: enterprise, Claude Code only, three products

Written 2026-08-19 01:20 JST, at the founder's direction given mid-run: "Our
angle is the focus on enterprise and on claude code only to differentiate
/brothersbe /brothermode find the path to domination."

This document is strategy, not measurement. Its factual base is the CodeBurn
benchmark of the same night ([2026-08-19-codeburn-benchmark.md](2026-08-19-codeburn-benchmark.md)),
which is sourced line by line to the primary README. Where a claim here is a
judgement rather than an observation, it says so.

## The reframe: breadth is CodeBurn's enterprise weakness, not its strength

The benchmark reads as bad news while the buyer is an individual developer.
Change the buyer to an enterprise and the same facts invert.

CodeBurn covers 41 tools. Its own README describes how it gets numbers out of
several of them:

- Cursor: "Output is a reply-text estimate and cache tokens are server-side
  only, so figures are marked estimated and undercount the Cursor admin console
  for long conversations."
- GitHub Copilot: "Other sources carry no explicit counts, so tokens are
  estimated from content length and the model is inferred from tool call ID
  prefixes."
- Kiro: "Token counts are estimated from content length. The model is not
  exposed, so sessions are labeled `kiro-auto` and costed at Sonnet rates."

That is honest engineering and it is fine for a developer curious about their
own spend. It is unusable for a chargeback, a cost allocation, or an audit.
Nobody signs a departmental recharge built on a reply-text estimate priced at
another model's rate.

Claude Code only, by contrast, means every token figure comes from Anthropic's
own provider-counted usage fields in the session transcript. Input, output,
cache read, cache write, per model, per session, counted by the vendor that
billed them. There is nothing to estimate. When the data is absent, the product
already says NO DATA rather than guessing, which is a law in this repository
rather than a preference.

**The claim that follows, and it is defensible:** we are the only tool in this
field whose every number is provider-counted. Breadth cannot make that claim,
because breadth requires estimating the tools that do not report.

## What CodeBurn structurally cannot do, and why

CodeBurn reads logs after the fact. That is its architecture and its virtue: no
wrapper, no proxy, no API keys, nothing to install into the runtime. It is a
READER.

Provenance cannot be read after the fact. Who decided this change, under which
constraint, with which files fenced, verified by which command, accepted by
which person: none of that is in a token log, and no amount of parsing recovers
it. It has to be CAPTURED AT EXECUTION TIME, by something present in the loop.

BrotherMode is present in the loop. BrotherSBE is present at the review. That is
not a feature CodeBurn lacks; it is a position CodeBurn cannot take without
becoming a different product.

**This is the moat.** Any competitor can add a cost chart in a weekend. Nobody
can retroactively add provenance to work they were not present for.

## The category, named

CodeBurn's category is AI coding cost observability. It is good at it and it is
winning it.

Ours is a different one: **AI coding assurance**. Cost, evidence, and
accountability, for one runtime, held to audit standard.

The question each answers:

- CodeBurn answers: what did I spend?
- We answer: what did we spend, was it worth it, what proves it, and who
  accepted it?

An individual developer only asks the first. An enterprise cannot stop at it.

## The three products, and why they are one product

Today these read as three repositories with three names. To an enterprise buyer
they are one system with three organs, and the seam already exists in
BrotherMode's own north star chain: human intent, then the team's own method,
then BrotherMode for execution provenance, then the CHANGE PASSPORT as the only
seam, then BrotherSBE's eight concerns, then human decision, release, and
verified reality.

| Organ | Question it owns | What it contributes to the passport |
|---|---|---|
| **Token Shield** | What did this cost, and is the optimization worth it? | The cost column, provider-counted, with a confidence label and a refusal when the comparison is invalid |
| **BrotherMode** | Who did this work, under what constraints, and can we prove the process held? | Execution provenance: fences, writers, done-checks run after the last edit, evidence filed |
| **BrotherSBE** | Is this change safe to release, and what proves it? | The eight concerns: behaviour, business impact, risk, required proof, evidence integrity, accountability, release readiness, production observation |

The CHANGE PASSPORT is the artifact that sells all three. One record per unit of
AI-produced work carrying: what it cost, what it changed, what proved it, who
accepted it. That single object is the answer to the question every enterprise
eventually asks about AI-written code, and no cost tracker can produce it.

## Why "Claude Code only" is a strategy rather than a limitation

Four reasons, in order of how much they matter to a buyer:

1. **Every number is provider-counted.** Argued above. This is the one claim
   that breadth forecloses.
2. **Provenance needs runtime knowledge.** Hooks, session lifecycle, subagent
   accounting, fences and compaction boundaries are all Claude Code specifics.
   A tool that must work across 41 runtimes cannot depend on any of them.
3. **Anthropic sells the seats; we sell the governance on top.** Enterprise
   Claude Code adoption is the growth curve we ride rather than compete with.
   Being the assurance layer for one fast-growing runtime beats being the
   twelfth cost chart for all of them.
4. **Procurement buys categories, not features.** "The Claude Code governance
   layer" is a category one product can own. "Another AI cost tracker" is a
   comparison you lose to the tool with 9,500 stars.

The honest cost of this choice, stated: we permanently forfeit the developer who
uses four coding tools and wants one dashboard. That developer is CodeBurn's and
should be conceded rather than fought for.

## The enterprise wedge that already exists and is not yet reachable

The fleet layer is the strongest enterprise asset in these repositories and it
is currently unreachable from the front door. Its architecture beats CodeBurn's
on exactly the axis procurement cares about:

| | CodeBurn sync (README line 458, marked preview) | Token Shield fleet |
|---|---|---|
| Where data goes | a remote endpoint, OIDC browser login | a private git repository the org already owns |
| Server to run | theirs | none |
| Machine identity | not stated | one way hash of hostname plus an org-only salt |
| Disclosure | "sends token counts, costs, models, and projects" | `fleet init` prints the exact list in plain words before anything is created |
| Small group protection | not stated | dashboard clamps to a minimum group size floor |
| Protocol stability | "may change between releases" | versioned records in a repo the org controls |

An enterprise that cannot ship telemetry to a third party endpoint has exactly
one option in this field, and it is ours. That is not a feature comparison, it
is a procurement outcome.

**The gap:** none of it is reachable from `cli.py`, and the org page is not
linked from the dashboard. T1.1 and T1.3 close that, and they are the highest
value tasks in the current plan for this reason.

## The sequence

**Phase 1, now, inside the current 14 day plan.** Make the enterprise door
real and visible. T1.1 (fleet routing through the one CLI), T1.3 (the MCP org
rollup with the minimum group floor intact), T1.2 (the dashboard links the org
page or says NO DATA naming the command), T7.1 (CSV export where every row
carries its confidence label and no total may cross labels). At the end of this
phase an admin can reach the org view in one command and hand finance a file
whose every row is provider-counted and labelled.

**Phase 2, the passport becomes the seam.** BrotherMode already names the change
passport as the only seam between itself and BrotherSBE. Token Shield adds the
cost column to that record. One JSON artifact per change: cost, provenance,
proof, acceptance. This is the integration work, and it is the hard part,
because it is the only part that requires all three products to agree on a
schema at once.

**Phase 3, the audit answer.** One command that returns every AI-produced change
in a period with its cost, its proof, and the person who accepted it. This is
what closes an enterprise deal, and nothing in the field is positioned to answer
it.

## What is hard about this, stated plainly

- Three repositories, one founder, and the integration in phase 2 is the part
  that cannot be parallelized away. It needs one schema decision made once and
  held.
- Enterprise selling needs a support story that a solo open source project does
  not have. This plan does not solve that and should not pretend to.
- The free core promise and an enterprise motion have to be reconciled
  deliberately. The roadmap's existing line (anything paid never paywalls
  personal token efficiency) is the right starting constraint, and the org
  layer is the natural paid boundary.
- CodeBurn could add provenance. It would mean entering the runtime and giving
  up the "no wrapper, nothing installed" position that is currently its best
  marketing line. Judgement, not observation: that trade is expensive enough
  that it is unlikely to be made quickly, which is the window.

## The one sentence

CodeBurn tells a developer what they spent across every tool. We tell an
enterprise what its Claude Code work cost, what it changed, what proved it, and
who signed for it, with every number counted by the vendor that billed it.
