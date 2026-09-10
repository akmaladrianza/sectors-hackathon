# Project Brief

## Overview
`Sectors_Hackathon` is a **comparable-companies ("comps") valuation screener**. It is
the codebase being built for the "Sectors" hackathon.

A comps screener lets a financial analyst select a universe of peer companies and
compare them on valuation multiples (EV/EBITDA, EV/Revenue, P/E, P/B) to identify
which peers are cheap or expensive relative to the group.

## Core Requirements (so far)
1. **A robust data model** for a single comparable company (`CompanyComp`), capturing
   identifiers, market data, balance-sheet figures, income-statement profitability,
   growth, margins, and metadata.
2. **Accurate, always-consistent valuation multiples** — derived from raw inputs
   rather than stored separately, so they can never drift or go stale.
3. **Graceful handling of missing data** — real-world financial feeds are frequently
   incomplete, so the model must degrade to `None` instead of raising.
4. **Explicit screening exclusions** — distinguish "peer with no usable data" from
   "peer that failed a range filter", and report *why* a peer was excluded.
5. **Cross-market support** — a `Currency` enum (USD, EUR, IDR, SGD, GBP, JPY) lays the
   groundwork for cross-currency normalization.

## Scope: In vs Out
**In scope (current):**
- The `CompanyComp` Pydantic data model and its validation/derivation logic.

**Out of scope (not built yet — see `progress.md`):**
- Screener/aggregation/ranking logic across multiple peers.
- Data ingestion / feed layer.
- Currency conversion / FX normalization logic (the enum exists, no conversion does).
- Any UI, API, or CLI.

## Goals
- Correctness over completeness: the model must never produce a wrong multiple or
  crash on partial inputs.
- Auditability: downstream consumers (and eventually UIs) can report *reasons* a peer
  was excluded, not just that it was skipped.
- Precision: use `Decimal` for monetary magnitudes to avoid floating-point error on
  large financial figures.

## Non-Goals / Unknowns
- Specific target data source, deployment target, UI/API shape, and the exact
  hackathon deliverable are **not yet defined** in the codebase. (Open questions for
  the user — see `activeContext.md`.)
