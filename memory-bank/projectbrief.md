# Project Brief

## Overview
`Sectors_Hackathon` is the codebase for **Mimir** (working name, pending trademark check) —
a fundamental-analysis workflow for the Indonesian capital market (IDX) and Singapore
(SGX), built on the Sectors v2 API for the Sectors Hackathon 2026.

At its core it is a **comparable-companies ("comps") valuation screener**, extended with a
**reserve-adjusted mining overlay** and a **two-mode valuation architecture** (Simple /
Advanced) so the same engine serves two different audiences without diluting either.

Seed tickers: BBCA (comps test case) and MDKA (mining overlay test case).

## Problem statement
Indonesia's capital market coverage stops at LQ45 and a handful of large caps; everything
else — and every mining name whose value depends on reserves rather than trailing earnings
— is underserved by both retail-facing screeners and institutional-grade valuation tooling.
Mimir automates the mechanical layers of fundamental analysis (comps, reserve-adjusted
metrics, DCF scaffolding) so a coverage-gap self-directed investor or a boutique M&A
advisor can get a defensible, source-cited valuation output in minutes rather than days.

## Core Requirements
1. **A robust data model** for a single comparable company (`CompanyComp`) — implemented.
   Captures identifiers, market data, balance-sheet figures, income-statement
   profitability, growth, margins, and metadata.
2. **Accurate, always-consistent valuation multiples** — derived from raw inputs rather
   than stored separately, so they can never drift or go stale. Implemented for standard
   comps (EV/EBITDA, EV/Revenue, P/E, P/B).
3. **Graceful handling of missing data** — the model degrades to `None`/`N/A` instead of
   raising. Implemented.
4. **Explicit screening exclusions** — distinguish "peer with no usable data" from "peer
   that failed a filter," and report *why*. Implemented for the single-peer model;
   multi-peer partitioning/ranking not yet built.
5. **Two-mode valuation architecture** (decided, not yet built):
   - **Simple mode** — comps + reserve-adjusted comps (EV/tonne of reserves, EV/tonne of
     production, reserve life). Both are arithmetic on current disclosed data; no
     forecasting. Audience: the coverage-gap self-directed investor.
   - **Advanced mode** — everything in Simple, plus corporate DCF (sector-conditional
     proxy defaults, "expected rate of return" in place of textbook WACC) and true
     per-asset NAV for miners. Both require forecasting, which is why they're grouped
     together. Audience: M&A advisors and other power users.
6. **Reserve-adjusted mining overlay** (decided, not yet built) — EV/tonne of reserves,
   EV/tonne of production, reserve life, export-destination concentration, sourced from
   Sectors' mining.sectors.app extension. Must carry a "self-reported, not independently
   audited" flag and a reserve price-deck vintage flag (open item — see
   `activeContext.md`).
7. **AI assistant for Advanced-mode input-filling** (decided, not yet built) — helps
   populate DCF assumptions (revenue growth, working capital, capex) and answers research
   lookups (e.g., asset useful life). Hard rule, non-negotiable: every value it supplies
   must carry a stated, verifiable reference. Sectors-native inputs (read from the cache)
   carry no citation risk and are exempt from this rule; external/general-knowledge
   lookups must cite from a small curated reference set, not open-ended generation.
8. **Sector-conditional proxy library** (planned; implementation now uses
   revenue CAGR, NOT production × price — see `progress.md` for the honest note since
   multi-year production history isn't stored) — default DCF assumptions
   branch by sector (e.g., bank → GDP + spread, miner → historical growth × commodity
   price assumption, generic → historical average) rather than one formula for every
   company. To be
   back-tested against Sectors' own historical financials before being trusted as a
   default (open item).
9. **Cross-market currency support** — a `Currency` enum exists (USD, EUR, IDR, SGD, GBP,
   JPY); no conversion logic yet. **Flag**: this enum is broader than the project's actual
   IDX/SGX scope (EUR/GBP/JPY aren't needed; USD likely is, for commodity-priced mining
   inputs) — worth trimming when the model is next touched.

## Scope: In vs Out
**In scope, implemented:**
- The `CompanyComp` Pydantic data model and its validation/derivation logic.
- Sectors v2 API client (`SectorsClient`, `GET /v2/company/report/{symbol}/`) and SQLite
  cache (`SQLiteCache`, keyed on company + period + endpoint), live-verified against BBCA.

**In scope, decided but not yet built:**
- Map cached Sectors report JSON into `CompanyComp` fields.
- Streamlit as the deliverable UI (single-user, local).
- Screener/aggregation/ranking logic across multiple peers.
- Mining overlay (reserve-adjusted metrics).
- Simple / Advanced two-mode valuation architecture, including DCF and true per-asset NAV.
- AI assistant for Advanced-mode input-filling, bound by the citation hard rule.
- Sector-conditional proxy library.
- Currency normalization / FX conversion.

**Permanently out of scope (decided against):**
- Precedent transactions — a control-premium concept irrelevant to secondary-market share
  purchases; dropped from the tool entirely.
- Designing for the low-literacy / sentiment-driven / "gambler" retail segment — a
  different problem (financial education) that this product doesn't attempt to solve.

## Goals
- Correctness over completeness: the model must never produce a wrong multiple or crash
  on partial inputs.
- Auditability: downstream consumers can report *reasons* a peer was excluded, not just
  that it was skipped.
- Precision: `Decimal` for monetary magnitudes to avoid floating-point error on large
  financial figures.
- **Defensibility**: every number in the product — comps, mining overlay, or AI-assisted —
  must trace to a source. This is the product's core promise, not a nice-to-have.

## Hackathon constraints (Sectors Hackathon 2026 official rules)
- No project code before 19 August 2026 (build period start); repository must be created
  during the build period.
- The product must lose its core functionality if Sectors data is removed — Sectors data
  is a required, load-bearing input, not decorative.
- Automated trade execution is prohibited in every track — analysis/screening/scoring
  only, never placing or executing orders.
- The product must not read as financial advice — position as an information/analysis
  tool, include a disclaimer.
- Submission freezes the repository (only exception: rotating a leaked credential).
- IP remains entirely with the participant — the hackathon is explicitly a valid stepping
  stone for continued development.

## Open Questions
See `activeContext.md` for the current list. Data source, deliverable shape, and market
scope (previously open here) are now decided — see Core Requirements above.
