"""Screener package.

Orchestrates a batch of tickers through the data pipeline: pull → map → join
mining overlay (where applicable) → partition into screenable vs. excluded peers.
"""

from screener.screener import (
    Exclusion,
    ScreenedMiner,
    ScreenerResult,
    screen_tickers,
)

__all__ = ["Exclusion", "ScreenedMiner", "ScreenerResult", "screen_tickers"]
