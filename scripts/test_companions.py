#!/usr/bin/env python3
"""Self-check for scripts/companions/ (unit H1). No framework, no fixtures
beyond the small ones built inline below.

    cd scripts && python3 test_companions.py

Calibrated tests (defect reinjected during development, confirmed red, then
restored and confirmed green): the registry-refusal path (companions.
describe() refusing an entry that is missing "install", "uninstall", or a
tested_version_range sub-field, naming the missing field), the never-
invented command path (activation and rollback commands must equal the
registry's own "install"/"uninstall" strings verbatim, checked here against
the real data/companions.json, not only a fixture), and the read-only path
(report() for all three adapters never opens a file in a writing mode).
"""

import builtins
import contextlib
import io
import json
import os
import time

import token_shield as ts
import config as cfg
from companions import caveman, describe, ponytail, token_saver

REAL_COMPANIONS_PATH = cfg.COMPANIONS_PATH


def _entry(name, install="claude plugin install x@y", uninstall="claude plugin uninstall x",
           tested_version_range=None, modes=None):
    entry = {"name": name, "install": install, "uninstall": uninstall}
    if tested_version_range is not None:
        entry["tested_version_range"] = tested_version_range
    if modes is not None:
        entry["modes"] = modes
    return entry


def _registry(*entries):
    return {"schema": 2, "companions": list(entries), "mentions": []}


def _state(discovered):
    return {"schema": 1, "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "discovered": discovered,
            "registry_match": {d["name"]: "curated" for d in discovered}}


GOOD_VR = {"min": "1.0.0", "max": "1.0.0", "tested_on": "2026-08-13"}


# --- hard rule 1: refuse a registry entry missing an evidence field ---

def test_describe_refuses_when_install_missing():
    # Calibrated: describe() briefly skipped the REQUIRED_FIELDS loop
    # entirely during development (every entry was accepted regardless of
    # missing fields); this test went red with no "reason" key at all;
    # restored to the per-field loop, green again.
    data = _registry({"name": "widget", "uninstall": "u", "tested_version_range": GOOD_VR})
    result = describe(data, _state([]), "widget")
    assert result["refused"] is True, result
    assert "install" in result["reason"], result


def test_describe_refuses_when_uninstall_missing():
    data = _registry(_entry("widget", tested_version_range=GOOD_VR))
    del data["companions"][0]["uninstall"]
    result = describe(data, _state([]), "widget")
    assert result["refused"] is True, result
    assert "uninstall" in result["reason"], result


def test_describe_refuses_when_tested_version_range_missing():
    data = _registry(_entry("widget"))
    result = describe(data, _state([]), "widget")
    assert result["refused"] is True, result
    assert "tested_version_range" in result["reason"], result


def test_describe_refuses_when_version_subfield_missing():
    incomplete_vr = {"min": "1.0.0", "max": "1.0.0"}  # no tested_on
    data = _registry(_entry("widget", tested_version_range=incomplete_vr))
    result = describe(data, _state([]), "widget")
    assert result["refused"] is True, result
    assert "tested_on" in result["reason"], result


def test_describe_refuses_when_entry_absent():
    data = _registry(_entry("other", tested_version_range=GOOD_VR))
    result = describe(data, _state([]), "widget")
    assert result["refused"] is True, result
    assert "widget" in result["reason"], result


# --- status vocabulary, mirroring discover_companions.py ---

def test_describe_status_active_installed_neither():
    data = _registry(
        _entry("ponytail", tested_version_range=GOOD_VR),
        _entry("caveman", tested_version_range=GOOD_VR),
        _entry("token-saver", tested_version_range=GOOD_VR),
    )
    state = _state([
        {"name": "ponytail", "enabled": True, "source_label": "CLAUDE PROJECTED"},
        {"name": "caveman", "enabled": False, "source_label": "CLAUDE PROJECTED"},
    ])
    assert describe(data, state, "ponytail")["status"] == "active"
    assert describe(data, state, "caveman")["status"] == "installed"
    assert describe(data, state, "token-saver")["status"] == "neither"


# --- modes: NO DATA when the registry carries no "modes" field ---

def test_describe_modes_no_data_when_field_absent():
    # Calibrated: modes_field briefly defaulted to {"label": "MEASURED",
    # "value": []} when "modes" was absent, which is a guess dressed as a
    # measurement; this test went red on label == "MEASURED"; restored to
    # the NO DATA branch, green again.
    data = _registry(_entry("widget", tested_version_range=GOOD_VR))
    result = describe(data, _state([]), "widget")
    assert result["modes"]["label"] == "NO DATA", result
    assert "modes" in result["modes"]["reason"], result


def test_describe_modes_measured_when_field_present():
    data = _registry(_entry("widget", tested_version_range=GOOD_VR, modes=["lite", "full"]))
    result = describe(data, _state([]), "widget")
    assert result["modes"] == {"label": "MEASURED", "value": ["lite", "full"],
                               "source": "data/companions.json"}, result


# --- hard rule 2: nothing invented, commands are verbatim registry strings ---

def test_describe_commands_are_verbatim_not_transformed():
    data = _registry(_entry("widget", install="INSTALL X", uninstall="UNINSTALL X",
                            tested_version_range=GOOD_VR))
    result = describe(data, _state([]), "widget")
    assert result["activation_command"]["value"] == "INSTALL X", result
    assert result["rollback_command"]["value"] == "UNINSTALL X", result


def test_real_registry_commands_appear_verbatim_in_companions_json():
    # Reads the checked-in data/companions.json (repo content, not the live
    # machine) and proves each of the three shipped adapters' commands are
    # substrings of that file's raw text, not rebuilt or templated.
    with open(REAL_COMPANIONS_PATH) as f:
        raw = f.read()
    for mod in (ponytail, caveman, token_saver):
        result = mod.report(state={"discovered": []})
        assert result["refused"] is False, (mod.NAME, result)
        assert result["activation_command"]["value"] in raw, (mod.NAME, result)
        assert result["rollback_command"]["value"] in raw, (mod.NAME, result)


def test_real_registry_version_matches_tested_version_range():
    with open(REAL_COMPANIONS_PATH) as f:
        data = json.load(f)
    by_name = {c["name"]: c for c in data["companions"]}
    for mod in (ponytail, caveman, token_saver):
        result = mod.report(state={"discovered": []})
        vr = by_name[mod.NAME]["tested_version_range"]
        expected = vr["min"] if vr["min"] == vr["max"] else f"{vr['min']} to {vr['max']}"
        assert result["version"]["value"] == expected, (mod.NAME, result)


# --- hard rule 3: adapters are read only ---

def test_adapters_never_open_a_file_in_writing_mode():
    # Calibrated: a first draft of report() called discover_companions.
    # write_state() to "warm" the state cache before reading it; this test
    # went red on a mode-"w" open of companions_state.json; restored to a
    # read-only load_state(), green again.
    real_open = builtins.open
    writes = []

    def spying_open(file, mode="r", *args, **kwargs):
        if any(c in mode for c in ("w", "a", "x", "+")):
            writes.append((file, mode))
        return real_open(file, mode, *args, **kwargs)

    builtins.open = spying_open
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            for mod in (ponytail, caveman, token_saver):
                mod.report(state={"discovered": []})
                mod.main([])
    finally:
        builtins.open = real_open
    assert writes == [], writes


def test_adapter_refusal_prints_the_reason():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = ponytail.report(companions_path=os.devnull, state={"discovered": []})
    assert result["refused"] is True, result
    assert result["reason"] in buf.getvalue(), buf.getvalue()


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
