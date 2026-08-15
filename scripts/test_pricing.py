#!/usr/bin/env python3
"""Calibrated checks for pricing.py, the shared net_saving formula, and the
command line surface in cli.py that presents them.

Every check is calibrated: the assertion would fail if the guard it protects
were removed, so a green result means something.
"""
import measure_tokens as mt
import pricing


def check(name, cond):
    print(("ok  " if cond else "FAIL ") + name)
    assert cond, name


def _capture(fn, *args):
    """Run fn and return (returncode, stdout, stderr).

    stdout and stderr are captured separately on purpose: a progress line that
    leaks into stdout corrupts anything piping the command's output.
    """
    import contextlib
    import io
    so, se = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(so), contextlib.redirect_stderr(se):
        rc = fn(*args)
    return rc, so.getvalue(), se.getvalue()


PRICING = {
    "snapshot": "2026-08-12",
    "stale_after_days": 120,
    "models": {"claude-opus-5": {"input": 5.0}, "claude-haiku-4-5": {"input": 1.0}},
}


def test_known_model_priced_at_its_own_rate():
    res = pricing.price_saving({"claude-opus-5": 1_000_000}, PRICING, "2026-08-13")
    # 1M units at $5/M input = $5.00 exactly.
    check("known model priced at its own rate", abs(res["usd"] - 5.0) < 1e-9)
    check("known model contributes priced_units", res["unpriced_units"] == 0)


def test_unknown_model_is_unpriced_never_substituted():
    res = pricing.price_saving({"<synthetic>": 1_000_000}, PRICING, "2026-08-13")
    # Calibration: a KNOWN model with the same units WOULD be priced, so a zero
    # here proves the unpriced path fired rather than a price of coincidentally 0.
    known = pricing.price_saving({"claude-opus-5": 1_000_000}, PRICING, "2026-08-13")
    check("unknown model contributes $0", res["usd"] == 0.0)
    check("unknown model's units land in the unpriced bucket", res["unpriced_units"] == 1_000_000)
    check("...and are not silently priced at another model's rate", known["usd"] > 0)


def test_mixed_prices_per_model_not_blended():
    res = pricing.price_saving({"claude-opus-5": 1_000_000, "claude-haiku-4-5": 1_000_000},
                               PRICING, "2026-08-13")
    # 1M at $5 + 1M at $1 = $6, which a single blended rate could never produce
    # from these two rows unless it used each row's own rate.
    check("mixed models priced per model, not blended", abs(res["usd"] - 6.0) < 1e-9)


def test_stale_snapshot_is_no_price_data_but_keeps_the_saving():
    res = pricing.price_saving({"claude-opus-5": 2_000_000}, PRICING, "2027-01-01")
    check("stale snapshot degrades to NO PRICE DATA", res["status"] == "NO_PRICE_DATA")
    check("stale snapshot returns usd None, never a number", res["usd"] is None)
    check("stale snapshot still reports the measured token saving",
          res["saved_units"] == 2_000_000)


def test_days_between():
    check("days_between counts whole days forward",
          pricing.days_between("2026-08-12", "2026-08-13") == 1)
    check("days_between is signed", pricing.days_between("2026-08-13", "2026-08-12") == -1)


def test_net_saving_is_the_canonical_formula():
    # 100 reads, 10 write_5m, 5 write_1h.
    # gross = 0.9*100 = 90; premium = 0.25*10 + 1.0*5 = 7.5; net = 82.5
    check("net_saving matches the hand computation",
          abs(mt.net_saving(100, 10, 5) - 82.5) < 1e-9)


def test_dashboard_and_meter_agree_on_the_formula():
    # The dashboard's savings_breakdown must equal net_saving on the same
    # aggregate, or two views would quote different savings.
    import metrics as met
    sm = {"read_total": 100_000, "write_5m_total": 10_000, "write_1h_total": 5_000,
          "input_total": 0}
    sv = met.savings_breakdown(sm)
    check("dashboard saving == canonical net_saving on the aggregate",
          abs(sv["saved"] - mt.net_saving(100_000, 10_000, 5_000)) < 1e-6)


