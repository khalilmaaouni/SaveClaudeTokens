#!/usr/bin/env python3
"""
generate_corpus.py: a synthetic session-transcript corpus for the benchmark
kit, with zero real user data.

Writes JSONL session files in the exact record shape
scripts/measure_tokens.py reads (its read_session() function): one line per
assistant call, each carrying a message.usage object with input_tokens,
the split cache_creation object, cache_read_input_tokens and output_tokens.
The field names here are copied from that function and from the seeding
helper in scripts/test_measure_tokens.py (_rec()), not invented.

Deterministic: the same --seed always writes the same session files, byte
for byte. Every token count is drawn from a seeded random.Random, so the
corpus is reproducible and contains nothing read from a real machine.

Alongside the session files this writes expected.json: the aggregate and
per-session numbers the corpus was built to contain, computed here by
straight arithmetic on the values just written, before the real meter ever
sees them. bench/run_benchmark.py compares the meter's own output against
this file.

USAGE
  python3 bench/generate_corpus.py --out /path/to/dir
  python3 bench/generate_corpus.py --out /path/to/dir --seed 7
"""

import argparse
import json
import os
import random

DEFAULT_SEED = 42
N_SESSIONS = 12
MODEL = "bench-model"


def _record(inp, w5, w1, read, out, timestamp):
    """One JSONL line, shaped exactly like read_session() in
    scripts/measure_tokens.py expects: isSidechain, message.model,
    message.usage.{input_tokens, cache_creation.ephemeral_5m_input_tokens,
    cache_creation.ephemeral_1h_input_tokens, cache_creation_input_tokens,
    cache_read_input_tokens, output_tokens}."""
    return json.dumps({
        "isSidechain": False,
        "timestamp": timestamp,
        "message": {
            "model": MODEL,
            "usage": {
                "input_tokens": inp,
                "cache_creation": {
                    "ephemeral_5m_input_tokens": w5,
                    "ephemeral_1h_input_tokens": w1,
                },
                "cache_creation_input_tokens": w5 + w1,
                "cache_read_input_tokens": read,
                "output_tokens": out,
            },
        },
    })


def _median(vals):
    n = len(vals)
    mid = n // 2
    if n % 2:
        return vals[mid]
    return (vals[mid - 1] + vals[mid]) / 2


def build_corpus(rng):
    """Return (files, expected). files maps a session filename to its list
    of JSONL line strings. expected mirrors, by direct construction, the
    numbers those files were built to contain: never call into
    scripts/measure_tokens.py here, or a bug shared by both sides would
    pass silently."""
    files = {}
    per_session = []
    totals = {"input": 0, "read": 0, "write_5m": 0, "write_1h": 0, "output": 0}

    for i in range(N_SESSIONS):
        n_calls = rng.randint(3, 6)
        lines = []
        s_input = s_read = s_w5 = s_w1 = s_output = 0
        first_request = None
        for c in range(n_calls):
            inp = rng.randint(50, 500)
            w5 = rng.randint(0, 300)
            w1 = rng.randint(0, 100)
            read = rng.randint(0, 3000)
            out = rng.randint(20, 800)
            ts = f"2026-01-01T00:{i:02d}:{c:02d}Z"
            lines.append(_record(inp, w5, w1, read, out, ts))
            if first_request is None:
                # The startup floor: the first call's own counters, same
                # formula as measure_tokens.read_session().
                first_request = inp + w5 + w1 + read
            s_input += inp
            s_read += read
            s_w5 += w5
            s_w1 += w1
            s_output += out

        fn = f"session_{i:03d}.jsonl"
        files[fn] = lines
        raw_input = s_input + s_w5 + s_w1 + s_read
        hit_ratio = (s_read / raw_input) if raw_input else 0.0
        per_session.append({
            "file": fn,
            "calls": n_calls,
            "input": s_input,
            "read": s_read,
            "write_5m": s_w5,
            "write_1h": s_w1,
            "output": s_output,
            "first_request": first_request,
            "hit_ratio": hit_ratio,
        })
        totals["input"] += s_input
        totals["read"] += s_read
        totals["write_5m"] += s_w5
        totals["write_1h"] += s_w1
        totals["output"] += s_output

    # Every session here has a non-sidechain first call, so all N_SESSIONS
    # count as parent sessions for first_request stats, same population
    # measure_tokens.summarize() uses.
    firsts = sorted(s["first_request"] for s in per_session)
    hits = sorted(s["hit_ratio"] for s in per_session)

    expected = {
        "seed": None,  # filled in by write_corpus()
        "sessions": per_session,
        "aggregate": {
            "input_total": totals["input"],
            "read_total": totals["read"],
            "write_5m_total": totals["write_5m"],
            "write_1h_total": totals["write_1h"],
            "output_total": totals["output"],
            "first_request_median": _median(firsts),
            "first_request_mean": sum(firsts) / len(firsts),
            "first_request_p90": (firsts[int(len(firsts) * 0.9)]
                                   if len(firsts) >= 10 else None),
            "hit_ratio_median": _median(hits),
        },
    }
    return files, expected


def write_corpus(out_dir, seed):
    rng = random.Random(seed)
    files, expected = build_corpus(rng)
    os.makedirs(out_dir, exist_ok=True)
    for fn, lines in files.items():
        with open(os.path.join(out_dir, fn), "w") as f:
            f.write("\n".join(lines) + "\n")
    expected["seed"] = seed
    with open(os.path.join(out_dir, "expected.json"), "w") as f:
        json.dump(expected, f, indent=2)
    return expected


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--out", required=True, help="directory to write the corpus into")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED,
                     help=f"RNG seed, default {DEFAULT_SEED}")
    a = ap.parse_args()
    expected = write_corpus(a.out, a.seed)
    n = len(expected["sessions"])
    print(f"wrote {n} session files and expected.json to {a.out} (seed {a.seed})")


if __name__ == "__main__":
    main()
