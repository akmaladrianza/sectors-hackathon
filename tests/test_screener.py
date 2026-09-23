"""Tests for the screener using an in-memory fake client (no network).

Verifies the three key behaviours:
  1. screenable peers are partitioned correctly (bank vs generic vs miner),
  2. data-quality exclusions carry a reason, and are never silently dropped,
  3. a bad ticker (pull failure) does NOT abort the whole batch.

Run:  python -m tests.test_screener
"""

from __future__ import annotations

import json
import os
from decimal import Decimal

from sectors_client.client import SectorsAPIError
from screener.screener import screen_tickers


FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def _load(ticker: str) -> dict:
    with open(os.path.join(FIXTURES, f"{ticker}.json"), encoding="utf-8") as f:
        return json.load(f)


class FakeClient:
    """Minimal stand-in for SectorsClient using frozen fixtures + failing tickers."""

    def __init__(self, fail: list[str] | None = None) -> None:
        self.fail = set(fail or [])

    def get_company_report(self, symbol: str, sections=None) -> dict:
        if symbol in self.fail:
            raise SectorsAPIError(404, f"/v2/company/report/{symbol}/", "not found")
        return _load(symbol)

    def get_sgx_company_report(self, symbol: str, sections=None) -> dict:
        # SGX fixtures don't exist; simulate a valid SGX payload with no EV inputs.
        return {
            "symbol": symbol + ".SI",
            "company_name": "SGX " + symbol,
            "overview": {
                "sector": "Financials",
                "sub_sector": "Banks",
                "market_cap": 159943278592,
            },
            "financials": {"eps": 3.8, "historical_financials": []},
        }

    def get_mining_companies(self, has_financials: bool | None = None) -> dict:
        # Return an empty list so the dynamic slug map falls back to the seed map
        # (MINING_SLUGS). Tests that need the live map pass explicit ``mining_slugs``.
        return {"results": [], "pagination": {"has_next": False}}

    def get_mining_performance(self, slug: str) -> dict:
        # MDKA and ADRO have mining-performance fixtures under fixtures/mining/.
        for ticker, sl in {"MDKA": "pt-merdeka-copper-gold-tbk",
                           "ADRO": "pt-alamtri-resources-indonesia-tbk"}.items():
            if slug == sl:
                path = os.path.join(FIXTURES, "mining", f"{ticker}_performance.json")
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
        raise SectorsAPIError(404, f"/v2/mining/.../{slug}/", "no data")


def test_partitions_bank_generic() -> None:
    client = FakeClient()
    result = screen_tickers(["BBCA", "TLKM", "ASII"], client=client)

    assert len(result.screenable) == 3, [e.ticker for e in result.excluded]
    assert len(result.excluded) == 0
    tickers = {c.ticker for c in result.screenable}
    assert tickers == {"BBCA.JK", "TLKM.JK", "ASII.JK"}
    print("PASS partitions: 3 screenable (bank + 2 generic), 0 excluded\n")


def test_data_quality_exclusion() -> None:
    # ASRM (insurance) has no cash and no ebitda -> screenable=False, excluded.
    client = FakeClient()
    result = screen_tickers(["ASRM"], client=client)

    assert len(result.screenable) == 0
    assert len(result.excluded) == 1
    assert result.excluded[0].ticker == "ASRM"
    # Pin the EXACT reason, not a fuzzy substring — so a change in exclusion
    # wording or a wrong exclusion cause can't slip through.
    assert result.excluded[0].reason == "missing ebitda", result.excluded[0].reason
    print(f"PASS data-quality exclusion: ASRM excluded (reason: {result.excluded[0].reason})\n")


class CountingClient(FakeClient):
    """FakeClient that counts company-report calls, proving cache reuse."""

    def __init__(self, fail: list[str] | None = None) -> None:
        super().__init__(fail=fail)
        self.report_calls = 0

    def get_company_report(self, symbol: str, sections=None) -> dict:
        self.report_calls += 1
        return super().get_company_report(symbol, sections=sections)


def test_sgx_routes_to_sgx_endpoint() -> None:
    client = FakeClient()
    result = screen_tickers(["D05.SI"], client=client)

    # SGX is NOT yet mapped (no SGX mapper exists); it is excluded with an
    # honest reason rather than silently mis-routed through the IDX mapper.
    assert len(result.screenable) == 0
    assert len(result.excluded) == 1
    assert result.excluded[0].ticker == "D05.SI"
    assert "SGX" in result.excluded[0].reason
    print(f"PASS SGX routing: SGX excluded honestly (reason: {result.excluded[0].reason})\n")


def test_cache_reuse() -> None:
    import tempfile, shutil

    # Use a fresh temp dir per run so a previous run's leftover cache can't
    # leak state into this assertion (the WAL file can resist deletion on Windows).
    tmpdir = tempfile.mkdtemp(prefix="screener_cache_test_")
    db_path = os.path.join(tmpdir, "cache.db")

    from cache.sqlite_cache import SQLiteCache
    cache = SQLiteCache(db_path)

    client = CountingClient()
    # First run: pulls from the API (2 calls for BBCA + TLKM).
    screen_tickers(["BBCA", "TLKM"], client=client, cache=cache)
    assert client.report_calls == 2, client.report_calls

    # Second run with a fresh client: should be served entirely from cache.
    client2 = CountingClient()
    screen_tickers(["BBCA", "TLKM"], client=client2, cache=cache)
    assert client2.report_calls == 0, client2.report_calls

    shutil.rmtree(tmpdir, ignore_errors=True)
    print("PASS cache reuse: 2nd run served from cache (0 API calls)\n")


def test_bad_ticker_does_not_abort_batch() -> None:
    client = FakeClient(fail=["NOTREAL"])
    result = screen_tickers(["BBCA", "NOTREAL", "TLKM"], client=client)

    # BBCA + TLKM still screen; NOTREAL is excluded with a reason.
    assert len(result.screenable) == 2, [e.ticker for e in result.excluded]
    assert len(result.excluded) == 1
    assert result.excluded[0].ticker == "NOTREAL"
    assert "pull/map failed" in result.excluded[0].reason
    print(f"PASS bad ticker isolated: 2 screenable, 1 excluded (NOTREAL)\n")


def test_mining_join() -> None:
    client = FakeClient()
    result = screen_tickers(["MDKA"], client=client, mining_slugs={"MDKA": "pt-merdeka-copper-gold-tbk"})

    # MDKA is a miner -> goes into `miners`, not `screenable`.
    assert len(result.miners) == 1, (len(result.screenable), len(result.miners))
    m = result.miners[0]
    assert m.comp.ticker == "MDKA.JK"
    assert m.overlay.total_reserves_Mt == Decimal("430.8")
    assert m.ev_per_tonne_reserves.available is True
    print(f"PASS mining join: MDKA reserves={m.overlay.total_reserves_Mt} Mt, "
          f"EV/t={m.ev_per_tonne_reserves.value}\n")


def main() -> None:
    test_partitions_bank_generic()
    test_data_quality_exclusion()
    test_bad_ticker_does_not_abort_batch()
    test_mining_join()
    test_sgx_routes_to_sgx_endpoint()
    test_cache_reuse()
    print("ALL SCREENER TESTS PASSED")


if __name__ == "__main__":
    main()
