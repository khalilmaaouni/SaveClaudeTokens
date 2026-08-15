#!/usr/bin/env python3
"""
formatting.py: the three primitives every surface formats numbers and text with.

Extracted from token_shield because BOTH halves of that module needed them:
the renderer obviously, and the metric half too, since prescriptions builds
the human-readable sentence that names its own saving. That single crossing
was the one thing standing between this codebase and a provable split between
what it COMPUTES and what it RENDERS.

Layer 0. Imports nothing else in this repository, which is what makes it the
floor. Nothing here decides anything: these three turn a value into
characters, and a function that starts choosing what to say has outgrown this
file (docs/ARCHITECTURE.md).
"""

import html


def esc(s):
    """HTML-escape anything that came from outside this file before it enters
    the page. Experiment labels are typed by the user, profile bases carry
    file paths, and the companion registry is an editable JSON file, so all
    three are attacker-shaped text as far as the renderer is concerned. None
    renders as an empty string rather than the word None."""
    return html.escape("" if s is None else str(s))


def human(n):
    """Compact a token count: 1_532_000 -> 1.5M."""
    if n is None:
        return "NO DATA"
    n = float(n)
    for unit, div in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if abs(n) >= div:
            return f"{n / div:.1f}{unit}"
    return f"{int(n):,}"


def pct(x):
    return "NO DATA" if x is None else f"{x * 100:.0f}%"
