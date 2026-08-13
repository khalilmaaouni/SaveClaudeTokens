"""Tool: get_advice. The single best card: problem with its measured
number, treatment, expected benefit with evidence label, drawback, how
steps with commands. Composes profile.build_profile and advisor.advise,
both already pure; no new logic.
"""

import advisor as adv
import profile as pf

from token_shield_mcp.wrappers import call_pure


def get_advice(root: str = None, window_days: float = 30):
    """The ranked next-move cards: best, alternatives, companion, or the
    do_nothing message when nothing crossed a trigger threshold."""
    profile = call_pure(pf.build_profile, root=root, days=window_days)
    return call_pure(adv.advise, profile=profile,
                      treatments=adv.load_treatments(), strategies=adv.load_strategies())
