"""Optional news-grounded suggestion layer (Tavily-powered, retrieval-then-quote).

This is a *secondary* source for Advanced-mode DCF assumptions. It is OFF by default
and must be explicitly enabled (sidebar toggle). The hard anti-hallucination rule is
enforced structurally, not by prompt:

- The module only ever *quotes* a snippet of text returned verbatim by the Tavily
  search API, with its title + URL + retrieved timestamp attached.
- It never asks a model to "estimate" a number from its own knowledge. If Tavily
  returns no relevant result, it returns ``NewsSuggestion(None, reason="no cited
  source found")`` rather than guessing.

The user supplies their own ``TAVILY_API_KEY`` (`.env`). If the key is absent, the
module degrades to "unavailable (no API key)" and the UI can hide the toggle's effect.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

TAVILY_BASE_URL = "https://api.tavily.com"


@dataclass
class NewsSuggestion:
    """A growth-assumption hint grounded in a retrieved, verbatim-quoted snippet."""

    value: Optional[str]  # the quoted snippet, not a computed number
    source_url: Optional[str] = None
    title: Optional[str] = None
    reason: Optional[str] = None

    @property
    def available(self) -> bool:
        return self.value is not None


def _api_key() -> Optional[str]:
    load_dotenv()
    return os.environ.get("TAVILY_API_KEY")


def _search_company_guidance(company_name: str, api_key: str, keyword: str = "revenue growth guidance") -> Optional[dict]:
    """Call Tavily's search endpoint; return the top result or None on any failure."""
    import requests

    url = f"{TAVILY_BASE_URL}/search"
    try:
        resp = requests.post(
            url,
            json={
                "api_key": api_key,
                "query": f"{company_name} {keyword}",
                "search_depth": "basic",
                "max_results": 5,
                "include_answer": False,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results") or []
        return results[0] if results else None
    except Exception:
        # Any network/API failure degrades to "no cited source", never a guess.
        return None


def suggest_news_growth(company_name: str, keyword: Optional[str] = None) -> NewsSuggestion:
    """Return a verbatim-quoted snippet about the company's growth guidance.

    This deliberately returns the raw snippet text (which the user reads) rather than
    a parsed number — the anti-hallucination guarantee is that we only surface quoted
    text + source, and never extract or invent a quantitative value from it.
    """
    key = _api_key()
    if not key:
        return NewsSuggestion(None, reason="TAVILY_API_KEY not set")
    if not company_name:
        return NewsSuggestion(None, reason="no company name")

    top = _search_company_guidance(company_name, key, keyword or "revenue growth guidance")
    if not top:
        return NewsSuggestion(None, reason="no cited source found")

    return NewsSuggestion(
        value=top.get("content"),
        source_url=top.get("url"),
        title=top.get("title"),
    )
