"""Tests for the :class:`CompanyComp` model, focusing on missing-data behavior.

Run:  python tests/test_company_comp.py
"""

from decimal import Decimal

from pydantic import ValidationError

from models.company_comp import CompanyComp, Currency


def assert_close(actual, expected, tol=1e-6):
    assert abs(actual - expected) < tol, f"{actual} != {expected}"


def main():
    # 1. Full data: everything computes.
    full = CompanyComp(
        ticker="BBCA.JK",
        company_name="PT Bank Central Asia Tbk",
        sector="Financials",
        market_cap=Decimal("1000"),
        total_debt=Decimal("300"),
        cash_and_equivalents=Decimal("100"),
        revenue=Decimal("500"),
        ebitda=Decimal("200"),
        eps=Decimal("2"),
        price=Decimal("20"),
        total_assets=Decimal("900"),
        total_liabilities=Decimal("600"),
        net_income=Decimal("150"),
    )
    assert full.enterprise_value == Decimal("1200"), full.enterprise_value
    assert_close(full.ev_to_ebitda, 6.0)
    assert_close(full.ev_to_revenue, 2.4)
    assert_close(full.pe_ratio, 10.0)
    # True P/B: total_equity backfilled = assets - liabilities = 900 - 600 = 300
    assert full.total_equity == Decimal("300"), full.total_equity
    assert_close(full.price_to_book, 1000 / 300)
    assert full.is_screenable is True
    assert full.exclusion_reasons == []
    print("PASS full-data case")

    # 2. Missing market_cap: multiples -> None, no crash, not screenable.
    no_cap = CompanyComp(
        ticker="MISSING.JK",
        company_name="No Market Cap Co",
        sector="Financials",
        total_debt=Decimal("300"),
        cash_and_equivalents=Decimal("100"),
        revenue=Decimal("500"),
        ebitda=Decimal("200"),
    )
    assert no_cap.market_cap is None
    assert no_cap.enterprise_value is None
    assert no_cap.ev_to_ebitda is None
    assert no_cap.ev_to_revenue is None
    assert no_cap.price_to_book is None
    assert no_cap.pe_ratio is None
    assert no_cap.is_screenable is False  # surfaced, not silently dropped
    assert no_cap.exclusion_reasons == ["missing market_cap"]
    print("PASS missing-market-cap case (graceful None, not screened)")

    # 3. market_cap backfilled from price * shares_outstanding.
    backfill = CompanyComp(
        ticker="BACKFILL.JK",
        company_name="Backfilled Co",
        sector="Industrials",
        price=Decimal("15"),
        shares_outstanding=Decimal("40"),
        ebitda=Decimal("100"),
        revenue=Decimal("500"),  # needed so EV/Revenue is computable too
    )
    assert backfill.market_cap == Decimal("600"), backfill.market_cap
    assert backfill.is_screenable is True
    print("PASS backfill case (market_cap = 600)")

    # 4. market_cap present but missing ebitda -> still not screenable, no crash.
    no_ebitda = CompanyComp(
        ticker="NOEBITDA.JK",
        company_name="No EBITDA Co",
        sector="Utilities",
        market_cap=Decimal("1000"),
        revenue=Decimal("500"),
    )
    assert no_ebitda.is_screenable is False
    assert no_ebitda.exclusion_reasons == ["missing ebitda"]
    assert no_ebitda.ev_to_ebitda is None
    assert_close(no_ebitda.ev_to_revenue, 1000 / 500)
    print("PASS missing-ebitda case (EV/Rev still computes)")

    # 5. zero ebitda must not divide-by-zero.
    zero_ebitda = CompanyComp(
        ticker="ZERO.JK",
        company_name="Zero EBITDA Co",
        sector="Tech",
        market_cap=Decimal("1000"),
        ebitda=Decimal("0"),
        revenue=Decimal("500"),  # present so the only exclusion is the zero EBITDA
    )
    assert zero_ebitda.ev_to_ebitda is None
    assert zero_ebitda.is_screenable is False
    assert zero_ebitda.exclusion_reasons == ["non-positive ebitda"]
    print("PASS zero-ebitda case (no div-by-zero)")

    # 6. screenable partition helper demonstration.
    rows = [full, no_cap, backfill, no_ebitda, zero_ebitda]
    usable = [r for r in rows if r.is_screenable]
    excluded = [r for r in rows if not r.is_screenable]
    assert len(usable) == 2  # full, backfill
    assert len(excluded) == 3  # no_cap, no_ebitda, zero_ebitda
    print(
        f"PASS screening partition: {len(usable)} usable, "
        f"{len(excluded)} excluded-for-data"
    )

    # 7. Serialization: JSON mode emits floats for Decimal computed fields.
    dumped = full.model_dump(mode="json")
    assert "enterprise_value" in dumped
    assert isinstance(dumped["enterprise_value"], float)
    assert dumped["ev_to_ebitda"] == 6.0
    print("PASS serialization (computed fields present, decimals as floats)")

    # 8. Validation: negative values on non-negative financial fields are rejected.
    for bad_params in [
        {"market_cap": Decimal("-1000")},
        {"price": Decimal("-5")},
        {"shares_outstanding": Decimal("-1")},
        {"revenue": Decimal("-500")},
        {"total_assets": Decimal("-1")},
        {"cash_and_equivalents": Decimal("-1")},
        {"total_liabilities": Decimal("-1")},
        {"total_equity": Decimal("-1")},
    ]:
        try:
            CompanyComp(
                ticker="BAD.JK", company_name="Bad Co", sector="X", **bad_params
            )
        except ValidationError:
            pass
        else:
            raise AssertionError(f"Expected ValidationError for {bad_params}")
    print("PASS validation: negative values rejected")

    # 9. Validation: empty-string identifiers are rejected.
    for kwargs in [
        {"ticker": "", "company_name": "X", "sector": "X"},
        {"ticker": "A", "company_name": "", "sector": "X"},
        {"ticker": "A", "company_name": "X", "sector": ""},
    ]:
        try:
            CompanyComp(**kwargs)
        except ValidationError:
            pass
        else:
            raise AssertionError(f"Expected ValidationError for {kwargs}")
    print("PASS validation: empty-string identifiers rejected")

    # 10b. Negative intrinsic_value (Sectors distress/over-leverage signal) is accepted
    #     at the model layer (no crash) but surfaced as a non-fatal data-quality flag
    #     and excluded from intrinsic_upside rather than producing a bogus gain.
    neg_iv = CompanyComp(
        ticker="INKP.JK",
        company_name="Indah Kiat",
        sector="Basic Materials",
        market_cap=Decimal("1000"),
        ebitda=Decimal("100"),
        revenue=Decimal("500"),
        price=Decimal("8575"),
        intrinsic_value=Decimal("-29670"),
    )
    assert neg_iv.intrinsic_value == Decimal("-29670")  # stored, not rejected
    assert neg_iv.intrinsic_upside is None  # negative IV is unusable
    assert neg_iv.is_screenable is True  # still screenable on EV multiples
    assert any("negative Sectors intrinsic value" in f for f in neg_iv.data_quality_flags)
    print("PASS negative intrinsic value: flagged + excluded from upside, not a crash")

    # 10c. Negative capital_expenditure (net of disposals — e.g. PIPA reports a
    #     negative capex while EBITDA is positive) is accepted at the model layer (no
    #     crash) and surfaced as a non-fatal data-quality flag rather than rejected
    #     by a ge=0 constraint. The company stays screenable on its EBITDA/revenue
    #     multiples.
    neg_capex = CompanyComp(
        ticker="PIPA.JK",
        company_name="Pool Advista Indonesia",
        sector="Financials",
        market_cap=Decimal("1000"),
        total_debt=Decimal("500"),
        cash_and_equivalents=Decimal("100"),
        revenue=Decimal("700"),
        ebitda=Decimal("200"),
        capital_expenditure=Decimal("-483092039"),
        depreciation_amortization=Decimal("50"),
    )
    assert neg_capex.capital_expenditure == Decimal("-483092039")  # stored, not rejected
    assert neg_capex.is_screenable is True  # still screenable on EV multiples
    assert any(
        "negative capital expenditure" in f for f in neg_capex.data_quality_flags
    ), neg_capex.data_quality_flags
    print("PASS negative capital expenditure: flagged, not a crash")

    # 10. ev_to_revenue / exclusion_reasons symmetry: missing revenue is now a
    #     first-class exclusion reason (previously only market_cap/ebitda were).
    no_revenue = CompanyComp(
        ticker="NOREV.JK",
        company_name="No Revenue Co",
        sector="Industrials",
        market_cap=Decimal("1000"),
        ebitda=Decimal("100"),
    )
    assert no_revenue.ev_to_revenue is None
    assert "missing revenue" in no_revenue.exclusion_reasons, no_revenue.exclusion_reasons
    assert no_revenue.is_screenable is False
    print("PASS ev_to_revenue/exclusion symmetry (missing revenue surfaced)")

    print("\nALL TESTS PASSED")


if __name__ == "__main__":
    main()
