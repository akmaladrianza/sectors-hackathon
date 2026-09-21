"""Sectors-native news grounding (retrieval-then-quote, no third-party source).

Replaces the earlier Tavily-backed layer. The only news source is Sectors' own
``GET /v2/news/`` endpoint, so every surfaced item is already the product's own
load-bearing data (and carries no external-dependency or citation-fabrication risk).

The anti-hallucination rule is enforced structurally: this module never parses or
interprets a growth figure from an article. It returns verbatim ``title`` / ``body``
with the source URL + timestamp, and the user reads them to inform their own DCF
assumption. No result -> ``NewsSuggestion(None, reason="no news found")``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sectors_client.client import SectorsClient, SectorsAPIError


@dataclass
class NewsSuggestion:
    """One verbatim-quoted news item (never interpreted into a number)."""

    title: Optional[str] = None
    body: Optional[str] = None
    source: Optional[str] = None
    timestamp: Optional[str] = None
    reason: Optional[str] = None

    @property
    def available(self) -> bool:
        return self.title is not None


def suggest_company_news(
    client: SectorsClient,
    symbols: Optional[list[str]] = None,
    company_name: Optional[str] = None,
    limit: int = 3,
) -> list[NewsSuggestion]:
    """Return up to ``limit`` Sectors-native news items for a company/ticker set.

    Prefers an exact ticker filter (``symbols``) when available; otherwise falls back
    to a title ``keyword`` match on the company name. Degrades cleanly to an empty
    list on any API error (never a fabricated article).
    """
    try:
        if symbols:
            payload = client.get_news(symbols=symbols, limit=limit)
        elif company_name:
            payload = client.get_news(keyword=company_name, limit=limit)
        else:
            return [NewsSuggestion(reason="no ticker or company name to search")]
    except SectorsAPIError as exc:
        return [NewsSuggestion(reason=f"Sectors news unavailable: {exc}")]
    except Exception as exc:  # noqa: BLE001
        return [NewsSuggestion(reason=f"news lookup failed ({type(exc).__name__})")]

    results = payload.get("results") or []
    out = []
    for item in results:
        out.append(
            NewsSuggestion(
                title=item.get("title"),
                body=item.get("body"),
                source=item.get("source"),
                timestamp=item.get("timestamp"),
            )
        )
    return out if out else [NewsSuggestion(reason="no news found")]
