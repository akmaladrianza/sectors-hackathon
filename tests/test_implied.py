"""Tests for the implied-valuation engine + expanded DCF (pure, deterministic).

Run:  python -m tests.test_implied
"""

from __future__ import annotations

from decimal import Decimal

from engine.implied_valuation import (
    build_implied_valuation,
    comps_implied_prices,
)
from engine.dcf import run_dcf
from models.company_comp import CompanyComp


def _comp(ticker, revenue, ebitda, eps, bvps, shares, price, debt=0, cash=0) -> CompanyComp:
    return CompanyComp(
        ticker=ticker,
        company_name=f"Co {ticker}",
        sector="Materials",
        revenue=Decimal(revenue),
        ebitda=Decimal(ebitda),
        eps=Decimal(eps),
        total_equity=Decimal(str(bvps)) * Decimal(str(shares)),
        shares_outstanding=Decimal(shares),
        price=Decimal(price),
        market_cap=Decimal(price) * Decimal(shares),
        total_debt=Decimal(debt),
        cash_and_equivalents=Decimal(cash),
        net_income=Decimal(ebitda),
    )


def test_comps_implied_excludes_subject() -> None:
    # Subject overpriced with a high multiple; peers should dominate the median.
    subject = _comp("SUB.JK", 100, 20, 2, 10, 100, 50)
    peer_a = _comp("AAA.JK", 100, 20, 2, 10, 100, 10)  # cheap
    peer_b = _comp("BBB.JK", 100, 20, 2, 10, 100, 20)
    # Peer P/E median: AAA (5), BBB (10) -> 7.5
    prices = comps_implied_prices(subject, [subject, peer_a, peer_b])
    names = {p.multiple for p in prices}
    assert "P/E" in names
    pe_implied = next(p for p in prices if p.multiple == "P/E")
    assert pe_implied.available
    # 7.5 * eps 2 = 15
    assert abs(float(pe_implied.price) - 15.0) < 1e-6, pe_implied.price
    print("PASS comps-implied P/E excludes subject, uses peer median\n")


def test_build_implied_valuation_verdict() -> None:
    subject = _comp("SUB.JK", 100, 20, 2, 10, 100, 50, debt=0, cash=0)
    peer_a = _comp("AAA.JK", 100, 20, 2, 10, 100, 10)
    peer_b = _comp("BBB.JK", 100, 20, 2, 10, 100, 20)
    iv = build_implied_valuation(subject, [subject, peer_a, peer_b])
    assert iv.current_price == Decimal("50")
    # Implied range is well below current price -> Overvalued.
    assert iv.verdict == "Overvalued", iv.verdict
    assert iv.implied_low is not None and iv.implied_high is not None
    print(f"PASS verdict range [{iv.implied_low}, {iv.implied_high}] -> {iv.verdict}\n")


def test_build_implied_valuation_no_peers() -> None:
    subject = _comp("SUB.JK", 100, 20, 2, 10, 100, 50)
    iv = build_implied_valuation(subject, [subject])
    assert iv.implied_prices == []
    assert iv.verdict is None
    print("PASS no-peer implied valuation -> empty, verdict None\n")


def test_dcf_fcff_buildup_and_equity() -> None:
    # FCFF build-up path: EBITDA margin 40%, D&A 5%, tax 20%, capex 15%, NWC 5%.
    r = run_dcf(
        revenue=Decimal("1000"),
        growth_rate=Decimal("0.05"),
        cash_flow_margin=Decimal("0.15"),
        discount_rate=Decimal("0.10"),
        terminal_growth=Decimal("0.02"),
        years=5,
        ebitda_margin=Decimal("0.40"),
        depreciation_margin=Decimal("0.05"),
        tax_rate=Decimal("0.20"),
        capex_margin=Decimal("0.15"),
        nwc_change_margin=Decimal("0.05"),
        shares_outstanding=Decimal("100"),
        net_debt=Decimal("200"),
    )
    assert r.available
    assert r.assumptions["fcff_buildup"] is True
    # FCF year 1: EBITDA 420 - D&A 52.5 = EBIT 367.5; NOPAT 294; +52.5 -157.5 -52.5 = 136.5
    assert r.intrinsic_ev is not None and r.intrinsic_ev > 0
    # Equity = EV - net debt; price = equity / shares.
    assert r.intrinsic_equity == r.intrinsic_ev - Decimal("200")
    assert r.intrinsic_price_per_share == r.intrinsic_equity / Decimal("100")
    print(
        f"PASS FCFF + FCFE: EV={r.intrinsic_ev:.2f} "
        f"equity={r.intrinsic_equity:.2f} price={r.intrinsic_price_per_share:.2f}\n"
    )


def test_dcf_sales_margin_fallback() -> None:
    # No FCFF build-up inputs -> falls back to the simple sales-margin model.
    r = run_dcf(
        revenue=Decimal("100"),
        growth_rate=Decimal("0.10"),
        cash_flow_margin=Decimal("0.20"),
        discount_rate=Decimal("0.12"),
        terminal_growth=Decimal("0.02"),
        years=5,
        shares_outstanding=Decimal("10"),
        net_debt=Decimal("50"),
    )
    assert r.available
    assert r.assumptions["fcff_buildup"] is False
    assert r.intrinsic_price_per_share == (r.intrinsic_ev - Decimal("50")) / Decimal("10")
    print("PASS sales-margin fallback + FCFE bridge\n")


def main() -> None:
    test_comps_implied_excludes_subject()
    test_build_implied_valuation_verdict()
    test_build_implied_valuation_no_peers()
    test_dcf_fcff_buildup_and_equity()
    test_dcf_sales_margin_fallback()
    print("ALL IMPLIED/DCF TESTS PASSED")


if __name__ == "__main__":
    main()
