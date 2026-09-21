"""Minimal Sectors v2 API client.

Authentication
--------------
The Sectors API authenticates via an ``Authorization`` header carrying the raw
API key (NOT a ``Bearer`` token). The key is read from the ``SECTORS_API_KEY``
environment variable, loaded from a local ``.env`` file via ``python-dotenv``.

Credit accounting (from the API docs)
-------------------------------------
- 2xx success     -> consumes credits (endpoint's stated cost)
- 404 not found   -> consumes 1 credit (a well-formed lookup was run)
- 400 bad request -> free
- 401/403 auth    -> free
- 429 rate limit  -> free
- 5xx server err  -> free

We therefore raise on any non-2xx response rather than retry-looping, which
could burn credits or hammer a rate limit pointlessly.
"""

from __future__ import annotations

import os
from typing import Optional

import requests
from dotenv import load_dotenv

BASE_URL = "https://api.sectors.app"


class SectorsAPIError(Exception):
    """Raised when a Sectors API request does not return a 2xx response."""

    def __init__(self, status_code: int, url: str, detail: object = None) -> None:
        self.status_code = status_code
        self.url = url
        self.detail = detail
        super().__init__(
            f"Sectors API error {status_code} for {url}: {detail!r}"
        )


class SectorsClient:
    """Thin HTTP client for the Sectors v2 API.

    ``request`` is exposed as a module-level-overridable method so callers (and
    tests) can count or stub actual network traffic to prove cache behaviour.
    """

    def __init__(self, api_key: Optional[str] = None) -> None:
        load_dotenv()  # no-op if .env is absent; fills os.environ otherwise
        self.api_key = api_key or os.environ.get("SECTORS_API_KEY")
        if not self.api_key:
            raise SectorsAPIError(
                401,
                BASE_URL,
                "Missing SECTORS_API_KEY (set it in .env or the environment).",
            )
        self.session = requests.Session()
        self.session.headers.update({"Authorization": self.api_key})

    @staticmethod
    def normalize_symbol(symbol: str) -> str:
        """Return the bare 4-letter IDX symbol (upper-cased, ``.jk`` stripped)."""
        return symbol.strip().upper().split(".")[0]

    def request(self, url: str, params: Optional[dict] = None) -> dict:
        """Perform a GET and return parsed JSON, raising on non-2xx."""
        response = self.session.get(url, params=params)
        if response.status_code != 200:
            # Try to surface the API's own error payload if it's JSON.
            detail = None
            try:
                detail = response.json()
            except Exception:
                detail = response.text
            raise SectorsAPIError(response.status_code, url, detail)
        return response.json()

    def get_company_report(
        self, symbol: str, sections: Optional[list[str]] = None
    ) -> dict:
        """Fetch a company report for an IDX symbol.

        ``sections`` may restrict which report sections are returned
        (``overview``, ``valuation``, ``future``, ``financials``, ``dividend``,
        ``management``, ``ownership``, ``peers``). Omitting it returns all
        eight and costs 8 credits; requesting ``N`` sections costs ``N``.
        """
        symbol = self.normalize_symbol(symbol)
        url = f"{BASE_URL}/v2/company/report/{symbol}/"
        params = None
        if sections:
            params = {"sections": ",".join(sections)}
        return self.request(url, params=params)

    def get_news(
        self,
        symbols: Optional[list[str]] = None,
        sub_sector: Optional[str] = None,
        sector: Optional[str] = None,
        keyword: Optional[str] = None,
        tags: Optional[list[str]] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        limit: int = 5,
    ) -> dict:
        """Fetch IDX news articles from Sectors' own ``GET /v2/news/`` endpoint.

        Filter by ticker ``symbols`` (comma-joined), ``sub_sector``/``sector`` slugs,
        a case-insensitive title ``keyword``, ``tags``, and optional ``start``/``end``
        ISO dates. Returns ``{results: [...], pagination: {...}}`` where each result
        carries ``title``, ``body``, ``source`` (URL), ``timestamp``, ``sub_sector``,
        ``tags`` and ``symbols``. This is the Sectors-native replacement for any
        third-party news source.
        """
        params: dict = {"extension": "idx", "limit": str(limit)}
        if symbols:
            params["symbols"] = ",".join(symbols)
        if sub_sector:
            params["sub_sector"] = sub_sector
        if sector:
            params["sector"] = sector
        if keyword:
            params["keyword"] = keyword
        if tags:
            params["tags"] = ",".join(tags)
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        return self.request(f"{BASE_URL}/v2/news/", params=params)

    def search_companies(
        self, keyword: str, limit: int = 10
    ) -> dict:
        """List IDX companies whose name fuzzy-matches ``keyword``.

        Uses the Companies Screener's structured SQL-like filter
        ``company_name like '%<keyword>%'`` (case-insensitive). Returns the screener
        payload; each result carries ``symbol``, ``company_name``, ``sub_sector`` etc.
        Used to power the "type a company name -> suggested ticker" input.
        """
        params = {
            "where": f"company_name like '%{keyword}%'",
            "limit": str(limit),
        }
        return self.request(f"{BASE_URL}/v2/companies/", params=params)

    def get_sgx_company_report(
        self, symbol: str, sections: Optional[list[str]] = None
    ) -> dict:
        """Fetch a company report for an SGX symbol (``.SI``-suffixed).

        SGX has only 4 sections (``overview``, ``valuation``, ``financials``,
        ``dividend``); there is no peers/management/ownership/future. Note the SGX
        schema exposes ``total_liabilities``/``total_equity`` but NOT ``total_debt``/
        ``cash_and_equivalents``, so EV-based multiples cannot be computed for SGX.
        """
        symbol = symbol.strip().upper().replace(".SI", "")
        url = f"{BASE_URL}/v2/sgx/company/report/{symbol}/"
        params = None
        if sections:
            params = {"sections": ",".join(sections)}
        return self.request(url, params=params)

    # --- Mining extension ---------------------------------------------------

    def get_mining_companies(
        self, keyword: Optional[str] = None, has_financials: Optional[bool] = None
    ) -> dict:
        """List mining companies (supports ``keyword``, ``has_financials`` filters).

        Returns a paginated list; each item carries ``slug``, ``symbol`` (null for
        unlisted), ``name``, ``company_type``, ``commodity_type``.
        """
        params = {}
        if keyword:
            params["keyword"] = keyword
        if has_financials is not None:
            params["has_financials"] = "true" if has_financials else "false"
        return self.request(f"{BASE_URL}/v2/mining/companies/", params=params or None)

    def get_mining_performance(self, slug: str) -> dict:
        """Per-commodity production/reserve data for a mining company slug."""
        return self.request(f"{BASE_URL}/v2/mining/companies/performance/{slug}/")

    def get_mining_financials(self, slug: str) -> dict:
        """USD financials for a mining company slug (404 -> no data)."""
        return self.request(f"{BASE_URL}/v2/mining/companies/financials/{slug}/")

    def get_mining_sales_destination(self, slug: str) -> dict:
        """Country-level sales-destination breakdown (404 -> no data)."""
        return self.request(f"{BASE_URL}/v2/mining/sales-destination/{slug}/")
