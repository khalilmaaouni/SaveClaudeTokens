# Attribution: the honesty model

The point of this tool is to tell you what actually saved tokens, and
to say plainly when it does not know. That runs on four labels and one
split.

## The four confidence labels

- **VERIFIED.** A real before/after measurement over the same window,
  produced only by Experiment Mode. The strongest label, and the
  hardest to earn.
- **MEASURED.** Read straight from the API usage counters. The number
  is real, but what caused it is not proven the way an experiment
  proves it.
- **ESTIMATED.** A transparent projection, labeled as a projection,
  never presented as a fact you can bank on.
- **NATIVE.** Claude Code's own automatic saving, mainly prompt
  caching. This tool did nothing to earn it and never claims it did.

These never merge into one number. A dashboard, a summary, a report:
wherever they show up, they stay in their own column and their own
sentence.

## Native versus tool: who actually saved what

Prompt caching is automatic. Claude Code does it on its own, it is
usually the largest saving in your session, and it happens whether or
not you ever install this tool. That saving is labeled NATIVE and this
tool does not take credit for it.

What this tool actually contributes is smaller and it is two things:
the OPPORTUNITY it helps you see and cut (context you did not need to
carry), and the VERIFIED before/after saving from an experiment you
actually ran. Both are honest because both are smaller than the native
number, and neither pretends to be it.

## What Anthropic already ships, and why we point at it

The same honesty that keeps NATIVE out of our column applies to
tooling. Anthropic already ships org-wide reporting for Claude Code,
and an organisation evaluating this tool deserves to be told that
before they adopt it, not after. Where the two overlap, theirs is the
source of truth for spend, and this tool is for finding and proving
what to change.

What is theirs, verified against their own documentation:

- An organisation-wide analytics dashboard for Teams and Enterprise
  plans, at `claude.ai/analytics/claude-code`, covering usage and
  acceptance metrics. Documented at
  https://code.claude.com/docs/en/analytics
- Real-time OpenTelemetry export of token and cost data, enabled with
  `CLAUDE_CODE_ENABLE_TELEMETRY=1`, publishing named metrics including
  `claude_code.token.usage` and `claude_code.cost.usd`. Documented at
  https://code.claude.com/docs/en/monitoring-usage
- Enterprise policy through managed settings, which outrank user and
  project settings, including allowlists governing which plugin
  marketplaces may be used at all. Documented at
  https://code.claude.com/docs/en/admin-setup

If your only question is "what are we spending", use theirs: it is
first party, it is real time, and it needs no plugin. Anthropic also
states plainly that its own contribution metrics are deliberately
conservative, which is the same posture this tool takes, and it is
worth reading their note rather than ours on that point.

What this tool adds on top, and would not exist otherwise:

- It attributes waste to a CAUSE rather than a total: which of your
  habits, files and installed plugins the tokens actually went to.
- It proves a change worked, with a before and after cohort and a
  verdict that can come back NOT_PROVEN. A spend chart can show you a
  number moved; it cannot tell you your change is what moved it.
- It runs with no account, no telemetry export and no network call in
  its single machine core, which matters where the org has not enabled
  telemetry, or cannot.

Flip condition, recorded so this section is not left to rot: if
Anthropic ships per-cause attribution or a before and after proof
mechanism, the overlapping part of this tool stops being worth
maintaining and this document says so at that point.

## How USD is priced

- Pricing comes from a dated snapshot in `data/pricing.json`, per
  model.
- A model that is not in the snapshot goes into an explicit unpriced
  bucket. It is never priced at another model's rate as a stand-in.
- If the snapshot itself is stale, pricing degrades to a NO PRICE DATA
  state rather than quoting an old number as current.
- For subscription usage, the dollar figure is phrased as API
  equivalent value, what the same usage would cost on the API. It is
  never phrased as "you saved $X", because a subscription does not
  bill per token the way the API does.

## Companion Fabric credits (unit CF1)

The following projects were reviewed against their own first-party
sources (repository, manifest, README, or release notes) on
2026-08-15, per `docs/research/2026-08-15-companion-fabric-facts.md`.
Every one is someone else's project; this section credits each by
name, owner and license. A published percentage attributed to a
project below is that project's own claim, in its own words, never a
Token Shield measurement.

Curated (prescribable treatments):

- **token-saver**, ppgranger (github.com/ppgranger/token-saver),
  Apache 2.0. Promoted from detect-and-measure only to a prescribable
  treatment this review, its identity having already been settled
  first party.
- **rtk**, rtk-ai (github.com/rtk-ai/rtk), Apache 2.0.
- **token-optimizer** (Token Optimizer MCP), ooples
  (github.com/ooples/token-optimizer-mcp), MIT.

Mentions (named honestly, never prescribed, with the reason on file in
`data/companions.json`):

- **context-mode**, Mert Koseoglu (github.com/mksglu/context-mode),
  Elastic License 2.0. Confirmed first-party; not prescribable because
  no uninstall command is documented for the Claude Code path.
- **ccusage**, ryoppippi (github.com/ryoppippi/ccusage), MIT. A meter,
  never a treatment.
- **claude-code-token-saver**, ww-w-ai
  (github.com/ww-w-ai/claude-code-token-saver), Apache 2.0. A
  different project from the token-saver companion above; named here
  to prevent that exact confusion.
- **codeburn**, getagentseal (github.com/getagentseal/codeburn), MIT.
  A meter primarily. Name caveat: no first-party source for a project
  literally spelled "CodeBurn" was found; getagentseal/codeburn,
  lowercase, is the closest match and is credited as such, not as a
  confirmed identity.
