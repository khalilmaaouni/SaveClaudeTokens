# Token Shield integration contract, v1

Date: 2026-08-13. Written for a plugin author who has never seen this project.

## What this is

Token Shield is a Claude Code plugin that measures where tokens go and reports on other
plugins that also affect token usage ("companions"). Historically, a companion could only
appear in Token Shield's reports after a human on the Token Shield side opened the
companion's own source, hooks, and docs and confirmed the facts by hand (that process is
called CURATION; see "The load-bearing distinction" below). Curation does not scale past a
handful of companions, and it has already blocked two real, first-party-verified plugins
from appearing at all, for a reason that has nothing to do with whether they are good
plugins: neither one documents an uninstall or rollback path for Claude Code, which curation
treats as a required piece of evidence.

This contract gives any optimization plugin a way in without waiting on hand-curation: ship
a small JSON file describing yourself, and Token Shield's discovery will read it.

## The file

- Name: `token-shield.integration.json`, exactly.
- Location: the root of your plugin's installed directory, next to your `.claude-plugin/`
  folder. On this machine that root looks like
  `~/.claude/plugins/cache/<marketplace>/<your-plugin-name>/<version>/token-shield.integration.json`;
  the exact root is wherever the Claude Code plugin installer puts your plugin, one file per
  installed version.
- Format: a single JSON object (not an array, not a bare string or number), UTF-8, no
  duplicate top-level keys (see "What Token Shield refuses" below), and no larger than
  `MAX_DECLARATION_BYTES` (65536 bytes as of this writing; see the named constant in
  `discover_companions.py`). A legitimate declaration is a few hundred bytes.

## Fields

| Field | Required | Type | Meaning |
|---|---|---|---|
| `capabilities` | **yes** | non-empty array of strings | What your plugin does to token usage. Free text is fine; token-shield's own vocabulary (`minimal_code`, `output_compression`, `tool_output_isolation`, `deterministic_deduplication`) is recommended where it applies, but not enforced. |
| `name` | no | string | Your plugin's name. When present and it matches an entry Token Shield has separately curated, see the collision rule below. |
| `modes` | no | array of strings | The operating modes your plugin supports (for example `off`, `lite`, `full`). Mirrors the "modes" question the curated companion adapters already answer. |
| `status_command` | no | string | How a user or tool checks whether your plugin is currently active. |
| `version_command` | no | string | How a user or tool checks your plugin's installed version. |
| `activation_command` | no | string | How a user turns your plugin on (install or enable). |
| `rollback_command` | no | string | How a user turns your plugin off or removes it. This is the field whose absence has been blocking otherwise-qualified plugins from curation. Declaring it here does not grant curation; it lets discovery report a DECLARED value for it instead of nothing. |

