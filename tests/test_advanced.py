"""Tests for the proxy library + DCF engine (pure, deterministic).

Run:  python -m tests.test_advanced
"""

from __future__ import annotations

from decimal import Decimal

from engine.proxy_library import (
    default_growth,
    classify_proxy,
    IDN_GDP_GROWTH,
    BANK_GROWTH_SPREAD,
    COMMODITY_PRICE_GROWTH,
)
from engine.dcf import run_dcf, estimate_working_capital_days
from models.company_comp import CompanyComp
from models.mining_overlay import MiningOverlay, CommodityStat


def _comp(sub_sector="Telecommunication", **kw) -> CompanyComp:
    base = dict(
        ticker="TEST.JK",
        company_name="Test",
        sector="Infrastructures",
        sub_sector=sub_sector,
        revenue=Decimal("100000000000"),
    )
    base.update(kw)
    return CompanyComp(**base)


RAW_HIST = [
    {"year": 2022, "revenue": 100},
    {"year": 2023, "revenue": 110},
    {"year": 2024, "revenue": 121},  # 10% CAGR
]


def test_bank_proxy_uses_gdp_plus_spread() -> None:
    comp = _comp(sub_sector="Banks")
    p = default_growth(comp)
    assert p.available is True
    assert p.value == IDN_GDP_GROWTH + BANK_GROWTH_SPREAD
    assert classify_proxy(comp) == "bank"
    print("PASS bank proxy = GDP growth + spread\n")


def test_generic_proxy_is_historical_cagr() -> None:
    comp = _comp(sub_sector="Telecommunication")
    p = default_growth(comp, raw_hist=RAW_HIST)
    assert p.available is True
    # 121/100 over 2 years -> 10% CAGR
    assert abs(float(p.value) - 0.10) < 1e-6, p.value
    assert classify_proxy(comp) == "generic"
    print("PASS generic proxy = historical CAGR (~10%)\n")


def test_generic_proxy_no_history() -> None:
    comp = _comp(sub_sector="Telecommunication")
    p = default_growth(comp, raw_hist=[])
    assert p.available is False
    assert p.reason is not None
    print("PASS generic proxy: no history -> None with reason\n")


def test_miner_proxy_is_revenue_cagr_times_commodity_price() -> None:
    """The miner branch classifies via overlay.has_performance_data, and its growth
    is historical *revenue* CAGR x (1 + commodity-price assumption) — NOT production
    x price (we store only the latest production volume)."""
    comp = _comp(sub_sector="Basic Materials")
    overlay = MiningOverlay(
        ticker="TEST.JK",
        commodities=[CommodityStat(commodity_type="Coal", production_volume=Decimal("10"))],
        has_performance_data=True,
    )
    assert classify_proxy(comp, overlay) == "miner"

    p = default_growth(comp, overlay=overlay, raw_hist=RAW_HIST)
    assert p.available is True
    # 10% CAGR * (1 + 2%) = 12.2%
    expected = Decimal("0.10") * (Decimal(1) + COMMODITY_PRICE_GROWTH)
    assert abs(float(p.value) - float(expected)) < 1e-6, p.value
    print(f"PASS miner proxy = revenue CAGR x commodity price (~{float(p.value)*100:.1f}%)\n")


def test_miner_proxy_no_history() -> None:
    comp = _comp(sub_sector="Basic Materials")
    overlay = MiningOverlay(ticker="TEST.JK", commodities=[], has_performance_data=True)
    p = default_growth(comp, overlay=overlay, raw_hist=[])
    assert p.available is False
    assert p.reason is not None
    print("PASS miner proxy: no history -> None with reason\n")


def test_dcf_positive() -> None:
    r = run_dcf(
        revenue=Decimal("100"),
        growth_rate=Decimal("0.10"),
        cash_flow_margin=Decimal("0.20"),
        discount_rate=Decimal("0.12"),
        terminal_growth=Decimal("0.02"),
        years=5,
    )
    assert r.available is True
    assert r.intrinsic_ev is not None and r.intrinsic_ev > 0
    # Hand-check: a growing, positive-margin firm discounted at 12% must yield a
    # finite positive EV well above current revenue.
    assert r.intrinsic_ev > Decimal("100"), r.intrinsic_ev
    print(f"PASS DCF positive: intrinsic EV = {r.intrinsic_ev:.2f}\n")


def test_dcf_requires_valid_rates() -> None:
    r1 = run_dcf(Decimal("100"), Decimal("0.10"), Decimal("0.20"),
                 Decimal("0.0"), Decimal("0.02"))
    assert r1.available is False and "discount" in r1.reason

    r2 = run_dcf(Decimal("100"), Decimal("0.10"), Decimal("0.20"),
                 Decimal("0.12"), Decimal("0.15"))  # terminal > discount
    assert r2.available is False and "terminal" in r2.reason

    r3 = run_dcf(None, Decimal("0.10"), Decimal("0.20"), Decimal("0.12"), Decimal("0.02"))
    assert r3.available is False and "revenue" in r3.reason
    print("PASS DCF validation: bad rates / missing revenue -> None with reason\n")


def test_working_capital_days_estimator() -> None:
    """Residual AR/AP + direct inventory days from the balance-sheet block."""
    # revenue 365, cost_of_revenue 365 -> every day maps 1.0 of balance.
    rev = Decimal("365")
    cor = Decimal("365")
    # Residual current assets: 100 - cash 10 - inv 20 - prepaid 5 = 65 -> AR days 65.
    # Inventory 20 -> inventory days 20.
    # Residual current liabilities: 50 - short_term_debt 10 = 40 -> AP days 40.
    ar, inv, ap = estimate_working_capital_days(
        revenue=rev,
        cost_of_revenue=cor,
        inventories=Decimal("20"),
        current_assets=Decimal("100"),
        current_liabilities=Decimal("50"),
        cash_and_equivalents=Decimal("10"),
        prepaid_assets=Decimal("5"),
        short_term_debt=Decimal("10"),
    )
    assert ar == 65.0, ar
    assert inv == 20.0, inv
    assert ap == 40.0, ap

    # Degrade: none of the fields -> all None.
    ar2, inv2, ap2 = estimate_working_capital_days()
    assert ar2 is None and inv2 is None and ap2 is None

    # Negative residual (cash > current assets) -> None, not a bogus negative.
    ar3, inv3, ap3 = estimate_working_capital_days(
        revenue=rev,
        current_assets=Decimal("5"),
        cash_and_equivalents=Decimal("100"),
    )
    assert ar3 is None and inv3 is None
    print("PASS working-capital days estimator (residual AR/AP + direct inventory)\n")


def main() -> None:
    test_bank_proxy_uses_gdp_plus_spread()
    test_generic_proxy_is_historical_cagr()
    test_generic_proxy_no_history()
    test_miner_proxy_is_revenue_cagr_times_commodity_price()
    test_miner_proxy_no_history()
    test_dcf_positive()
    test_dcf_requires_valid_rates()
    test_working_capital_days_estimator()
    print("ALL ADVANCED-MODE TESTS PASSED")


if __name__ == "__main__":
    main()
