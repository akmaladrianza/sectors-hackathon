# Mimir — Comparable-company valuation screener (Sectors Hackathon 2026)

Mimir (working name) automates the mechanical layers of fundamental analysis for the
Indonesian (IDX) and Singapore (SGX) listed markets, built on the **Sectors v2 API**.

It turns a list of tickers into a defensible, source-cited **comps table** — and, for
mining names, a **reserve-adjusted overlay** (EV/tonne of reserves/resources) — with a
**Simple mode** (comps) and an **Advanced mode** (editable DCF assumptions).

## What it does

| Component | Where | What |
|---|---|---|
| Data model | `models/company_comp.py` | One company's financial snapshot + derived valuation multiples (EV/EBITDA, EV/Revenue, P/E, P/B) |
| Data pipeline | `sectors_client/`, `cache/` | Pulls from the Sectors API, caches to SQLite (keyed on company + period + endpoint) |
| Mapper | `mapper/` | Translates Sectors' two reporting templates (bank vs generic) into the model; maps the mining extension |
| Mining overlay | `models/mining_overlay.py`, `engine/mining_valuation.py` | Reserve tonnage + EV/tonne, with "self-reported" + vintage-year flags |
| Screener | `screener/` | Batches tickers into screenable / miners / excluded (with reasons) |
| Advanced mode | `engine/proxy_library.py`, `engine/dcf.py` | Sector-conditional growth proxies + a 2-stage DCF |
| Assistant | `assistant.py` | Citation-safe DCF suggestion helper (curated references only) |
| UI | `app.py`, `view.py` | Streamlit app with xlsx export |

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set your Sectors API key (obtained from sectors.app)
#    Create a .env file in the repo root:
#      SECTORS_API_KEY=your_key_here
#    (or export it as an environment variable)

# 3. Run the app
streamlit run app.py
```

## Run the tests

```bash
python -m tests.test_company_comp
python -m tests.test_mapper
python -m tests.test_mining_overlay
python -m tests.test_ev_tonne
python -m tests.test_screener
python -m tests.test_view
python -m tests.test_advanced
python -m tests.test_assistant
```

The test suite is **fixture-based** (frozen JSON under `tests/fixtures/`), so it is
deterministic and runs without an API key or network connection.

## Design principles (why this is defensible)

1. **Never fabricate.** A missing input yields `None`/an explicit exclusion — never a
   silently-wrong number. This is the product's core promise.
2. **Every number traces to a source.** Multiples are *derived*, not stored; reserve
   figures carry "self-reported" + measurement-vintage flags; AI-assisted suggestions
   only ever come from a hand-curated, cited reference set (or our own cached data).
3. **Exclusions are explicit.** A peer that can't be compared is reported *with a reason*,
   never quietly dropped.
4. **Precision.** Monetary values use `Decimal`, never binary floating point.

## Scope notes

- **SGX**: EV-based multiples are not computable from the Sectors SGX schema (no
  `total_debt`/`cash_and_equivalents`), so SGX names are currently excluded with an
  honest "not yet supported" reason rather than mis-mapped.
- **Mining overlay ticker coverage**: the mining overlay (reserve tonnage, EV/tonne,
  self-reported/vintage flags) currently only applies to the two hardcoded seed miners
  (`MDKA`, `ADRO`) in `screener/screener.py`. Other real miners will be treated as
  generic comps for now — a known limitation, not a silently-wrong number.
- **Advanced-mode DCF growth defaults**: the sector-conditional growth proxy only
  auto-populates for banks (a documented GDP+spread assumption). Generic/miner companies
  require you to enter a growth rate yourself, because the screener doesn't retain the
  historical revenue series the CAGR-based proxies need. Entering a value is always
  required before running the DCF.
- **Advanced-mode DCF** uses an "expected rate of return" in place of textbook WACC, and
  sector-conditional proxies are *sanity-checked against realized growth*, not
  statistically validated forecasts.
- **True per-asset NAV** is a narrated roadmap item, not implemented.

## Disclaimer

Informational analysis tool only — not financial advice. Data from the Sectors API.
