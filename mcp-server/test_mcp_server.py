#!/usr/bin/env python3
"""Self-check for the Token Shield MCP server. No framework, no fixtures.
Mirrors scripts/test_profile.py's and scripts/test_experiment.py's own
calibrated style, including test_experiment.py's own _run_cli pattern
(subprocess with HOME set in the env before Python starts) for anything
that touches a module-level path constant computed from HOME at import time.

    cd mcp-server && python3 test_mcp_server.py
"""

import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.normpath(os.path.join(HERE, "..", "scripts"))
SRC = os.path.join(HERE, "src")
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, SRC)

from token_shield_mcp.datasource import TranscriptDataSource, by_source  # noqa: E402
from token_shield_mcp.tools.get_advice import get_advice  # noqa: E402
from token_shield_mcp.tools.get_detailed_report import get_detailed_report  # noqa: E402
from token_shield_mcp.tools.get_monthly_report import get_monthly_report  # noqa: E402
from token_shield_mcp.tools.get_profile import get_profile  # noqa: E402
from token_shield_mcp.tools.get_summary import get_summary  # noqa: E402
from token_shield_mcp.tools.list_strategies import list_strategies  # noqa: E402


def check(name, cond):
    print(("ok  " if cond else "FAIL ") + name)
    assert cond, name


def _rec(ts, model="claude-x", inp=1000, w5=0, w1=0, read=5000, out=200, sub=False):
    return json.dumps({"isSidechain": sub, "timestamp": ts, "message": {
        "model": model, "usage": {"input_tokens": inp, "cache_read_input_tokens": read,
        "output_tokens": out, "cache_creation": {"ephemeral_5m_input_tokens": w5,
                                                  "ephemeral_1h_input_tokens": w1}}}})


def _seed_transcripts(root, n_sessions=5, calls=12):
    os.makedirs(root, exist_ok=True)
    for i in range(n_sessions):
        lines = []
        for c in range(calls):
            ts = time.strftime("%Y-%m-%dT%H:%M:%S+00:00",
                               time.gmtime(time.time() - (n_sessions - i) * 3600 + c * 60))
            lines.append(_rec(ts))
        with open(os.path.join(root, f"s{i}.jsonl"), "w") as f:
            f.write("\n".join(lines) + "\n")


# --- read-only tools, called directly against a seeded sandbox root ---

def test_get_profile_against_seeded_transcripts():
    with tempfile.TemporaryDirectory() as d:
        root = os.path.join(d, "projects")
        _seed_transcripts(root)
        result = get_profile(root=root, window_days=30)
        check("get_profile returns the five metric groups",
              all(k in result for k in ("usage", "behavior", "instruction",
                                        "environment", "skipped")))


def test_get_profile_no_data_on_empty_root():
    with tempfile.TemporaryDirectory() as d:
        result = get_profile(root=os.path.join(d, "empty"), window_days=30)
        check("get_profile still returns a dict on an empty root", isinstance(result, dict))
        check("no sessions counted is reported as NO DATA, not a fabricated zero",
              result["behavior"]["sessions"]["label"] == "NO DATA")


def test_get_summary_seeded_and_empty():
    with tempfile.TemporaryDirectory() as d:
        root = os.path.join(d, "projects")
        _seed_transcripts(root)
        result = get_summary(root=root)
        check("get_summary carries the four top-level keys",
              all(k in result for k in
                  ("verified", "native_saved", "opportunity_estimated", "top_issue")))
        check("native_saved is a real number on seeded data",
              isinstance(result["native_saved"], (int, float)))

    with tempfile.TemporaryDirectory() as d:
        result = get_summary(root=os.path.join(d, "empty"))
        check("get_summary on an empty root reports NO DATA, not a crash",
              result.get("label") == "NO DATA")


def test_get_advice_seeded():
    with tempfile.TemporaryDirectory() as d:
        root = os.path.join(d, "projects")
        _seed_transcripts(root)
        result = get_advice(root=root, window_days=30)
        check("get_advice returns the advisor's own shape",
              all(k in result for k in
                  ("best", "alternatives", "companion", "queue", "do_nothing",
                   "advisor_cost_tokens", "insufficient")))
        check("advisor cost is always 0 (deterministic, no model calls)",
              result["advisor_cost_tokens"] == 0)


def test_get_monthly_report_defaults_to_previous_month():
    with tempfile.TemporaryDirectory() as d:
        result = get_monthly_report(root=os.path.join(d, "empty"))
        check("get_monthly_report returns markdown", isinstance(result, str))
        check("the report names itself", "Token Shield monthly report" in result)


