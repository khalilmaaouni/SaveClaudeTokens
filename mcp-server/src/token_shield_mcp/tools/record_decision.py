"""Tool: record_decision(strategy_id, decision). The one write tool besides
the experiment pair. Echoes exactly what advisor.record_decision recorded
and when it resurfaces; an unknown decision string's ValueError propagates
unmodified (see errors.py), never caught here.
"""

import advisor as adv

from token_shield_mcp.wrappers import call_pure


def record_decision(strategy_id: str, decision: str, days: int = 90, note: str = ""):
    """Record a decision on an advisor card. decision is one of
    accepted/rejected/suppressed; an unknown value raises ValueError."""
    return call_pure(adv.record_decision, strategy_id, decision, days=days,
                      note=note, path=adv.TREATMENTS_PATH)