def test_prices_leads_with_the_disclaimer_and_prints_no_grand_total():
    """The prices screen is the easiest number in the product to quote out of
    context: the saving is Anthropic's own caching doing its job, and nobody's
    bill moved. So the caveat leads, in words a non-technical reader takes
    correctly, and the grand total (the figure that travels alone once the
    caveat is stripped) is not printed at all. The per-model rows stay: those
    are genuinely useful when choosing a model.
    """
    import time
    import cli
    today = time.strftime("%Y-%m-%d")
    fresh = dict(PRICING, snapshot=today)
    fake = {"claude-opus-5": 24_000_000_000, "claude-haiku-4-5": 1_000_000_000}
    real_load, real_by_model = cli.pr.load_pricing, cli.pr.saving_by_model
    cli.pr.load_pricing = lambda *a, **k: fresh
    cli.pr.saving_by_model = lambda root, days: fake
    try:
        rc, out, _err = _capture(cli.prices)
    finally:
        cli.pr.load_pricing, cli.pr.saving_by_model = real_load, real_by_model

    low = out.lower()
    check("prices exits 0", rc == 0)
    check("the first line says this is not money you saved",
          "not money you saved" in out.strip().splitlines()[0].lower())
    check("...and carries no figure of its own",
          "$" not in out.strip().splitlines()[0])
    check("the disclaimer comes before any dollar figure",
          low.index("not money you saved") < out.index("$"))
    # 24B units at $5/M is $120,000.00; 1B at $1/M is $1,000.00. Each row is
    # useful on its own; only their sum is the six-figure headline.
    check("the per-model breakdown is kept",
          "$120,000.00" in out and "$1,000.00" in out)
    check("the grand total is gone", "$121,000.00" not in out)
    check("the existing labels are kept",
          "API-equivalent" in out and f"snapshot {today}" in out)


def test_version_is_reported_and_matches_the_plugin_manifest():
    """A tool an administrator deploys to a thousand machines has to be able
    to answer which build is on any of them. `--help` existed and `--version`
    did not, so the only way to identify an installed copy was to read the
    marketplace manifest by hand. The number comes FROM the manifest rather
    than a second copy in the source, so the two cannot drift apart.
    """
    import json
    import os as _os
    import cli
    rc, out, _err = _capture(cli.main, ["--version"])
    check("--version exits 0", rc == 0)
    manifest = _os.path.join(_os.path.dirname(_os.path.dirname(
        _os.path.abspath(cli.__file__))), ".claude-plugin", "plugin.json")
    with open(manifest, encoding="utf-8") as f:
        version = json.load(f)["version"]
    check("--version prints the manifest's version", version in out)
    check("...and names the tool it belongs to", "token-shield" in out.lower())


def test_uninstall_refuses_rather_than_hangs_when_nothing_can_answer_it():
    """The enterprise removal path. uninstall() called sys.stdin.readline()
    with no check that anything was attached to stdin, so under an MDM run, a
    CI job, or any `< /dev/null` invocation it either blocked forever or read
    an empty line. Blocking forever is the bad one: a removal that hangs on a
    thousand machines is an incident, not a prompt.

    Refuse by default (nothing is deleted, and the message names the flag),
    and delete only when --yes was passed deliberately.
    """
    import io
    import os as _os
    import tempfile
    import cli
    real_stdin = sys.stdin
    real_expand = _os.path.expanduser
    with tempfile.TemporaryDirectory() as d:
        # Redirect BOTH paths uninstall() walks into the temp dir, so this
        # test can never reach the real ~/.token-shield on this machine.
        home = _os.path.join(d, "home")
        _os.makedirs(_os.path.join(home, ".token-shield"))
        with open(_os.path.join(home, ".token-shield", "ledger.jsonl"), "w") as f:
            f.write("{}\n")
        _os.path.expanduser = lambda p: p.replace("~", home, 1) if p.startswith("~") else p
        try:
            # A pipe that is not a terminal, which is what MDM and CI give it.
            sys.stdin = io.StringIO("")
            rc, out, _err = _capture(cli.uninstall, [])
            check("a non-interactive uninstall refuses instead of deleting", rc == 2)
            check("...and names the flag that would have worked", "--yes" in out)
            check("...and the data is still there",
                  _os.path.isdir(_os.path.join(home, ".token-shield")))

            rc, out, _err = _capture(cli.uninstall, ["--yes"])
            check("--yes removes without asking", rc == 0)
            check("...and the data is gone",
                  not _os.path.isdir(_os.path.join(home, ".token-shield")))
        finally:
            sys.stdin = real_stdin
            _os.path.expanduser = real_expand


