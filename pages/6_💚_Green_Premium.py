"""
pages/6_💚_Green_Premium.py — Green Premium + BCR distributional analysis.

For any time period (Day / Day Range / Month / Year), shows:
  - Green Premium (GP = DAM_MCP − GDAM_MCP) analysis
  - DAM BCR analysis (volume-weighted)
  - GDAM BCR analysis (volume-weighted)

Each shows: time-series (if multi-day) + distribution (histogram + normal overlay) + summary stats.
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
from src.green_premium import (
    GRANULARITY_LEVELS,
    resolve_period,
    get_gp_analysis,
    get_bcr_analysis,
    normal_fit_params,
)


# ============================================================
# Page setup
# ============================================================
st.set_page_config(
    page_title="Green Premium · Agent Monsoon",
    page_icon="💚",
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
        background: linear-gradient(135deg, #00D4FF 0%, #2E8B57 50%, #4A90E2 100%);
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
st.markdown('<div class="page-title">💚 Green Premium Analysis</div>', unsafe_allow_html=True)
st.markdown('<p class="page-subtitle">Distributional view of Green Premium (DAM−GDAM) and Bid Coverage Ratio. Time-series + histogram + normal-fit overlay.</p>', unsafe_allow_html=True)


# ============================================================
# Load data + bounds
# ============================================================
data = load_dataframes()
df_daily = data['df_daily']
DATA_MIN = df_daily['date'].min().date()
DATA_MAX = df_daily['date'].max().date()

# Available years and months in the dataset
available_years = sorted(df_daily['date'].dt.year.unique().tolist())
year_to_months = {}
for y in available_years:
    months_in_year = sorted(df_daily[df_daily['date'].dt.year == y]['date'].dt.month.unique().tolist())
    year_to_months[y] = months_in_year


# ============================================================
# Session state
# ============================================================
ss = st.session_state
if "gp_initialized" not in ss:
    ss.gp_initialized   = True
    ss.gp_granularity   = "Month"
    ss.gp_day_date      = DATA_MAX
    ss.gp_range_start   = max(DATA_MIN, DATA_MAX - timedelta(days=29))
    ss.gp_range_end     = DATA_MAX
    ss.gp_month_year    = available_years[-1]
    ss.gp_month_month   = year_to_months[available_years[-1]][-1]
    ss.gp_year          = available_years[-1]
    ss.gp_log_scale_bcr = False
    ss.gp_last_result   = None


# ============================================================
# Granularity selector
# ============================================================
st.markdown('<div class="selector-label">⏱️ TIME GRANULARITY</div>', unsafe_allow_html=True)
granularity = st.radio(
    "Granularity",
    options=GRANULARITY_LEVELS,
    horizontal=True,
    label_visibility="collapsed",
    index=GRANULARITY_LEVELS.index(ss.gp_granularity),
    key="gp_granularity_widget",
)
ss.gp_granularity = granularity


# ============================================================
# Period picker (adapts to granularity)
# ============================================================
st.markdown("---")
st.markdown('<div class="selector-label">📅 TIME WINDOW</div>', unsafe_allow_html=True)

period_kwargs = {}

if granularity == "Day":
    selected = st.date_input("Date", value=ss.gp_day_date,
                              min_value=DATA_MIN, max_value=DATA_MAX, key="gp_day_picker")
    ss.gp_day_date = selected
    period_kwargs = {"date": str(selected)}

elif granularity == "Day Range":
    col_a, col_b = st.columns(2)
    with col_a:
        s = st.date_input("Start date", value=ss.gp_range_start,
                           min_value=DATA_MIN, max_value=DATA_MAX, key="gp_range_start_picker")
        ss.gp_range_start = s
    with col_b:
        e = st.date_input("End date", value=ss.gp_range_end,
                           min_value=DATA_MIN, max_value=DATA_MAX, key="gp_range_end_picker")
        ss.gp_range_end = e
    if e < s:
        st.warning("⚠️ End date is before start date. Please correct.")
    period_kwargs = {"start_date": str(s), "end_date": str(e)}

elif granularity == "Month":
    col_a, col_b = st.columns(2)
    with col_a:
        y = st.selectbox("Year", options=available_years,
                          index=available_years.index(ss.gp_month_year), key="gp_month_year_picker")
        ss.gp_month_year = y
    months_available = year_to_months[y]
    with col_b:
        # Build month labels
        month_names = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
        month_label_to_num = {f"{month_names[m-1]} ({m:02d})": m for m in months_available}
        # Pick default
        default_label = next((lbl for lbl, num in month_label_to_num.items() if num == ss.gp_month_month),
                              list(month_label_to_num.keys())[-1])
        chosen_label = st.selectbox("Month", options=list(month_label_to_num.keys()),
                                      index=list(month_label_to_num.keys()).index(default_label),
                                      key="gp_month_picker")
        ss.gp_month_month = month_label_to_num[chosen_label]
    period_kwargs = {"year": y, "month": ss.gp_month_month}

elif granularity == "Year":
    y = st.selectbox("Year", options=available_years,
                      index=available_years.index(ss.gp_year), key="gp_year_picker")
    ss.gp_year = y
    period_kwargs = {"year": y}


# ============================================================
# Run button
# ============================================================
st.markdown("---")
col_run, col_log = st.columns([1, 2])
with col_run:
    run = st.button("⚡ Run Analysis", type="primary", use_container_width=True)
with col_log:
    log_scale = st.toggle("📊 Log scale for BCR distribution charts", value=ss.gp_log_scale_bcr,
                           help="Apply log scale to BCR x-axis. Useful because BCR is right-skewed.")
    ss.gp_log_scale_bcr = log_scale


# ============================================================
# Helpers — fig to base64
# ============================================================
def _fig_to_base64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format='png', bbox_inches='tight', dpi=130, facecolor='white')
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode('utf-8')


# ============================================================
# Chart: time-series of daily values across the period
# ============================================================
def chart_timeseries(daily_series, metric_name, value_key, unit, color):
    df = pd.DataFrame(daily_series)
    if df.empty or value_key not in df.columns:
        return None
    fig, ax = plt.subplots(figsize=(10, 3.2))
    df['Date'] = pd.to_datetime(df['Date'])
    df_sorted = df.sort_values('Date').reset_index(drop=True)
    ax.plot(df_sorted['Date'], df_sorted[value_key],
            color=color, linewidth=1.8, marker='o', markersize=3, alpha=0.85)
    if 'GP' in metric_name:
        ax.axhline(0, color='gray', linestyle='--', alpha=0.6, linewidth=0.8)
    ax.set_title(f"{metric_name} — Daily Time Series", fontsize=12, fontweight='bold')
    ax.set_ylabel(f"{value_key} ({unit})", fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate(rotation=30)
    return _fig_to_base64(fig)


# ============================================================
# Chart: distribution histogram with KDE + normal-fit overlay
# ============================================================
def chart_distribution(values, metric_name, unit, color, log_scale=False):
    arr = np.array([v for v in values if v is not None and not np.isnan(v)])
    if len(arr) == 0:
        return None

    fig, ax = plt.subplots(figsize=(10, 3.5))

    # Histogram
    if log_scale and arr.min() > 0:
        bins = np.logspace(np.log10(max(arr.min(), 0.01)), np.log10(arr.max()), 50)
        ax.hist(arr, bins=bins, color=color, alpha=0.55, edgecolor='white', linewidth=0.4, density=True, label='Empirical (histogram)')
        ax.set_xscale('log')
    else:
        ax.hist(arr, bins=50, color=color, alpha=0.55, edgecolor='white', linewidth=0.4, density=True, label='Empirical (histogram)')

    # KDE — empirical smooth curve
    try:
        kde = scipy_stats.gaussian_kde(arr)
        if log_scale and arr.min() > 0:
            x_smooth = np.logspace(np.log10(arr.min()), np.log10(arr.max()), 200)
        else:
            x_smooth = np.linspace(arr.min(), arr.max(), 200)
        ax.plot(x_smooth, kde(x_smooth), color='#1F3864', linewidth=2.2, label='Empirical (KDE)')
    except Exception:
        pass

    # Normal-fit overlay
    mu, sigma = float(arr.mean()), float(arr.std(ddof=1)) if len(arr) > 1 else 0.0
    if sigma > 0:
        if log_scale and arr.min() > 0:
            x_norm = np.logspace(np.log10(max(arr.min(), 0.01)), np.log10(arr.max()), 200)
        else:
            x_norm = np.linspace(arr.min(), arr.max(), 200)
        normal_pdf = scipy_stats.norm.pdf(x_norm, mu, sigma)
        ax.plot(x_norm, normal_pdf, color='#D7263D', linewidth=2.2, linestyle='--',
                label=f'Normal fit (μ={mu:.2f}, σ={sigma:.2f})')

    # Vertical lines: mean + median
    ax.axvline(mu, color='#D7263D', linestyle=':', alpha=0.7, linewidth=1.2)
    median = float(np.median(arr))
    ax.axvline(median, color='#2E8B57', linestyle=':', alpha=0.7, linewidth=1.2, label=f'Median ({median:.2f})')

    ax.set_title(f"{metric_name} — Block-level Distribution (n={len(arr):,})", fontsize=12, fontweight='bold')
    ax.set_xlabel(f"Value ({unit})", fontsize=9)
    ax.set_ylabel("Density", fontsize=9)
    ax.legend(loc='best', fontsize=8, framealpha=0.9)
    ax.grid(True, alpha=0.3)
    return _fig_to_base64(fig)


# ============================================================
# Render: 3 stats cards in a row
# ============================================================
def render_stats_cards(stats, unit, headline_key=None, headline_label=None):
    """Render summary stats as cards. Optionally show a headline metric first."""
    cards_to_show = []
    if headline_key and headline_key in stats and stats[headline_key] is not None:
        cards_to_show.append((headline_label or headline_key, stats[headline_key]))
    for key in ['mean', 'median', 'std', 'p10', 'p50', 'p90', 'min', 'max']:
        v = stats.get(key)
        cards_to_show.append((key.upper(), v))

    # Render in rows of 3
    for i in range(0, len(cards_to_show), 3):
        cols = st.columns(3)
        for j, (label, val) in enumerate(cards_to_show[i:i+3]):
            with cols[j]:
                if val is None:
                    val_str = "—"
                else:
                    val_str = f"{val:,.3f}" if abs(val) < 1000 else f"{val:,.0f}"
                st.markdown(f"""
                <div class="stats-card">
                    <div class="stats-label">{label}</div>
                    <div class="stats-value">{val_str}<span class="stats-unit">{unit}</span></div>
                </div>
                """, unsafe_allow_html=True)


# ============================================================
# Render one metric's full analysis
# ============================================================
def render_metric_analysis(analysis, metric_name, unit, color, granularity, log_scale=False, headline_key=None, headline_label=None):
    """Render time-series (if multi-day) + distribution + stats for one metric."""

    if 'error' in analysis:
        st.error(f"{metric_name}: {analysis['error']}")
        return

    # Section header
    st.markdown(f"""
    <div class="metric-section-header">
        <div class="metric-section-title">{metric_name}</div>
        <div class="metric-section-subtitle">{analysis['n_blocks_total']:,} blocks · {analysis['n_days']} day(s) · Unit: {unit}</div>
    </div>
    """, unsafe_allow_html=True)

    # Time-series (only if multi-day)
    if granularity != "Day":
        ts_key = "gp_mean" if "GP" in metric_name else "bcr_vol_wt"
        ts_b64 = chart_timeseries(analysis['daily_series'], metric_name, ts_key, unit, color)
        if ts_b64:
            st.markdown(f'<img src="data:image/png;base64,{ts_b64}" style="width:100%;margin-bottom:8px;"/>', unsafe_allow_html=True)

    # Distribution
    dist_b64 = chart_distribution(analysis['distribution'], metric_name, unit, color, log_scale=log_scale)
    if dist_b64:
        st.markdown(f'<img src="data:image/png;base64,{dist_b64}" style="width:100%;margin-bottom:8px;"/>', unsafe_allow_html=True)

    # Stats cards
    render_stats_cards(analysis['aggregate_stats'], unit, headline_key=headline_key, headline_label=headline_label)


# ============================================================
# Execute on click
# ============================================================
if run:
    try:
        s, e, label = resolve_period(granularity, **period_kwargs)
        gp_analysis     = get_gp_analysis(str(s), str(e))
        dam_bcr_analysis  = get_bcr_analysis(str(s), str(e), "DAM")
        gdam_bcr_analysis = get_bcr_analysis(str(s), str(e), "GDAM")

        ss.gp_last_result = {
            'period_label': label,
            'start_date':   s,
            'end_date':     e,
            'gp':           gp_analysis,
            'dam_bcr':      dam_bcr_analysis,
            'gdam_bcr':     gdam_bcr_analysis,
            'granularity':  granularity,
            'log_scale':    log_scale,
        }
    except Exception as ex:
        st.error(f"Analysis failed: {ex}")
        ss.gp_last_result = None


# ============================================================
# Render last result (persists)
# ============================================================
if ss.gp_last_result is not None:
    r = ss.gp_last_result
    st.markdown(f"### 📋 Analysis: {r['period_label']}")
    st.caption(f"Showing distributional + time-series analysis for the selected period")

    render_metric_analysis(
        r['gp'],
        "Green Premium (DAM − GDAM)",
        "₹/kWh",
        color='#2E8B57',
        granularity=r['granularity'],
        log_scale=False,
    )

    render_metric_analysis(
        r['dam_bcr'],
        "DAM Bid Coverage Ratio",
        "x (ratio)",
        color='#1F3864',
        granularity=r['granularity'],
        log_scale=r['log_scale'],
        headline_key='mean_volume_weighted',
        headline_label='VOL-WEIGHTED',
    )

    render_metric_analysis(
        r['gdam_bcr'],
        "GDAM Bid Coverage Ratio",
        "x (ratio)",
        color='#4A90E2',
        granularity=r['granularity'],
        log_scale=r['log_scale'],
        headline_key='mean_volume_weighted',
        headline_label='VOL-WEIGHTED',
    )
else:
    st.info("""
    👆 Pick a time granularity + period, then click **Run Analysis**.

    The page will show three parallel analyses for the selected period:
    - **Green Premium (GP)** = DAM_MCP − GDAM_MCP. Positive = DAM costlier (green discount). Negative = GDAM costlier (green stress).
    - **DAM Bid Coverage Ratio** = sum(DAM Sell Bids) / sum(DAM Buy Bids). Volume-weighted at the aggregate level.
    - **GDAM Bid Coverage Ratio** = sum(GDAM Sell Bids) / sum(GDAM Buy Bids). Same formula, green market.

    Each analysis includes (when multi-day): daily time-series + block-level distribution with normal-fit overlay + summary stats (mean, median, std, P10, P50, P90, min, max).
    """)


# ============================================================
# Sidebar
# ============================================================
with st.sidebar:
    st.markdown("### 💚 Green Premium Analysis")
    st.markdown(f"**Coverage:** {DATA_MIN} → {DATA_MAX}")
    st.markdown(f"**Granularities:** {len(GRANULARITY_LEVELS)}")

    st.markdown("---")
    st.markdown("### 📖 Methodology notes")
    st.caption("""
    - **GP** = DAM_MCP − GDAM_MCP at block level
    - **BCR aggregation** uses volume-weighted formula: sum(Sell) / sum(Buy). NOT mean of block-level ratios.
    - **Distribution charts** show empirical histogram + KDE + fitted normal curve overlay
    - **Real-world distributions** (especially BCR) are non-normal — the fit shows you how far off the data is from "normal"
    - **Log scale** for BCR helps when distribution is right-skewed
    """)

    st.markdown("---")
    st.markdown("### 💡 Try these")
    st.caption("""
    - **Day**: 2026-05-05 (intraday distribution)
    - **Month**: May 2026 (full-month spread)
    - **Year**: 2025 (full-year picture)
    """)