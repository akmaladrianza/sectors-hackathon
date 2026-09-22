"""Mimir — a comps + mining-overlay valuation screener.

Streamlit UI (Simple + Advanced mode). Entry point:
    streamlit run app.py
"""

from __future__ import annotations

import sys
import os
from datetime import date

# Ensure the repo root is importable when Streamlit launches app.py directly.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
import pandas as pd
from decimal import Decimal

import view
from cache.sqlite_cache import SQLiteCache
from screener.screener import screen_tickers
from engine.proxy_library import default_growth
from engine.dcf import run_dcf, nwc_change_margin_from_days, estimate_working_capital_days
from engine.xlsx_export import write_dcf_sheet
from engine.football_field import build_football_field
from engine.peer_lookup import lookup_peers
from sectors_client.client import SectorsClient

# Self-healing guard against a stale-import failure: if the running process somehow
# bound an *older* `lookup_peers` (one without the `cache` kwarg — a known signature
# added later, and the exact cause of a past `TypeError: unexpected keyword argument
# 'cache'` on a long-lived Streamlit deploy), reload the module from disk so the call
# in the football-field block matches the on-disk code. No-op when the signature is
# already correct; it repairs a stale binding without changing runtime behaviour.
import inspect as _inspect  # noqa: E402
import importlib as _importlib  # noqa: E402
import engine.peer_lookup as _peer_lookup_module  # noqa: E402
try:
    _sig = _inspect.signature(lookup_peers)
    _has_cache_kwarg = "cache" in _sig.parameters
except (TypeError, ValueError):
    _has_cache_kwarg = False
if not _has_cache_kwarg:
    _peer_lookup_module = _importlib.reload(_peer_lookup_module)
    lookup_peers = _peer_lookup_module.lookup_peers
import assistant
import sectors_news

DEFAULT_TICKERS = "BBCA, BBNI, BRIS"
CACHE_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "sectors_cache.db")

# US-style comma-separated number rendering for the dataframe tables.
_PRICE_FORMAT = "%,.0f"      # e.g. 13,694
_MULTIPLE_FORMAT = "%.2f"    # e.g. 9.28 (multiples are small ratios, not currency)
_PCT_FORMAT = "%.2f%%"       # upside as a percent (signed)

from streamlit.column_config import NumberColumn  # noqa: E402


def _comps_column_config() -> dict:
    """Number formatting for the comps/implied tables (US comma separators)."""
    return {
        "EV/EBITDA": NumberColumn(format=_MULTIPLE_FORMAT),
        "EV/Revenue": NumberColumn(format=_MULTIPLE_FORMAT),
        "P/E": NumberColumn(format=_MULTIPLE_FORMAT),
        "P/B": NumberColumn(format=_MULTIPLE_FORMAT),
        "Sectors IV": NumberColumn(format=_PRICE_FORMAT),
        "Current price": NumberColumn(format=_PRICE_FORMAT),
        "Implied low": NumberColumn(format=_PRICE_FORMAT),
        "Implied high": NumberColumn(format=_PRICE_FORMAT),
        "Upside": NumberColumn(format=_PCT_FORMAT),
        "EV/tonne (reserves)": NumberColumn(format=_MULTIPLE_FORMAT),
        "EV/tonne (resources)": NumberColumn(format=_MULTIPLE_FORMAT),
        "Reserves (Mt)": NumberColumn(format="%,.2f"),
        "Resources (Mt)": NumberColumn(format="%,.2f"),
    }


st.set_page_config(page_title="Mimir — Comps Screener", layout="wide")

