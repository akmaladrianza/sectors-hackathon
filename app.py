"""Mimir — a comps + mining-overlay valuation screener.

Streamlit UI (Simple + Advanced mode). Entry point:
    streamlit run app.py

Usage: type/pick tickers, click Run, and get a comps table + an implied-valuation
panel + a mining overlay + an explicit excluded-peers panel, all source-dated, with a
formula-driven xlsx export (DCF + implied valuation included).
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
from engine.dcf import run_dcf
from engine.xlsx_export import write_dcf_sheet
import assistant
import news_assistant

DEFAULT_TICKERS = "BBCA, TLKM, ASII, UNVR, MDKA"
CACHE_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "sectors_cache.db")

st.set_page_config(page_title="Mimir — Comps Screener", layout="wide")

# --- Header: name pinned upper-right + explainer -------------------------
_c1, _c2 = st.columns([3, 1])
with _c2:
    st.markdown(
        "<div style='text-align:right; line-height:1.05'>"
        "<span style='font-size:2.4rem; font-weight:700; letter-spacing:-0.02em'>Mimir</span><br>"
        "<span style='font-size:0.85rem; color:#888'>Comparable-company analysis<br>+ mining overlay</span>"
        "</div>",
        unsafe_allow_html=True,
    )
with _c1:
    st.caption(
        "Named after Mímir, the Norse god of wisdom and knowledge. Mimir automates the "
        "mechanical layers of fundamental analysis — comps, reserve-adjusted mining "
        "valuation, and DCF scaffolding — for IDX & SGX equities, sourced from the "
        "Sectors API, with every number traceable to a source."
    )

# --- Sidebar: inputs ------------------------------------------------------
st.sidebar.header("Screener")
tickers_input = st.sidebar.text_area(
    "Tickers (comma-separated)",
    value=DEFAULT_TICKERS,
    help="IDX tickers, e.g. BBCA, TLKM, ASII. Mining peers (MDKA, ADRO) get an overlay.",
)
advanced = st.sidebar.checkbox("Advanced mode (DCF)", value=False)
news_enabled = st.sidebar.checkbox("Enable news-grounded suggestions (beta)", value=False)
run = st.sidebar.button("Run screener", type="primary")

# --- Disclaimer (hackathon rule: not financial advice) --------------------
st.sidebar.markdown(
    "---\n"
    "**Disclaimer**: informational analysis tool, not financial advice. "
    "Data sourced from the Sectors API; reserve figures are company self-reported. "
    "News snippets (if enabled) are verbatim-quoted with source, never interpreted."
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

    with st.spinner("Screening..."):
        try:
            st.session_state["result"] = screen_tickers(tickers, cache=cache)
            st.session_state["has_run"] = True
        except Exception as exc:  # noqa: BLE001
            st.error(f"Could not run screener: {exc}")
            st.session_state["has_run"] = False
            st.stop()

result = st.session_state.get("result")
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
    st.dataframe(comps_df, use_container_width=True, hide_index=True)
    st.caption(
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
    st.dataframe(implied_df, use_container_width=True, hide_index=True)
    st.caption(
        "Implied prices are peer-median-multiple inversions (excluding the subject) "
        "combined with Sectors' own intrinsic value. Verdict is informational only — "
        "not a buy/sell recommendation."
    )

# --- Mining overlay ---------------------------------------------------------
if result.miners:
    st.subheader("Mining overlay (reserve-adjusted)")
    mining_df = view.to_mining_dataframe(result)
    st.dataframe(mining_df, use_container_width=True, hide_index=True)
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
            if proxy.source:
                st.caption(f"Growth heuristic: {proxy.source}")
            if c.intrinsic_value is not None:
                st.caption(
                    f"Sectors fair value: {float(c.intrinsic_value):,.0f} vs last close "
                    f"{float(c.price or 0):,.0f}"
                )

            # Optional news-grounded layer (verbatim quotes, never interpreted).
            if news_enabled:
                ns = news_assistant.suggest_news_growth(c.company_name)
                if ns.available:
                    st.info(
                        f"**News snippet** (verbatim, not interpreted): {ns.value}\n\n"
                        f"[{ns.title or 'source'}]({ns.source_url})"
                    )
                else:
                    st.caption(f"News grounding unavailable: {ns.reason}")

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
                _nwc_default = float(wc_sugg.value) if wc_sugg and wc_sugg.available else 0.05
                nw = st.number_input("Δ net working capital (% of revenue)", -0.5, 0.5,
                                     value=_nwc_default, step=0.01, key=f"nw_{c.ticker}")
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
                nwc_change_margin=Decimal(str(nw)) if nw is not None else None,
                shares_outstanding=c.shares_outstanding,
                net_debt=net_debt,
            )
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


# --- Export ------------------------------------------------------------------
try:
    import io as _io
    buf = _io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
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
        # Formula-driven DCF sheet per company (tuneable in Excel).
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
            )
    st.download_button(
        "Download .xlsx",
        data=buf.getvalue(),
        file_name="mimir_comps.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
except Exception as exc:  # noqa: BLE001
    st.warning(f"Excel export unavailable: {exc}")
