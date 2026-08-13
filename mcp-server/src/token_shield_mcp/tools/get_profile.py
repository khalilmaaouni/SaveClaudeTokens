"""Tool: get_profile. The deterministic usage profile (startup floor, cache
behavior, model switches), labels intact. Thin wrapper over
profile.build_profile; no new logic.
"""

import profile as pf

from token_shield_mcp.wrappers import call_pure


def get_profile(root: str = None, window_days: float = 30):
    """The deterministic usage profile: startup floor, cache behavior, model
    switches, each leaf carrying its MEASURED/SIGNAL/INFERRED/NO DATA label."""
    return call_pure(pf.build_profile, root=root, days=window_days)
