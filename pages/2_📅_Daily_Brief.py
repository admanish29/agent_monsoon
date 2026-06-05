"""
pages/1_📅_Daily_Brief.py — Daily Brief page

User picks a date, clicks Generate, gets:
  - Headline metrics table (DAM vs GDAM)
  - Cross-Market Indicators mini-table
  - 4 charts (intraday MCP, premium, RMTI gauge, source curtailment)
  - Claude-generated narrative
  - RMTI footnote
"""

import streamlit as st
import pandas as pd
from datetime import datetime
import time

from src.data_loader import load_dataframes
import os
# Inject GTK3 binaries into PATH so weasyprint can find libcairo (Windows quirk)
os.environ['PATH'] = r'C:\Program Files\GTK3-Runtime Win64\bin' + os.pathsep + os.environ['PATH']

from src.brief import generate_daily_brief_v2
from weasyprint import HTML
import io


# ============================================================
# Page setup
# ============================================================
st.set_page_config(
    page_title="Daily Brief · Agent Monsoon",
    page_icon="📅",
    layout="wide",
)


# ============================================================
# Minimal styling — match the home page aesthetic without animations
# ============================================================
st.markdown("""
<style>
    footer {visibility: hidden;}
    #MainMenu {visibility: hidden;}

    .page-title {
        background: linear-gradient(135deg, #00D4FF 0%, #0077B6 50%, #4A90E2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        font-size: 36px;
        font-weight: 800;
        letter-spacing: -1px;
        margin-bottom: 6px;
    }
    .page-subtitle {
        color: #8a93a8;
        font-size: 14px;
        margin-bottom: 24px;
    }
    .picker-card {
        background: linear-gradient(135deg, rgba(19, 24, 38, 0.85) 0%, rgba(26, 33, 56, 0.85) 100%);
        border: 1px solid rgba(31, 42, 68, 0.8);
        border-radius: 12px;
        padding: 20px 24px;
        margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================
# Header
# ============================================================
st.markdown('<div class="page-title">📅 Daily Brief</div>', unsafe_allow_html=True)
st.markdown('<p class="page-subtitle">Select any date in the dataset to generate a full IEX market brief.</p>', unsafe_allow_html=True)


# ============================================================
# Load data (cached)
# ============================================================
data = load_dataframes()
df_daily = data['df_daily']

min_date = df_daily['date'].min().date()
max_date = df_daily['date'].max().date()
# ============================================================
# Session state initialization
# ============================================================
ss = st.session_state
if "dbr_initialized" not in ss:
    ss.dbr_initialized   = True
    ss.dbr_selected_date = max_date     # defaults to latest data
    ss.dbr_last_html     = None
    ss.dbr_last_info     = None
    ss.dbr_last_elapsed  = None
    ss.dbr_last_pdf      = None

# ============================================================
# Date picker + Generate button
# ============================================================
col1, col2, col3 = st.columns([2, 1, 1])

with col1:
    selected_date = st.date_input(
        "**Select a date**",
        value=ss.dbr_selected_date,
        min_value=min_date,
        max_value=max_date,
        key="dbr_date_picker",
        help=f"Dataset covers {min_date} to {max_date}"
    )
    ss.dbr_selected_date = selected_date

with col2:
    st.markdown("<br>", unsafe_allow_html=True)   # spacer to align button
    generate = st.button("⚡ Generate Brief", type="primary", use_container_width=True)

with col3:
    # Show RMTI for selected date as a preview
    selected_row = df_daily[df_daily['date'] == pd.to_datetime(selected_date)]
    if not selected_row.empty:
        rmti = selected_row.iloc[0]['rmti_composite']
        is_record = selected_row.iloc[0]['rmti_is_record']
        record_str = " 🔴" if is_record else ""
        st.markdown(f"""
        <div style="text-align:right;padding-top:30px;">
          <div style="font-size:11px;color:#8a93a8;text-transform:uppercase;letter-spacing:1.5px;">RMTI for this day</div>
          <div style="font-size:24px;color:#00D4FF;font-family:monospace;font-weight:700;">
            {rmti:.1f}{record_str}
          </div>
        </div>
        """, unsafe_allow_html=True)


# ============================================================
# Generate brief on click
# ============================================================
if generate:
    with st.spinner("⏳ Calling Claude to generate analysis..."):
        t0 = time.time()
        try:
            html, info = generate_daily_brief_v2(str(selected_date))
            elapsed = time.time() - t0
            pdf_bytes = HTML(string=html).write_pdf()

            # Cache in session state so it survives page-switches
            ss.dbr_last_html    = html
            ss.dbr_last_info    = info
            ss.dbr_last_elapsed = elapsed
            ss.dbr_last_pdf     = pdf_bytes

        except Exception as e:
            st.error(f"Failed to generate brief: {e}")
            ss.dbr_last_html = None

# Render last brief (persists across reruns / page-switches)
if ss.dbr_last_html is not None:
    import streamlit.components.v1 as components
    components.html(ss.dbr_last_html, height=3200, scrolling=True)

    info = ss.dbr_last_info or {}
    elapsed = ss.dbr_last_elapsed or 0

    col_status, col_download = st.columns([3, 1])
    with col_status:
        st.markdown(f"""
        <div style="padding:10px 16px;background:rgba(0,212,255,0.05);
                    border-left:3px solid #00D4FF;border-radius:6px;font-size:12px;color:#8a93a8;">
            ✅ Generated in {elapsed:.1f} sec · {info.get('tokens_in',0)} input + {info.get('tokens_out',0)} output tokens · ${info.get('cost_usd',0):.5f}
        </div>
        """, unsafe_allow_html=True)
    with col_download:
        if ss.dbr_last_pdf:
            st.download_button(
                "📥 Download PDF",
                data=ss.dbr_last_pdf,
                file_name=f"agent_monsoon_daily_{ss.dbr_selected_date}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
else:
    # Default helper text when no brief generated yet
    st.info(f"""
    👆 Pick a date above and click **Generate Brief**.

    The brief includes:
    - Headline metrics table (DAM vs GDAM) with peak/trough block times
    - Cross-Market Indicators (RMTI + Storage Arbitrage with tradable path)
    - 4 charts: intraday MCP curve, block-by-block premium, RMTI gauge, source-wise curtailment
    - AI-generated narrative analysis (Market Dynamics, RMTI Verdict, Notable Blocks)
    - Footnote with RMTI definitions

    Generation takes ~6-10 seconds (the Claude API call dominates).
    """)


# ============================================================
# Sidebar
# ============================================================
with st.sidebar:
    st.markdown("### 📅 Date Range")
    st.markdown(f"**Earliest:** {min_date}")
    st.markdown(f"**Latest:** {max_date}")
    st.markdown(f"**Total days:** {len(df_daily)}")

    st.markdown("---")
    st.markdown("### 💡 Quick picks")
    st.caption("Notable days you might want to try:")
    st.markdown("""
    - **2025-09-30** — Worst RMTI day (97.5)
    - **2025-08-27** — Best arbitrage (₹9.90/kWh)
    - **2026-03-03** — FY-end stress peak
    - **2026-05-05** — Reference day
    """)