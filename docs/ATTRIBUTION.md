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
