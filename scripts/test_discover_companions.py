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


def test_discover_captures_the_version_field():
    # Calibrated: discover() dropped the "version" key entirely before this
    # unit; confirmed red (KeyError below) against the code prior to this
    # change, green once discover() started reading e.get("version").
    dc.subprocess.run = _fake_run({("plugin", "list", "--json"): LIST_JSON})
    rows = dc.discover()
    by_name = {r["name"]: r for r in rows}
    assert by_name["ponytail"]["version"] == "4.9.0", rows
    assert by_name["unrelated-plugin"]["version"] == "1.0.0", rows


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


def test_version_drift_detects_an_injected_version_change():
    # Central calibration for this unit: dc.version_drift does not exist
    # before this change (AttributeError, confirmed red running this test
    # against the prior code). The fixture below injects a fake version
    # change (state says 4.9.0, live says 5.0.0) so the assertions only
    # pass once real drift detection compares the two.
    live = [{"name": "ponytail", "version": "5.0.0", "enabled": True,
             "source_label": "CLAUDE PROJECTED"}]
    state = {"schema": 1, "checked_at": "2026-08-12T00:00:00Z",
             "discovered": [{"name": "ponytail", "version": "4.9.0", "enabled": True,
                             "source_label": "CLAUDE PROJECTED"}]}
    result = dc.version_drift(["ponytail"], live, state)
    assert result["no_data"] is False, result
    assert len(result["drifted"]) == 1, result
    d = result["drifted"][0]
    assert d["name"] == "ponytail", d
    assert d["recorded_version"] == "4.9.0", d
    assert d["live_version"] == "5.0.0", d
    assert d["recorded_at"] == "2026-08-12T00:00:00Z", d
    assert result["missing"] == [], result


def test_version_drift_clean_when_versions_match():
    live = [{"name": "ponytail", "version": "4.9.0", "enabled": True,
             "source_label": "CLAUDE PROJECTED"}]
    state = {"schema": 1, "checked_at": "2026-08-12T00:00:00Z",
             "discovered": [{"name": "ponytail", "version": "4.9.0", "enabled": True,
                             "source_label": "CLAUDE PROJECTED"}]}
    result = dc.version_drift(["ponytail"], live, state)
    assert result == {"no_data": False, "drifted": [], "missing": []}, result


def test_version_drift_no_data_when_state_missing():
    live = [{"name": "ponytail", "version": "4.9.0", "enabled": True,
             "source_label": "CLAUDE PROJECTED"}]
    result = dc.version_drift(["ponytail"], live, None)
    assert result["no_data"] is True, result
    assert result["drifted"] == [] and result["missing"] == [], result


def test_version_drift_missing_recorded_version_is_no_data_not_no_drift():
    # NO DATA beats a guess: a companion the state never recorded a version
    # for must never be folded into "no drift".
    live = [{"name": "ponytail", "version": "4.9.0", "enabled": True,
             "source_label": "CLAUDE PROJECTED"}]
    state = {"schema": 1, "checked_at": "2026-08-12T00:00:00Z",
             "discovered": [{"name": "ponytail", "enabled": True,
                             "source_label": "CLAUDE PROJECTED"}]}
    result = dc.version_drift(["ponytail"], live, state)
    assert result["drifted"] == [], result
    assert result["missing"] == [{"name": "ponytail", "live_version": "4.9.0"}], result


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


# I1: the open declaration contract, docs/superpowers/specs/
# integration-contract-v1.md. Fixture plugin roots are built here with
# tempfile, never against the live machine's ~/.claude/plugins/cache. Every
# declaration is UNTRUSTED THIRD-PARTY INPUT in these tests, on purpose:
# fixtures deliberately include hostile and malformed shapes.

def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


def test_read_declaration_labels_every_field_declared():
    # Calibrated: read_declaration does not exist before this change
    # (AttributeError, confirmed red running this test against the prior
    # code). A valid declaration with several fields must come back with
    # every one of those fields wrapped {"label": "DECLARED", ...}.
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "token-shield.integration.json")
        _write_json(path, {
            "name": "widget-saver",
            "capabilities": ["output_compression"],
            "modes": ["off", "full"],
            "rollback_command": "claude plugin uninstall widget-saver",
        })
        row = dc.read_declaration(path)
        assert row["refused"] is False, row
        assert row["name"] == "widget-saver", row
        for key in ("name", "capabilities", "modes", "rollback_command"):
            assert row["fields"][key]["label"] == "DECLARED", row["fields"][key]
            assert row["fields"][key]["source"] == path, row["fields"][key]
        assert row["fields"]["capabilities"]["value"] == ["output_compression"], row