def test_list_strategies_sources_are_citable():
    result = list_strategies()
    check("list_strategies returns every strategy", len(result) > 0)
    check("every entry carries a non-empty source",
          all(s.get("source") for s in result))
    claim_coded = [s for s in result if s["source"].startswith("docs/CLAIMS.md")]
    check("at least one strategy's source was rewritten to a citable "
          "docs/CLAIMS.md pointer by format_source",
          len(claim_coded) > 0)


def test_get_detailed_report_schema_v1():
    with tempfile.TemporaryDirectory() as d:
        root = os.path.join(d, "projects")
        _seed_transcripts(root)
        result = get_detailed_report(window_days=30, root=root)
        check("schema v1 top level carries every documented key",
              all(k in result for k in
                  ("report_schema", "generated_at", "window_days", "source_label",
                   "startup_floor", "subagents", "cache", "rhythm", "habits",
                   "daily_series")))
        check("report_schema is 1", result["report_schema"] == 1)
        check("daily_series never exceeds window_days rows",
              len(result["daily_series"]) <= 30)


# --- the two write tools, round-tripped under a sandbox HOME. Run as a
# subprocess with HOME set in the env before Python starts, exactly like
# scripts/test_experiment.py's own _run_cli helper: TREATMENTS_PATH, STORE,
# EXP_DIR, and LEDGER are all computed from HOME at module import time, and
# a subprocess is the simplest way to get that computed correctly without a
# fragile reload dance inside one process. ---

def _run(home, code):
    env = dict(os.environ)
    env["HOME"] = home
    env["PYTHONPATH"] = os.pathsep.join([SCRIPTS, SRC])
    return subprocess.run([sys.executable, "-c", code], env=env,
                          capture_output=True, text=True)


def test_record_decision_round_trips_under_sandbox_home():
    with tempfile.TemporaryDirectory() as home:
        code = (
            "from token_shield_mcp.tools.record_decision import record_decision\n"
            "rec = record_decision('wave1-test-strategy', 'suppressed', days=90, "
            "note='mcp test')\n"
            "print(rec['decision'])\n"
        )
        r = _run(home, code)
        check("record_decision subprocess does not raise", "Traceback" not in r.stderr)
        check("record_decision wrote 'suppressed'", "suppressed" in r.stdout)
        path = os.path.join(home, ".token-shield", "treatments.json")
        check("treatments.json was written under the sandbox HOME", os.path.exists(path))
        with open(path) as f:
            data = json.load(f)
        check("the file on disk matches what record_decision returned (round trip)",
              data["wave1-test-strategy"]["decision"] == "suppressed")


def test_record_decision_unknown_decision_raises():
    # Per design decision 1 and errors.py: an unknown decision string is
    # never caught inside the tool. Calibrated: catching it here (turning
    # this into a captured {"error": ...} dict) would make this test pass
    # for the wrong reason; asserting the raw traceback is what proves
    # nothing swallowed it.
    with tempfile.TemporaryDirectory() as home:
        code = (
            "from token_shield_mcp.tools.record_decision import record_decision\n"
            "record_decision('x', 'not-a-real-decision')\n"
        )
        r = _run(home, code)
        check("an unknown decision string is not swallowed, it raises",
              r.returncode != 0 and "ValueError" in r.stderr)


def test_experiment_start_round_trips_a_baseline_file():
    with tempfile.TemporaryDirectory() as home:
        projects = os.path.join(home, ".claude", "projects", "p")
        _seed_transcripts(projects, n_sessions=5)
        start_code = (
            "from token_shield_mcp.tools.experiment_start import experiment_start\n"
            f"r = experiment_start('mcp-wave1-round-trip', root={projects!r}, days=30)\n"
            "print(r['exit_code'])\n"
        )
        r = _run(home, start_code)
        check("experiment_start subprocess does not raise", "Traceback" not in r.stderr)
        check("experiment_start exits 0", r.stdout.splitlines()[0] == "0")
        snap = os.path.join(home, ".claude", "token-shield", "experiments",
                            "mcp-wave1-round-trip.json")
        check("experiment_start pinned a baseline file", os.path.exists(snap))
        with open(snap) as f:
            baseline = json.load(f)
        check("the file on disk matches what experiment_start wrote (round trip)",
              baseline["label"] == "mcp-wave1-round-trip" and baseline["window_days"] == 30)


