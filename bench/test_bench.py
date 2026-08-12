#!/usr/bin/env python3
"""Self-check for bench/generate_corpus.py and bench/run_benchmark.py.
No framework, no fixtures, same style as scripts/test_measure_tokens.py.

    python3 bench/test_bench.py

Every assertion here was run against a broken version of the code first
(noted per test), to confirm it can fail rather than pass no matter what.
"""

import importlib.util
import json
import os
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gc = _load("gc", "generate_corpus.py")
rb = _load("rb", "run_benchmark.py")


def test_generator_is_deterministic():
    # Calibrated red: writing the two draws with random.Random() (no seed)
    # instead of random.Random(seed) makes this fail on almost every run,
    # since the process's own entropy differs between the two temp dirs.
    with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
        gc.write_corpus(d1, seed=gc.DEFAULT_SEED)
        gc.write_corpus(d2, seed=gc.DEFAULT_SEED)
        files1 = sorted(os.listdir(d1))
        files2 = sorted(os.listdir(d2))
        assert files1 == files2, (files1, files2)
        for fn in files1:
            with open(os.path.join(d1, fn)) as f1, open(os.path.join(d2, fn)) as f2:
                assert f1.read() == f2.read(), f"{fn} differs between two same-seed runs"


def test_clean_corpus_passes():
    with tempfile.TemporaryDirectory() as d:
        gc.write_corpus(d, seed=gc.DEFAULT_SEED)
        with open(os.path.join(d, "expected.json")) as f:
            expected = json.load(f)
        mt = rb._load_measure_tokens()
        sessions = mt.collect(d, days=1_000_000)
        sm = mt.summarize(sessions)
        rows = rb.compare(expected, sessions, sm)
        failed = [r for r in rows if not r[3]]
        assert not failed, failed
        assert len(rows) > 0


def test_corrupted_corpus_fails():
    # Calibrated red: this test was first run with the corruption line
    # removed (the untouched clean corpus), which passes; then with the
    # input_tokens tamper restored below, which must FAIL at least one row.
    # A runner that reports PASS on tampered data cannot be trusted to
    # catch a real regression in scripts/measure_tokens.py either.
    with tempfile.TemporaryDirectory() as d:
        gc.write_corpus(d, seed=gc.DEFAULT_SEED)
        with open(os.path.join(d, "expected.json")) as f:
            expected = json.load(f)
        target = os.path.join(d, expected["sessions"][0]["file"])
        with open(target) as f:
            lines = f.read().splitlines()
        rec = json.loads(lines[0])
        rec["message"]["usage"]["input_tokens"] += 9999  # the injected wrong count
        lines[0] = json.dumps(rec)
        with open(target, "w") as f:
            f.write("\n".join(lines) + "\n")

        mt = rb._load_measure_tokens()
        sessions = mt.collect(d, days=1_000_000)
        sm = mt.summarize(sessions)
        rows = rb.compare(expected, sessions, sm)
        failed = [r for r in rows if not r[3]]
        assert failed, "a corrupted corpus must produce at least one FAIL row"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
