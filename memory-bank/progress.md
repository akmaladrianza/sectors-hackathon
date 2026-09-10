# Progress

## What works
- `CompanyComp` Pydantic model fully implemented (`models/company_comp.py`):
  - Identifiers, market data, balance-sheet, income-statement, growth, margin, and
    metadata fields.
  - `model_validator` backfills `market_cap` from `price * shares_outstanding`.
  - Derived `computed_field` multiples: `enterprise_value`, `ev_to_ebitda`,
    `ev_to_revenue`, `pe_ratio`, `price_to_book`.
  - `is_screenable` flag and `exclusion_reasons` list for auditability.
  - `field_serializer` emits monetary fields as floats in JSON mode.
- `Currency` enum (USD, EUR, IDR, SGD, GBP, JPY).
- `models/__init__.py` re-exports `CompanyComp`, `Currency`.
- Full test suite passing (verified by running `python -m tests.test_company_comp`):
  all 9 scenarios PASS — full-data, missing-market-cap, backfill, missing-ebitda,
  zero-ebitda, screening partition, JSON serialization, negative-value rejection,
  empty-string-identifier rejection.

## What's left to build
- **Screener / aggregation / ranking logic** across multiple peers (currently only the
  per-company model exists).
- **Data ingestion / loading layer** (source TBD).
- **Currency normalization / FX conversion** (enum exists; no conversion logic).
- **True P/B** — `price_to_book` currently approximates with `market_cap / total_assets`;
  it needs `total_equity` (assets - liabilities) to be correct.
- **Dependency manifest** (`requirements.txt` / `pyproject.toml`).
- **README** and possibly CI/pytest.

## Current status
- Project is at its initial commit (model + tests only). Memory bank freshly
  initialized.

## Known issues
- `price_to_book` is documented as an approximation (uses `total_assets` as a proxy
  for equity of book value).
- No cross-currency conversion — the `Currency` enum exists but values are not
  normalized, so cross-market comparisons would be wrong until FX handling is added.
- Running tests via `python tests/test_company_comp.py` (script path) fails due to
  import path; must use `python -m tests.test_company_comp`.

## Evolution of decisions
- Chose `Decimal` for monetary fields (precision) over `float`.
- Chose computed/derived multiples over stored fields (consistency, no staleness).
- Chose explicit `is_screenable` + `exclusion_reasons` over silently skipping peers.
- Chose to avoid deprecated `json_encoders` (removed in Pydantic V3), using
  `field_serializer` instead.
- Chose a hand-rolled script test runner over pytest (no test framework installed).
