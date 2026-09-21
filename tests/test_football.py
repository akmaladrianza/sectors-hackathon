"""Tests for the football-field engine + working-capital-days helpers (pure).

Run:  python -m tests.test_football
"""

from __future__ import annotations

from decimal import Decimal

from engine.football_field import build_football_field, peer_price_ranges
from engine.dcf import working_capital_days_to_margin, nwc_change_margin_from_days
from models.company_comp import CompanyComp


def _subject() -> CompanyComp:
    return CompanyComp(
        ticker="BBCA.JK",
        company_name="PT Bank Central Asia Tbk.",
        sector="Financials",
        sub_sector="Banks",
        revenue=Decimal("100000000000000"),
        ebitda=Decimal("30000000000000"),
        eps=Decimal("400"),
        total_equity=Decimal("280000000000000"),
        shares_outstanding=Decimal("120000000000"),
        price=Decimal("6500"),
        market_cap=Decimal("780000000000000"),
        total_debt=Decimal("2000000000000"),
        cash_and_equivalents=Decimal("78000000000000"),
        net_income=Decimal("50000000000000"),
        intrinsic_value=Decimal("7000"),
    )


def test_peer_price_ranges_invert_pe_multiples() -> None:
    subject = _subject()
    peers = [
        {"symbol": "BBRI", "pe": 10, "pb": 2, "enterprise_to_ebitda": None,
         "enterprise_to_revenue": None},
        {"symbol": "BMRI", "pe": 12, "pb": 2.5, "enterprise_to_ebitda": None,
         "enterprise_to_revenue": None},
        {"symbol": "BBNI", "pe": 8, "pb": 1.5, "enterprise_to_ebitda": None,
         "enterprise_to_revenue": None},
    ]
    rows = peer_price_ranges(peers, subject)
    by_method = {r.method: r for r in rows}

    pe_row = by_method["P/E (peers)"]
    # peer P/E in [8, 12]; subject EPS 400 -> price in [3200, 4800]
    assert pe_row.low == 3200.0, pe_row.low
    assert pe_row.high == 4800.0, pe_row.high

    pb_row = by_method["P/B (peers)"]
    bvps = 280000000000000 / 120000000000  # ~2333.33
    assert abs(pb_row.low - (1.5 * bvps)) < 0.01
    assert abs(pb_row.high - (2.5 * bvps)) < 0.01
    print("PASS peer P/E + P/B price-range inversion\n")


def test_football_field_adds_dcf_and_iv() -> None:
    subject = _subject()
    peers = [{"symbol": "BBRI", "pe": 10, "pb": 2}]
    rows, current, iv = build_football_field(
        subject, peers, dcf_price=Decimal("5200")
    )
    methods = [r.method for r in rows]
    assert "DCF (FCFF)" in methods
    assert "Sectors IV" in methods
    assert current == 6500.0
    assert iv == 7000.0
    dcf_row = next(r for r in rows if r.method == "DCF (FCFF)")
    assert dcf_row.low == 5200.0 and dcf_row.high == 5200.0
    print("PASS football field: DCF + Sectors IV single-point rows\n")


def test_working_capital_days() -> None:
    loading = working_capital_days_to_margin(Decimal("30"), Decimal("30"), Decimal("30"))
    assert round(float(loading), 6) == round(30 / 365, 6)
    delta = nwc_change_margin_from_days(
        Decimal("30"), Decimal("30"), Decimal("30"), Decimal("0.10")
    )
    # loading * g/(1+g)
    expected = Decimal(str(30/365)) * Decimal("0.10") / Decimal("1.10")
    assert abs(float(delta) - float(expected)) < 1e-9
    # zero growth -> zero delta
    assert nwc_change_margin_from_days(
        Decimal("30"), Decimal("30"), Decimal("30"), Decimal("0")
    ) == Decimal(0)
    print("PASS working-capital days -> loading + delta margin\n")


def main() -> None:
    test_peer_price_ranges_invert_pe_multiples()
    test_football_field_adds_dcf_and_iv()
    test_working_capital_days()
    print("ALL FOOTBALL-WC TESTS PASSED")


if __name__ == "__main__":
    main()