def test_experiment_end_round_trips_a_ledger_record():
    # experiment_start immediately followed by experiment_end in one test
    # would have both cohorts cover the same [now-30d, now) window and trip
    # the overlap guard (REFUSED, nothing written) -- that guard is real and
    # correct, not a bug to work around by shrinking the window. Instead this
    # seeds a baseline exactly like a real one, just already a safe distance
    # in the past (cohort ended 40 days ago), so the fresh after-cohort
    # (last 30 days) starts after it ends, same as a real experiment that
    # was started weeks ago.
    with tempfile.TemporaryDirectory() as home:
        projects = os.path.join(home, ".claude", "projects", "p")
        _seed_transcripts(projects, n_sessions=5)
        exp_dir = os.path.join(home, ".claude", "token-shield", "experiments")
        os.makedirs(exp_dir, exist_ok=True)
        now = time.time()
        baseline = {
            "label": "mcp-wave1-end-round-trip", "started": "2026-07-01T00:00:00",
            "window_days": 30, "schema": 2,
            "cohort_start_ts": now - 70 * 86400, "cohort_end_ts": now - 40 * 86400,
            "fingerprint_start": "seeded-for-test", "treats": None,
            "fingerprint_excluded": [],
            "summary": {"first_request_median": 80000, "normalized_input_total": 1_000_000,
                        "parent_sessions": 10},
        }
        with open(os.path.join(exp_dir, "mcp-wave1-end-round-trip.json"), "w") as f:
            json.dump(baseline, f)

        end_code = (
            "from token_shield_mcp.tools.experiment_end import experiment_end\n"
            f"r = experiment_end('mcp-wave1-end-round-trip', root={projects!r}, days=30)\n"
            "print(r['exit_code'])\n"
        )
        r = _run(home, end_code)
        check("experiment_end subprocess does not raise", "Traceback" not in r.stderr)
        ledger = os.path.join(home, ".claude", "token-shield", "savings.jsonl")
        check("experiment_end appended a ledger record", os.path.exists(ledger))
        with open(ledger) as f:
            records = [json.loads(line) for line in f if line.strip()]
        check("the ledger's last record matches the label experiment_end wrote (round trip)",
              records[-1]["label"] == "mcp-wave1-end-round-trip")


def test_experiment_end_no_baseline_is_no_data_verbatim():
    with tempfile.TemporaryDirectory() as home:
        code = (
            "from token_shield_mcp.tools.experiment_end import experiment_end\n"
            "r = experiment_end('no-such-label', root='/nonexistent-path-for-check', "
            "days=30)\n"
            "print(r['exit_code'])\n"
            "print(r['text'])\n"
        )
        r = _run(home, code)
        out_lines = r.stdout.splitlines()
        check("experiment_end refusal exits 2", out_lines[0] == "2")
        check("the refusal text carries NO DATA verbatim, not a paraphrase",
              "NO DATA" in r.stdout)


# --- the no-blend rule. Wave 1 ships one real DataSource implementation
# (TranscriptDataSource), so this proves the contract itself: by_source()
# keys results by source_label and never flattens two sources into one
# number, using two fake sources to exercise the multi-source path wave 1
# does not otherwise reach. See datasource.py's own docstring. ---

class _FakeSourceA:
    source_label = "fake-source-a"

    def list_usage_records(self, root=None, days=30):
        return [{"tokens": 100}]


class _FakeSourceB:
    source_label = "fake-source-b"

    def list_usage_records(self, root=None, days=30):
        return [{"tokens": 900}]


def test_no_blend_rule_keeps_sources_separate():
    combined = by_source([_FakeSourceA(), _FakeSourceB()])
    check("both fake sources are present, keyed by their own label",
          set(combined.keys()) == {"fake-source-a", "fake-source-b"})
    check("source A's records were not merged into source B's",
          combined["fake-source-a"] == [{"tokens": 100}])
    check("source B's records were not merged into source A's",
          combined["fake-source-b"] == [{"tokens": 900}])
    check("there is no flattened cross-source total anywhere in the result",
          "total" not in combined and sum(len(v) for v in combined.values()) == 2)
    ds = TranscriptDataSource()
    check("the real DataSource implementation carries its own distinct label",
          ds.source_label not in (_FakeSourceA.source_label, _FakeSourceB.source_label))


if __name__ == "__main__":
    n = 0
    for name in sorted(dir(sys.modules[__name__])):
        if name.startswith("test_"):
            globals()[name]()
            n += 1
    print(f"\n{n} passed")