Only `capabilities` is required. Every optional field, when present, must match the type in
the table above or the whole declaration is refused, naming the offending field (see "What
Token Shield refuses"). A file with `capabilities` alone is a valid declaration.

Any additional field beyond the table above is read and reported the same way as the fields
listed here (its type is not checked): nothing is silently dropped, and nothing beyond
`capabilities` is required.

## What is actually read today, and what is not yet consumed

Discovery (`discover_companions.py`) reads `token-shield.integration.json` from every
installed plugin root it can find, validates it against this contract, and prints the result
when you run `python3 scripts/discover_companions.py` directly. That is the whole surface
that exists today.

Nothing downstream consumes a declaration yet. A declaration is never written to
`~/.token-shield/companions_state.json`, never shown by `cli.py doctor`, `cli.py profile`, or
`cli.py advise`, and never appears in any dashboard or report. Filling in every field of your
declaration today changes nothing about what a Token Shield user sees; it only changes what
`discover_companions.py`'s own console output shows when run by hand. A consumer that reads
declarations into the state file and the reports a user actually sees is future work, tracked
separately; this contract is deliberately scoped to the file format and discovery alone.

## The load-bearing distinction: DECLARED versus CURATED

- **CURATED** means a human on the Token Shield side opened your plugin's own source, hooks,
  and documentation first-party and confirmed the facts by hand. That bar does not move, and
  nothing in this contract changes it.
- **DECLARED** means your plugin said so about itself, in `token-shield.integration.json`.
  It is useful, and Token Shield treats it as honest, but it is **not evidence**. A
  declaration is a claim, not a verification.

Every single field Token Shield reads out of your declaration file is labeled `DECLARED`
wherever it is shown. A declaration can never promote itself to `CURATED`; there is no field
you can add, no value you can set, that will cause Token Shield to treat your self-reported
data as first-party-verified. If you want curated status, that still requires a human at
Token Shield to independently verify your plugin, exactly as it always has.

This distinction is the entire point of this contract. Letting self-assertion quietly become
evidence would be the single worst outcome for a project whose reason to exist is measuring
and proving token savings honestly. So this rule is absolute: DECLARED data is reported as
DECLARED, forever, no matter how complete or how old the declaration is.

## The curated-plus-declaring case

A plugin can be both curated (it has a hand-verified entry in `data/companions.json`) and
also ship its own `token-shield.integration.json`. When Token Shield's discovery finds both
for the same plugin name:

- **The curated evidence wins.** Any field Token Shield already has from curation is what
  gets reported as the plugin's evidence. The declaration is never merged into the curated
  entry, and it never overwrites a curated field, even when the two disagree.
  For fields the curated entry doesn't happen to carry, the declared value stays exactly
  that: reported as DECLARED, never silently upgraded because a curated entry exists nearby.
- **The collision is reported, not resolved silently.** Discovery marks the plugin's
  declaration row with `"curated_conflict": true` and a plain-language note naming the rule
  above. A human reading the discovery output can see, explicitly, that this plugin has both
  a curated registry entry and a self-declaration, and that the curated one is the one in
  force. Nothing about this resolution happens invisibly.

## Which cached version a row reflects

Claude Code caches every version of a plugin it has ever installed under
`<marketplace>/<plugin>/<version>/`, and an old, no-longer-installed version's declaration is
still sitting on disk. Every row discovery reports carries its own `version` (the cache
directory name it was read from), and, when discovery is also given a live
`claude plugin list --json` result to compare against, an `installed` field: `true` when that
cached version is the one actually installed, `false` when it is not (or the plugin is not
currently installed at all), or `null` with an `installed_note` explaining why it could not be
determined (no live discovery was supplied, or the declaration has no `name` field to look
up). A row is never presented as current when discovery cannot back that claim.

## What Token Shield refuses

Discovery refuses (skips) a declaration file, and prints the exact reason naming what is
wrong, when:

- the file cannot be read (missing, a directory, a broken symlink, permission denied);
- it exceeds `MAX_DECLARATION_BYTES`;
- it is not valid JSON, including inputs so deeply nested that parsing them would exhaust the
  interpreter's recursion limit;
- it contains a duplicate top-level key (a second occurrence of the same key could otherwise
  silently overwrite an already-read value such as `rollback_command`, so this is refused
  outright rather than resolved last-value-wins);
- the parsed JSON is not an object;
- the required `capabilities` field is missing, or present but not a non-empty array of
  non-empty strings;
- any other field from the table above is present but does not match its declared type.

A refused declaration never partially loads: either the whole file is accepted as one
DECLARED record, or none of it is used. A malformed or hostile declaration from one plugin
never stops discovery of any other plugin's declaration; the rest of the walk always
continues, and discovery itself never raises because of anything a plugin's declaration file
contains.

## What Token Shield will never do

- Never writes to `data/companions.json` (the curated registry) because of a declaration.
  Nothing in this contract, ever, under any condition, promotes a DECLARED field to CURATED
  or adds a plugin to the curated list.
- Never sums, blends, or averages a DECLARED value into a MEASURED, VERIFIED, ESTIMATED, or
  NATIVE figure. Confidence labels never blend in this project, and DECLARED is no
  exception.
- Never treats the presence of a declaration file as proof the plugin works as described.
- Never executes anything from your declaration file. `status_command`,
  `version_command`, `activation_command`, and `rollback_command` are reported as strings
  for a human to read, not run automatically by Token Shield.
