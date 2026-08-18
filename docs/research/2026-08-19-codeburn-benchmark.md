# CodeBurn benchmark, 2026-08-19

One read-only research pass against the primary source, run overnight at the
founder's instruction: "I want us ahead on benchmark against all competition
especially in Enterprise mode... and beat codeburn on every aspect on Claude
Code."

This document answers that instruction honestly, which means most of it is bad
news. Nothing here is a Token Shield measurement. Every claim names the line of
the page a researcher actually opened.

**Source of record.** `https://raw.githubusercontent.com/getagentseal/codeburn/main/README.md`,
fetched 2026-08-19 00:47 JST, 785 lines, saved to the session scratchpad and
read line by line. Cross-checked against
`https://github.com/getagentseal/codeburn` the same night. `https://codeburn.app/`
returned HTTP 403 to an automated fetch and was NOT read, so no claim below
rests on it.

## The headline, first, because it is the part that changes plans

Token Shield is behind CodeBurn on most axes the founder named, and two of the
differentiators this repository has been claiming are STALE. "Beat CodeBurn on
every aspect" is not reachable in one night, and pretending otherwise would put
a false benchmark in front of him. What IS reachable, and what the 14 day WBS
already targets, is a narrower and defensible lead on three things: refusal,
attribution, and the privacy architecture of the org rollup.

## Correction 1: "nothing re-measures whether the fix helped" is now WRONG

**What we said.** The 2026-08-15 field map, CodeBurn row: "No experiment behind
any number and no confidence labelling. `codeburn optimize` estimates a saving;
nothing re-measures whether the fix helped."

**What is actually true.** CodeBurn README line 195, verbatim: "The loop closes
on honesty: once an applied fix is at least 3 days old, `codeburn act report`
compares its estimated savings against what your sessions actually did, and
every later `codeburn optimize` run lists it under `Applied fixes` with a plain
verdict, worked, under its estimate, or did not help, with the undo command for
that last case. `--auto-revert` undoes the ones that did nothing (never
`CLAUDE.md` rules). Estimates get checked against reality, not just claimed."

They re-measure. They have re-measured for some time.

## Correction 2: "no confidence labelling" is also WRONG

**What we said.** Same row, same sentence.

**What is actually true.** CodeBurn README line 173, verbatim: "Each one says
whether its savings number is `measured` from provider-counted usage or
`estimated`."

That is a two label confidence system. Token Shield runs five (VERIFIED,
MEASURED, ESTIMATED, NATIVE, RECOMMENDED). Five is more granular than two, and
the NATIVE label in particular has no CodeBurn equivalent that this pass found.
But "no confidence labelling" was false, and the honest comparison is five
labels against two, not five against zero.

**How both errors happened, which is the part worth keeping.** The same way
threat 4 went wrong in the 2026-08-15 map, and the map's own correction note
predicted this: the sweep read CodeBurn as a METER, filed it under "reports and
displays", and then reasoned about the category instead of re-reading the page.
The row was written from a category, not from a source. A tool that is
genuinely a meter can still ship a proof loop, and this one does.

## Where CodeBurn is ahead, stated plainly

| Axis | CodeBurn | Token Shield |
|---|---|---|
| Tools covered | 41, including Claude Code, Cursor, Codex, Gemini, Copilot, Zed, Warp | 1 (Claude Code) |
| Reach | 9,500+ stars, 1,404 commits, MIT, created 2026-04-13 | one machine, one founder |
| Surfaces | TUI, localhost web dashboard (`codeburn web`), macOS menubar app, Windows tray, GNOME extension, MCP server, status line | one HTML file the user opens by hand, plus an MCP server |
| First run | `npx codeburn`, installs nothing | marketplace add, then plugin install |
| Budget enforcement | `codeburn guard`, soft cap, hard cap that stops the session, checkpoint nudge | none by design (zero hooks by default) |
| Git yield correlation | `codeburn yield` splits spend into productive, reverted, abandoned, ambiguous | nothing equivalent |
| Currency | 162 currencies, ECB rates | USD only, dated snapshot |
| Model comparison | `codeburn compare`, interactive side by side | none |
| Context inspection | `codeburn context <id>` browses context window composition | none |

`codeburn yield` deserves its own line. Correlating spend against whether the
commits actually landed in main is the single most interesting thing either
product does, and Token Shield does not do it at all.

## Where Token Shield genuinely leads, narrowed to what survives scrutiny

1. **Refusal, not just re-measurement.** CodeBurn compares estimate against
   reality at three days. Nothing in its README declines that comparison when
   the comparison is invalid. Token Shield's Experiment Mode v2 refuses across
   a schema change, a window mismatch, a model mix change, and thin data, and
   downgrades to NOT_PROVEN rather than reporting a number it cannot stand
   behind. The defensible claim is not "they do not check", it is "they do not
   refuse". That is narrower than what we have been saying and it is true.

2. **NATIVE attribution.** Token Shield never counts Anthropic's own prompt
   caching as a Token Shield saving. This pass found no CodeBurn equivalent,
   but absence in a README is not proof of absence in the product, so this is
   labelled UNVERIFIED rather than claimed.

3. **The org rollup's privacy architecture.** This is the Enterprise answer, and
   it is a real architectural difference rather than a feature gap. CodeBurn's
   `codeburn sync setup <url>` (README line 458, marked _preview_, "the protocol
   may change between releases") authenticates by OIDC in a browser and pushes
   usage to a REMOTE ENDPOINT. Token Shield's fleet has no server at all: the
   org designates a private git repository IT ALREADY OWNS as the store, machine
   ids are a one way hash of hostname plus an org-only salt, `fleet init` prints
   the exact disclosure list in plain words before anything is created, and the
   dashboard clamps to a MIN_GROUP_MACHINES floor so a small group cannot be
   de-anonymised. For an enterprise that cannot ship telemetry to a third party
   endpoint, those are not competing features, they are competing architectures,
   and ours is the one that survives a procurement review.

4. **No cross label totals.** A five label system with an enforced ban on
   summing across labels cannot produce the flattering aggregate a two label
   system can. This is a discipline, not a feature, and it is invisible until
   someone tries to quote a single number.

## What this means for tonight, and what it does not

The WBS already points at the right work. E1 (one front door), E2 (the four
state command center), E4 (the first sixty seconds) and the fleet tasks T1.1
and T1.3 are the items that move the founder's three stated wants. Nothing in
this benchmark asks for a new epic.

What this benchmark DOES ask for is that the marketing sentence change. "Nobody
else closes the loop" is no longer true and must not be shipped. The sentence
that survives tonight's evidence is about refusing an invalid comparison and
about an org rollup with no server in it.

## Unverified, and why

- Whether CodeBurn separates Anthropic's native caching from its own attributed
  savings. Not found in the README either way; not asserted in either direction.
- Everything on `https://codeburn.app/`. The host returned 403 to an automated
  fetch and was not read.
- CodeBurn's actual behaviour. This is a documentation pass, not an install. No
  claim here rests on running the tool, and the numbers in the table above are
  CodeBurn's own claims about CodeBurn, recorded as claims.
