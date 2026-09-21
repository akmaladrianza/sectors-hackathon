"""Map a cached Sectors ``company_report`` payload into a :class:`CompanyComp`.

Two templates (discovered empirically, see architectureOverview.md / progress.md):
- ``bank`` (67 fields)  -> ``overview.sub_sector == "Banks"``; no
  ``cash_and_equivalents`` field — cash is ``total_cash_and_due_from_banks``
  *alone* (that aggregate already includes ``cash_only`` as a sub-line; summing
  ``cash_only`` on top would double-count — verified against BBCA's audited
  FY2025 balance sheet).
- ``generic`` (39 fields) -> everything else (telecom, industrials, consumer,
  energy, materials, insurance, multifinance, software/tech). Direct 1:1 names.

The split is on ``sub_sector``, not ``sector == "Financials"``: insurance (ASRM)
and multifinance (ADMF) are Financials but generic; fintech (GOTO) is Technology
and generic. Missing fields always degrade to ``None`` (never patched).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Optional, Tuple

from pydantic import ValidationError

from models.company_comp import CompanyComp, Currency


class Template(str, Enum):
    """The two financial-reporting schemas the Sectors API emits."""

    GENERIC = "generic"
    BANK = "bank"


class MapperError(Exception):
    """Raised when a report payload cannot be mapped to a ``CompanyComp``.

    Carries the offending ticker so a batch caller can report *which* company
    failed without losing the underlying validation detail.
    """

    def __init__(self, ticker: str, cause: Exception) -> None:
        self.ticker = ticker
        self.cause = cause
        super().__init__(f"failed to map ticker {ticker!r}: {cause}")


def classify_template(overview: Optional[dict]) -> Template:
    """Choose the template from ``overview.sub_sector`` (``"Banks"`` => bank)."""
    if not overview:
        return Template.GENERIC
    sub_sector = (overview.get("sub_sector") or "").strip().lower()
    if sub_sector == "banks":
        return Template.BANK
    return Template.GENERIC


def _dec(value) -> Optional[Decimal]:
    """Coerce a JSON number to ``Decimal``; ``None`` for missing/garbage input.

    A single malformed numeric field degrades to ``None`` (treated like any other
    missing value) rather than aborting the whole mapping. Only ``None``, a
    ``Decimal``, or a value ``str()``-convertible to ``Decimal`` is accepted.
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _fiscal_period(row: Optional[dict]) -> Optional[str]:
    if not row or row.get("year") is None:
        return None
    return "FY" + str(row["year"])


class ReportMapper:
    """Maps a Sectors ``company_report`` payload into a ``CompanyComp``."""

    def map(self, payload: dict, year: Optional[int] = None) -> CompanyComp:
        """Build a ``CompanyComp``; ``year`` picks the historical-financials row
        (default: latest). ``overview`` supplies identifiers/market data,
        ``financials`` supplies balance-sheet + income-statement figures.

        Raises :class:`MapperError` if the payload cannot produce a valid model
        (e.g. missing/empty required identifiers), with the ticker attached.
        """
        overview = payload.get("overview") or {}
        financials = payload.get("financials") or {}
        valuation = payload.get("valuation") or {}

        template = classify_template(overview)
        row = self._select_financial_row(financials, year)

        ticker = payload.get("symbol") or ""
        company_name = payload.get("company_name") or ""
        sector = overview.get("sector") or ""

        try:
            return CompanyComp(
                ticker=ticker,
                company_name=company_name,
                sector=sector,
                sub_sector=overview.get("sub_sector"),
                industry=overview.get("industry"),
                country="IDN",  # all current seeds are IDX; SGX mapping is TODO
                exchange="IDX",
                currency=Currency.IDR,
                price=_dec(overview.get("last_close_price")),
                shares_outstanding=_dec(row.get("outstanding_shares")) if row else None,
                market_cap=_dec(overview.get("market_cap")),
                total_debt=_dec(row.get("total_debt")) if row else None,
                cash_and_equivalents=self._resolve_cash(template, row),
                total_assets=_dec(row.get("total_assets")) if row else None,
                total_liabilities=_dec(row.get("total_liabilities")) if row else None,
                total_equity=_dec(row.get("total_equity")) if row else None,
                revenue=_dec(row.get("revenue")) if row else None,
                ebitda=_dec(row.get("ebitda")) if row else None,
                ebit=_dec(row.get("ebit")) if row else None,
                net_income=_dec(row.get("earnings")) if row else None,
                eps=_dec(financials.get("eps")),
                intrinsic_value=_dec(valuation.get("intrinsic_value")),
                forward_pe=self._to_float(valuation.get("forward_pe")),
                pe_peer_avg=self._latest_peer_avg(valuation, "pe_peer_avg"),
                pb_peer_avg=self._latest_peer_avg(valuation, "pb_peer_avg"),
                ps_peer_avg=self._latest_peer_avg(valuation, "ps_peer_avg"),
                as_of_date=overview.get("latest_close_date"),
                fiscal_period=_fiscal_period(row),
            )
        except ValidationError as exc:
            raise MapperError(ticker or "?", exc) from exc

    @staticmethod
    def _select_financial_row(
        financials: dict, year: Optional[int]
    ) -> Optional[dict]:
        hist = financials.get("historical_financials") or []
        if not hist:
            return None
        if year is None:
            # Defensive: pick the max year rather than assuming ascending order.
            return max(hist, key=lambda r: r.get("year") or 0)
        for row in hist:
            if row.get("year") == year:
                return row
        return None

    @staticmethod
    def _to_float(value) -> Optional[float]:
        """Coerce a JSON number to ``float``; ``None`` for missing/garbage input."""
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _latest_peer_avg(valuation: dict, key: str) -> Optional[float]:
        """Read the most-recent peer-average multiple from ``historical_valuation``.

        Sectors' ``valuation.historical_valuation`` is a per-year list; each row
        carries ``pe_peer_avg``/``pb_peer_avg``/``ps_peer_avg``. We take the latest
        year's value (matching how we pick the latest financial row). Returns
        ``None`` when the section is absent or the field is missing/``null``.
        """
        hist = valuation.get("historical_valuation") or []
        if not hist:
            return None
        latest = max(hist, key=lambda r: r.get("year") or 0)
        return ReportMapper._to_float(latest.get(key))

    @staticmethod
    def _resolve_cash(template: Template, row: Optional[dict]) -> Optional[Decimal]:
        """Resolve ``cash_and_equivalents`` depending on the template.

        For banks, ``total_cash_and_due_from_banks`` is already the aggregate
        cash line (it *includes* ``cash_only`` as a sub-line — verified against
        BBCA's audited FY2025 balance sheet, where Kas + Giro BI + Giro bank lain
        sum to the total). Summing ``cash_only`` on top would double-count cash.
        """
        if not row:
            return None
        if template == Template.BANK:
            return _dec(row.get("total_cash_and_due_from_banks"))
        return _dec(row.get("cash_and_equivalents"))


def report_to_company_comp(
    payload: dict, year: Optional[int] = None
) -> Tuple[CompanyComp, Template]:
    """Map a cached report payload to a ``CompanyComp``.

    Returns ``(comp, template)`` so callers can surface *which* of the two
    templates (bank vs generic) produced the row — the minimal provenance needed
    for the "defensible by design" goal without bloating the model's fields.
    """
    return ReportMapper().map(payload, year=year), classify_template(
        payload.get("overview")
    )
