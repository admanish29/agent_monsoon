"""
pages/4_📆_Weekly_Brief.py — Weekly Brief page

User picks any date → snaps to that Mon-Sun week → generates full brief.
Includes:
  - WoW deltas (RMTI / DAM / Arbitrage)
  - Headline metrics table + Cross-Market mini-table
  - 4 charts: continuous MCP timeline / RMTI evolution / intraday spread / hour heatmap
  - Claude narrative (5 sections)
  - Sidebar with notable weeks
"""

import streamlit as st
import pandas as pd
import time
from datetime import timedelta

import os
# Inject GTK3 binaries into PATH so weasyprint can find libcairo (Windows quirk)
os.environ['PATH'] = r'C:\Program Files\GTK3-Runtime Win64\bin' + os.pathsep + os.environ['PATH']

from src.data_loader import load_dataframes
from src.weekly import generate_weekly_brief
from weasyprint import HTML


# ============================================================
# Page setup
# ============================================================
st.set_page_config(
    page_title="Weekly Brief · Agent Monsoon",
    page_icon="📆",
    layout="wide",
)


# ============================================================
# Styling
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
</style>
""", unsafe_allow_html=True)


# ============================================================
# Header
# ============================================================
st.markdown('<div class="page-title">📆 Weekly Brief</div>', unsafe_allow_html=True)
st.markdown('<p class="page-subtitle">Mon–Sun analysis with cross-day pattern detection, WoW deltas, and structural insight.</p>', unsafe_allow_html=True)


# ============================================================
# Load data
# ============================================================
data = load_dataframes()
df_weekly = data['df_weekly']
df_daily  = data['df_daily']

DATA_MIN = df_daily['date'].min().date()
DATA_MAX = df_daily['date'].max().date()

# Default week = last available complete week
_max_monday = DATA_MAX - timedelta(days=DATA_MAX.weekday())
DEFAULT_WEEK_ANCHOR = _max_monday


# ============================================================
# Session state
# ============================================================
ss = st.session_state
if "wb_initialized" not in ss:
    ss.wb_initialized   = True
    ss.wb_anchor_date   = DEFAULT_WEEK_ANCHOR
    ss.wb_last_brief    = None   # cached HTML brief
    ss.wb_last_info     = None
    ss.wb_last_week     = None


# ============================================================
# Week picker + generate button
# ============================================================
col1, col2, col3 = st.columns([2, 1, 1])

with col1:
    picked = st.date_input(
        "**Pick any date in the week**",
        value=ss.wb_anchor_date,
        min_value=DATA_MIN,
        max_value=DATA_MAX,
        key="wb_date_picker",
        help=f"Dataset covers {DATA_MIN} to {DATA_MAX}. The brief will be for the Mon-Sun week containing this date."
    )
    ss.wb_anchor_date = picked
    monday = picked - timedelta(days=picked.weekday())
    sunday = monday + timedelta(days=6)
    # Clip Sunday if it's beyond data
    sunday_capped = min(sunday, DATA_MAX)
    st.caption(f"📆 Week: **{monday}** (Mon) → **{sunday}** (Sun)" + (f" · capped to {sunday_capped} (data ends)" if sunday_capped < sunday else ""))

with col2:
    st.markdown("<br>", unsafe_allow_html=True)
    generate = st.button("⚡ Generate Brief", type="primary", use_container_width=True)

with col3:
    # RMTI preview for this week
    week_row = df_weekly[df_weekly['week_start'] == monday]
    if not week_row.empty:
        rmti_avg = week_row.iloc[0]['rmti_avg']
        rmti_max = week_row.iloc[0]['rmti_max']
        records  = int(week_row.iloc[0]['record_days_count'])
        record_badge = f" · 🔴 {records}" if records > 0 else ""
        st.markdown(f"""
        <div style="text-align:right;padding-top:24px;">
          <div style="font-size:11px;color:#8a93a8;text-transform:uppercase;letter-spacing:1.5px;">RMTI Avg · Max{record_badge}</div>
          <div style="font-size:24px;color:#00D4FF;font-family:monospace;font-weight:700;">
            {rmti_avg:.1f} · {rmti_max:.1f}
          </div>
        </div>
        """, unsafe_allow_html=True)


# ============================================================
# Generate on click
# ============================================================
if generate:
    week_row = df_weekly[df_weekly['week_start'] == monday]
    if week_row.empty:
        st.error(f"No weekly data for week of {monday}. Try a different date.")
    else:
        with st.spinner("⏳ Aggregating week + calling Claude for analysis..."):
            t0 = time.time()
            try:
                html, info = generate_weekly_brief(str(monday), df_weekly)
                elapsed = time.time() - t0
                pdf_bytes = HTML(string=html).write_pdf()
                ss.wb_last_brief = html
                ss.wb_last_pdf   = pdf_bytes
                ss.wb_last_info  = info
                ss.wb_last_week  = (str(monday), elapsed)
            except Exception as e:
                st.error(f"Failed to generate brief: {e}")
                ss.wb_last_brief = None
                ss.wb_last_pdf   = None


# ============================================================
# Render last brief (persists across reruns)
# ============================================================
if ss.wb_last_brief is not None:
    import streamlit.components.v1 as components
    components.html(ss.wb_last_brief, height=3800, scrolling=True)

    info = ss.wb_last_info or {}
    elapsed = ss.wb_last_week[1] if ss.wb_last_week else 0
    week_label = ss.wb_last_week[0] if ss.wb_last_week else "unknown"

    col_status, col_download = st.columns([3, 1])
    with col_status:
        st.markdown(f"""
        <div style="margin-top:14px;padding:10px 16px;background:rgba(0,212,255,0.05);
                    border-left:3px solid #00D4FF;border-radius:6px;font-size:12px;color:#8a93a8;">
            ✅ Generated in {elapsed:.1f}s · {info.get('tokens_in',0)} input + {info.get('tokens_out',0)} output tokens · ${info.get('cost_usd',0):.5f}
        </div>
        """, unsafe_allow_html=True)
    with col_download:
        st.markdown("<br>", unsafe_allow_html=True)
        if ss.get('wb_last_pdf'):
            st.download_button(
                "📥 Download PDF",
                data=ss.wb_last_pdf,
                file_name=f"agent_monsoon_weekly_{week_label}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
else:
    st.info("""
    👆 Pick any date above and click **Generate Brief**.

    The weekly brief includes:
    - Week-over-week deltas (RMTI / DAM avg / Arbitrage)
    - Headline metrics table (DAM vs GDAM aggregates)
    - Cross-Market indicators (avg RMTI + max RMTI day + record-setting day count + best arbitrage)
    - 4 charts: continuous MCP timeline / daily RMTI bars / intraday spread evolution / hour-of-day premium heatmap
    - AI-generated 5-section analysis (Headline · Weekly Dynamics · RMTI Verdict · Notable Days · Curtailment & Anomalies)

    Generation takes ~8-12 seconds.
    """)


# ============================================================
# Sidebar
# ============================================================
with st.sidebar:
    st.markdown("### 📆 Weekly Coverage")
    st.markdown(f"**Earliest week:** {df_weekly['week_start'].min()}")
    st.markdown(f"**Latest week:** {df_weekly['week_start'].max()}")
    st.markdown(f"**Total weeks:** {len(df_weekly)}")

    st.markdown("---")
    st.markdown("### 💡 Notable weeks")
    st.caption("Try these for interesting patterns:")

    # Top 3 worst-RMTI weeks
    worst_weeks = df_weekly.nlargest(3, 'rmti_max')
    for _, w in worst_weeks.iterrows():
        st.markdown(f"- **{w['week_start']}** · max RMTI {w['rmti_max']:.1f}")

    st.markdown("**Top arbitrage week:**")
    best_arb_week = df_weekly.loc[df_weekly['arbitrage_max'].idxmax()]
    st.markdown(f"- **{best_arb_week['week_start']}** · ₹{best_arb_week['arbitrage_max']:.2f}/kWh peak")

    st.markdown("---")
    st.markdown("### 📖 Key concepts")
    st.caption("""
    - **RMTI** = RPO market tightness (0-100)
    - **Record day** = new 30-day RMTI high
    - **Stressed block** = GDAM > DAM
    - **All prices in ₹/kWh**
    """)