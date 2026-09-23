"""Tests for the citation-safe assistant.

Verifies the two hard guarantees:
  1. Every suggestion carries a source citation (never bare numbers).
  2. Unknown values return "no cited value available" — never a fabricated number.

Run:  python -m tests.test_assistant
"""

from __future__ import annotations

from decimal import Decimal

from assistant import (
    suggest_asset_useful_life,
    suggest_working_capital,
    suggest_capex,
    capex_anchors,
    sectors_native_revenue,
)
from models.company_comp import CompanyComp


def _comp(sub_sector="Telecommunication", industry="Telecommunication Service", **kw):
    base = dict(
        ticker="T.JK",
        company_name="T",
        sector="Infrastructures",
        sub_sector=sub_sector,
        industry=industry,
        revenue=Decimal("100000000000"),
    )
    base.update(kw)
    return CompanyComp(**base)


def test_mining_suggestions_are_cited() -> None:
    comp = _comp(sub_sector="Basic Materials", industry="Metals & Minerals")
    life = suggest_asset_useful_life(comp)
    wc = suggest_working_capital(comp)
    capex = suggest_capex(comp)

    assert life is not None and life.available and life.source, "useful life must be cited"
    assert wc is not None and wc.available and wc.source, "working capital must be cited"
    assert capex is not None and capex.available and capex.source, "capex must be cited"
    assert life.value == Decimal("15")
    assert capex.value == Decimal("0.25")
    print(f"PASS mining suggestions cited (life={life.value}, wc={wc.value}, capex={capex.value})\n")


def test_materials_bucket_is_not_mining() -> None:
    # A "Materials" GICS company (e.g. chemicals/packaging) must NOT be mis-classified
    # as mining just because the string is a near-match.
    comp = _comp(sub_sector="Chemicals", industry="Specialty Chemicals")
    life = suggest_asset_useful_life(comp)
    assert life is not None and life.available is False, (
        "chemicals/packaging should NOT get a mining asset-life"
    )
    print("PASS 'Materials'-like industry NOT mis-classified as mining\n")


def test_bank_zero_working_capital() -> None:
    comp = _comp(sub_sector="Banks", industry="Banks")
    wc = suggest_working_capital(comp)
    assert wc is not None and wc.available
    assert wc.value == Decimal("0.00")  # banks: no conventional NWC
    print("PASS bank working capital = 0 (no conventional NWC line)\n")


def test_unknown_industry_is_honest() -> None:
    # An un-curated industry -> "no cited value available", never a fabricated number.
    comp = _comp(sub_sector="Aerospace", industry="Aerospace & Defense")
    life = suggest_asset_useful_life(comp)
    assert life is not None and life.available is False
    assert "no curated value" in life.source
    print(f"PASS unknown industry: honest 'no cited value' ({life.source})\n")


def test_sectors_native_revenue_exempt() -> None:
    comp = _comp(revenue=Decimal("123456"))
    r = sectors_native_revenue(comp)
    assert r is not None and r.available and r.sector_native is True
    assert r.value == Decimal("123456")
    print(f"PASS sectors-native revenue exempt from citation (value={r.value})\n")


def test_sectors_native_revenue_missing() -> None:
    comp = _comp(revenue=None)
    r = sectors_native_revenue(comp)
    assert r is not None and r.available is False
    print("PASS sectors-native revenue missing -> not available\n")


def test_capex_anchors_from_own_data() -> None:
    comp = _comp(
        revenue=Decimal("1000"),
        ebitda=Decimal("250"),
        capital_expenditure=Decimal("100"),
        depreciation_amortization=Decimal("80"),
        fixed_assets=Decimal("2000"),
    )
    anchors = capex_anchors(comp)
    by_src_terms = {a.source.split(" — ")[0]: a.value for a in anchors}
    assert "capex / revenue" in by_src_terms
    assert round(float(by_src_terms["capex / revenue"]), 4) == 0.1
    assert "capex / EBITDA" in by_src_terms
    assert round(float(by_src_terms["capex / EBITDA"]), 4) == 0.4
    assert "capex / D&A" in by_src_terms
    assert round(float(by_src_terms["capex / D&A"]), 2) == 1.25
    assert any("fixed-asset turnover" in k for k in by_src_terms)
    fa_turnover = next(v for k, v in by_src_terms.items() if "fixed-asset turnover" in k)
    assert round(float(fa_turnover), 2) == 0.5
    print(f"PASS capex anchors from own audited data ({len(anchors)} anchors)\n")


def test_capex_anchors_no_data() -> None:
    comp = _comp(revenue=Decimal("1000"))  # no capex/fixed assets
    anchors = capex_anchors(comp)
    assert anchors == []
    print("PASS capex anchors empty when raw lines missing\n")


def test_capex_anchors_da_fallback_and_reinvestment_rate() -> None:
    # Sectors' raw depreciation is often None; D&A should fall back to EBITDA − EBIT,
    # and the reinvestment-rate anchor should fire from EBIT + tax.
    comp = _comp(
        revenue=Decimal("1000"),
        ebitda=Decimal("400"),
        ebit=Decimal("300"),
        capital_expenditure=Decimal("120"),
        depreciation_amortization=None,  # <-- forces the fallback -> D&A = 400-300 = 100
        fixed_assets=Decimal("1000"),
        tax_expense=Decimal("66"),
    )
    anchors = capex_anchors(comp)
    terms = [a.source.split(" — ")[0] for a in anchors]
    # D&A fallback -> capex / D&A = 120 / 100 = 1.2
    assert any("capex / D&A" in t for t in terms), terms
    da_anchor = next(a for a in anchors if "capex / D&A" in a.source)
    assert round(float(da_anchor.value), 2) == 1.2, da_anchor.value
    # Reinvestment rate = capex / NOPAT = 120 / (300 - 66) = 120/234 ≈ 0.51
    assert any("reinvestment rate" in t for t in terms), terms
    reinv = next(a for a in anchors if "reinvestment rate" in a.source)
    assert round(float(reinv.value), 2) == round(120 / 234, 2), reinv.value
    print(f"PASS capex anchors D&A fallback + reinvestment rate ({len(anchors)} anchors)\n")


def main() -> None:
    test_mining_suggestions_are_cited()
    test_materials_bucket_is_not_mining()
    test_bank_zero_working_capital()
    test_unknown_industry_is_honest()
    test_sectors_native_revenue_exempt()
    test_sectors_native_revenue_missing()
    test_capex_anchors_from_own_data()
    test_capex_anchors_no_data()
    test_capex_anchors_da_fallback_and_reinvestment_rate()
    print("ALL ASSISTANT TESTS PASSED")


if __name__ == "__main__":
    main()
