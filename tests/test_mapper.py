"""Tests for the report → ``CompanyComp`` mapper using static JSON fixtures.

The 10 ticker payloads are frozen under ``tests/fixtures/*.json`` (captured from
the live Sectors API). This makes the suite deterministic and reviewable without
an API key, a live network connection, or a same-day cache — deliberately NOT
keyed on ``date.today()`` (an earlier version did that and broke silently the
moment the wall-clock rolled over, since the cache keys embed the fetch date).

Run:  python -m tests.test_mapper
"""

from __future__ import annotations

import json
import os
from datetime import date

from mapper.mapper import Template, report_to_company_comp, MapperError

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

# ticker -> expected template
CASES = {
    "BBCA": Template.BANK,
    "ARTO": Template.BANK,
    "TLKM": Template.GENERIC,
    "ASII": Template.GENERIC,
    "UNVR": Template.GENERIC,
    "PGAS": Template.GENERIC,
    "MDKA": Template.GENERIC,
    "ADMF": Template.GENERIC,
    "ASRM": Template.GENERIC,
    "GOTO": Template.GENERIC,
}


def _load(ticker: str) -> dict:
    path = os.path.join(FIXTURES, f"{ticker}.json")
    assert os.path.exists(path), f"missing fixture {path}"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def test_fixture_cases() -> None:
    for ticker, expected in CASES.items():
        payload = _load(ticker)
        comp, template = report_to_company_comp(payload)
        assert template == expected, f"{ticker}: expected {expected}, got {template}"
        assert comp.ticker == ticker + ".JK", comp.ticker
        assert comp.market_cap is not None, f"{ticker} market_cap missing"
        # as_of_date should be coerced from the fixture's latest_close_date
        # (an ISO date string) into a datetime.date by Pydantic.
        latest_close = payload["overview"].get("latest_close_date")
        if latest_close is not None:
            assert comp.as_of_date is not None, f"{ticker} as_of_date missing"
            assert isinstance(comp.as_of_date, date), (
                f"{ticker} as_of_date not a date: {type(comp.as_of_date)!r}"
            )
            assert comp.as_of_date.isoformat() == latest_close, (
                f"{ticker} as_of_date {comp.as_of_date} != {latest_close}"
            )
        print(
            f"PASS {ticker:<5} [{expected.value:7}] "
            f"mcap={comp.market_cap} cash={comp.cash_and_equivalents} "
            f"ev={comp.enterprise_value} screenable={comp.is_screenable} "
            f"as_of={comp.as_of_date}"
        )
    print(f"\n{len(CASES)} fixture mapper cases PASSED\n")


def test_bank_cash_regression() -> None:
    """Regression: bank cash must NOT double-count (audited BBCA cross-check)."""
    payload = _load("BBCA")
    comp, template = report_to_company_comp(payload)
    assert template == Template.BANK
    # The aggregate cash line already includes "Kas" (cash_only) as a sub-line.
    fin = payload["financials"]["historical_financials"][-1]
    aggregate = fin["total_cash_and_due_from_banks"]
    assert comp.cash_and_equivalents == aggregate, (
        f"cash should equal aggregate {aggregate}, got {comp.cash_and_equivalents}"
    )
    assert comp.cash_and_equivalents != aggregate + fin["cash_only"], (
        "cash must NOT include cash_only on top of the aggregate (double-count)"
    )
    print(
        "PASS bank cash regression: "
        f"cash={comp.cash_and_equivalents} == aggregate (no double-count)\n"
    )


def test_bank_cash_no_double_count_synthetic() -> None:
    """Synthetic payload proves the derivation rule independent of the fixture."""
    payload = {
        "symbol": "TEST.JK",
        "company_name": "Test Bank",
        "overview": {"sector": "Financials", "sub_sector": "Banks", "market_cap": 1000},
        "financials": {"historical_financials": [{
            "year": 2025,
            "cash_only": 25305031000000,
            "total_cash_and_due_from_banks": 78406483000000,
            "total_debt": 2395446000000,
        }]},
    }
    comp, template = report_to_company_comp(payload)
    assert template == Template.BANK
    assert comp.cash_and_equivalents == 78406483000000, comp.cash_and_equivalents
    print("PASS bank cash synthetic: aggregate only, not + cash_only\n")


def test_sparse_overview() -> None:
    payload = {
        "symbol": "X.JK",
        "company_name": "Sparse Overview Co",
        "overview": {"sector": "Tech"},
        "financials": {},
    }
    comp, template = report_to_company_comp(payload)
    assert template == Template.GENERIC
    assert comp.market_cap is None and comp.cash_and_equivalents is None
    print("PASS sparse overview: defaults to generic, missing fields None\n")


def test_empty_financials() -> None:
    payload = {
        "symbol": "Y.JK",
        "company_name": "No Financials Co",
        "overview": {"sector": "Tech", "market_cap": 500},
        "financials": {},
    }
    comp, template = report_to_company_comp(payload)
    assert comp.market_cap == 500
    assert comp.revenue is None and comp.ebitda is None
    assert comp.cash_and_equivalents is None
    print("PASS empty financials: all dependent fields None, no crash\n")


def test_malformed_numeric_field() -> None:
    payload = {
        "symbol": "Z.JK",
        "company_name": "Bad Number Co",
        "overview": {"sector": "Tech", "market_cap": 500},
        "financials": {"historical_financials": [{
            "year": 2025,
            "revenue": "N/A",
            "ebitda": 100,
        }]},
    }
    comp, template = report_to_company_comp(payload)
    assert comp.revenue is None, comp.revenue
    assert comp.ebitda == 100
    print("PASS malformed numeric field: degraded to None, other fields intact\n")


def test_missing_identifiers_raises() -> None:
    payload = {"overview": {"sector": "Tech"}}
    try:
        report_to_company_comp(payload)
    except MapperError as e:
        assert e.ticker == "?"
        print(f"PASS missing identifiers: MapperError raised ({e.ticker})\n")
        return
    raise AssertionError("expected MapperError for missing identifiers")


def main() -> None:
    test_fixture_cases()
    test_bank_cash_regression()
    test_bank_cash_no_double_count_synthetic()
    test_sparse_overview()
    test_empty_financials()
    test_malformed_numeric_field()
    test_missing_identifiers_raises()
    print("ALL MAPPER TESTS PASSED")


if __name__ == "__main__":
    main()

