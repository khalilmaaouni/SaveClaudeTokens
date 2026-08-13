"""Tool: list_strategies. The full strategy registry with citable sources.

load_strategies() returns each entry's raw `source` field as stored in
data/strategies.json (a claim code like "A6"), which is opaque without the
docs/CLAIMS.md row it points at. Per the spec's "with citable sources" line,
this tool runs each entry's source through advisor.format_source (the only
function in the repo that renders a citable source string) before
returning, rather than the raw code advisor._card() would otherwise be the
only caller of.
"""

import copy

import advisor as adv

from token_shield_mcp.wrappers import call_pure


def list_strategies():
    """The full strategy registry, each entry's source rewritten to a
    citable docs/CLAIMS.md pointer."""
    strategies = call_pure(adv.load_strategies)
    out = []
    for s in strategies:
        s = copy.deepcopy(s)
        s["source"] = adv.format_source(s.get("source"))
        out.append(s)
    return out
