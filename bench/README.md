# Benchmark kit

A reproducible proof surface for `scripts/measure_tokens.py`. It writes a
synthetic corpus of session transcripts, runs the real meter over that
corpus, and checks the meter's output against the numbers the corpus was
built to contain. No real user data anywhere in it: every token count is
drawn from a seeded random number generator, so the corpus is the same on
every machine that runs the same seed.

## Run it

Two commands, from the repository root:

```bash
python3 bench/generate_corpus.py --out /tmp/bench-corpus
python3 bench/run_benchmark.py --corpus /tmp/bench-corpus
```

The second command prints one row per checked number, each marked PASS or
FAIL, and exits 0 only when every row passes.

To confirm the kit itself is trustworthy (the generator is deterministic,
and the runner actually catches a broken corpus rather than rubber-stamping
it):

```bash
python3 bench/test_bench.py
```

## What this proves

That `scripts/measure_tokens.py` reads the `usage` counters out of a
session transcript correctly: input tokens, cache reads, cache writes split
by 5 minute and 1 hour TTL, output tokens, the per-session first-request
floor, and the cache hit ratio. `bench/generate_corpus.py` writes JSONL
files in the exact shape Claude Code writes those counters in, and computes
the expected numbers itself, by direct arithmetic on the values it just
wrote, before the meter ever touches the files. `bench/run_benchmark.py`
then runs the real meter and compares its output field by field against
that expectation. Every row in the printed table is labeled CONSTRUCTED
(what the generator built) or MEASURED (what the meter read back), and the
two never blend into one number.

If every row passes, the arithmetic in the meter is sound on data whose
right answer is known in advance.

## What this does not prove

Your own token savings. This corpus is synthetic and contains no real
conversation history, no real plugin or MCP footprint, and no real caching
behavior from your own sessions. A clean run here says the meter's counting
is correct. It says nothing about how many tokens your own sessions
actually use, whether your own cache hit ratio is healthy, or whether a
change you made actually cut anything. For that, run the meter against your
real transcripts (`python3 scripts/measure_tokens.py`) and use Experiment
Mode (`/token-shield:token-audit`) to get a before-and-after that is
VERIFIED rather than estimated.