def test_read_declaration_refuses_missing_capabilities_by_name():
    # Requirement: a fixture with a missing capabilities key is refused BY
    # NAME (the reason string must name the field), never silently loaded.
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "token-shield.integration.json")
        _write_json(path, {"name": "widget-saver", "modes": ["full"]})
        row = dc.read_declaration(path)
        assert row["refused"] is True, row
        assert "capabilities" in row["reason"], row["reason"]
        assert "missing" in row["reason"], row["reason"]


def test_read_declaration_refuses_empty_capabilities_with_the_right_reason():
    # Major 4: {"capabilities": []} is present, not missing. Mutating the
    # presence check (dropped in favor of a bare truthiness test on
    # data.get("capabilities")) previously reported this as "missing",
    # which is the wrong reason for a key that IS there but empty.
    # Confirmed red against the reviewer-found mutation (truthiness check
    # only, no separate presence check): it reported "missing" for this
    # exact fixture; green once presence and shape are checked separately.
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "token-shield.integration.json")
        _write_json(path, {"capabilities": []})
        row = dc.read_declaration(path)
        assert row["refused"] is True, row
        assert "missing" not in row["reason"], row["reason"]
        assert "non-empty" in row["reason"], row["reason"]


def test_read_declaration_refuses_malformed_json_without_crashing():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "token-shield.integration.json")
        with open(path, "w") as f:
            f.write("{not valid json,,,")
        row = dc.read_declaration(path)  # must not raise
        assert row["refused"] is True, row
        assert "malformed JSON" in row["reason"], row["reason"]


def test_read_declaration_refuses_a_json_array_not_an_object():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "token-shield.integration.json")
        _write_json(path, ["not", "an", "object"])
        row = dc.read_declaration(path)
        assert row["refused"] is True, row
        assert "not a JSON object" in row["reason"], row["reason"]


def test_declared_field_label_is_never_curated():
    # Calibrated: briefly hardcoding "CURATED" as the per-field label inside
    # read_declaration() (in place of DECLARED_LABEL) was confirmed to turn
    # this assertion red; restored to DECLARED_LABEL, green again. The load
    # bearing rule of this unit: a declared field can never appear labeled
    # CURATED, no matter what the declaration file claims about itself.
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "token-shield.integration.json")
        _write_json(path, {"name": "widget-saver", "capabilities": ["minimal_code"],
                           "status": "CURATED"})
        row = dc.read_declaration(path)
        assert row["refused"] is False, row
        labels = {f["label"] for f in row["fields"].values()}
        assert labels == {"DECLARED"}, labels
        assert "CURATED" not in labels, labels


# Critical 2 (reviewer-reproduced): json.loads on deeply nested JSON raises
# RecursionError, which is neither OSError nor JSONDecodeError, and the
# prior code let it escape read_declaration and kill the whole discovery
# walk. Confirmed red against the prior code (uncaught RecursionError);
# green once read_declaration catches it and returns a named refusal.

def test_read_declaration_refuses_deeply_nested_json_without_crashing():
    # 20000 levels of array nesting, ~40KB: comfortably under
    # MAX_DECLARATION_BYTES (so this exercises the RecursionError catch
    # itself, not the size guard), and independently confirmed on this
    # machine to raise RecursionError from plain json.loads.
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "token-shield.integration.json")
        with open(path, "w") as f:
            f.write('{"capabilities":' + "[" * 20000 + "]" * 20000 + "}")
        row = dc.read_declaration(path)  # must not raise
        assert row["refused"] is True, row


