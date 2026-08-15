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
    import token_shield as ts
    sm = {"read_total": 100_000, "write_5m_total": 10_000, "write_1h_total": 5_000,
          "input_total": 0}
    sv = ts.savings_breakdown(sm)
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
    real = (cli.mt.collect, cli.mt.summarize, cli.ts.savings_breakdown,
            cli.ts.native_note, cli.ts.prescriptions, cli.ROOT)

    def fake_collect(root, days):
        calls.append((root, days))
        return sessions

    def fake_prescriptions(sm, s):
        passed.append(s)
        return []

    with tempfile.TemporaryDirectory() as d:
        cli.mt.collect = fake_collect
        cli.mt.summarize = lambda s: {"first_request_median": 0}
        cli.ts.savings_breakdown = lambda sm: {"saved": 0}
        cli.ts.native_note = lambda sv: ""
        cli.ts.prescriptions = fake_prescriptions
        cli.ROOT = d
        try:
            rc, out, err = _capture(cli.summary)
        finally:
            (cli.mt.collect, cli.mt.summarize, cli.ts.savings_breakdown,
             cli.ts.native_note, cli.ts.prescriptions, cli.ROOT) = real

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
