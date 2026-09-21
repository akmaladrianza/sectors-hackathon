"""Tests for the mining overlay mapper using static JSON fixtures.

Fixtures under ``tests/fixtures/mining/*.json`` (captured from the live Sectors
mining extension). Deterministic, no network/date dependency. Run:
    python -m tests.test_mining_overlay
"""

from __future__ import annotations

import json
import os

from decimal import Decimal

from mapper.mining_overlay import map_mining_overlay

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "mining")


def _load(name: str) -> dict:
    path = os.path.join(FIXTURES, name)
    assert os.path.exists(path), f"missing fixture {path}"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def test_adro_full_overlay() -> None:
    perf = _load("ADRO_performance.json")
    fin = _load("ADRO_financials.json")
    sale = _load("ADRO_sales_destination.json")

    overlay = map_mining_overlay(
        ticker="ADRO.JK",
        slug="pt-alamtri-resources-indonesia-tbk",
        performance=perf,
        financials=fin,
        sales_destination=sale,
    )

    # identity resolved from financials
    assert overlay.ticker == "ADRO.JK", overlay.ticker
    assert overlay.company_name == "PT Alamtri Resources Indonesia Tbk"
    assert overlay.slug == "pt-alamtri-resources-indonesia-tbk"

    # flags all true
    assert overlay.has_performance_data is True
    assert overlay.has_financials_data is True
    assert overlay.has_sales_destination_data is True

    # single commodity (Coal)
    assert len(overlay.commodities) == 1
    coal = overlay.commodities[0]
    assert coal.commodity_type == "Coal"
    assert coal.production_volume == Decimal("64.64")
    assert coal.total_reserves_Mt == Decimal("996.2")
    assert coal.total_resources_Mt == Decimal("5356.9")
    assert coal.measurement_year == 2024

    # aggregated + financials
    assert overlay.total_reserves_Mt == Decimal("996.2")
    assert overlay.reserve_vintage_year == 2024
    assert overlay.revenue_usd == Decimal("2079000000.0")
    assert overlay.net_profit_usd == Decimal("1556000000.0")
    assert overlay.assets_usd == Decimal("6702000000.0")

    # sales destination volume map (India 7.0, Japan 29.0, Korea 14.0, Malaysia 2.0)
    assert overlay.sales_destination_volume["India"] == Decimal("7.0")
    assert overlay.sales_destination_volume.get("China") is None  # China reports % not volume
    assert overlay.sales_destination_volume["Japan"] == Decimal("29.0")

    # defensibility flags
    assert overlay.is_self_reported is True
    print("PASS ADRO full overlay (coal: prod/reserves/financials/sales-dest)\n")


def test_mdka_performance_only() -> None:
    perf = _load("MDKA_performance.json")

    overlay = map_mining_overlay(
        ticker="MDKA.JK",
        slug="pt-merdeka-copper-gold-tbk",
        performance=perf,
        # financials + sales_destination deliberately omitted (they 404 for MDKA)
    )

    assert overlay.has_performance_data is True
    assert overlay.has_financials_data is False
    assert overlay.has_sales_destination_data is False

    # multi-commodity: Copper + Gold (Silver is a commodity_type label but only 2 rows)
    assert set(overlay.commodity_types) == {"Copper", "Gold"}, overlay.commodity_types
    assert len(overlay.commodities) == 2

    # company-level reserves repeated identically across commodities
    assert overlay.total_reserves_Mt == Decimal("430.8")
    assert overlay.total_resources_Mt == Decimal("2207.4")
    assert overlay.reserve_vintage_year == 2024

    # per-commodity production differs; copper in kton, gold in koz
    units = {c.commodity_type: c.unit for c in overlay.commodities}
    assert units["Copper"] == "kton"
    assert units["Gold"] == "koz"
    copper = next(c for c in overlay.commodities if c.commodity_type == "Copper")
    assert copper.production_volume == Decimal("13.902")

    # financials absent
    assert overlay.revenue_usd is None
    assert overlay.net_profit_usd is None
    assert overlay.sales_destination_volume == {}
    print("PASS MDKA performance-only overlay (multi-commodity, no fin/sales)\n")


def test_no_data_at_all() -> None:
    overlay = map_mining_overlay(ticker="XXX.JK")
    assert overlay.has_performance_data is False
    assert overlay.has_financials_data is False
    assert overlay.has_sales_destination_data is False
    assert overlay.commodities == []
    assert overlay.total_reserves_Mt is None
    print("PASS no-data overlay: all flags False, no crash\n")


def main() -> None:
    test_adro_full_overlay()
    test_mdka_performance_only()
    test_no_data_at_all()
    print("ALL MINING OVERLAY TESTS PASSED")


if __name__ == "__main__":
    main()
