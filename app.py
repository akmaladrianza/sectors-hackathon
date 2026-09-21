"""Mimir (working name) — a comps + mining-overlay valuation screener.

Streamlit "Simple mode" UI. Entry point:
    streamlit run app.py

Usage: type/pick tickers, click Run, and get a comps table + a mining overlay panel
+ an explicit excluded-peers panel, all source-dated, with xlsx export.
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
import assistant

DEFAULT_TICKERS = "BBCA, TLKM, ASII, UNVR, MDKA"
CACHE_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "sectors_cache.db")

st.set_page_config(page_title="Mimir — Comps Screener", layout="wide")
st.title("Mimir")
st.caption("Comparable-company analysis + mining overlay")

# --- Sidebar: inputs (defined first so `run` is available to the intro) -----
st.sidebar.header("Screener")
tickers_input = st.sidebar.text_area(
    "Tickers (comma-separated)",
    value=DEFAULT_TICKERS,
    help="IDX tickers, e.g. BBCA, TLKM, ASII. Mining peers (MDKA, ADRO) get an overlay.",
)
advanced = st.sidebar.checkbox("Advanced mode (DCF)", value=False)
run = st.sidebar.button("Run screener", type="primary")

# --- Disclaimer (hackathon rule: not financial advice) --------------------
st.sidebar.markdown(
    "---\n"
    "**Disclaimer**: informational analysis tool, not financial advice. "
    "Data sourced from the Sectors API; reserve figures are company self-reported."
)

# --- How to use (first-load intro, expandable) -----------------------------
with st.expander("ℹ️ How to use this", expanded=not run):
    st.markdown(
        "1. **Enter tickers** in the sidebar (e.g. `BBCA, TLKM, ASII, UNVR, MDKA`), "
        "one per line or comma-separated.\n"
        "2. Click **Run screener**.\n"
        "3. Read the **Comparable companies** table (EV/EBITDA, EV/Revenue, P/E, P/B), "
        "the **Mining overlay** panel (reserve-adjusted metrics), and the **Excluded** "
        "panel (companies that can't be fairly compared, with the reason why).\n"
        "4. Toggle **Advanced mode** to see and edit DCF assumptions.\n"
        "5. **Download .xlsx** to export."
    )
    st.caption(
        "Mining overlay currently only covers **MDKA** and **ADRO** (hardcoded seed "
        "miners); other miners are shown as generic comps. Data from Sectors API; "
        "reserve figures are company self-reported, not independently audited."
    )

if run:
    tickers = [t.strip() for t in tickers_input.split(",") if t.strip()]

    cache = None
    if os.path.dirname(CACHE_DB):
        os.makedirs(os.path.dirname(CACHE_DB), exist_ok=True)
    cache = SQLiteCache(CACHE_DB)

    with st.spinner("Screening..."):
        try:
            result = screen_tickers(tickers, cache=cache)
        except Exception as exc:  # noqa: BLE001
            # A missing/invalid API key or an unreachable Sectors API should show a
            # clean message, not a raw Python traceback (consistent with the "one bad
            # ticker -> clean exclusion" principle applied everywhere else).
            st.error(f"Could not run screener: {exc}")
            st.stop()

    # --- Comps table -------------------------------------------------------
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

    # --- Mining overlay -----------------------------------------------------
    if result.miners:
        st.subheader("Mining overlay (reserve-adjusted)")
        mining_df = view.to_mining_dataframe(result)
        st.dataframe(mining_df, use_container_width=True, hide_index=True)
        st.caption(
            "Reserve figures are company self-reported (not independently audited) "
            "and carry a measurement-vintage year. Tonnage is Mt of ore, not metal content."
        )

    # --- Excluded peers ------------------------------------------------------
    if result.excluded:
        st.subheader("Excluded peers")
        excl_df = pd.DataFrame(view.exclusion_rows(result))
        st.dataframe(excl_df, use_container_width=True, hide_index=True)
        st.caption("Excluded because comparable data is unavailable — never silently dropped.")

    # --- Advanced mode: DCF -------------------------------------------------
    if advanced:
        st.subheader("Advanced mode — DCF (intrinsic value)")
        st.caption(
            "A simplified corporate DCF. Assumptions are seeded from sector-conditional "
            "proxies (see the Memory Bank) but are editable here. Not financial advice."
        )
        for c in result.screenable + [m.comp for m in result.miners]:
            # Bank proxy works without history (GDP+spread constant); generic/miner
            # proxies need historical revenue which isn't retained here, so we seed
            # banks from the proxy and ask for manual growth for everything else.
            proxy = default_growth(c, raw_hist=None)
            default_g = float(proxy.value) if proxy.value is not None else 0.10
            with st.expander(f"{c.ticker} — {c.company_name}"):
                st.caption(
                    "Growth default is sector-conditional where available (banks); "
                    "otherwise enter your own estimate."
                )
                # Citation-safe suggestions (Sectors-native + curated references only).
                wc_sugg = assistant.suggest_working_capital(c)
                capex_sugg = assistant.suggest_capex(c)
                life_sugg = assistant.suggest_asset_useful_life(c)
                if wc_sugg and wc_sugg.available:
                    st.caption(f"Working-capital suggestion: {float(wc_sugg.value)*100:.0f}% of revenue ({wc_sugg.source})")
                if capex_sugg and capex_sugg.available:
                    st.caption(f"Capex suggestion: {float(capex_sugg.value)*100:.0f}% of revenue ({capex_sugg.source})")
                if life_sugg and life_sugg.available:
                    st.caption(f"Asset useful-life suggestion: {life_sugg.value} years ({life_sugg.source})")

                g = st.number_input(
                    "Revenue growth rate", min_value=-0.5, max_value=1.0,
                    value=default_g, step=0.01, key=f"g_{c.ticker}",
                    format="%.3f",
                )
                m = st.number_input(
                    "FCF margin (of revenue)", min_value=0.0, max_value=1.0,
                    value=0.15, step=0.01, key=f"m_{c.ticker}",
                )
                r = st.number_input(
                    "Expected rate of return (discount)", min_value=0.01, max_value=0.50,
                    value=0.12, step=0.01, key=f"r_{c.ticker}",
                    format="%.3f",
                )
                tvg = st.number_input(
                    "Terminal growth", min_value=0.0, max_value=0.10,
                    value=0.02, step=0.005, key=f"tvg_{c.ticker}",
                    format="%.3f",
                )
                dcf = run_dcf(
                    revenue=c.revenue,
                    growth_rate=Decimal(str(g)),
                    cash_flow_margin=Decimal(str(m)),
                    discount_rate=Decimal(str(r)),
                    terminal_growth=Decimal(str(tvg)),
                )
                if dcf.available and c.revenue:
                    st.write(
                        f"**Intrinsic EV ≈ {float(dcf.intrinsic_ev):,.0f}** "
                        f"(vs. actual EV {float(c.enterprise_value or 0):,.0f})"
                    )
                else:
                    st.info(f"DCF unavailable: {dcf.reason or 'missing revenue history'}")

    # --- Export --------------------------------------------------------------
    try:
        import io as _io
        buf = _io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            if result.screenable:
                view.to_dataframe(result).to_excel(writer, sheet_name="Comps", index=False)
            if result.miners:
                view.to_mining_dataframe(result).to_excel(writer, sheet_name="Mining", index=False)
            if result.excluded:
                pd.DataFrame(view.exclusion_rows(result)).to_excel(
                    writer, sheet_name="Excluded", index=False
                )
        st.download_button(
            "Download .xlsx",
            data=buf.getvalue(),
            file_name="mimir_comps.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Excel export unavailable: {exc}")
