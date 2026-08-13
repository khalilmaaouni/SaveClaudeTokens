#!/usr/bin/env python3
"""Self-check for discover_companions.py. No framework, no fixtures.

    python3 scripts/test_discover_companions.py

Calibrated tests (defect reinjected during development, confirmed red, then
restored and confirmed green): the CLAUDE PROJECTED label on every
discovered row, the Hooks-line parser against the real captured `claude
plugin details` shape (docs/superpowers/plans/2026-08-13-v18-wave1-plan.md:
52-94), a reworded Hooks line falling to NO DATA instead of guessing, and
registry_match correctly separating curated / mention / unknown names.
"""

import json
import os
import tempfile

import discover_companions as dc

_ORIG_RUN = dc.subprocess.run


class _FakeCompleted:
    def __init__(self, stdout, returncode=0):
        self.stdout = stdout
        self.returncode = returncode


def _fake_run(stdout_by_cmd):
    """subprocess.run stand-in keyed by the argv tail after "claude"."""
    def run(cmd, **kwargs):
        key = tuple(cmd[1:])
        if key not in stdout_by_cmd:
            raise AssertionError(f"unexpected command: {cmd}")
        return _FakeCompleted(stdout_by_cmd[key])
    return run


LIST_JSON = json.dumps([
    {"id": "ponytail@claude-community", "version": "4.9.0", "enabled": True},
    {"id": "unrelated-plugin@claude-plugins-official", "version": "1.0.0", "enabled": False},
])

# Real captured shape, docs/superpowers/plans/2026-08-13-v18-wave1-plan.md:52-68.
PONYTAIL_DETAILS = (
    "ponytail 4.9.0\n"
    "Component inventory\n"
    "  Skills (6)  ponytail, ponytail-audit\n"
    "  Agents (0)\n"
    "  Hooks (3)  SessionStart, SubagentStart, UserPromptSubmit  (harness-only, no model context cost)\n"
    "  MCP servers (0)\n"
)


def test_discover_labels_every_row_claude_projected():
    dc.subprocess.run = _fake_run({("plugin", "list", "--json"): LIST_JSON})
    rows = dc.discover()
    assert rows, rows
    # Calibrated: hardcoding any other string in discover()'s source_label
    # assignment (or dropping it) makes this assert fail; confirmed red
    # during development, restored to the literal "CLAUDE PROJECTED", green.
    assert all(r["source_label"] == "CLAUDE PROJECTED" for r in rows), rows
    names = {r["name"] for r in rows}
    assert names == {"ponytail", "unrelated-plugin"}, names


def test_discover_returns_none_on_bad_json():
    dc.subprocess.run = _fake_run({("plugin", "list", "--json"): "not json"})
    assert dc.discover() is None


def test_hook_footprint_parses_the_real_captured_shape():
    dc.subprocess.run = _fake_run({("plugin", "details", "ponytail"): PONYTAIL_DETAILS})
    hooks = dc.hook_footprint_of("ponytail")
    assert hooks == ["SessionStart", "SubagentStart", "UserPromptSubmit"], hooks


def test_hook_footprint_is_no_data_on_a_reworded_line():
    # Calibrated: a future CLI release rewording "Hooks (" to "Hook events:"
    # must fall to None, not guess or crash. Confirmed red when the parser
    # was briefly loosened to match on "Hook" alone (it then returned []
    # instead of None on this fixture); restored to the exact "Hooks ("
    # prefix check, green again.
    reworded = PONYTAIL_DETAILS.replace("Hooks (3)", "Hook events: 3")
    dc.subprocess.run = _fake_run({("plugin", "details", "ponytail"): reworded})
    assert dc.hook_footprint_of("ponytail") is None


def test_hook_footprint_empty_list_for_zero_hooks():
    zero = PONYTAIL_DETAILS.replace(
        "  Hooks (3)  SessionStart, SubagentStart, UserPromptSubmit  (harness-only, no model context cost)\n",
        "  Hooks (0)\n")
    dc.subprocess.run = _fake_run({("plugin", "details", "ponytail"): zero})
    assert dc.hook_footprint_of("ponytail") == []


def test_registry_match_separates_curated_mention_unknown():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "companions.json")
        with open(path, "w") as f:
            json.dump({"schema": 2, "companions": [{"name": "ponytail"}],
                      "mentions": [{"name": "ccusage"}]}, f)
        match = dc._registry_match(["ponytail", "ccusage", "something-else"], path)
        assert match == {"ponytail": "curated", "ccusage": "mention",
                         "something-else": "unknown"}, match


def test_write_state_round_trips_and_never_carries_a_priced_field():
    with tempfile.TemporaryDirectory() as d:
        state_path = os.path.join(d, "companions_state.json")
        companions_path = os.path.join(d, "companions.json")
        with open(companions_path, "w") as f:
            json.dump({"schema": 2, "companions": [], "mentions": []}, f)
        discovered = [{"name": "ponytail", "enabled": True, "source_label": "CLAUDE PROJECTED"}]
        state = dc.write_state(discovered, path=state_path, companions_path=companions_path)
        assert state["schema"] == 1
        assert os.path.exists(state_path)
        reloaded = json.load(open(state_path))
        assert reloaded == state
        blob = json.dumps(state)
        for forbidden in ("MEASURED", "VERIFIED", "ESTIMATED", "NATIVE", "\"usd\""):
            assert forbidden not in blob, (forbidden, blob)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    dc.subprocess.run = _ORIG_RUN
    print(f"\n{len(tests)} passed")
