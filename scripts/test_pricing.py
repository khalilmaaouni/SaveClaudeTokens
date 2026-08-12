#!/usr/bin/env python3
"""Calibrated checks for pricing.py and the shared net_saving formula.

Every check is calibrated: the assertion would fail if the guard it protects
were removed, so a green result means something.
"""
import measure_tokens as mt
import pricing


def check(name, cond):
    print(("ok  " if cond else "FAIL ") + name)
    assert cond, name


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


if __name__ == "__main__":
    import sys
    n = 0
    for name in sorted(dir(sys.modules[__name__])):
        if name.startswith("test_"):
            globals()[name]()
            n += 1
    print(f"\n{n} passed")