def test_read_declaration_refuses_oversized_file_without_reading_it_all():
    # The reviewer's own repro: {"capabilities": + 200000 open brackets +
    # closes + }, well over MAX_DECLARATION_BYTES. Must refuse, not raise,
    # and must not require parsing the whole hostile payload to do it.
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "token-shield.integration.json")
        with open(path, "w") as f:
            f.write('{"capabilities":' + "[" * 200000 + "]" * 200000 + "}")
        row = dc.read_declaration(path)  # must not raise
        assert row["refused"] is True, row
        assert "size limit" in row["reason"], row["reason"]


def test_read_declaration_refuses_duplicate_top_level_keys():
    # Minor 8: a duplicate top-level key must not silently smuggle a second
    # value (e.g. a different rollback_command) past a reader that reads
    # only the first occurrence. Confirmed red with plain json.loads (no
    # object_pairs_hook): it silently returns the LAST value, no refusal.
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "token-shield.integration.json")
        with open(path, "w") as f:
            f.write('{"capabilities": ["x"], "rollback_command": "safe", '
                    '"rollback_command": "evil"}')
        row = dc.read_declaration(path)  # must not raise
        assert row["refused"] is True, row
        assert "duplicate" in row["reason"].lower(), row["reason"]


# Major 3: the schema was decorative, never enforced anywhere. The
# orchestrator confirmed these four shapes were all ACCEPTED before this
# fix; each must now be refused.

def test_read_declaration_refuses_capabilities_as_a_string():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "token-shield.integration.json")
        _write_json(path, {"capabilities": "a string"})
        row = dc.read_declaration(path)
        assert row["refused"] is True, row


def test_read_declaration_refuses_capabilities_as_a_number():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "token-shield.integration.json")
        _write_json(path, {"capabilities": 3})
        row = dc.read_declaration(path)
        assert row["refused"] is True, row


def test_read_declaration_refuses_capabilities_with_a_null_item():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "token-shield.integration.json")
        _write_json(path, {"capabilities": [None]})
        row = dc.read_declaration(path)
        assert row["refused"] is True, row


def test_read_declaration_refuses_rollback_command_of_the_wrong_type():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "token-shield.integration.json")
        _write_json(path, {"capabilities": ["x"], "rollback_command": ["rm -rf ~"]})
        row = dc.read_declaration(path)
        assert row["refused"] is True, row
        assert "rollback_command" in row["reason"], row["reason"]


def _build_fixture_cache(root, plugin_name, version, declaration=None, marketplace="fixture-marketplace"):
    """cache_root/<marketplace>/<plugin_name>/<version>/, with a declaration
    file written there when `declaration` is given (a dict) or left absent
    (None), or written as raw malformed text when `declaration` is a str."""
    vdir = os.path.join(root, marketplace, plugin_name, version)
    os.makedirs(vdir, exist_ok=True)
    if declaration is None:
        return
    decl_path = os.path.join(vdir, dc.INTEGRATION_FILENAME)
    if isinstance(declaration, str):
        with open(decl_path, "w") as f:
            f.write(declaration)
    else:
        _write_json(decl_path, declaration)


def test_discover_declarations_walks_fixture_roots_and_skips_malformed():
    # Calibrated: discover_declarations does not exist before this change
    # (AttributeError, confirmed red). Two fixture plugin roots: one valid
    # declaration, one malformed; discovery must return both rows and must
    # not raise on the malformed one.
    with tempfile.TemporaryDirectory() as cache_root, \
         tempfile.TemporaryDirectory() as reg_dir:
        _build_fixture_cache(cache_root, "good-plugin", "1.0.0",
                             {"capabilities": ["output_compression"]})
        _build_fixture_cache(cache_root, "bad-plugin", "2.0.0", "{broken")
        companions_path = os.path.join(reg_dir, "companions.json")
        _write_json(companions_path, {"schema": 2, "companions": [], "mentions": []})
        rows = dc.discover_declarations(cache_root=cache_root,
                                        companions_path=companions_path)
        assert len(rows) == 2, rows
        refused = [r for r in rows if r["refused"]]
        accepted = [r for r in rows if not r["refused"]]
        assert len(refused) == 1 and len(accepted) == 1, rows
        assert "bad-plugin" in refused[0]["path"], refused
        # Major 6: every row, refused or not, carries the cache version dir.
        assert accepted[0]["version"] == "1.0.0", accepted
        assert refused[0]["version"] == "2.0.0", refused


