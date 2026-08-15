# Security

## The trust model

There are two layers, and they have different answers. Read both
before you decide anything, because the honest answer to "does this
talk to the network" is "the part you install does not, and the part
you have to opt into does, to one place you own".

### The single machine core: no account, no service, no network

Everything you get by installing the plugin runs entirely on your
machine. There is no account and no cloud service. It never uploads a
prompt, a file, or a conversation, and it never makes a background call
to a model. The only thing it does is read the API usage counters that
Claude Code already wrote to your own disk, and do arithmetic on them.

### The fleet layer: opt in, and it does make network calls

If an administrator turns on the optional fleet layer (`scripts/fleet.py`,
documented in `docs/FLEET.md`), that layer makes exactly two kinds of
outbound call, both to a git remote your own organisation controls:
`git clone` to read the org store, and `git push` to add this machine's
record to it. Nothing is sent to us, and there is no third party in the
path. No machine joins a fleet without an administrator running
`fleet init` and the machine running `fleet join`.

### Confirming this yourself, with a check that actually works

An earlier version of this page told you to grep `scripts/` for a socket
or an HTTP connection and said there was nothing to find. That grep still
returns nothing, and on its own it would have misled you: the fleet layer
reaches the network by handing a URL to `git` as a subprocess, which no
socket grep can see. The check is corrected here rather than left
standing, because a check that passes by failing is worse than no check.

Two greps, and between them they cover both routes out. The exact
output each one produces is written below, so you can tell a real
finding from an expected line rather than having to judge for yourself:

```bash
grep -rnE 'socket|urllib|http\.client|requests|smtplib' scripts/
grep -rn 'subprocess' scripts/ | grep -v test_
```

The first finds no network code. It does print two lines, both comments
in `scripts/signals.py` stating that the file contains none. Anything
else the first grep prints is a real finding, so tell us.

The second prints every place this tool starts another program, and
there are exactly two kinds:

- `scripts/fleet.py`, the opt in fleet layer, which runs `git` and is
  the only thing here that reaches a remote. Every one of its calls goes
  through a single helper, `_run_git`, so that is the one function to
  read.
- `scripts/plugin_prune.py`, which runs `claude plugin list --json` to
  see which plugins you have installed. That is the Claude Code command
  line tool on your own machine, invoked to read local state. What that
  program does internally is Anthropic's to document, not ours to claim,
  so we describe only what we call and why.

## What the tool reads

- The `usage` object in each session transcript under
  `~/.claude/projects/`: input tokens, cache creation and cache read
  tokens, output tokens.
- The transcript file's own basename, used only to tell sessions apart
  while counting, never stored or sent anywhere.

## What the tool never reads

- Conversation text, message content, or tool output.
- File contents from your project.
- Prompts, or anything you typed.

The counters are aggregates. The content that produced them is never
opened.

## Reporting a security concern

Open a GitHub issue on this repository. If the concern is sensitive and
you would rather not describe it in a public issue, say so in the issue
and ask a maintainer to move the discussion private before you share
details.
