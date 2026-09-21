"""Tests for the EV/tonne-of-reserves valuation engine.

Pure unit tests: construct a ``CompanyComp`` + ``MiningOverlay`` in memory (no
network, no fixtures) and assert the join produces the correct ratio and the
correct ``None``+reason degradation.

Run:  python -m tests.test_ev_tonne
"""

from __future__ import annotations

from decimal import Decimal

from engine.mining_valuation import (
    ev_to_tonne_of_reserves,
    ev_to_tonne_of_resources,
)
from models.company_comp import CompanyComp
from models.mining_overlay import CommodityStat, MiningOverlay


def _comp(**overrides) -> CompanyComp:
    kwargs = dict(
        ticker="TEST.JK",
        company_name="Test Miner",
        sector="Basic Materials",
        market_cap=Decimal("1000000000000"),  # 1T
        total_debt=Decimal("200000000000"),   # 0.2T
        cash_and_equivalents=Decimal("100000000000"),  # 0.1T
        ebitda=Decimal("100000000000"),
        revenue=Decimal("500000000000"),
    )
    kwargs.update(overrides)
    return CompanyComp(**kwargs)


def _overlay(reserves: Decimal, resources: Decimal) -> MiningOverlay:
    return MiningOverlay(
        ticker="TEST.JK",
        slug="test",
        commodities=[
            CommodityStat(
                commodity_type="Coal",
                production_volume=Decimal("10"),
                total_reserves_Mt=reserves,
                total_resources_Mt=resources,
                measurement_year=2024,
            )
        ],
        has_performance_data=True,
    )


def test_ev_per_tonne_positive() -> None:
    # EV = 1T + 0.2T - 0.1T = 1.1T
    comp = _comp()
    overlay = _overlay(reserves=Decimal("1000"), resources=Decimal("5000"))

    r = ev_to_tonne_of_reserves(comp, overlay)
    assert r.available is True
    # 1000 Mt = 1_000_000_000 tonnes; EV 1.1e12 / 1e9 tonnes = 1100 per tonne
    assert r.value == Decimal("1100"), r.value
    assert r.reason is None

    res = ev_to_tonne_of_resources(comp, overlay)
    # 5000 Mt = 5_000_000_000 tonnes; 1.1e12 / 5e9 = 220 per tonne
    assert res.value == Decimal("220"), res.value
    print("PASS EV/tonne positive (reserves & resources, Mt->tonne converted)\n")


def test_real_world_magnitude_sanity() -> None:
    """Regression guard: EV/tonne must land in a realistic per-tonne range.

    This specific bug (dividing EV by megatonnes instead of tonnes) inflated every
    result by ~1,000,000x. A coal miner's EV-per-tonne-of-reserves should be a few
    USD (single/low-double digits), NOT millions. Asserting a magnitude band here
    means a unit-conversion regression can't silently pass.
    """
    # ADRO-like: EV ~72.3T IDR, reserves 996.2 Mt. At ~15,700 IDR/USD that's ~4.6B
    # USD over ~996M tonnes ≈ ~$4.6/tonne ≈ ~72k IDR/tonne.
    comp = _comp(
        market_cap=Decimal("72303433948860"),
        total_debt=Decimal("0"),
        cash_and_equivalents=Decimal("0"),
    )
    overlay = _overlay(reserves=Decimal("996.2"), resources=Decimal("5356.9"))
    r = ev_to_tonne_of_reserves(comp, overlay)
    assert r.available is True
    # Expect ~72,579 IDR/tonne. Assert the order of magnitude (1e4 - 1e6 IDR/t):
    assert Decimal("1000") < r.value < Decimal("1000000"), r.value
    # Tighter: within 2x of the known-correct ~72.6k IDR/t
    assert Decimal("30000") < r.value < Decimal("150000"), r.value
    print("PASS real-world magnitude sanity (ADRO-like per-tonne scale)\n")


def test_ev_per_tonne_missing_ev() -> None:
    comp = _comp(market_cap=None)  # no market cap -> EV is None
    overlay = _overlay(reserves=Decimal("1000"), resources=Decimal("5000"))

    r = ev_to_tonne_of_reserves(comp, overlay)
    assert r.available is False
    assert r.value is None
    assert "enterprise_value" in r.reason
    print("PASS EV/tonne missing EV -> None with reason\n")


def test_ev_per_tonne_missing_tonnage() -> None:
    comp = _comp()
    overlay = MiningOverlay(ticker="TEST.JK", commodities=[], has_performance_data=False)

    r = ev_to_tonne_of_reserves(comp, overlay)
    assert r.available is False
    assert r.value is None
    assert "tonnage" in r.reason
    print("PASS EV/tonne missing tonnage -> None with reason\n")


def main() -> None:
    test_ev_per_tonne_positive()
    test_real_world_magnitude_sanity()
    test_ev_per_tonne_missing_ev()
    test_ev_per_tonne_missing_tonnage()
    print("ALL EV/TONNE TESTS PASSED")


if __name__ == "__main__":
    main()