def test_discover_declarations_missing_cache_root_returns_empty_never_raises():
    with tempfile.TemporaryDirectory() as reg_dir:
        companions_path = os.path.join(reg_dir, "companions.json")
        _write_json(companions_path, {"schema": 2, "companions": [], "mentions": []})
        rows = dc.discover_declarations(
            cache_root=os.path.join(reg_dir, "does-not-exist"),
            companions_path=companions_path)
        assert rows == [], rows


def test_discover_declarations_reports_curated_conflict_without_merging():
    # Requirement 4: a plugin that is both curated and declaring must have
    # the collision reported, never silently resolved, and the curated
    # registry itself must be untouched by this unit (no write path exists
    # from discover_declarations back into companions.json).
    with tempfile.TemporaryDirectory() as cache_root, \
         tempfile.TemporaryDirectory() as reg_dir:
        _build_fixture_cache(cache_root, "ponytail", "9.9.9",
                             {"name": "ponytail", "capabilities": ["minimal_code"],
                              "rollback_command": "self-reported uninstall"})
        _build_fixture_cache(cache_root, "solo-plugin", "1.0.0",
                             {"name": "solo-plugin", "capabilities": ["output_compression"]})
        companions_path = os.path.join(reg_dir, "companions.json")
        before = {"schema": 2, "companions": [{"name": "ponytail", "install": "x",
                                               "uninstall": "y"}], "mentions": []}
        _write_json(companions_path, before)
        rows = dc.discover_declarations(cache_root=cache_root,
                                        companions_path=companions_path)
        by_name = {r["name"]: r for r in rows}
        assert by_name["ponytail"]["curated_conflict"] is True, by_name["ponytail"]
        assert "note" in by_name["ponytail"], by_name["ponytail"]
        assert by_name["solo-plugin"]["curated_conflict"] is False, by_name["solo-plugin"]
        assert "note" not in by_name["solo-plugin"], by_name["solo-plugin"]
        # the curated registry file on disk is exactly what it was before:
        # this unit never writes to data/companions.json.
        after = json.load(open(companions_path))
        assert after == before, after


# Critical 1 (reviewer-reproduced): a hostile declaration with a non-string
# "name" (a dict, unhashable) previously blew up the set-membership check
# `name in curated_names` with an uncaught TypeError, killing the entire
# discovery walk and losing every other plugin's declaration with it.
# Fixture layout matches the orchestrator's own repro: <root>/mkt/honest/
# 1.0.0/ and <root>/mkt/evil/1.0.0/.

def test_discover_declarations_survives_a_hostile_unhashable_name():
    with tempfile.TemporaryDirectory() as cache_root, \
         tempfile.TemporaryDirectory() as reg_dir:
        companions_path = os.path.join(reg_dir, "companions.json")
        _write_json(companions_path, {"schema": 2, "companions": [], "mentions": []})
        # honest-only baseline, matching the orchestrator's repro shape.
        _build_fixture_cache(cache_root, "honest", "1.0.0",
                             {"name": "honest", "capabilities": ["output_compression"]},
                             marketplace="mkt")
        rows = dc.discover_declarations(cache_root=cache_root,
                                        companions_path=companions_path)
        assert len(rows) == 1, rows
        assert rows[0]["refused"] is False and rows[0]["name"] == "honest", rows
        # Calibrated: on the prior code, adding "evil" below raised
        # TypeError: unhashable type, confirmed red. Every other plugin's
        # declaration was lost with it (the whole walk died). Green once
        # the hostile name is refused by type validation instead of
        # reaching the set-membership check unvalidated.
        _build_fixture_cache(cache_root, "evil", "1.0.0",
                             {"name": {"a": 1}, "capabilities": ["x"]},
                             marketplace="mkt")
        rows = dc.discover_declarations(cache_root=cache_root,
                                        companions_path=companions_path)  # must not raise
        assert len(rows) == 2, rows
        by_name_or_path = {r.get("name") or r["path"]: r for r in rows}
        honest_rows = [r for r in rows if r.get("name") == "honest"]
        assert len(honest_rows) == 1 and honest_rows[0]["refused"] is False, rows
        evil_rows = [r for r in rows if r["refused"] and "evil" in r["path"]]
        assert len(evil_rows) == 1, rows
        assert "name" in evil_rows[0]["reason"], evil_rows


