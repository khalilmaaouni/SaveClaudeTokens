# Failure modes, all observed here, all transferable

These are not hypotheticals. Each one happened in this repository, most of them
in the single session that wrote this file. They are ordered by how expensive
they are when they recur.

---

## 1. The interpreter kept the code you deleted

**What happened.** A defect was reinjected to prove a test real, the test went
red with the defect verbatim, the file was restored, and the restore was proven
by digest. Every step correct. The next full run then failed on that same test
against source that was demonstrably right on disk.

CPython validates a cached `.pyc` on the source's **modification time and size
only**. The mutation and its revert were the same string length and happened
inside the same second, so the cache stayed "valid" and the interpreter kept
serving the reinjected code.

```
grep .hero .big.w token_shield.py   ->  color:var(--warn);
python3 -c "import token_shield"    ->  color:var(--good);
```

**Why it is worse than it looks.** This produced a false *failure*, which is the
harmless direction. The same mechanism produces a false *pass* when the timing
runs the other way. A green suite proving nothing is the worst outcome this
project has.

**The rule.** `rm -rf __pycache__` is the last step of every reinjection and the
first line of every verifying run. The digest proof does not protect you: it
proves the file, not what Python loaded.

---

## 2. A pattern reported to the founder from a sample of two

**What happened.** `gh pr merge` was refused by a permission classifier, twice,
including once as a bare single command. Both observations were real and were
reported accurately. What was reported on top of them was not an observation:
that merging was **blocked on this machine**. That framing reached a chat
summary, `STATE.md`, the progress page, and a decision window where Khalil
chose to keep the block as a safety rail.

An hour later the same command succeeded, with nothing changed.

**The rule.** Report the observation, not the generalisation, until the sample
can carry one. "Refused twice, including as a bare command" is honest and loses
nothing. "Blocked on this machine" is a claim about every future attempt, made
from two data points. When a category claim will reach a decision, it carries
its sample: how many attempts, how many failed, whether a success was ever seen.

---

## 3. A test that asserts the defect

**What happened.** The organisation dashboard suppressed any figure standing on
fewer than five machines. An existing test required a **six**-machine team to
publish beside a suppressed three-machine one, and had been green for a long
time. That is the same leak one group larger: publishing the six-machine figure
next to an org total of nine hands a reader the three-machine residual by
subtraction.

**The rule.** When a test fails after a correct fix, read what it is asserting
before you "fix" the test. If it encodes the defect, correct it **in place with
the reasoning written into the file**. Never delete it, never loosen it until
green. Two other tests were *sharpened* rather than loosened the same day: what
they were really for was that a label marks exactly one figure, so they now
count label positions instead of occurrences of a word.

---

## 4. Coverage that counts and does not cover

**What happened, three times.**

- A unit had 23 passing tests, every one asserting about a **single table**. The
  privacy leak lived *between* two tables that each passed alone.
- A no-data test's fixture never reached the parser: the line gate requires the
  exact substring `"usage"` including the closing quote, and the fixture
  `{"no": "usage here"}` puts the quote after the space. It was proven inert by
  showing its output byte identical to running against an empty directory.
- A "never writes to disk" test compared a before and after snapshot **of the
  sandbox root only**, so a write to the home directory or the repository
  itself was invisible, which is exactly where an accidental write would go.

**The rule.** Ask what the test would fail on, not what it covers. If you cannot
name a defect it catches, it catches none. Assert that a fixture reaches the
code path it names.

---

## 5. A guard undone by the next statement

**What happened.** A non-numeric metric value was named as "not comparable" and
downgraded, and then the very next block subtracted the same unvalidated values
gated only on `is not None`. For the default metric those are literally the same
two values, so it raised `TypeError` out of the function it was guarding.

**The rule.** A guard undone by a later statement is not a guard. When you add
one, grep the same function for every other use of the value you just refused.

---

## 6. Advice that makes things permanently worse

**What happened.** A refusal message offered two ways out: wait longer, **or**
shorten the measurement window. Taking the second trips an unconditional
downgrade and writes a permanent NOT_PROVEN into an append-only ledger. The
reader follows our own instruction and buys a permanent unproven verdict for an
experiment that had nothing wrong with it.

**The rule.** Every branch of advice in an error message gets followed once
before it ships. If a suggested action makes the state worse, it is not an
alternative, and offering it is worse than offering nothing.

---

## 7. A conclusion printed beside its own contradicting evidence

**What happened.** A calibration script compared two outputs raw, including a
temporary directory path that differs on every run, and printed
`identical: False` on the line directly above a conclusion asserting they were
identical. Normalised, they were identical.

A related one the same day: a new check crashed inside its own message-parsing
(it split its message on `":"`, which also split the message text) and went
"red" for a reason unrelated to what it tests.

**The rule.** Normalise what you do not mean to compare. Read the failure
message, not just the exit code: a red test that failed for the wrong reason is
uncalibrated, not calibrated.

---

## 8. A claim carried forward onto a commit nobody checked

**What happened.** CI was verified green on one commit; another commit was then
pushed; and the earlier verification was repeated as though it applied. A merge
was recommended on that basis. It happened to be fine.

**The rule.** Verify CI against the pull request's **current head**, every time.
"It was green" is about a SHA, not about a branch.

---

## 9. The documented command is not the whole suite

**What happened.** A refactor moved symbols out of a module. The documented test
line came back 525 green. CI went red, because `mcp-server/` imports the same
symbols and that suite is a separate CI step.

**The rule.** For any change that moves or renames a symbol, ask what else
imports it, including packages outside the directory you are working in. The
full command list is in `03`.
