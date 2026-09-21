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


def main() -> None:
    test_mining_suggestions_are_cited()
    test_materials_bucket_is_not_mining()
    test_bank_zero_working_capital()
    test_unknown_industry_is_honest()
    test_sectors_native_revenue_exempt()
    test_sectors_native_revenue_missing()
    print("ALL ASSISTANT TESTS PASSED")


if __name__ == "__main__":
    main()