# Minor 7: a declaration path that is a directory or a broken symlink was
# silently dropped by the prior code (`if not os.path.isfile: continue`),
# indistinguishable from a plugin that simply never shipped a declaration.

def test_discover_declarations_refuses_a_directory_at_the_declaration_path():
    with tempfile.TemporaryDirectory() as cache_root, \
         tempfile.TemporaryDirectory() as reg_dir:
        companions_path = os.path.join(reg_dir, "companions.json")
        _write_json(companions_path, {"schema": 2, "companions": [], "mentions": []})
        vdir = os.path.join(cache_root, "mkt", "dir-plugin", "1.0.0")
        os.makedirs(os.path.join(vdir, dc.INTEGRATION_FILENAME), exist_ok=True)
        rows = dc.discover_declarations(cache_root=cache_root,
                                        companions_path=companions_path)  # must not raise
        assert len(rows) == 1, rows
        assert rows[0]["refused"] is True, rows


def test_discover_declarations_refuses_a_broken_symlink_at_the_declaration_path():
    with tempfile.TemporaryDirectory() as cache_root, \
         tempfile.TemporaryDirectory() as reg_dir:
        companions_path = os.path.join(reg_dir, "companions.json")
        _write_json(companions_path, {"schema": 2, "companions": [], "mentions": []})
        vdir = os.path.join(cache_root, "mkt", "link-plugin", "1.0.0")
        os.makedirs(vdir, exist_ok=True)
        decl_path = os.path.join(vdir, dc.INTEGRATION_FILENAME)
        os.symlink(os.path.join(vdir, "does-not-exist"), decl_path)
        rows = dc.discover_declarations(cache_root=cache_root,
                                        companions_path=companions_path)  # must not raise
        assert len(rows) == 1, rows
        assert rows[0]["refused"] is True, rows


# Major 6: an uninstalled, cached version's self-claims must not read as
# current. This machine really does have token-shield cached at
# {1.4.0, 1.7.0, 1.7.1} with only 1.7.1 installed (confirmed by ls on
# ~/.claude/plugins/cache/token-shield/token-shield/ during this fix).

def test_discover_declarations_marks_the_installed_version_from_live_data():
    with tempfile.TemporaryDirectory() as cache_root, \
         tempfile.TemporaryDirectory() as reg_dir:
        companions_path = os.path.join(reg_dir, "companions.json")
        _write_json(companions_path, {"schema": 2, "companions": [], "mentions": []})
        _build_fixture_cache(cache_root, "multi-version", "1.0.0",
                             {"name": "multi-version", "capabilities": ["minimal_code"]},
                             marketplace="mkt")
        _build_fixture_cache(cache_root, "multi-version", "2.0.0",
                             {"name": "multi-version", "capabilities": ["minimal_code"]},
                             marketplace="mkt")
        live = [{"name": "multi-version", "version": "2.0.0", "enabled": True,
                 "source_label": "CLAUDE PROJECTED"}]
        rows = dc.discover_declarations(cache_root=cache_root,
                                        companions_path=companions_path, live=live)
        by_version = {r["version"]: r for r in rows}
        assert by_version["2.0.0"]["installed"] is True, by_version["2.0.0"]
        assert by_version["1.0.0"]["installed"] is False, by_version["1.0.0"]


def test_discover_declarations_installed_is_no_data_without_live():
    # NO DATA beats a guess: with no live discovery supplied, a row must
    # never imply it is (or is not) the installed version.
    with tempfile.TemporaryDirectory() as cache_root, \
         tempfile.TemporaryDirectory() as reg_dir:
        companions_path = os.path.join(reg_dir, "companions.json")
        _write_json(companions_path, {"schema": 2, "companions": [], "mentions": []})
        _build_fixture_cache(cache_root, "solo", "1.0.0",
                             {"name": "solo", "capabilities": ["minimal_code"]},
                             marketplace="mkt")
        rows = dc.discover_declarations(cache_root=cache_root,
                                        companions_path=companions_path)
        assert rows[0]["installed"] is None, rows
        assert "installed_note" in rows[0], rows[0]


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    dc.subprocess.run = _ORIG_RUN
    print(f"\n{len(tests)} passed")