def test_pricings_own_main_leads_with_the_caveat_and_prints_no_grand_total():
    """The same screen, reached by the other door.

    `cli prices` was fixed to lead with the disclaimer and drop the summed
    six-figure headline, but pricing.py's own main() is a second entry point
    onto the same numbers and kept the old shape: a "priced total" line at
    $121,000.00 with its "not money anyone saved" note printed five lines
    BELOW it. A reader who runs the module directly met the number before
    the caveat, which is the exact failure the cli fix was for. Two doors
    onto one figure have to say the same thing.
    """
    import tempfile
    import time
    today = time.strftime("%Y-%m-%d")
    fresh = dict(PRICING, snapshot=today)
    fake = {"claude-opus-5": 24_000_000_000, "claude-haiku-4-5": 1_000_000_000}
    real_load, real_by_model = pricing.load_pricing, pricing.saving_by_model
    pricing.load_pricing = lambda *a, **k: fresh
    pricing.saving_by_model = lambda root, days: fake
    argv = sys.argv
    try:
        with tempfile.TemporaryDirectory() as d:
            sys.argv = ["pricing.py", "--root", d]
            rc, out, _err = _capture(pricing.main)
    finally:
        pricing.load_pricing, pricing.saving_by_model = real_load, real_by_model
        sys.argv = argv

    low = out.lower()
    check("pricing.main exits 0", rc == 0)
    check("the first line says this is not money you saved",
          "not money you saved" in out.strip().splitlines()[0].lower())
    check("...and carries no figure of its own",
          "$" not in out.strip().splitlines()[0])
    check("the disclaimer comes before any dollar figure",
          low.index("not money you saved") < out.index("$"))
    # Same fixture as the cli test above, so the two doors are compared on
    # identical numbers: 24B at $5/M is $120,000.00, 1B at $1/M is $1,000.00.
    check("the per-model breakdown is kept",
          "$120,000.00" in out and "$1,000.00" in out)
    check("the grand total is gone", "$121,000.00" not in out)
    check("the pricing snapshot is still named", f"snapshot   {today}" in out)


def test_summary_scans_the_transcripts_once_and_says_so_on_stderr():
    """summary is what the trial screen sends a stranger to run next. It used
    to collect every transcript on disk twice, in silence, so a first run sat
    blank for minutes. One scan, and one line naming it, on stderr so a pipe
    stays clean.
    """
    import tempfile
    import cli
    calls = []
    passed = []
    sessions = ["<the one collected batch>"]
    real = (cli.mt.collect, cli.mt.summarize, cli.met.savings_breakdown,
            cli.ts.native_note, cli.met.prescriptions, cli.ROOT)

    def fake_collect(root, days):
        calls.append((root, days))
        return sessions

    def fake_prescriptions(sm, s):
        passed.append(s)
        return []

    with tempfile.TemporaryDirectory() as d:
        cli.mt.collect = fake_collect
        cli.mt.summarize = lambda s: {"first_request_median": 0}
        cli.met.savings_breakdown = lambda sm: {"saved": 0}
        cli.ts.native_note = lambda sv: ""
        cli.met.prescriptions = fake_prescriptions
        cli.ROOT = d
        try:
            rc, out, err = _capture(cli.summary)
        finally:
            (cli.mt.collect, cli.mt.summarize, cli.met.savings_breakdown,
             cli.ts.native_note, cli.met.prescriptions, cli.ROOT) = real

    check("summary exits 0", rc == 0)
    check("the transcripts are collected once, not twice", len(calls) == 1)
    check("the collected batch is handed to the prescriptions, not re-read",
          len(passed) == 1 and passed[0] is sessions)
    check("a progress line reaches stderr before the scan",
          "transcript" in err.lower())
    check("...and never contaminates stdout", "transcript" not in out.lower())


def test_help_flag_exits_zero_and_gives_a_beginner_an_entry_point():
    import cli
    for flag in ("-h", "--help"):
        rc, out, _err = _capture(cli.main, [flag])
        check(f"'{flag}' exits 0, because asking for help is not an error",
              rc == 0)
        check(f"'{flag}' opens with a start-here group before the advanced one",
              "START HERE" in out and "ADVANCED" in out
              and out.index("START HERE") < out.index("ADVANCED"))
        check(f"'{flag}' still lists every subcommand",
              all(c in out for c in ("summary", "dashboard", "experiment",
                                     "prices", "optimize", "prune", "trim",
                                     "profile", "advise", "report", "doctor",
                                     "uninstall")))


def test_experiment_report_routes_to_the_ledger_report():
    """commands/optimize.md tells the user to run `cli.py experiment report`.
    It has to reach experiment.py's own report instead of a usage error."""
    import cli
    seen = []
    real = cli.ex.cmd_report
    cli.ex.cmd_report = lambda: (seen.append(True), 0)[1]
    try:
        rc, out, _err = _capture(cli.main, ["experiment", "report"])
    finally:
        cli.ex.cmd_report = real
    check("experiment report reaches experiment.py's own report", seen == [True])
    check("...and returns its exit code, not the usage error", rc == 0)
    check("...and prints no usage line", "usage:" not in out)

    rc2, out2, _err2 = _capture(cli.main, ["experiment", "wat"])
    check("a wrong experiment action still fails", rc2 == 2)
    check("...and its usage line names report as a real alternative",
          "report" in out2)


if __name__ == "__main__":
    import sys
    n = 0
    for name in sorted(dir(sys.modules[__name__])):
        if name.startswith("test_"):
            globals()[name]()
            n += 1
    print(f"\n{n} passed")
