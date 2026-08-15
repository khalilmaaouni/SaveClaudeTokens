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
