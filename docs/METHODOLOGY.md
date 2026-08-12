# Methodology: how this project stays honest

This is a token-economy tool, and the fastest way for one to become a gimmick
is to report savings it cannot prove. So the method comes first, and the method
is one sentence: **measure with the counters that bill, never estimate, and say
NO DATA rather than invent a number.** Everything below is that sentence made
mechanical.

## 1. Measurement, not estimation

Claude Code writes one JSONL transcript per session under
`~/.claude/projects/`. Every assistant message carries the `usage` object the
API returned: `input_tokens`, `cache_creation` (split into
`ephemeral_5m_input_tokens` and `ephemeral_1h_input_tokens`),
`cache_read_input_tokens`, and `output_tokens`. Those are the counters your bill
is computed from. `scripts/measure_tokens.py` reads them and does arithmetic. It
does not model, sample, or extrapolate.

This matters because the alternative, guessing context cost from file sizes or
from the plugin manager's own projections, is systematically wrong on a harness
that defers MCP tool schemas and caches aggressively. The counters are the
ground truth; the projections are not. When the two disagree, the counters win.

## 2. The cost model the numbers rest on

Verified against first-party documentation on 2026-08-12, every claim recorded
in `docs/CLAIMS.md` with its quote and URL:

- Caching is an exact prefix match. A byte change anywhere in the prefix
  recomputes everything after it.
- Cache writes bill at 1.25x base input for the 5 minute TTL and 2x for the
  1 hour TTL. Cache reads bill at 0.1x.
- Which TTL you get is set by how you authenticate: a Claude subscription
  requests 1 hour automatically, an API key stays at 5 minutes, subagents use
  5 minutes either way.
- Two things outside the prompt text are still part of the cache key: the model
  and the effort level. Either switch rebuilds the whole prefix.

`measure_tokens.py` weights the raw counters by these exact multipliers to get a
single comparable "normalized input" number in base-input units. It carries no
dollar price table on purpose: a hardcoded model price goes stale and a stale
price silently corrupts every later comparison. Relative cost in base-input
units is honest and durable; a dollar figure is neither.

## 3. What "savings" means here, and how it is checked for real

Savings are not "the context got smaller." Savings are a measured drop in what a
session pays, verified against a baseline, with quality held constant. The
procedure:

1. **Baseline.** `measure_tokens.py --days N --baseline before.json`. This pins
   a snapshot with a timestamp.
2. **Change one variable.** Prune one plugin, diet CLAUDE.md, quiet one hook.
   One thing, or the result attributes to nothing.
3. **Compare like for like.** `measure_tokens.py --days N --compare before.json`,
   with the SAME window. The script refuses to compare across a schema change
   and warns on a window mismatch, because both produce a confident number that
   means nothing.
4. **Hold quality.** A token drop that doubles rework is not a saving. The
   denominator that matters is tokens per accepted result, not tokens per
   response. Where the harness exposes it, track whether the work landed first
   time; where it does not, say so rather than pretend.

The headline number is the **first request**: what a session pays before any
work happens, plus the opening message. On one machine over 90 days its median
was 85,021 tokens and its share of everything read was 36 percent (snapshot in
`docs/CLAIMS.md`). That share is the single largest lever, because it is paid
again on every call of every session. Cutting it is where real savings live.

## 3b. Native caching versus what this tool adds (the load-bearing distinction)

The Token Shield's headline is the saving from prompt caching. That saving is
Claude Code's, not this tool's. Claude Code manages prompt caching
automatically, by default, so the cache reads that produce the headline happen
whether or not Token Shield is installed. The dashboard attributes the
number to Anthropic's caching in the hero itself, in bold, and does not claim
it. Presenting a native benefit as the plugin's own achievement is the exact
dishonesty this whole project exists to avoid, so it is called out rather than
quietly enjoyed.

What this tool actually contributes, and what it is honest to credit it with:

1. **Visibility.** The native saving was invisible before; the meter makes it a
   measured number you can watch.
2. **Protection.** Native caching collapses the moment a session turns
   cache-hostile. On one machine, 28 percent of sessions switched model
   mid-flight, and each one threw the native saving away for the rest of the
   session. The tool's rules are how you stop leaking a benefit you already
   have.
3. **Cuts caching cannot make.** The always-loaded startup floor is paid on
   every call and caching cannot shrink it. The pain-point prescriptions can,
   and their projected savings are computed from your own sessions. That figure,
   not the native one, is the tool's own contribution.

So the dashboard reports two different quantities and never merges them: the
native saving (large, not ours) and the tool-attributable saving (smaller,
ours, and the actual reason to keep the tool).

## 4. How it stays honest over time

A meter drifts into dishonesty in predictable ways. Each is closed by a
mechanism, not a promise:

- **A metric silently changes what it counts.** The transcript-versus-session
  fix is the worked example: an early figure of 41,890 averaged 6,020 subagent
  transcripts against 229 real sessions and read low. When the metric's
  population changed, comparing the new number to the old would have measured
  the edit to the meter, not the spend. Guard: baselines carry a `schema`
  version, and the compare path REFUSES to diff a metric across a schema
  change. See `docs/CLAIMS.md` B7 and test `test_legacy_baseline_keys...`.
- **Two windows of different length get compared.** A 1 day window against a
  90 day baseline measures which sessions fell in each window, not any change.
  Guard: the compare path warns loudly on a window mismatch.
- **An unmeasurable value gets a plausible fill.** Guard: every path that
  cannot measure prints NO DATA. Normalized cost is NO DATA when the TTL split
  is absent, rather than an assumed 5 minute price.
- **A number is reported without saying which statistic it is.** The hit ratio
  has a per-session median (0.865) and a pooled form (0.966); reporting one as
  the other is a quiet lie. Guard: the register states which, and the code
  labels the median as a median.
- **A single pass is trusted.** Guard: the headline numbers are re-derived by a
  second, independent code path and checked for zero drift before they are
  published (recorded in `docs/CLAIMS.md`).

## 5. The standing honesty caveat

Every measured number in this repo was taken on one machine. They are defaults
for illustration, not universal constants. The portable thing is the method:
run the tools on your own machine and read your own numbers. This is stated at
every point a number appears, not buried once here.

## 6. Why the tool is trustworthy to install

The optimizer must not become the thing it optimizes against. So the plugin
registers no hooks and runs nothing on its own: installing it costs one skill
listing line and one command listing line, and no code executes until you run
it or wire it in yourself. The three helper scripts
(`context_lint.py`, `session_end_telemetry.py`, `obsidian_export.py`,
`token_shield.py`) are opt in, documented in the README, and each does nothing
until invoked. A token-saving tool that quietly ran code on every session of
every machine that installed it would be spending exactly what it claims to
save.
