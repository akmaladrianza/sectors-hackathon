"""Tests for the presentation-layer transforms (ScreenerResult -> table rows).

Pure, deterministic: build a ScreenerResult by hand (or via the screener with a
fake client) and assert the row shapes/values. No Streamlit, no network.

Run:  python -m tests.test_view
"""

from __future__ import annotations

import json
import os

from screener.screener import ScreenerResult, ScreenedMiner, Exclusion
from models.company_comp import CompanyComp
from models.mining_overlay import MiningOverlay, CommodityStat
from engine.mining_valuation import ev_to_tonne_of_reserves, ev_to_tonne_of_resources
from view import comps_rows, mining_rows, exclusion_rows, _valuation_label, _valuation_result

from decimal import Decimal


def _comp(ticker: str, name: str, **kw) -> CompanyComp:
    base = dict(
        ticker=ticker,
        company_name=name,
        sector="Financials",
        market_cap=Decimal("1000000000000"),
        total_debt=Decimal("100000000000"),
        cash_and_equivalents=Decimal("100000000000"),
        ebitda=Decimal("100000000000"),
        revenue=Decimal("500000000000"),
        eps=Decimal("100"),
        price=Decimal("1000"),
        total_assets=Decimal("900000000000"),
        total_liabilities=Decimal("600000000000"),
    )
    base.update(kw)
    return CompanyComp(**base)


def test_comps_rows_shape_and_rounding() -> None:
    comp = _comp("BBCA.JK", "Test")
    result = ScreenerResult(screenable=[comp])
    rows = comps_rows(result)

    assert len(rows) == 1
    r = rows[0]
    assert r["Ticker"] == "BBCA.JK"
    assert r["Company"] == "Test"
    assert "Period" in r and "As of" in r
    # ev_to_ebitda = EV/ebitda = (1T + 0.1T - 0.1T)/0.1T = 1T/0.1T = 10.0
    assert r["EV/EBITDA"] == 10.0
    # P/E = price/eps = 1000/100 = 10.0
    assert r["P/E"] == 10.0
    print("PASS comps_rows: correct shape + rounded multiples\n")


def test_mining_rows_include_defensibility_flags() -> None:
    comp = _comp("MDKA.JK", "Merdeka")
    overlay = MiningOverlay(
        ticker="MDKA.JK",
        company_name="Merdeka Copper Gold",
        commodities=[
            CommodityStat(commodity_type="Copper", total_reserves_Mt=Decimal("430.8"),
                          total_resources_Mt=Decimal("2207.4"), measurement_year=2024)
        ],
        has_performance_data=True,
    )
    miner = ScreenedMiner(
        comp=comp,
        overlay=overlay,
        ev_per_tonne_reserves=ev_to_tonne_of_reserves(comp, overlay),
        ev_per_tonne_resources=ev_to_tonne_of_resources(comp, overlay),
    )
    result = ScreenerResult(miners=[miner])
    rows = mining_rows(result)

    assert len(rows) == 1
    r = rows[0]
    assert r["Ticker"] == "MDKA.JK"
    assert r["Commodities"] == "Copper"
    assert r["Reserves (Mt)"] == 430.8
    assert r["Reserve vintage"] == 2024
    assert r["Self-reported"] is True
    assert r["EV/tonne (reserves)"] is not None
    print("PASS mining_rows: flags (vintage, self-reported) surfaced\n")


def test_exclusion_rows() -> None:
    result = ScreenerResult(excluded=[Exclusion("BAD", "missing market_cap")])
    rows = exclusion_rows(result)
    assert rows == [{"Ticker": "BAD", "Reason": "missing market_cap"}]
    print("PASS exclusion_rows: ticker + reason\n")


def test_mining_rows_name_fallback() -> None:
    """When the overlay lacks a company_name, mining_rows falls back to the comp."""
    comp = _comp("MDKA.JK", "Merdeka Copper Gold")
    overlay = MiningOverlay(
        ticker="MDKA.JK",
        company_name=None,  # <-- the fallback path under test
        commodities=[
            CommodityStat(commodity_type="Copper", total_reserves_Mt=Decimal("430.8"),
                          total_resources_Mt=Decimal("2207.4"), measurement_year=2024)
        ],
        has_performance_data=True,
    )
    miner = ScreenedMiner(
        comp=comp,
        overlay=overlay,
        ev_per_tonne_reserves=ev_to_tonne_of_reserves(comp, overlay),
        ev_per_tonne_resources=ev_to_tonne_of_resources(comp, overlay),
    )
    result = ScreenerResult(miners=[miner])
    rows = mining_rows(result)

    assert len(rows) == 1
    assert rows[0]["Company"] == "Merdeka Copper Gold", rows[0]["Company"]
    print("PASS mining_rows: name falls back to comp.company_name when overlay is None\n")


def test_valuation_label_thresholds() -> None:
    """The ±5% materiality dead-zone + direction mapping."""
    assert _valuation_label(0.10) == "Undervalued"       # +10%
    assert _valuation_label(0.0501) == "Undervalued"      # just above +5%
    assert _valuation_label(0.05) == "Fairly valued"      # exactly +5% boundary
    assert _valuation_label(0.0) == "Fairly valued"
    assert _valuation_label(-0.05) == "Fairly valued"     # exactly -5% boundary
    assert _valuation_label(-0.0501) == "Overvalued"      # just below -5%
    assert _valuation_label(-0.10) == "Overvalued"        # -10%
    assert _valuation_label(None) is None
    print("PASS _valuation_label thresholds (±5% dead-zone)\n")


def test_valuation_result_formats() -> None:
    """The combined display string keeps the % and direction."""
    assert _valuation_result(0.083) == "Undervalued (+8.3%)"
    assert _valuation_result(-0.051) == "Overvalued (-5.1%)"
    assert _valuation_result(0.0) == "Fairly valued (+0.0%)"
    assert _valuation_result(None) is None
    print("PASS _valuation_result formatting\n")


def test_comps_rows_include_valuation_field() -> None:
    """comps_rows() now emits a 'Valuation' label alongside the raw 'Upside'."""
    # intrinsic_upside is a computed field (IV/price - 1); build with explicit
    # intrinsic_value + price so the field is populated.
    comp = _comp(
        "SUB.JK", "Subject",
        price=Decimal("1000"), intrinsic_value=Decimal("1100"),  # upside = +10%
    )
    result = ScreenerResult(screenable=[comp])
    rows = comps_rows(result)
    r = rows[0]
    assert "Valuation" in r, r.keys()
    assert r["Valuation"] == "Undervalued (+10.0%)", r["Valuation"]
    # The numeric Upside column is preserved (no information loss).
    assert "Upside" in r
    print("PASS comps_rows includes Valuation label + keeps Upside\n")


def test_comps_rows_valuation_none_when_no_iv() -> None:
    """When intrinsic value is missing, Valuation is blank (None), never a bogus label."""
    comp = _comp("NOLV.JK", "No IV")  # no intrinsic_value
    result = ScreenerResult(screenable=[comp])
    rows = comps_rows(result)
    assert rows[0]["Valuation"] is None
    print("PASS comps_rows Valuation blank when IV absent\n")


def main() -> None:
    test_comps_rows_shape_and_rounding()
    test_mining_rows_include_defensibility_flags()
    test_mining_rows_name_fallback()
    test_exclusion_rows()
    test_valuation_label_thresholds()
    test_valuation_result_formats()
    test_comps_rows_include_valuation_field()
    test_comps_rows_valuation_none_when_no_iv()
    print("ALL VIEW TESTS PASSED")


if __name__ == "__main__":
    main()
