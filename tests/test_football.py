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


def _peer(ticker, price, eps, market_cap, book_equity, shares) -> CompanyComp:
    """A lightweight bank peer with enough data to compute P/E and P/B."""
    return CompanyComp(
        ticker=ticker,
        company_name=f"Bank {ticker}",
        sector="Financials",
        sub_sector="Banks",
        price=Decimal(price),
        eps=Decimal(eps),
        market_cap=Decimal(market_cap),
        total_equity=Decimal(book_equity),
        shares_outstanding=Decimal(shares),
    )


def test_peer_price_ranges_invert_pe_multiples() -> None:
    subject = _subject()
    # P/E peers: price/eps -> BBRI (10), BMRI (12), BBNI (8)
    # P/B peers: market_cap/equity -> BBRI (2.0), BMRI (2.5), BBNI (1.5)
    peers = [
        _peer("BBRI.JK", 2000, 200, 200000000000000, 100000000000000, 100000000000),
        _peer("BMRI.JK", 3000, 250, 300000000000000, 120000000000000, 100000000000),
        _peer("BBNI.JK", 1500, 187.5, 150000000000000, 100000000000000, 100000000000),
    ]
    rows = peer_price_ranges(peers, subject)
    by_method = {r.method: r for r in rows}

    pe_row = by_method["P/E (peers)"]
    # peer P/E sorted [8, 10, 12]; IQR 25th=9, 75th=11; subject EPS 400 -> [3600, 4400]
    assert abs(pe_row.low - 3600.0) < 0.01, pe_row.low
    assert abs(pe_row.high - 4400.0) < 0.01, pe_row.high

    pb_row = by_method["P/B (peers)"]
    bvps = 280000000000000 / 120000000000  # ~2333.33
    # P/B sorted [1.5, 2.0, 2.5]; IQR 25th=1.75, 75th=2.25
    assert abs(pb_row.low - (1.75 * bvps)) < 0.01
    assert abs(pb_row.high - (2.25 * bvps)) < 0.01
    print("PASS peer P/E + P/B price-range inversion (IQR, not min/max)\n")


def test_football_field_resists_outlier_peer() -> None:
    """A single absurd-multiple peer must not blow up the range (TKIM/ALKA case)."""
    subject = _subject()
    peers = [
        _peer("BBRI.JK", 2000, 200, 200000000000000, 100000000000000, 100000000000),  # P/E 10
        _peer("BMRI.JK", 3000, 250, 300000000000000, 120000000000000, 100000000000),  # P/E 12
        # Outlier: P/E 100 (nano-cap), should be IQR-clipped away.
        _peer("ALKA.JK", 100000, 1000, 100000000000000, 100000000000000, 100000000000),
    ]
    rows = peer_price_ranges(peers, subject)
    pe_row = next(r for r in rows if r.method == "P/E (peers)")
    # IQR of [10, 12, 100] = [11, 56]; the 100 outlier can no longer set the ceiling at
    # 100*400 = 40000. The 75th percentile (56) bounds it instead.
    assert pe_row.high < 40000.0, pe_row.high
    assert pe_row.high == 56.0 * 400.0, pe_row.high
    print("PASS football-field resists outlier peer (IQR clipping)\n")


def test_football_field_adds_dcf_and_iv() -> None:
    subject = _subject()
    peers = [_peer("BBRI.JK", 2000, 200, 200000000000000, 100000000000000, 100000000000)]
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


def test_ev_range_degraded_when_no_shares() -> None:
    """A subject with EBITDA/revenue but no shares_outstanding must not emit a
    (None, None) EV row — it is omitted, and other rows degrade cleanly."""
    subject = CompanyComp(
        ticker="X.JK",
        company_name="No Shares Co",
        sector="Financials",
        sub_sector="Banks",
        ebitda=Decimal("1000"),
        revenue=Decimal("100000"),
        total_debt=Decimal("0"),
        cash_and_equivalents=Decimal("0"),
        shares_outstanding=None,
    )
    peers = [
        _peer("BBRI.JK", 2000, 200, 200000000000000, 100000000000000, 100000000000),
    ]
    rows = peer_price_ranges(peers, subject)
    # Every emitted row must have concrete low/high; no (None, None) rows may leak.
    assert all(r.low is not None and r.high is not None for r in rows), rows
    # The EV-based rows are correctly omitted (no shares to bridge EV -> price).
    methods = {r.method for r in rows}
    assert "EV/EBITDA (peers)" not in methods
    assert "EV/Revenue (peers)" not in methods
    print("PASS EV range omitted cleanly when shares_outstanding missing\n")


def main() -> None:
    test_peer_price_ranges_invert_pe_multiples()
    test_football_field_resists_outlier_peer()
    test_football_field_adds_dcf_and_iv()
    test_working_capital_days()
    test_ev_range_degraded_when_no_shares()
    print("ALL FOOTBALL-WC TESTS PASSED")


if __name__ == "__main__":
    main()
