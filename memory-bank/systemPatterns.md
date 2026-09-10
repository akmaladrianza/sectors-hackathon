# System Patterns

## Architecture
```
Sectors_Hackathon/
├── models/                     # package of Pydantic schemas
│   ├── __init__.py             # re-exports CompanyComp, Currency
│   └── company_comp.py         # CompanyComp model + Currency enum
├── tests/
│   └── test_company_comp.py    # script-style test runner (no pytest)
└── memory-bank/                # this documentation
```

The project is currently a single self-contained data model. There is no service,
API, or persistence layer yet. The pattern is a classic **single model / schema
package** ready to be consumed by a future screener.

## Key design patterns

### 1. Derived (computed) multiples, not stored fields
Valuation multiples are implemented with `@computed_field @property`. They are
recomputed from raw inputs on every access, so they can never diverge from their
underlying figures. A missing/zero input yields `None` rather than an exception.

### 2. Optional everywhere except stable identifiers
Only `ticker`, `company_name`, and `sector` are required (non-optional). Everything
else is `Optional`, reflecting that real data feeds have gaps. `ticker`/
`company_name`/`sector` enforce `min_length=1` and are validated as non-empty strings.

### 3. Decimal for monetary magnitudes
All monetary fields (`market_cap`, `price`, `shares_outstanding`, `total_debt`,
`cash_and_equivalents`, `total_assets`, `revenue`, `ebitda`, `ebit`, `net_income`,
`eps`) use `Decimal` to avoid floating-point precision error on large figures.

### 4. Cross-field backfill via `model_validator(mode="after")`
`_fill_market_cap` derives `market_cap = price * shares_outstanding` when
`market_cap` is omitted but both inputs are present.

### 5. Explicit screening exclusion instead of silent skipping
`is_screenable` (a `computed_field`, `True` iff `exclusion_reasons` is empty) plus
`exclusion_reasons` (a `computed_field` returning a human-readable list) let
downstream code report *why* a peer was excluded.

### 6. JSON float serialization for Decimals
A `@field_serializer(..., when_used="json")` converts the `Decimal` monetary fields
(and `enterprise_value`) to floats for JSON output, so clients receive numeric
values rather than Pydantic's default string representation. The code deliberately
avoids the deprecated `json_encoders` config, which is slated for removal in Pydantic V3.

### 7. Enum for currency
`Currency(str, Enum)` holds USD/EUR/IDR/SGD/GBP/JPY. It inherits `str` so values
serialize as plain strings. No FX conversion logic exists yet — the enum is the
hook for future cross-currency normalization.

## Formulas implemented
- `enterprise_value = market_cap + total_debt - cash_and_equivalents`
  (`None` if `market_cap` is missing; missing debt/cash treated as 0)
- `ev_to_ebitda = enterprise_value / ebitda` (`None` if EV missing or EBITDA
  missing/zero)
- `ev_to_revenue = enterprise_value / revenue` (`None` if EV missing or revenue
  missing/zero)
- `pe_ratio = price / eps` (`None` if price missing or EPS missing/zero; computed from
  `price`, not market cap)
- `price_to_book = market_cap / total_assets` (**approximation** — true P/B needs
  `total_assets - total_liabilities`, which is not modeled yet)

## Exclusion reasons
- `"missing market_cap"` — no market cap (and not backfillable)
- `"missing ebitda"` — EBITDA absent
- `"non-positive ebitda"` — EBITDA <= 0
