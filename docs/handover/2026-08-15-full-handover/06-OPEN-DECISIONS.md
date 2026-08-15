# Open decisions, which are Khalil's and not yours

Put each of these to him through the client's question UI, one window per
decision, recommended option first and labelled, highest stakes first. Not as a
wall of chat text.

---

## 1. How fleet records earn trust, given zero dependencies

**The situation.** Records are unsigned and forgeable by anyone with write
access to an organisation's store. He already chose a trust model: a
machine-local key generated at join, public half carried in the record,
detecting tampering after the fact. That choice was made before anyone checked
whether it could be built here.

**Why it needs revisiting.** No crypto library is available and this plugin
ships zero dependencies by design. Stdlib gives HMAC, which needs a shared
secret that everyone with store access would hold, defending against nothing in
the actual threat model. And a public key carried inside the record can be
rewritten by whoever rewrote the record, so it needs pinning at join.

**Options to put to him:**

- **Recommended: pin the public key at join, in the org profile.** The machine
  generates a keypair at join and the org profile records the public half, so a
  later rewrite of a record cannot rewrite the key it is checked against. Still
  needs a signing primitive, so it is gated on the dependency question below.
- Accept one dependency (`cryptography`) for the fleet path only, and state
  plainly in the README that the fleet feature has a dependency the rest of the
  plugin does not.
- Leave records unsigned and keep documenting it. Honest, and it stops the
  fleet layer being described as tamper-evident when it is not.

---

## 2. Whether the two-host law applies to this repository

**The situation.** A standing law says every development works on GitHub and
Bitbucket Cloud, applying backward to shipped code. This repository is GitHub
only.

**Why it needs a decision.** The law reads as aimed at a checks product with
host adapters. Token Shield's fleet layer is already host-neutral (it uses
plain `git`), so arguably it satisfies the spirit. What is GitHub-only is this
repository's **own CI**.

Separately, the Bitbucket half cannot be verified at all: that workspace is
read-only until a billing change only he can make.

**Options:** confirm the law covers this repository's own CI and accept it stays
BLOCKED; or scope the law to products with host adapters and mark this one out
of scope with a recorded reason.

---

## 3. Whether to register this project with the BrotherMode tooling

**The situation.** `/brothermode:next` and `/brothermode:status` cannot answer
for this project: the store holds **0 projects and 0 tasks**. It was never
registered. The same is true of `/brothersbe`: there is no dossier, and its
own design check returns NO-DATA rather than FAIL because it cannot tell
whether this repository is supposed to have one.

**Why it needs a decision rather than a default.** Registering buys mechanical
status answers. It also creates a second task graph that has to be kept true
alongside `STATE.md` and the progress page, which are already good.

**Recommendation: leave it unregistered**, and stop invoking those two commands
for this project, since they are currently dead weight here.

---

## 4. Nothing else is waiting on him

Four decisions were taken on 2026-08-15 and are recorded with their rejected
alternatives and flip conditions in `STATE.md`:

1. He merges pull requests by hand rather than granting a permission rule.
2. The proof ledger's defects came before the architecture debt.
3. `build/signals-s1-impl` was deleted.
4. The fleet trust model, which item 1 above now reopens.

**A correction he should have.** He was told `gh pr merge` was blocked on this
machine, on the strength of two refusals. It worked on the third attempt with
nothing changed. It is **intermittent**. That claim reached a decision window
before it was corrected, so do not plan around the block being absolute in
either direction.
