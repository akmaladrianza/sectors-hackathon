-- Sectors Hackathon 2026 -- comps tool schema
-- See BLUEPRINT.md section 3 for rationale behind each design choice.
--
-- NOTE (added after the Memory Bank was created): this DDL predates the built
-- `cache/sqlite_cache.py`. The cache that actually shipped differs from `api_cache`
-- below: it uses `cache_entries(company, period, endpoint, payload, fetched_at)` —
-- no `credits_spent` column, and `company` instead of `entity_id`. `company` is the
-- term of record (a generic entity key, also holding mining slugs later); see
-- `systemPatterns.md` section 7b and `BLUEPRINT.md` "Reconciliation with the Memory Bank".
-- The `build_sessions` table below is superseded by `progress.md`/`activeContext.md`
-- (dropped); it is retained here only as a historical record.

PRAGMA foreign_keys = ON;

-- Seed universe: one row per ticker in scope for the comp set(s) being built.
CREATE TABLE IF NOT EXISTS companies (
    ticker          TEXT PRIMARY KEY,          -- canonical form: 'BBCA.JK' (IDX), 'D05' (SGX has no suffix)
    exchange        TEXT NOT NULL CHECK (exchange IN ('IDX','SGX')),
    company_name    TEXT,
    sector          TEXT,
    sub_sector      TEXT,
    industry        TEXT,
    is_bank         INTEGER NOT NULL DEFAULT 0,   -- 1 => apply bank metric swap (net_interest_income, gross_loan, etc.)
    is_mining       INTEGER NOT NULL DEFAULT 0,   -- 1 => eligible for the mining overlay
    mining_slug     TEXT,                          -- join key into /v2/mining/companies/{slug}/ namespace; NULL until matched
    added_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Every raw API response, keyed generically enough to cover tickers AND mining slugs.
CREATE TABLE IF NOT EXISTS api_cache (
    entity_id       TEXT NOT NULL,      -- ticker (IDX/SGX), mining slug, or 'UNIVERSE' for list/directory calls
    endpoint        TEXT NOT NULL,      -- logical key from endpoint_registry.py, NOT a raw URL
    period          TEXT NOT NULL,      -- 'YYYY' | 'Qn-YYYY' | 'latest' | ISO date
    response_json   TEXT NOT NULL,      -- raw response, unnormalized -- normalize in Python at read time
    credits_spent   INTEGER NOT NULL DEFAULT 0,   -- 0 for rows split out of an already-billed batch call
    fetched_at      TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (entity_id, endpoint, period)
);

CREATE INDEX IF NOT EXISTS idx_api_cache_endpoint_period ON api_cache(endpoint, period);
CREATE INDEX IF NOT EXISTS idx_api_cache_fetched_at ON api_cache(fetched_at);

-- Phase 7: one row per build session.
CREATE TABLE IF NOT EXISTS build_sessions (
    session_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_date            TEXT NOT NULL DEFAULT (date('now')),
    phase                   TEXT NOT NULL,      -- e.g. 'schema', 'endpoint_map', 'comps_pipeline', 'mining_overlay', 'xlsx_export'
    status                  TEXT NOT NULL CHECK (status IN ('in_progress','blocked','done')),
    summary                 TEXT,
    blockers                TEXT,
    credits_spent_session   INTEGER NOT NULL DEFAULT 0,
    logged_at               TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Session 1 log entry (architecture + endpoint mapping, this chat).
INSERT INTO build_sessions (session_date, phase, status, summary, blockers, credits_spent_session)
VALUES (
    date('now'),
    'schema,endpoint_map',
    'done',
    'Researched live Sectors v2 API reference; drafted cache schema, endpoint registry, and 5 architecture decisions (see BLUEPRINT.md).',
    'SGX EV computability and symbol-in-list screener syntax need resolving before Phase 3.',
    0
);
