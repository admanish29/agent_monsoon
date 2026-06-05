"""
pages/7_🔋_Arbitrage_Analysis.py — Multi-hour arbitrage distributional + time-series analysis.

For each duration (1h/2h/3h/4h) and path (DAM-only/GDAM-only/Cross/Best), shows:
  - Time-series chart (when multi-day)
  - Block-level distribution (histogram + KDE + normal-fit overlay)
  - Summary stats (mean, median, std, P10, P50, P90, min, max)

Reads precomputed columns from df_daily (84 multi-hour arbitrage fields).
Same UX pattern as Green Premium page.
"""

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import io
import base64
from datetime import date, timedelta
from scipy import stats as scipy_stats

from src.data_loader import load_dataframes
from src.green_premium import resolve_period, GRANULARITY_LEVELS


# ============================================================
# Page setup
# ============================================================
st.set_page_config(
    page_title="Arbitrage Analysis · Agent Monsoon",
    page_icon="🔋",
    layout="wide",
)


# ============================================================
# Styling (same as Green Premium for visual consistency)
# ============================================================
st.markdown("""
<style>
    footer {visibility: hidden;}
    #MainMenu {visibility: hidden;}

    .page-title {
        background: linear-gradient(135deg, #00D4FF 0%, #FFA500 50%, #4A90E2 100%);
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
    .selector-label {
        color: #00D4FF;
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        margin-bottom: 6px;
    }
    .metric-section-header {
        background: linear-gradient(90deg, rgba(0,212,255,0.15) 0%, transparent 100%);
        border-left: 4px solid #00D4FF;
        padding: 10px 16px;
        margin-top: 30px;
        margin-bottom: 16px;
        border-radius: 6px;
    }
    .metric-section-title {
        color: #E4E7EB;
        font-size: 20px;
        font-weight: 700;
        margin: 0;
    }
    .metric-section-subtitle {
        color: #8a93a8;
        font-size: 13px;
        margin-top: 4px;
    }
    .stats-card {
        background: linear-gradient(135deg, rgba(19, 24, 38, 0.85) 0%, rgba(26, 33, 56, 0.85) 100%);
        border: 1px solid rgba(31, 42, 68, 0.8);
        border-radius: 12px;
        padding: 16px 20px;
        margin: 10px 0;
    }
    .stats-label {
        color: #8a93a8;
        font-size: 10px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        margin-bottom: 4px;
    }
    .stats-value {
        color: #E4E7EB;
        font-size: 22px;
        font-weight: 700;
        font-family: 'SF Mono', 'Menlo', 'Consolas', monospace;
        line-height: 1.1;
    }
    .stats-unit {
        color: #00D4FF;
        font-size: 13px;
        font-weight: 500;
        margin-left: 4px;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================
# Header
# ============================================================
st.markdown('<div class="page-title">🔋 Arbitrage Analysis</div>', unsafe_allow_html=True)
st.markdown('<p class="page-subtitle">Multi-hour battery arbitrage spreads across durations and paths. Time-series + distribution + summary stats.</p>', unsafe_allow_html=True)


# ============================================================
# Load data
# ============================================================
data = load_dataframes()
df_daily = data['df_daily']
DATA_MIN = df_daily['date'].min().date()
DATA_MAX = df_daily['date'].max().date()

available_years = sorted(df_daily['date'].dt.year.unique().tolist())
year_to_months = {}
for y in available_years:
    months_in_year = sorted(df_daily[df_daily['date'].dt.year == y]['date'].dt.month.unique().tolist())
    year_to_months[y] = months_in_year


# ============================================================
# Session state
# ============================================================
ss = st.session_state
if "arb_initialized" not in ss:
    ss.arb_initialized = True
    ss.arb_granularity = "Month"
    ss.arb_day_date    = DATA_MAX
    ss.arb_range_start = max(DATA_MIN, DATA_MAX - timedelta(days=29))
    ss.arb_range_end   = DATA_MAX
    ss.arb_month_year  = available_years[-1]
    ss.arb_month_month = year_to_months[available_years[-1]][-1]
    ss.arb_year        = available_years[-1]
    ss.arb_duration    = "4-hour"
    ss.arb_path        = "Best (across 3 paths)"
    ss.arb_last_result = None


# ============================================================
# Selectors row 1: Granularity + Duration + Path
# ============================================================
col_gran, col_dur, col_path = st.columns([1.2, 1, 1.3])

with col_gran:
    st.markdown('<div class="selector-label">⏱️ TIME GRANULARITY</div>', unsafe_allow_html=True)
    granularity = st.radio(
        "Granularity",
        options=GRANULARITY_LEVELS,
        index=GRANULARITY_LEVELS.index(ss.arb_granularity),
        label_visibility="collapsed",
        horizontal=False,
        key="arb_granularity_widget",
    )
    ss.arb_granularity = granularity

with col_dur:
    st.markdown('<div class="selector-label">⚡ DURATION</div>', unsafe_allow_html=True)
    duration_options = ["1-hour", "2-hour", "3-hour", "4-hour"]
    duration_label = st.radio(
        "Duration",
        options=duration_options,
        index=duration_options.index(ss.arb_duration),
        label_visibility="collapsed",
        horizontal=False,
        key="arb_duration_widget",
    )
    ss.arb_duration = duration_label
    duration_n = int(duration_label.split('-')[0])   # 1, 2, 3, or 4

with col_path:
    st.markdown('<div class="selector-label">🛤️ PATH</div>', unsafe_allow_html=True)
    path_options = ["DAM-only", "GDAM-only", "Cross (GDAM→DAM)", "Best (across 3 paths)"]
    path_label = st.radio(
        "Path",
        options=path_options,
        index=path_options.index(ss.arb_path),
        label_visibility="collapsed",
        horizontal=False,
        key="arb_path_widget",
    )
    ss.arb_path = path_label
    path_to_key = {
        "DAM-only":               "dam",
        "GDAM-only":              "gdam",
        "Cross (GDAM→DAM)":       "cross",
        "Best (across 3 paths)":  "best",
    }
    path_key = path_to_key[path_label]


# ============================================================
# Period picker (adapts to granularity)
# ============================================================
st.markdown("---")
st.markdown('<div class="selector-label">📅 TIME WINDOW</div>', unsafe_allow_html=True)

period_kwargs = {}

if granularity == "Day":
    selected = st.date_input("Date", value=ss.arb_day_date,
                              min_value=DATA_MIN, max_value=DATA_MAX, key="arb_day_picker")
    ss.arb_day_date = selected
    period_kwargs = {"date": str(selected)}

elif granularity == "Day Range":
    col_a, col_b = st.columns(2)
    with col_a:
        s = st.date_input("Start date", value=ss.arb_range_start,
                           min_value=DATA_MIN, max_value=DATA_MAX, key="arb_range_start_picker")
        ss.arb_range_start = s
    with col_b:
        e = st.date_input("End date", value=ss.arb_range_end,
                           min_value=DATA_MIN, max_value=DATA_MAX, key="arb_range_end_picker")
        ss.arb_range_end = e
    if e < s:
        st.warning("⚠️ End date is before start date. Please correct.")
    period_kwargs = {"start_date": str(s), "end_date": str(e)}

elif granularity == "Month":
    col_a, col_b = st.columns(2)
    with col_a:
        y = st.selectbox("Year", options=available_years,
                          index=available_years.index(ss.arb_month_year), key="arb_month_year_picker")
        ss.arb_month_year = y
    months_available = year_to_months[y]
    with col_b:
        month_names = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
        month_label_to_num = {f"{month_names[m-1]} ({m:02d})": m for m in months_available}
        default_label = next((lbl for lbl, num in month_label_to_num.items() if num == ss.arb_month_month),
                              list(month_label_to_num.keys())[-1])
        chosen_label = st.selectbox("Month", options=list(month_label_to_num.keys()),
                                      index=list(month_label_to_num.keys()).index(default_label),
                                      key="arb_month_picker")
        ss.arb_month_month = month_label_to_num[chosen_label]
    period_kwargs = {"year": y, "month": ss.arb_month_month}

elif granularity == "Year":
    y = st.selectbox("Year", options=available_years,
                      index=available_years.index(ss.arb_year), key="arb_year_picker")
    ss.arb_year = y
    period_kwargs = {"year": y}


# ============================================================
# Run button
# ============================================================
st.markdown("---")
run = st.button("⚡ Run Arbitrage Analysis", type="primary", use_container_width=True)
# RtE caveat — italics, right-aligned, below all selectors
from src.arbitrage import rte_caveat_text
st.markdown(f"""
<div style="text-align:right;font-size:12px;color:#8a93a8;font-style:italic;margin-top:6px;margin-bottom:8px;">
  ({rte_caveat_text(include_formula=True)})
</div>
""", unsafe_allow_html=True)

# ============================================================
# Helpers
# ============================================================
def _fig_to_base64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format='png', bbox_inches='tight', dpi=130, facecolor='white')
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode('utf-8')


def get_arb_series(start_date, end_date, duration_n, path_key):
    """Pull the arbitrage spread column from df_daily for the period.
    Returns (daily_series_df, distribution_values, n_days)."""
    s = pd.to_datetime(start_date)
    e = pd.to_datetime(end_date)
    sub = df_daily[(df_daily['date'] >= s) & (df_daily['date'] <= e)].copy()

    spread_col = f'arb_{duration_n}h_{path_key}_spread'
    if spread_col not in sub.columns:
        return None, None, 0

    daily = sub[['date', spread_col]].rename(columns={spread_col: 'spread'}).copy()
    daily['date'] = pd.to_datetime(daily['date']).dt.date
    distribution = daily['spread'].dropna().tolist()
    return daily, distribution, len(daily)


def chart_timeseries_arb(daily_df, metric_label, color):
    if daily_df is None or daily_df.empty:
        return None
    fig, ax = plt.subplots(figsize=(10, 3.2))
    df = daily_df.copy()
    df['date'] = pd.to_datetime(df['date'])
    df_sorted = df.sort_values('date').reset_index(drop=True)
    ax.plot(df_sorted['date'], df_sorted['spread'], color=color, linewidth=1.8,
            marker='o', markersize=3, alpha=0.85)
    ax.set_title(f"{metric_label} — Daily Time Series", fontsize=12, fontweight='bold')
    ax.set_ylabel("Spread (₹/kWh)", fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate(rotation=30)
    return _fig_to_base64(fig)


def chart_distribution_arb(values, metric_label, color):
    arr = np.array([v for v in values if v is not None and not np.isnan(v)])
    if len(arr) == 0:
        return None

    fig, ax = plt.subplots(figsize=(10, 3.5))
    ax.hist(arr, bins=40, color=color, alpha=0.55, edgecolor='white', linewidth=0.4,
            density=True, label='Empirical (histogram)')

    # KDE
    try:
        if len(arr) > 1 and np.std(arr) > 0:
            kde = scipy_stats.gaussian_kde(arr)
            x_smooth = np.linspace(arr.min(), arr.max(), 200)
            ax.plot(x_smooth, kde(x_smooth), color='#1F3864', linewidth=2.2, label='Empirical (KDE)')
    except Exception:
        pass

    # Normal fit
    mu, sigma = float(arr.mean()), float(arr.std(ddof=1)) if len(arr) > 1 else 0.0
    if sigma > 0:
        x_norm = np.linspace(arr.min(), arr.max(), 200)
        normal_pdf = scipy_stats.norm.pdf(x_norm, mu, sigma)
        ax.plot(x_norm, normal_pdf, color='#D7263D', linewidth=2.2, linestyle='--',
                label=f'Normal fit (μ={mu:.2f}, σ={sigma:.2f})')

    # Mean + median lines
    ax.axvline(mu, color='#D7263D', linestyle=':', alpha=0.7, linewidth=1.2)
    median = float(np.median(arr))
    ax.axvline(median, color='#2E8B57', linestyle=':', alpha=0.7, linewidth=1.2,
                label=f'Median ({median:.2f})')

    ax.set_title(f"{metric_label} — Daily Spread Distribution (n={len(arr)} days)",
                  fontsize=12, fontweight='bold')
    ax.set_xlabel("Spread (₹/kWh)", fontsize=9)
    ax.set_ylabel("Density", fontsize=9)
    ax.legend(loc='best', fontsize=8, framealpha=0.9)
    ax.grid(True, alpha=0.3)
    return _fig_to_base64(fig)


def summary_stats(values):
    arr = np.array([v for v in values if v is not None and not np.isnan(v)])
    if len(arr) == 0:
        return {k: None for k in ['mean','median','std','p10','p50','p90','min','max','n']}
    return {
        'mean':   round(float(arr.mean()),   3),
        'median': round(float(np.median(arr)),3),
        'std':    round(float(arr.std(ddof=1)) if len(arr) > 1 else 0.0, 3),
        'p10':    round(float(np.percentile(arr, 10)), 3),
        'p50':    round(float(np.percentile(arr, 50)), 3),
        'p90':    round(float(np.percentile(arr, 90)), 3),
        'min':    round(float(arr.min()), 3),
        'max':    round(float(arr.max()), 3),
        'n':      int(len(arr)),
    }


def render_stats_cards(stats):
    cards = [('MEAN','mean'),('MEDIAN','median'),('STD','std'),
             ('P10','p10'),('P50','p50'),('P90','p90'),
             ('MIN','min'),('MAX','max'),('N (DAYS)','n')]
    for i in range(0, len(cards), 3):
        cols = st.columns(3)
        for j, (label, key) in enumerate(cards[i:i+3]):
            with cols[j]:
                val = stats.get(key)
                if val is None:
                    val_str = "—"
                elif key == 'n':
                    val_str = f"{val:,}"
                else:
                    val_str = f"{val:,.3f}" if abs(val) < 1000 else f"{val:,.0f}"
                unit = "" if key == 'n' else "₹/kWh"
                st.markdown(f"""
                <div class="stats-card">
                    <div class="stats-label">{label}</div>
                    <div class="stats-value">{val_str}<span class="stats-unit">{unit}</span></div>
                </div>
                """, unsafe_allow_html=True)


# ============================================================
# Execute on click
# ============================================================
if run:
    try:
        s, e, period_label = resolve_period(granularity, **period_kwargs)
        daily_df, distribution, n_days = get_arb_series(str(s), str(e), duration_n, path_key)
        if daily_df is None or daily_df.empty:
            st.error(f"No arbitrage data between {s} and {e}.")
            ss.arb_last_result = None
        else:
            stats = summary_stats(distribution)
            ss.arb_last_result = {
                'period_label': period_label,
                'start_date':   s,
                'end_date':     e,
                'duration':     duration_label,
                'duration_n':   duration_n,
                'path':         path_label,
                'path_key':     path_key,
                'granularity':  granularity,
                'daily_df':     daily_df,
                'distribution': distribution,
                'stats':        stats,
                'n_days':       n_days,
            }
    except Exception as ex:
        st.error(f"Analysis failed: {ex}")
        ss.arb_last_result = None


# ============================================================
# Render last result (persists)
# ============================================================
if ss.arb_last_result is not None:
    r = ss.arb_last_result
    metric_label = f"{r['duration']} Arbitrage — {r['path']}"

    st.markdown(f"### 📋 Analysis: {r['period_label']}")
    st.caption(f"Metric: **{metric_label}** · Window: **{r['start_date']} → {r['end_date']}** · {r['n_days']} day(s) with data")

    # Section header
    st.markdown(f"""
    <div class="metric-section-header">
        <div class="metric-section-title">{metric_label}</div>
        <div class="metric-section-subtitle">Spread series across {r['n_days']} day(s) · Reading from precomputed df_daily</div>
    </div>
    """, unsafe_allow_html=True)

    # Time-series (only if multi-day)
    if r['granularity'] != "Day":
        ts_b64 = chart_timeseries_arb(r['daily_df'], metric_label, color='#FFA500')
        if ts_b64:
            st.markdown(f'<img src="data:image/png;base64,{ts_b64}" style="width:100%;margin-bottom:8px;"/>',
                          unsafe_allow_html=True)
    else:
        # For single day, show the spread value directly
        single_val = r['daily_df'].iloc[0]['spread'] if not r['daily_df'].empty else None
        if single_val is not None:
            st.markdown(f"""
            <div style="text-align:center;padding:30px;background:rgba(0,212,255,0.05);border-radius:12px;margin:10px 0;">
                <div style="font-size:12px;color:#8a93a8;text-transform:uppercase;letter-spacing:1.5px;">Spread for {r['start_date']}</div>
                <div style="font-size:48px;color:#FFA500;font-family:monospace;font-weight:700;line-height:1.1;">₹{single_val:.2f}/kWh</div>
            </div>
            """, unsafe_allow_html=True)

    # Distribution (skip for single day — only 1 point)
    if r['granularity'] != "Day" and r['n_days'] >= 5:
        dist_b64 = chart_distribution_arb(r['distribution'], metric_label, color='#FFA500')
        if dist_b64:
            st.markdown(f'<img src="data:image/png;base64,{dist_b64}" style="width:100%;margin-bottom:8px;"/>',
                          unsafe_allow_html=True)
    elif r['granularity'] != "Day" and r['n_days'] < 5:
        st.info(f"📊 Distribution chart requires ≥5 days. Current: {r['n_days']} day(s). Try a longer window.")

    # Stats cards (always)
    render_stats_cards(r['stats'])

else:
    st.info("""
    👆 Pick a time granularity + period + duration + path, then click **Run Arbitrage Analysis**.

    The page shows:
    - **Time-series** of the chosen arbitrage spread across the selected period (when multi-day)
    - **Distribution** of daily spreads with histogram + KDE + normal-fit overlay (requires ≥5 days)
    - **Summary stats**: mean, median, std, P10, P50, P90, min, max

    **Duration choices:** 1h / 2h / 3h / 4h — battery charging+discharging cycle length.
    **Path choices:** DAM-only / GDAM-only / Cross (GDAM→DAM) / Best (across 3 paths).
    """)


# ============================================================
# Sidebar
# ============================================================
with st.sidebar:
    st.markdown("### 🔋 Arbitrage Analysis")
    st.markdown(f"**Coverage:** {DATA_MIN} → {DATA_MAX}")
    st.markdown(f"**Durations:** 1h / 2h / 3h / 4h")
    st.markdown(f"**Paths:** DAM / GDAM / Cross / Best")

    st.markdown("---")
    st.markdown("### 📖 Methodology notes")
    st.caption("""
    - **N-hour arbitrage:** N hours buy + ≥15-min cooling + N hours sell
    - **Window flexibility:** Each "hour" = 4 contiguous 15-min blocks. Gap between hours: 0 or 1 block.
    - **Best path:** highest spread across DAM-only / GDAM-only / Cross
    - **Cross path:** buy GDAM (green), sell DAM (grey)
    - **Spread = sell_avg − buy_avg** in ₹/kWh
    - **Time-series & distribution** show daily best-spread evolution
    """)

    st.markdown("---")
    st.markdown("### 💡 Try these")
    st.caption("""
    - **Year 2025, 4h-Best**: full-year picture of optimal long-duration arbitrage
    - **Month May 2026, 1h-DAM**: distribution of best 1-hour DAM spreads
    - **Day 2026-05-05, 4h-Cross**: single-day cross-market arb value
    """)