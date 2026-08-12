# Security

## The trust model

Token Shield runs entirely on your machine. There is no account, no
cloud service, and no network call anywhere in the code. It never
uploads a prompt, a file, or a conversation. It never makes a
background call to a model. The only thing it does is read the API
usage counters that Claude Code already wrote to your own disk, and do
arithmetic on them.

If you want to confirm this yourself, the tool is small enough to read:
grep the `scripts` directory for anything that opens a socket or an
HTTP connection. There is nothing to find.

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