# ---------------------------------------------------------------------------
# Custom theme (clean, modern, professional) via CSS injection.
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    :root {
        --accent: #d97757;          /* warm accent, Claude-ish terracotta */
        --accent-soft: rgba(217, 119, 87, 0.12);
        --ink: #1f1e1b;             /* near-black warm ink */
        --muted: #8a8578;
        --surface: #faf9f6;         /* warm off-white */
        --border: #e7e3d8;
    }
    .block-container { padding-top: 1.5rem; padding-bottom: 3rem; }
    h1, h2, h3 { color: var(--ink); letter-spacing: -0.01em; }
    .mimir-card {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 1.1rem 1.25rem;
        margin-bottom: 1rem;
    }
    .mimir-badge {
        display: inline-block;
        background: var(--accent-soft);
        color: var(--accent);
        border-radius: 999px;
        padding: 0.15rem 0.7rem;
        font-size: 0.78rem;
        font-weight: 600;
    }
    .mimir-muted { color: var(--muted); font-size: 0.85rem; }
    .mimir-brand {
        text-align: right;
        font-size: 2.6rem;
        font-weight: 700;
        letter-spacing: -0.03em;
        color: var(--ink);
        line-height: 1.0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- Header: name pinned upper-right + explainer -------------------------
_c1, _c2 = st.columns([3, 1])
with _c2:
    st.markdown(
        "<div class='mimir-brand'>Mimir</div>"
        "<div style='text-align:right'><span class='mimir-badge'>Comps · Mining · DCF</span></div>",
        unsafe_allow_html=True,
    )
with _c1:
    st.caption(
        "Named after Mímir, the Norse god of wisdom and knowledge. Mimir automates the "
        "mechanical layers of fundamental analysis — comparable-company valuation, "
        "reserve-adjusted mining metrics, and DCF — for IDX equities, sourced entirely "
        "from the Sectors API, with every number traceable to a source."
    )

# --- Sidebar: inputs ------------------------------------------------------
st.sidebar.header("Screener")

# Company search -> suggested ticker
search_box = st.sidebar.text_input(
    "Search company by name",
    placeholder="e.g. Unilever, Merdeka, Mandiri…",
)


def _company_suggestions(keyword: str, client: SectorsClient) -> list[dict]:
    """Return [(symbol, company_name)] for a company-name keyword."""
    if len(keyword.strip()) < 3:
        return []
    try:
        payload = client.search_companies(keyword.strip())
    except Exception:
        return []
    out = []
    for r in payload.get("results") or []:
        sym = r.get("symbol")
        nm = r.get("company_name")
        if sym and nm:
            out.append({"symbol": sym, "name": nm})
    return out[:8]


search_hits = []
if search_box:
    _client = SectorsClient()
    search_hits = _company_suggestions(search_box, _client)
    if search_hits:
        st.sidebar.caption(f"{len(search_hits)} match(es):")
        for hit in search_hits:
            st.sidebar.markdown(
                f"`{hit['symbol']}` — {hit['name']}",
                help="Copy this ticker into the box below.",
            )
    else:
        st.sidebar.caption("No matches (try ≥3 letters).")

tickers_input = st.sidebar.text_area(
    "Tickers (comma-separated)",
    value=DEFAULT_TICKERS,
    help="IDX tickers, e.g. BBCA, BBNI, BRIS. Use same-industry peers for a fair "
    "comparison — mixing a bank, a coal miner and a consumer name is meaningless.",
)
advanced = st.sidebar.checkbox("Advanced mode (DCF)", value=False)
news_enabled = st.sidebar.checkbox("Show Sectors news", value=False)
run = st.sidebar.button("Run screener", type="primary")

# --- Disclaimer ------------------------------------------------------------
st.sidebar.markdown(
    "---\n"
    "**Disclaimer**: informational analysis tool, not financial advice. "
    "All data sourced from the Sectors API."
)

# ---------------------------------------------------------------------------
# Session-state: persist the result so Advanced-mode widgets re-render live on
# every interaction (a plain `if run:` block only executes on the button rerun).
# ---------------------------------------------------------------------------
if run:
    tickers = [t.strip() for t in tickers_input.split(",") if t.strip()]

    if os.path.dirname(CACHE_DB):
        os.makedirs(os.path.dirname(CACHE_DB), exist_ok=True)
    cache = SQLiteCache(CACHE_DB)
    client = SectorsClient()

    with st.spinner("Screening..."):
        try:
            st.session_state["result"] = screen_tickers(tickers, cache=cache, client=client)
            st.session_state["client"] = client
            st.session_state["cache"] = cache
            st.session_state["has_run"] = True
        except Exception as exc:  # noqa: BLE001
            st.error(f"Could not run screener: {exc}")
            st.session_state["has_run"] = False
            st.stop()

result = st.session_state.get("result")
_client = st.session_state.get("client") or SectorsClient()
_cache = st.session_state.get("cache")
if result is None:
    # First load: show intro, no result yet.
    with st.expander("ℹ️ How to use this", expanded=True):
        st.markdown(
            "1. **Enter tickers** in the sidebar (e.g. `BBCA, TLKM, ASII, UNVR, MDKA`), "
            "one per line or comma-separated.\n"
            "2. Click **Run screener**.\n"
            "3. Read the **Comparable companies** table, the **Implied valuation** panel "
            "(target vs current price), the **Mining overlay**, and the **Excluded** panel.\n"
            "4. Toggle **Advanced mode** to edit DCF assumptions (they update live).\n"
            "5. **Download .xlsx** to export a tuneable, formula-driven DCF model."
        )
    st.stop()

# --- Comps table -----------------------------------------------------------
st.subheader("Comparable companies")
comps_df = view.to_dataframe(result)
if not comps_df.empty:
    st.dataframe(
        comps_df, use_container_width=True, hide_index=True,
        column_config=_comps_column_config(),
    )
    st.caption(
        "**Sectors IV** = Sectors' own disclosed fair-value estimate per share. "
        "**Upside** = (Sectors IV ÷ current price) − 1. Both are Sectors-native "
        "(not our own forecast). "
        f"Source: Sectors API ({date.today().isoformat()}). "
        f"{len(result.screenable)} non-mining peers."
    )
else:
    st.write("No screenable (non-mining) peers.")

# --- Implied valuation (target vs current price) ---------------------------
st.subheader("Implied valuation (target vs current price)")
implied_df = view.to_implied_dataframe(result)
if len(result.screenable) + len(result.miners) < 2:
    st.info(
        "Add at least one more screenable ticker to compute a peer-median implied "
        "price (a single peer is not a peer group). Sectors' own fair value, where "
        "available, is still shown in the comps table above."
    )
elif not implied_df.empty:
    st.dataframe(
        implied_df, use_container_width=True, hide_index=True,
        column_config=_comps_column_config(),
    )
    st.caption(
        "Implied prices are peer-median-multiple inversions (excluding the subject) "
        "combined with Sectors' own intrinsic value. Verdict is informational only — "
        "not a buy/sell recommendation."
    )

# --- Mining overlay ---------------------------------------------------------
if result.miners:
    st.subheader("Mining overlay (reserve-adjusted)")
    mining_df = view.to_mining_dataframe(result)
    st.dataframe(
        mining_df, use_container_width=True, hide_index=True,
        column_config=_comps_column_config(),
    )
    st.caption(
        "Reserve figures are company self-reported (not independently audited) "
        "and carry a measurement-vintage year. Tonnage is Mt of ore, not metal content."
    )

# --- Excluded peers ----------------------------------------------------------
if result.excluded:
    st.subheader("Excluded peers")
    excl_df = pd.DataFrame(view.exclusion_rows(result))
    st.dataframe(excl_df, use_container_width=True, hide_index=True)
    st.caption("Excluded because comparable data is unavailable — never silently dropped.")

# --- Advanced mode: DCF ------------------------------------------------------
if advanced:
    st.subheader("Advanced mode — DCF (intrinsic value)")
    st.caption(
        "A corporate DCF (FCFF, with an FCFE bridge when balance-sheet data exists). "
        "Assumptions are seeded from sector-conditional proxies + curated references "
        "and update live. Not financial advice."
    )
    for c in result.screenable + [m.comp for m in result.miners]:
        proxy = default_growth(c, raw_hist=None)
        default_g = float(proxy.value) if proxy.value is not None else 0.10
        with st.expander(f"{c.ticker} — {c.company_name}"):
            # Sectors-native grounding (zero-hallucination): the cached facts a human
            # would use to pick growth, shown before the editable inputs.
            st.caption(
                f"Baseline financials: {c.fiscal_period or 'latest FY'} annual "
                f"(revenue {float(c.revenue):,.0f} IDR). DCF projects from this "
                "annual base; point-in-time price/market cap are current."
            )
            if proxy.source:
                st.caption(f"Growth heuristic: {proxy.source}")
            if c.intrinsic_value is not None:
                st.caption(
                    f"Sectors fair value: {float(c.intrinsic_value):,.0f} vs last close "
                    f"{float(c.price or 0):,.0f}"
                )

            # Optional Sectors-native news (verbatim quote, never interpreted).
            if news_enabled:
                items = sectors_news.suggest_company_news(
                    _client, symbols=[c.ticker.split(".")[0]]
                )
                for ns in items:
                    if ns.available:
                        st.info(
                            f"**{ns.title}** ({ns.timestamp[:10] if ns.timestamp else 'n/a'})\n\n"
                            f"{ns.body}\n\n[{ns.source}]({ns.source})"
                        )
                    else:
                        st.caption(f"News: {ns.reason}")

            # Curated (citation-safe) suggestions — now wired into the DCF below.
            wc_sugg = assistant.suggest_working_capital(c)
            capex_sugg = assistant.suggest_capex(c)

            g = st.number_input(
                "Revenue growth rate", min_value=-0.5, max_value=1.0,
                value=default_g, step=0.01, key=f"g_{c.ticker}", format="%.3f",
            )
            m = st.number_input(
                "FCF margin (of revenue)", min_value=0.0, max_value=1.0,
                value=0.15, step=0.01, key=f"m_{c.ticker}",
            )
            # --- FCFF build-up (advanced FCF/FCFE parameters) -----------------
            use_buildup = st.checkbox("Use FCFF build-up (EBITDA → FCF)", value=False,
                                      key=f"bu_{c.ticker}")
            em = dm = tx = cx = nw = None
            if use_buildup:
                if c.revenue and c.ebitda:
                    _default_em = float(c.ebitda / c.revenue)
                else:
                    _default_em = 0.30
                em = st.number_input("EBITDA margin", 0.0, 0.9, value=_default_em,
                                     step=0.01, key=f"em_{c.ticker}")
                dm = st.number_input("D&A (% of revenue)", 0.0, 0.5, value=0.05,
                                     step=0.005, key=f"dm_{c.ticker}")
                tx = st.number_input("Tax rate", 0.0, 0.5, value=0.22,
                                     step=0.01, key=f"tx_{c.ticker}")
                _capex_default = float(capex_sugg.value) if capex_sugg and capex_sugg.available else 0.15
                cx = st.number_input("Capex (% of revenue)", 0.0, 1.0, value=_capex_default,
                                     step=0.01, key=f"cx_{c.ticker}")
                # Working-capital breakdown into AR / Inventory / AP days, seeded from
                # the balance sheet where derivable (residual current assets/liabilities).
                _est_ar, _est_inv, _est_ap = estimate_working_capital_days(
                    revenue=c.revenue,
                    cost_of_revenue=c.cost_of_revenue,
                    inventories=c.inventories,
                    current_assets=c.current_assets,
                    current_liabilities=c.current_liabilities,
                    cash_and_equivalents=c.cash_and_equivalents,
                    prepaid_assets=c.prepaid_assets,
                    short_term_debt=c.short_term_debt,
                )
                _cap_note = (
                    "Working capital (days), estimated from the balance sheet "
                    "(AR = residual current assets; AP = residual current liabilities). "
                    "Editable."
                )
                st.caption(_cap_note)
                ar_days = st.number_input(
                    "AR days", 0.0, 365.0, value=_est_ar if _est_ar is not None else 30.0,
                    step=1.0, key=f"ar_{c.ticker}",
                )
                inv_days = st.number_input(
                    "Inventory days", 0.0, 365.0, value=_est_inv if _est_inv is not None else 30.0,
                    step=1.0, key=f"inv_{c.ticker}",
                )
                ap_days = st.number_input(
                    "AP days", 0.0, 365.0, value=_est_ap if _est_ap is not None else 30.0,
                    step=1.0, key=f"ap_{c.ticker}",
                )
                nw = nwc_change_margin_from_days(
                    Decimal(str(ar_days)),
                    Decimal(str(inv_days)),
                    Decimal(str(ap_days)),
                    Decimal(str(g)),
                )
            r = st.number_input(
                "Expected rate of return (discount)", min_value=0.01, max_value=0.50,
                value=0.12, step=0.01, key=f"r_{c.ticker}", format="%.3f",
            )
            tvg = st.number_input(
                "Terminal growth", min_value=0.0, max_value=0.10,
                value=0.02, step=0.005, key=f"tvg_{c.ticker}", format="%.3f",
            )

            net_debt = None
            if c.total_debt is not None and c.cash_and_equivalents is not None:
                net_debt = c.total_debt - c.cash_and_equivalents

            dcf = run_dcf(
                revenue=c.revenue,
                growth_rate=Decimal(str(g)),
                cash_flow_margin=Decimal(str(m)),
                discount_rate=Decimal(str(r)),
                terminal_growth=Decimal(str(tvg)),
                ebitda_margin=Decimal(str(em)) if em is not None else None,
                depreciation_margin=Decimal(str(dm)) if dm is not None else None,
                tax_rate=Decimal(str(tx)) if tx is not None else None,
                capex_margin=Decimal(str(cx)) if cx is not None else None,
                nwc_change_margin=nw if nw is not None else None,
                shares_outstanding=c.shares_outstanding,
                net_debt=net_debt,
            )
            # Persist the DCF price so the football field (rendered after) picks it up.
            if dcf.available and dcf.intrinsic_price_per_share is not None:
                st.session_state[f"dcf_price_{c.ticker}"] = dcf.intrinsic_price_per_share
            if dcf.available and c.revenue:
                lines = [f"**Intrinsic EV ≈ {float(dcf.intrinsic_ev):,.0f}**"]
                if dcf.intrinsic_price_per_share is not None:
                    lines.append(
                        f"Intrinsic price/share ≈ {float(dcf.intrinsic_price_per_share):,.0f} "
                        f"(current {float(c.price or 0):,.0f})"
                    )
                lines.append(f"vs. actual EV {float(c.enterprise_value or 0):,.0f}")
                st.write(" — ".join(lines))
            else:
                st.info(f"DCF unavailable: {dcf.reason or 'missing revenue history'}")


# --- Football field (industry-matched valuation ranges) ---------------------
st.subheader("Valuation football field")
st.caption(
    "Each bar spans the min–max implied share price from **same-sub_sector peers** "
    "(sourced from Sectors, not the ticker list you typed) inverted via the subject's "
    "own figures. The ▲ marker is the current price; DCF (Advanced mode) and Sectors IV "
    "are single-point methods. Chart is informational, not a recommendation."
)

_plotly_ok = True
try:
    import plotly.graph_objects as go
except Exception:
    _plotly_ok = False

subjects = list(result.screenable) + [m.comp for m in result.miners]
if _plotly_ok and subjects:
    for c in subjects:
        try:
            peer_cache_key = f"peers_{c.ticker}"
            if peer_cache_key not in st.session_state:
                with st.spinner(f"Resolving peers for {c.ticker}…"):
                    st.session_state[peer_cache_key] = lookup_peers(
                        c, _client, cache=_cache, limit=5
                    )
            pr = st.session_state[peer_cache_key]
        except Exception as exc:  # noqa: BLE001
            # A transient peer-lookup failure must degrade this one chart, not crash
            # the whole render (consistent with screener.py's graceful-degradation rule).
            st.warning(
                f"{c.ticker}: peer lookup failed ({type(exc).__name__}: {exc}) — "
                "football field skipped for this ticker."
            )
            continue

        dcf_price = st.session_state.get(f"dcf_price_{c.ticker}")

        if not pr.has_peers:
            st.info(f"{c.ticker}: {pr.reason or 'no screenable same-sub_sector peers'}.")
            continue

        rows, current, sectors_iv = build_football_field(c, pr.peers, dcf_price)
        if not rows:
            st.info(f"{c.ticker}: no same-sub_sector peers found to chart.")
            continue

        _notes = f"{len(pr.peers)} peer(s)"
        if pr.skipped:
            _notes += f" ({len(pr.skipped)} skipped: {', '.join(pr.skipped[:4])})"
        st.caption(f"{c.ticker}: {_notes}")

        fig = go.Figure()
        methods = [r.method for r in rows]
        lows = [r.low for r in rows]
        highs = [r.high for r in rows]
        fig.add_trace(
            go.Bar(
                x=[(h - l) if (h is not None and l is not None) else 0
                   for h, l in zip(highs, lows)],
                y=methods,
                base=lows,
                orientation="h",
                marker_color="#d97757",
                opacity=0.75,
                name="Peer range",
                hovertemplate="%{y}: %{base:,.0f} – %{x:,.0f}<extra></extra>",
            )
        )
        if current is not None:
            fig.add_trace(
                go.Scatter(
                    x=[current],
                    y=[methods[0] if methods else 0],
                    mode="markers",
                    marker=dict(symbol="triangle-up", size=14, color="#1f1e1b"),
                    name="Current price",
                    hovertemplate="Current: %{x:,.0f}<extra></extra>",
                )
            )
        fig.update_layout(
            height=280,
            margin=dict(l=10, r=10, t=30, b=10),
            title=dict(text=f"{c.ticker} — valuation range vs current", font=dict(size=14)),
            xaxis_title="Implied share price (IDR)",
            barmode="overlay",
        )
        st.plotly_chart(fig, use_container_width=True, key=f"ff_{c.ticker}")
elif not _plotly_ok:
    st.warning("Plotly is not installed — install `plotly` to enable the football-field chart.")


# --- Export (always visible, prominent section) ------------------------------
import io as _io
import traceback as _traceback

st.divider()
st.subheader("📥 Download financial model")
st.caption(
    "Formula-driven `.xlsx` workbook: Comps + Implied valuation + Mining + Excluded "
    "sheets, plus a per-company **DCF** sheet with live Excel formulas so you can "
    "re-tune assumptions offline."
)
_export_error = None
_buf = _io.BytesIO()
try:
    with pd.ExcelWriter(_buf, engine="openpyxl") as writer:
        if result.screenable:
            view.to_dataframe(result).to_excel(writer, sheet_name="Comps", index=False)
        implied_out = view.to_implied_dataframe(result)
        if not implied_out.empty:
            implied_out.to_excel(writer, sheet_name="Implied", index=False)
        if result.miners:
            view.to_mining_dataframe(result).to_excel(writer, sheet_name="Mining", index=False)
        if result.excluded:
            pd.DataFrame(view.exclusion_rows(result)).to_excel(
                writer, sheet_name="Excluded", index=False
            )
        for c in result.screenable + [m.comp for m in result.miners]:
            g_val = Decimal(str(st.session_state.get(f"g_{c.ticker}", 0.10)))
            m_val = Decimal(str(st.session_state.get(f"m_{c.ticker}", 0.15)))
            r_val = Decimal(str(st.session_state.get(f"r_{c.ticker}", 0.12)))
            tvg_val = Decimal(str(st.session_state.get(f"tvg_{c.ticker}", 0.02)))
            net_debt_val = None
            if c.total_debt is not None and c.cash_and_equivalents is not None:
                net_debt_val = c.total_debt - c.cash_and_equivalents
            write_dcf_sheet(
                writer,
                sheet_name=f"DCF {c.ticker}",
                revenue=c.revenue,
                g=g_val,
                m=m_val,
                r=r_val,
                tvg=tvg_val,
                years=5,
                shares_outstanding=c.shares_outstanding,
                net_debt=net_debt_val,
                fiscal_period=c.fiscal_period,
                as_of_date=c.as_of_date.isoformat() if c.as_of_date else None,
            )
except Exception as exc:  # noqa: BLE001
    _export_error = exc

if _export_error is None:
    st.download_button(
        "Download financial model (.xlsx)",
        data=_buf.getvalue(),
        file_name="mimir_financial_model.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
else:
    st.error(f"Excel export failed: {_export_error}")
    with st.expander("Export error details", expanded=False):
        st.code(_traceback.format_exc())


# --- Footer: build provenance (helps diagnose stale deploys) -----------------
def _app_git_sha() -> str | None:
    """Return the current commit's short SHA, or None if git metadata is absent.

    Surfaces in the footer so a stale Streamlit-cloud deploy (serving an older
    module set than the committed top-level app.py) is diagnosable at a glance.
    """
    import subprocess

    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=2,
            cwd=os.path.dirname(os.path.abspath(__file__)),
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:  # noqa: BLE001
        pass
    return None


st.divider()
_sha = _app_git_sha()
st.caption(
    "Mimir · informational analysis, not financial advice · data from the Sectors API"
    + (f" · build {_sha}" if _sha else "")
)
