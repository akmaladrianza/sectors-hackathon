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


def test_implied_band_excludes_sectors_intrinsic() -> None:
    """Sectors' own intrinsic value must not define the comps band's ceiling.

    A subject whose Sectors IV is far above every peer-implied price must have its
    implied_high reflect the *peer-relative* multiples only — otherwise a premium name
    (e.g. BBCA) would get an inflated ceiling and always read "fairly valued".
    """
    subject = _comp("SUB.JK", 100, 20, 2, 10, 100, 50)
    subject = subject.model_copy(update={"intrinsic_value": Decimal("999")})
    peer_a = _comp("AAA.JK", 100, 20, 2, 10, 100, 10)  # P/E 5
    peer_b = _comp("BBB.JK", 100, 20, 2, 10, 100, 20)  # P/E 10
    iv = build_implied_valuation(subject, [subject, peer_a, peer_b])
    assert iv.sectors_intrinsic == Decimal("999")
    # P/E implied = median(5,10) * eps 2 = 15. Band must NOT be [.., 999].
    assert iv.implied_high == Decimal("15.0"), iv.implied_high
    assert iv.implied_prices[-1] == Decimal("999")  # implied_prices still lists it
    # And 999 still shows as a standalone fact, not a band edge.
    assert iv.implied_high != Decimal("999")
    print("PASS implied band excludes Sectors intrinsic value\n")


def test_pb_normalized_by_roe_for_premium_subject() -> None:
    """A premium (high-ROE) subject must not inherit a low-ROE peer's raw P/B.

    Two low-ROE peers trade at low P/B *correctly for their own ROE*; applying that
    raw median to a high-ROE subject understates it. ROE-normalization (justified
    P/B) corrects this by re-applying the per-unit-ROE ratio at the subject's ROE.
    """
    def make(ticker, net_income, equity, market_cap):
        return CompanyComp(
            ticker=ticker,
            company_name=f"Co {ticker}",
            sector="Financials",
            sub_sector="Banks",
            net_income=Decimal(net_income),
            total_equity=Decimal(equity),
            market_cap=Decimal(market_cap),
            shares_outstanding=Decimal(100),
            eps=Decimal("1.0"),
            ebitda=Decimal("10"),
            revenue=Decimal("100"),
        )

    # Peers: ROE 5%, P/B 0.5. Subject: ROE 20%, P/B 2.0 (book value/share = 1.0).
    peer_a = make("AAA.JK", 5, 100, 50)   # ROE 5%, P/B 0.5
    peer_b = make("BBB.JK", 10, 200, 100)  # ROE 5%, P/B 0.5
    subject = make("SUB.JK", 20, 100, 200)  # ROE 20%, P/B 2.0, bvps = 1.0

    prices = comps_implied_prices(subject, [subject, peer_a, peer_b])
    pb_row = next(p for p in prices if p.multiple == "P/B")
    assert pb_row.available, pb_row
    # Raw peer-median P/B = 0.5 -> 0.5 * bvps(1.0) = 0.5 (grossly understates subject).
    # ROE-normalized: k = median(0.5/0.05, 0.5/0.05) = 10; subject ROE 20% -> P/B 2.0.
    assert "ROE-normalized" in pb_row.source, pb_row.source
    assert float(pb_row.price) == 2.0, pb_row.price
    # Guard: the raw median used below would have been 0.5, far below the normalized 2.0.
    print("PASS P/B ROE-normalized: premium subject no longer inherits low-ROE peer P/B\n")


def test_pe_normalized_by_growth_for_high_growth_subject() -> None:
    """PEG-style: a high-growth subject shouldn't inherit stagnant peers' low P/E."""
    def make(ticker, eps, pe, growth):
        return CompanyComp(
            ticker=ticker,
            company_name=f"Co {ticker}",
            sector="Tech",
            eps=Decimal(str(eps)),
            price=Decimal(str(pe * eps)),
            shares_outstanding=Decimal(10),
            revenue_growth_yoy=growth,
            ebitda=Decimal("1"),
            revenue=Decimal("1"),
        )

    peers_low_g = [make(f"P{i}.JK", 1.0, 10.0, 0.02) for i in range(2)]  # P/E 10, g 2%
    subject_high_g = make("SUB.JK", 1.0, 20.0, 0.20)  # P/E 20 (via price), g 20%

    prices = comps_implied_prices(subject_high_g, [subject_high_g] + peers_low_g)
    pe_row = next(p for p in prices if p.multiple == "P/E")
    assert pe_row.available
    # Raw median P/E = 10 -> 10 * eps 1 = 10. PEG-normalized: k = median(10/0.02)=500;
    # subject growth 20% -> P/E 100 -> price 100.
    assert "growth-normalized" in pe_row.source, pe_row.source
    assert float(pe_row.price) == 100.0, pe_row.price
    print("PASS P/E PEG-normalized: high-growth subject not understated by stagnant peers\n")


def test_missing_normalizer_falls_back_to_raw_median() -> None:
    """No growth/ROE anywhere -> raw peer median (graceful fallback, no crash)."""
    def make(ticker, eps, pe):
        return CompanyComp(
            ticker=ticker,
            company_name=f"Co {ticker}",
            sector="Tech",
            eps=Decimal(str(eps)),
            price=Decimal(str(pe * eps)),
            shares_outstanding=Decimal(10),
            ebitda=Decimal("1"),
            revenue=Decimal("1"),
        )

    subject = make("SUB.JK", 2.0, 20.0)
    peer_a = make("AAA.JK", 2.0, 5.0)
    peer_b = make("BBB.JK", 2.0, 10.0)
    prices = comps_implied_prices(subject, [subject, peer_a, peer_b])
    pe_row = next(p for p in prices if p.multiple == "P/E")
    assert pe_row.available
    # median(5,10)=7.5 -> 7.5 * 2 = 15; source indicates raw fallback.
    assert "peer-median P/E" in pe_row.source and "growth-normalized" not in pe_row.source
    assert float(pe_row.price) == 15.0, pe_row.price
    print("PASS missing normalizer -> raw peer-median fallback\n")


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
    test_implied_band_excludes_sectors_intrinsic()
    test_pb_normalized_by_roe_for_premium_subject()
    test_pe_normalized_by_growth_for_high_growth_subject()
    test_missing_normalizer_falls_back_to_raw_median()
    test_dcf_fcff_buildup_and_equity()
    test_dcf_sales_margin_fallback()
    print("ALL IMPLIED/DCF TESTS PASSED")


if __name__ == "__main__":
    main()
