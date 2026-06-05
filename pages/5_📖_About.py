"""
pages/5_📖_About.py — User guide / About page.

Three sections:
  1. Dataset Overview — what data, where from, methodology
  2. Metric Library — definitions for every metric used
  3. Feature Guide — what each page does
"""

import streamlit as st
import pandas as pd

from src.data_loader import load_dataframes


# ============================================================
# Page setup
# ============================================================
st.set_page_config(
    page_title="About · Agent Monsoon",
    page_icon="📖",
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
    .section-header {
        color: #00D4FF;
        font-size: 13px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 2px;
        margin-top: 32px;
        margin-bottom: 16px;
        border-bottom: 1px solid rgba(0, 212, 255, 0.15);
        padding-bottom: 10px;
    }
    .metric-def-card {
        background: rgba(19, 24, 38, 0.65);
        border: 1px solid rgba(31, 42, 68, 0.8);
        border-left: 3px solid #00D4FF;
        border-radius: 8px;
        padding: 14px 18px;
        margin-bottom: 12px;
    }
    .metric-def-name {
        color: #00D4FF;
        font-size: 14px;
        font-weight: 700;
        margin-bottom: 4px;
        font-family: 'SF Mono', 'Menlo', 'Consolas', monospace;
    }
    .metric-def-formula {
        color: #6b7387;
        font-size: 12px;
        font-style: italic;
        margin-bottom: 6px;
    }
    .metric-def-body {
        color: #E4E7EB;
        font-size: 13px;
        line-height: 1.5;
    }
    .feature-info-card {
        background: rgba(19, 24, 38, 0.65);
        border: 1px solid rgba(31, 42, 68, 0.8);
        border-radius: 10px;
        padding: 16px 20px;
        margin-bottom: 12px;
    }
    .feature-info-title {
        color: #00D4FF;
        font-size: 15px;
        font-weight: 700;
        margin-bottom: 6px;
    }
    .feature-info-body {
        color: #E4E7EB;
        font-size: 13px;
        line-height: 1.5;
    }
    .feature-info-when {
        color: #8a93a8;
        font-size: 12px;
        font-style: italic;
        margin-top: 8px;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================
# Header
# ============================================================
st.markdown('<div class="page-title">📖 About Agent Monsoon</div>', unsafe_allow_html=True)
st.markdown('<p class="page-subtitle">Methodology, metrics, feature reference. Everything you need to use the tool effectively.</p>', unsafe_allow_html=True)


# ============================================================
# Load data (for dataset stats display)
# ============================================================
data = load_dataframes()
df_daily  = data['df_daily']
df_blocks = data['df_blocks']
df_weekly = data['df_weekly']
metadata  = data['metadata']


# ============================================================
# SECTION 1: Dataset Overview
# ============================================================
st.markdown('<div class="section-header">📊 DATASET OVERVIEW</div>', unsafe_allow_html=True)

col1, col2 = st.columns([1, 1])
with col1:
    st.markdown("### What's in here")
    st.markdown(f"""
    **Source:** Indian Energy Exchange (IEX) — iexindia.com market snapshot exports.

    **Markets covered:** Two parallel auctions:
    - **DAM** — Day-Ahead Market (conventional/grey power)
    - **GDAM** — Green Day-Ahead Market (renewable-sourced power only)

    **Granularity:** 96 fifteen-minute blocks per day, per market.

    **Coverage:**
    - {df_daily['date'].min().date()} to {df_daily['date'].max().date()}
    - {len(df_daily)} days total
    - {len(df_blocks):,} block-level rows (DAM + GDAM combined)
    - {len(df_weekly)} weekly aggregates
    """)

with col2:
    st.markdown("### Methodology notes")
    st.markdown("""
    - All prices stored as **₹/kWh** (rupees per kilowatt-hour). IEX publishes in ₹/MWh — Agent Monsoon auto-converts on load.
    - **Volumes** captured at block-level: MCV (cleared), Sell Bid (offered supply), Purchase Bid (demanded). GDAM further split into Solar / Non-Solar / Hydro.
    - **30-day rolling baselines** used for anomaly detection (Metric 4 z-scores) and RMTI normalization. Rolling window updates daily.
    - **ISO weeks** used for weekly aggregation (Monday-Sunday).
    - **Fiscal calendar awareness:** Indian FY runs 1 April → 31 March. H1 close = 30 September. Agent narrative contextualizes when relevant.
    """)


# ============================================================
# SECTION 2: Metric Library
# ============================================================
st.markdown('<div class="section-header">📐 METRIC LIBRARY</div>', unsafe_allow_html=True)

st.markdown("Every metric Agent Monsoon tracks. Group definitions below.")

# Pricing
st.markdown("#### 💰 Pricing")
st.markdown("""
<div class="metric-def-card">
    <div class="metric-def-name">MCP (Market Clearing Price)</div>
    <div class="metric-def-formula">unit: ₹/kWh · per block, per market</div>
    <div class="metric-def-body">The auction-clearing price for a 15-min block. Set by the intersection of supply (sell bids) and demand (purchase bids). DAM and GDAM clear separately each day.</div>
</div>
<div class="metric-def-card">
    <div class="metric-def-name">DAM−GDAM Premium</div>
    <div class="metric-def-formula">= DAM_MCP − GDAM_MCP · per block · ₹/kWh</div>
    <div class="metric-def-body">Positive = green discount (GDAM cheaper, usually solar peak). Negative = green stress (GDAM costlier, RPO compliance pressure).</div>
</div>
<div class="metric-def-card">
    <div class="metric-def-name">Intraday Spread</div>
    <div class="metric-def-formula">= max(MCP across 96 blocks) − min(MCP) · daily · ₹/kWh</div>
    <div class="metric-def-body">The peak-to-trough range within a single day. Wide spread = storage arbitrage value high, peaking stress present. Narrow spread = oversupply or flat demand.</div>
</div>
""", unsafe_allow_html=True)

# Volumes
st.markdown("#### 📦 Volumes")
st.markdown("""
<div class="metric-def-card">
    <div class="metric-def-name">MCV (Market Clearing Volume)</div>
    <div class="metric-def-formula">unit: MW · per block</div>
    <div class="metric-def-body">The actual power cleared in the auction for a 15-min block. GDAM splits into Solar / Non-Solar / Hydro sub-volumes.</div>
</div>
<div class="metric-def-card">
    <div class="metric-def-name">Sell Bid / Purchase Bid</div>
    <div class="metric-def-formula">unit: MW · per block</div>
    <div class="metric-def-body">Sell Bid = supply offered into the auction. Purchase Bid = demand demanded. The gap tells you about market tightness even when MCP looks calm.</div>
</div>
""", unsafe_allow_html=True)

# Liquidity
st.markdown("#### 💧 Liquidity Health")
st.markdown("""
<div class="metric-def-card">
    <div class="metric-def-name">DFR (Demand Fulfillment Ratio)</div>
    <div class="metric-def-formula">= (MCV / Purchase Bid) × 100 · per block · %</div>
    <div class="metric-def-body">Of every unit of demand bid in, what fraction actually got served. 100% = perfect match. 60% = supply-constrained (only 60% of buyers got their order filled). Lower in GDAM during pre-dawn (renewable scarcity).</div>
</div>
<div class="metric-def-card">
    <div class="metric-def-name">BCR (Bid Coverage Ratio)</div>
    <div class="metric-def-formula">= Sell Bid / Purchase Bid · per block · x (ratio)</div>
    <div class="metric-def-body">How much supply was offered relative to demand. >1.0 = oversupplied market (extra sellers). <1.0 = undersupplied (more buyers than sellers). Strong leading indicator for price direction.</div>
</div>
""", unsafe_allow_html=True)

# Cross-market & RMTI
st.markdown("#### 🎯 RMTI — RPO Market Tightness Index")
st.markdown("""
<div class="metric-def-card">
    <div class="metric-def-name">RMTI Composite</div>
    <div class="metric-def-formula">= 0.4 × BPC_norm + 0.4 × AGP_norm + 0.2 × PTC_norm · daily · 0-100 scale</div>
    <div class="metric-def-body">A single number capturing how stressed the green power market is relative to conventional. Higher = greater RPO compliance pressure. Normalized against rolling 30-day max of each component.</div>
</div>
<div class="metric-def-card">
    <div class="metric-def-name">BPC — Block Premium Count (Frequency)</div>
    <div class="metric-def-formula">= % of 96 blocks where GDAM_MCP > DAM_MCP</div>
    <div class="metric-def-body">How often was green power costlier during the day? Measures the frequency of tightness.</div>
</div>
<div class="metric-def-card">
    <div class="metric-def-name">AGP — Average Green Premium (Severity)</div>
    <div class="metric-def-formula">= mean(GDAM − DAM) on stressed blocks · ₹/kWh</div>
    <div class="metric-def-body">When green WAS costlier, how much costlier on average? Measures the severity.</div>
</div>
<div class="metric-def-card">
    <div class="metric-def-name">PTC — Peak-hour Tightness Concentration</div>
    <div class="metric-def-formula">= % of stressed blocks falling in 18:00-24:00 window</div>
    <div class="metric-def-body">Of the day's stress, how much was concentrated in evening peak? High PTC = evening-driven; low PTC = structural across the day.</div>
</div>
<div class="metric-def-card">
    <div class="metric-def-name">Record Day Flag</div>
    <div class="metric-def-formula">boolean · daily</div>
    <div class="metric-def-body">True if the day's RMTI was a new high vs the prior 30 days. Useful for spotting regime shifts.</div>
</div>
""", unsafe_allow_html=True)

# Congestion
st.markdown("#### 🚦 Grid Congestion & Curtailment")
st.markdown("""
<div class="metric-def-card">
    <div class="metric-def-name">Total Congestion</div>
    <div class="metric-def-formula">= (MCV − FSV) / MCV × 100 · per block · %</div>
    <div class="metric-def-body">FSV = Final Scheduled Volume (what actually got dispatched). Difference = curtailed by grid constraints. Usually 0% on a clean grid day; spikes during transmission stress.</div>
</div>
<div class="metric-def-card">
    <div class="metric-def-name">Source-wise Curtailment (Solar / Non-Solar / Hydro)</div>
    <div class="metric-def-formula">same formula, split by source · GDAM only</div>
    <div class="metric-def-body">Tells you which renewable type got curtailed. Solar curtailment at noon = evacuation tightness in solar-heavy zones. Worth tracking as renewable capacity grows.</div>
</div>
""", unsafe_allow_html=True)

# Anomaly
st.markdown("#### 🚨 Anomaly Detection")
st.markdown("""
<div class="metric-def-card">
    <div class="metric-def-name">Metric 4 — z-score Anomaly Flag</div>
    <div class="metric-def-formula">|today_MCP − 30d_same_block_mean| / 30d_std > 2 · per block</div>
    <div class="metric-def-body">Flags blocks where MCP deviated more than 2 standard deviations from its own 30-day baseline. Direction = HIGH (price spike) or LOW (price crash). Surface drivers like grid outages, weather extremes, or demand shocks.</div>
</div>
""", unsafe_allow_html=True)

# Arbitrage
st.markdown("#### 🔋 Multi-Hour Battery Arbitrage")
st.markdown("""
<div class="metric-def-card">
    <div class="metric-def-name">Multi-Hour Arbitrage Spread (1h / 2h / 3h / 4h)</div>
    <div class="metric-def-formula">= sell_avg − buy_avg / RtE · per kWh of energy SOLD · ₹/kWh · RtE = 0.83 (83%)</div>
    <div class="metric-def-body">The best RtE-corrected arbitrage spread achievable for a battery storage operator on a given day, across 4 durations (1h, 2h, 3h, 4h) and 3 paths (DAM-only, GDAM-only, Cross GDAM→DAM). Each "hour" of buying or selling = 4 contiguous 15-min blocks. Between consecutive hours within a window, max 1-block (15-min) gap is allowed. Between buy-end and sell-start, minimum 1 block (15-min) cooling. Algorithm exhaustively searches all valid combinations and reports the spread, optimal buy/sell windows, and best path. For full distributional + time-series analysis, see the <strong>🔋 Arbitrage Analysis</strong> page.</div>
</div>
""", unsafe_allow_html=True)


# ============================================================
# SECTION 3: Feature Guide
# ============================================================
st.markdown('<div class="section-header">🗺️ FEATURE GUIDE</div>', unsafe_allow_html=True)

st.markdown("Each page of Agent Monsoon has a specific purpose. Use this guide to pick the right one.")

features = [
    ("📅 Daily Brief",
     "Generate a full one-day market brief: headline metrics table (DAM vs GDAM), 4 charts (intraday MCP, premium, RMTI gauge, source curtailment), AI-generated 5-section narrative.",
     "Pick a date, click Generate. ~10 seconds. Download PDF if needed.",
     "Use when you want depth on a specific day — yesterday's stress, a known anomaly, an FY-end day, etc."),

    ("💬 Ask Agent Monsoon",
     "Free-form conversational interface backed by the agent's 8 tools. Supports multi-turn memory and dataset-grounded analysis.",
     "Type any question. Agent infers intent, calls the right tool(s), responds in natural language. Conversations auto-save and can be resumed.",
     "Use for ad-hoc analysis: 'Compare Q1 2025 vs Q1 2026', 'Which days had the worst RMTI in March?', 'What was 6:30 PM like on 5 May?'"),

    ("🔍 Data Explorer",
     "Direct query interface for raw block-level data. 5 granularities (Block / Block Range / Day / Day Range / Week), 33 metrics across 7 categories, smart chart grouping by scale.",
     "Pick a granularity → pick metrics → run. Auto-recommended view + override dropdown + CSV/Excel download.",
     "Use when you know exactly what numbers you want. Faster than asking the agent for simple lookups. Best for exporting data for further analysis."),

    ("📆 Weekly Brief",
     "Mon-Sun aggregated brief with cross-day pattern detection. Week-over-week deltas, 4 charts (continuous MCP timeline, RMTI evolution, intraday spread lines, hour-of-day heatmap), 5-section narrative.",
     "Pick any date — auto-snaps to that Monday. Click Generate. Download PDF.",
     "Use for spotting patterns no single daily brief can show: 'Is this week structurally tight or anomaly-driven?', 'Did Wednesday's stress eased by Sunday?'"),

    ("🔋 Arbitrage Analysis",
     "Multi-hour battery arbitrage analysis. 4 durations (1h/2h/3h/4h) × 4 paths (DAM/GDAM/Cross/Best). RtE-corrected spreads (per kWh sold). Same architecture as Green Premium: time-series + distribution + summary stats.",
     "Pick granularity / period / duration / path → Run Analysis.",
     "Use to answer: 'How big is the arbitrage opportunity for a 4-hour battery?' or 'How has 2h arbitrage evolved over the year?' Best for spotting trends + outliers + understanding the spread distribution."),

    ("💚 Green Premium",
     "Distributional + time-series analysis of Green Premium (DAM−GDAM) and Bid Coverage Ratios. 4 granularities, histogram + KDE + normal-fit overlay, summary stats.",
     "Pick granularity / period → Run Analysis. Optional log-scale toggle for BCR.",
     "Use to understand: 'Is the green market structurally tight?', 'What's the BCR distribution shape?', 'How leptokurtic is GP?'"),
    ("📖 About",
     "This page. Dataset overview + metric library + feature guide.",
     "Browse the sections.",
     "Use when you forget what a metric means, or want to share context with someone new to the tool."),
]

for title, what, how, when in features:
    st.markdown(f"""
    <div class="feature-info-card">
        <div class="feature-info-title">{title}</div>
        <div class="feature-info-body"><b>What:</b> {what}</div>
        <div class="feature-info-body"><b>How:</b> {how}</div>
        <div class="feature-info-when"><b>When to use:</b> {when}</div>
    </div>
    """, unsafe_allow_html=True)


# ============================================================
# Footer — build/version info
# ============================================================
st.markdown('<div class="section-header">ℹ️ BUILD INFO</div>', unsafe_allow_html=True)

st.markdown(f"""
- **Streamlit version:** `{st.__version__}`
- **Pickle version:** `{metadata.get('version', 'unknown')}`
- **Last data refresh:** `{pd.Timestamp(metadata.get('last_saved')).strftime('%Y-%m-%d %H:%M') if metadata.get('last_saved') else 'unknown'}`
- **Built by:** Manish Anand · Agent Monsoon v1
- **AI:** Claude Haiku 4.5 (Anthropic)
""")


# ============================================================
# Sidebar
# ============================================================
with st.sidebar:
    st.markdown("### 📖 Quick Glossary")
    st.markdown("""
    - **DAM** — Day-Ahead Market (grey)
    - **GDAM** — Green Day-Ahead Market
    - **MCP** — Market Clearing Price
    - **MCV** — Market Clearing Volume
    - **FSV** — Final Scheduled Volume
    - **RMTI** — RPO Market Tightness
    - **BPC** — Block Premium Count
    - **AGP** — Avg Green Premium
    - **PTC** — Peak Tightness Concentration
    - **DFR** — Demand Fulfillment Ratio
    - **BCR** — Bid Coverage Ratio
    """)

    st.markdown("---")
    st.markdown("### 🔗 Jump to")
    st.markdown("""
    - [📊 Dataset Overview](#dataset-overview)
    - [📐 Metric Library](#metric-library)
    - [🗺️ Feature Guide](#feature-guide)
    """)