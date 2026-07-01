"""
pages/8_💰_Capture_Price.py — Effective Capture Price calculator.

Stage 1: Period selector + blank CSV download + populated CSV upload + headline numbers.
Stage 2: Daily capture price chart + hour-of-day profile + best/worst 5 hours table.
Stage 3 (coming): Heatmap.
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import date, timedelta

from src.data_loader import load_dataframes
from src.capture_price import (
    GRANULARITY_LEVELS,
    resolve_period,
    generate_blank_csv,
    parse_uploaded_csv,
    compute_capture_price,
)


# ============================================================
# Page setup
# ============================================================
st.set_page_config(
    page_title="Capture Price · Agent Monsoon",
    page_icon="💰",
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
        background: linear-gradient(135deg, #00D4FF 0%, #FFB200 50%, #4A90E2 100%);
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
    .assumption-box {
        background: rgba(255, 178, 0, 0.08);
        border-left: 3px solid #FFB200;
        padding: 10px 14px;
        border-radius: 6px;
        margin-bottom: 16px;
        font-size: 12px;
        color: #d4a574;
        font-style: italic;
    }
    .selector-label {
        color: #00D4FF;
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        margin-bottom: 6px;
    }
    .step-header {
        background: linear-gradient(90deg, rgba(0,212,255,0.15) 0%, transparent 100%);
        border-left: 4px solid #00D4FF;
        padding: 8px 14px;
        margin-top: 24px;
        margin-bottom: 12px;
        border-radius: 6px;
        color: #E4E7EB;
        font-size: 16px;
        font-weight: 700;
    }
    .chart-header {
        background: linear-gradient(90deg, rgba(74,144,226,0.12) 0%, transparent 100%);
        border-left: 4px solid #4A90E2;
        padding: 8px 14px;
        margin-top: 32px;
        margin-bottom: 12px;
        border-radius: 6px;
        color: #E4E7EB;
        font-size: 15px;
        font-weight: 700;
    }
    .headline-card {
        background: linear-gradient(135deg, rgba(19, 24, 38, 0.85) 0%, rgba(26, 33, 56, 0.85) 100%);
        border: 1px solid rgba(31, 42, 68, 0.8);
        border-left: 4px solid #FFB200;
        border-radius: 12px;
        padding: 20px 24px;
        margin: 10px 0;
    }
    .headline-label {
        color: #8a93a8;
        font-size: 11px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        margin-bottom: 6px;
    }
    .headline-value {
        font-size: 32px;
        font-weight: 700;
        color: #E4E7EB;
        font-family: 'SF Mono', 'Menlo', 'Consolas', monospace;
        line-height: 1.1;
    }
    .headline-unit {
        color: #FFB200;
        font-size: 14px;
        font-weight: 500;
        margin-left: 6px;
    }
    .headline-sub {
        color: #8a93a8;
        font-size: 12px;
        margin-top: 8px;
    }
    .delta-positive { color: #2E8B57; font-weight: 600; }
    .delta-negative { color: #D7263D; font-weight: 600; }
    .delta-zero     { color: #8a93a8; font-weight: 600; }

    /* Best/worst table */
    .bw-table { width: 100%; border-collapse: collapse; font-size: 13px; }
    .bw-table th {
        color: #8a93a8; font-size: 10px; text-transform: uppercase;
        letter-spacing: 1.2px; padding: 6px 10px; border-bottom: 1px solid rgba(255,255,255,0.07);
        text-align: left;
    }
    .bw-table td { padding: 7px 10px; border-bottom: 1px solid rgba(255,255,255,0.04); color: #E4E7EB; }
    .bw-table tr:last-child td { border-bottom: none; }
    .pill-best  { background: rgba(46,139,87,0.2);  color:#2E8B57; border-radius:4px; padding:2px 7px; font-size:11px; font-weight:700; }
    .pill-worst { background: rgba(215,38,61,0.2);  color:#D7263D; border-radius:4px; padding:2px 7px; font-size:11px; font-weight:700; }
</style>
""", unsafe_allow_html=True)


# ============================================================
# Header
# ============================================================
col_title, col_assumption = st.columns([2, 1])
with col_title:
    st.markdown('<div class="page-title">💰 Effective Capture Price</div>', unsafe_allow_html=True)
    st.markdown('<p class="page-subtitle">Energy-weighted realized price (₹/kWh) had your generation been sold on DAM or GDAM.</p>', unsafe_allow_html=True)
with col_assumption:
    st.markdown("""
    <div class="assumption-box">
      <strong>Hour mapping:</strong> Hour 1 = blocks 00:00–01:00 (00:00-00:15, 00:15-00:30, 00:30-00:45, 00:45-01:00 averaged). Hours run 1-24 per day.
    </div>
    """, unsafe_allow_html=True)


# ============================================================
# Load data + bounds
# ============================================================
data = load_dataframes()
df_daily = data['df_daily']
df_blocks = data['df_blocks']
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
if "cp_initialized" not in ss:
    ss.cp_initialized   = True
    ss.cp_granularity   = "Month"
    ss.cp_day_date      = DATA_MAX
    ss.cp_range_start   = max(DATA_MIN, DATA_MAX - timedelta(days=29))
    ss.cp_range_end     = DATA_MAX
    ss.cp_month_year    = available_years[-1]
    ss.cp_month_month   = year_to_months[available_years[-1]][-1]
    ss.cp_year          = available_years[-1]
    ss.cp_last_result   = None


# ============================================================
# Step 1: Granularity selector
# ============================================================
st.markdown('<div class="step-header">Step 1 — Choose time granularity & period</div>', unsafe_allow_html=True)

st.markdown('<div class="selector-label">⏱️ TIME GRANULARITY</div>', unsafe_allow_html=True)
granularity = st.radio(
    "Granularity",
    options=GRANULARITY_LEVELS,
    horizontal=True,
    label_visibility="collapsed",
    index=GRANULARITY_LEVELS.index(ss.cp_granularity),
    key="cp_granularity_widget",
)
ss.cp_granularity = granularity

st.markdown('<div class="selector-label" style="margin-top:14px;">📅 TIME WINDOW</div>', unsafe_allow_html=True)

period_kwargs = {}
valid_period = True

if granularity == "Day":
    selected = st.date_input("Date", value=ss.cp_day_date,
                              min_value=DATA_MIN, max_value=DATA_MAX, key="cp_day_picker")
    ss.cp_day_date = selected
    period_kwargs = {"date": str(selected)}

elif granularity == "Day Range":
    col_a, col_b = st.columns(2)
    with col_a:
        s = st.date_input("Start date", value=ss.cp_range_start,
                           min_value=DATA_MIN, max_value=DATA_MAX, key="cp_range_start_picker")
        ss.cp_range_start = s
    with col_b:
        e = st.date_input("End date", value=ss.cp_range_end,
                           min_value=DATA_MIN, max_value=DATA_MAX, key="cp_range_end_picker")
        ss.cp_range_end = e
    if e < s:
        st.warning("⚠️ End date is before start date.")
        valid_period = False
    period_kwargs = {"start_date": str(s), "end_date": str(e)}

elif granularity == "Month":
    col_a, col_b = st.columns(2)
    with col_a:
        y = st.selectbox("Year", options=available_years,
                          index=available_years.index(ss.cp_month_year), key="cp_month_year_picker")
        ss.cp_month_year = y
    months_available = year_to_months[y]
    with col_b:
        month_names = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
        month_label_to_num = {f"{month_names[m-1]} ({m:02d})": m for m in months_available}
        default_label = next((lbl for lbl, num in month_label_to_num.items() if num == ss.cp_month_month),
                              list(month_label_to_num.keys())[-1])
        chosen_label = st.selectbox("Month", options=list(month_label_to_num.keys()),
                                      index=list(month_label_to_num.keys()).index(default_label),
                                      key="cp_month_picker")
        ss.cp_month_month = month_label_to_num[chosen_label]
    period_kwargs = {"year": y, "month": ss.cp_month_month}

elif granularity == "Year":
    y = st.selectbox("Year", options=available_years,
                      index=available_years.index(ss.cp_year), key="cp_year_picker")
    ss.cp_year = y
    period_kwargs = {"year": y}


# ============================================================
# Resolve period
# ============================================================
period_label = "—"
n_hours = 0
csv_bytes = b""
s_date = e_date = None

if valid_period:
    try:
        s_date, e_date, period_label = resolve_period(granularity, **period_kwargs)
        csv_bytes = generate_blank_csv(s_date, e_date)
        if csv_bytes:
            text = csv_bytes.decode('utf-8')
            data_lines = [ln for ln in text.split('\n') if not ln.strip().startswith('#') and ln.strip()]
            n_hours = max(0, len(data_lines) - 1)
    except Exception as ex:
        st.error(f"Period resolution failed: {ex}")
        valid_period = False


# ============================================================
# Step 2: Download blank CSV
# ============================================================
st.markdown('<div class="step-header">Step 2 — Download blank CSV template</div>', unsafe_allow_html=True)

if valid_period and csv_bytes:
    st.markdown(f"""
    <div style="background:rgba(0,212,255,0.08);border-left:3px solid #00D4FF;
                padding:10px 14px;border-radius:6px;margin-bottom:10px;font-size:13px;color:#8a93a8;">
      📥 Template for <strong style="color:#E4E7EB;">{period_label}</strong> · {n_hours} hours · 4 columns (Hour, Date, HourOfDay, Energy_MWh).
      Fill the <strong style="color:#FFB200;">Energy_MWh</strong> column only. Don't reorder rows or rename columns.
    </div>
    """, unsafe_allow_html=True)

    filename_period = period_label.replace(" ", "_").replace("(", "").replace(")", "").replace(",", "")
    st.download_button(
        label=f"📥 Download blank CSV ({n_hours} hours)",
        data=csv_bytes,
        file_name=f"capture_price_template_{filename_period}.csv",
        mime="text/csv",
        type="primary",
        use_container_width=False,
    )
else:
    st.info("Pick a valid period above to enable CSV download.")


# ============================================================
# Step 3: Upload populated CSV
# ============================================================
st.markdown('<div class="step-header">Step 3 — Upload populated CSV</div>', unsafe_allow_html=True)

uploaded_file = st.file_uploader(
    "Choose your filled CSV",
    type=['csv'],
    help="Upload the CSV after filling the Energy_MWh column. Strict template — don't reorder rows."
)


# ============================================================
# Step 4: Compute
# ============================================================
if uploaded_file is not None and valid_period:
    if st.button("⚡ Compute Capture Price", type="primary"):
        try:
            file_bytes = uploaded_file.read()
            parsed = parse_uploaded_csv(file_bytes, s_date, e_date)

            if parsed.get('errors'):
                for err in parsed['errors']:
                    st.error(f"❌ {err}")
            else:
                parsed_df = parsed['parsed_df']
                result = compute_capture_price(parsed_df, s_date, e_date)
                if 'error' in result:
                    st.error(f"❌ {result['error']}")
                else:
                    ss.cp_last_result = {
                        'period_label':  period_label,
                        'start_date':    s_date,
                        'end_date':      e_date,
                        'granularity':   granularity,
                        'parsed':        parsed,
                        'result':        result,
                    }
        except Exception as ex:
            st.error(f"❌ Compute failed: {ex}")
            ss.cp_last_result = None


# ============================================================
# Render result (persists across reruns)
# ============================================================
if ss.cp_last_result is not None:
    r = ss.cp_last_result
    parsed  = r['parsed']
    result  = r['result']
    parsed_df = parsed['parsed_df']

    st.markdown(f"### 📋 Capture Price: {r['period_label']}")

    # Coverage
    coverage   = parsed['coverage_pct']
    n_filled   = parsed['n_filled']
    n_expected = parsed['n_expected']
    n_missing  = n_expected - n_filled

    if n_missing > 0:
        st.warning(
            f"⚠️ Profile covers {coverage:.1f}% of period — "
            f"{n_filled} of {n_expected} hours filled · {n_missing} missing. "
            f"Capture price below is computed using ONLY the filled hours."
        )
    else:
        st.success(f"✅ Profile covers 100% of period — all {n_expected} hours filled.")

    # ─── HEADLINE CARDS ───────────────────────────────────────
    col_dam, col_gdam = st.columns(2)

    def _delta_html(delta_val, unit="₹/kWh"):
        if delta_val > 0:
            cls, sign, verdict = "delta-positive", "+", "above time-avg (gained)"
        elif delta_val < 0:
            cls, sign, verdict = "delta-negative", "", "below time-avg (lost)"
        else:
            cls, sign, verdict = "delta-zero", "", "matches time-avg"
        return f'<span class="{cls}">{sign}{delta_val:.3f}</span> {unit} · {verdict}'

    with col_dam:
        st.markdown(f"""
        <div class="headline-card">
            <div class="headline-label">DAM Capture Price</div>
            <div class="headline-value">₹{result['dam_capture']:.3f}<span class="headline-unit">/kWh</span></div>
            <div class="headline-sub">
                Time-avg ref: ₹{result['dam_time_avg']:.3f}/kWh<br/>
                Δ: {_delta_html(result['dam_capture_loss'])}
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col_gdam:
        st.markdown(f"""
        <div class="headline-card">
            <div class="headline-label">GDAM Capture Price</div>
            <div class="headline-value">₹{result['gdam_capture']:.3f}<span class="headline-unit">/kWh</span></div>
            <div class="headline-sub">
                Time-avg ref: ₹{result['gdam_time_avg']:.3f}/kWh<br/>
                Δ: {_delta_html(result['gdam_capture_loss'])}
            </div>
        </div>
        """, unsafe_allow_html=True)

    # ─── SUMMARY CARDS ────────────────────────────────────────
    col_e, col_h, col_p = st.columns(3)
    with col_e:
        st.markdown(f"""
        <div class="headline-card" style="border-left-color:#2E8B57;">
            <div class="headline-label">Total Energy</div>
            <div class="headline-value">{result['total_energy_mwh']:,.1f}<span class="headline-unit">MWh</span></div>
        </div>
        """, unsafe_allow_html=True)
    with col_h:
        st.markdown(f"""
        <div class="headline-card" style="border-left-color:#1F3864;">
            <div class="headline-label">Hours Used</div>
            <div class="headline-value">{result['n_hours_used']:,}<span class="headline-unit">/ {n_expected}</span></div>
        </div>
        """, unsafe_allow_html=True)
    with col_p:
        st.markdown(f"""
        <div class="headline-card" style="border-left-color:#4A90E2;">
            <div class="headline-label">Coverage</div>
            <div class="headline-value">{coverage:.1f}<span class="headline-unit">%</span></div>
        </div>
        """, unsafe_allow_html=True)

    # ===========================================================
    # STAGE 2 CHARTS
    # ===========================================================

    # ── Build hourly price lookup from df_blocks ──────────────
    # df_blocks columns: Date, Hour (1-24), DAM_MCP, GDAM_MCP
    blk = df_blocks.copy()
    blk['date_d'] = pd.to_datetime(blk['Date']).dt.date

    # Filter to period
    s_d = r['start_date']
    e_d = r['end_date']
    blk_period = blk[(blk['date_d'] >= s_d) & (blk['date_d'] <= e_d)]

    # Hourly avg price per day (avg across the 4 blocks within each hour)
    hourly_prices = (
        blk_period.groupby(['date_d', 'Hour'])
        [['DAM_MCP', 'GDAM_MCP']]
        .mean()
        .reset_index()
        .rename(columns={'date_d': 'Date', 'Hour': 'HourOfDay',
                         'DAM_MCP': 'dam_price', 'GDAM_MCP': 'gdam_price'})
    )

    # Merge generation profile
    gen = parsed_df[['Date', 'HourOfDay', 'Energy_MWh']].copy()
    gen['Date'] = pd.to_datetime(gen['Date'], dayfirst=True).dt.date
    merged = gen.merge(hourly_prices, on=['Date', 'HourOfDay'], how='left')
    merged = merged[merged['Energy_MWh'] > 0].copy()

    # ── Chart 1: Daily capture price ──────────────────────────
    # Only show for multi-day periods
    n_days = (e_d - s_d).days + 1

    if n_days > 1:
        st.markdown('<div class="chart-header">📈 Chart 1 — Daily Capture Price</div>', unsafe_allow_html=True)
        st.caption("Energy-weighted DAM vs GDAM capture price per day. Gaps = days with zero generation.")

        daily_cp = (
            merged.groupby('Date')
            .apply(lambda g: pd.Series({
                'dam_cp':  (g['Energy_MWh'] * g['dam_price']).sum()  / g['Energy_MWh'].sum()  if g['Energy_MWh'].sum() > 0 else np.nan,
                'gdam_cp': (g['Energy_MWh'] * g['gdam_price']).sum() / g['Energy_MWh'].sum() if g['Energy_MWh'].sum() > 0 else np.nan,
            }), include_groups=False)
            .reset_index()
        )
        daily_cp = daily_cp.dropna(subset=['dam_cp', 'gdam_cp'])
        daily_cp['Date'] = pd.to_datetime(daily_cp['Date'])
        daily_cp = daily_cp.sort_values('Date')

        if not daily_cp.empty:
            import altair as alt

            base = alt.Chart(daily_cp).encode(
                x=alt.X('Date:T', axis=alt.Axis(
                    format='%d %b', labelColor='#8a93a8', tickColor='#8a93a8',
                    domainColor='rgba(255,255,255,0.1)', gridColor='rgba(255,255,255,0.05)',
                    title=None
                ))
            )

            dam_line = base.mark_line(
                color='#00D4FF', strokeWidth=2, interpolate='monotone'
            ).encode(
                y=alt.Y('dam_cp:Q', title='₹/kWh',
                         axis=alt.Axis(labelColor='#8a93a8', tickColor='#8a93a8',
                                       domainColor='rgba(255,255,255,0.1)',
                                       gridColor='rgba(255,255,255,0.05)',
                                       titleColor='#8a93a8')),
                tooltip=[
                    alt.Tooltip('Date:T', format='%d %b %Y'),
                    alt.Tooltip('dam_cp:Q', title='DAM Capture ₹/kWh', format='.3f'),
                ]
            )

            gdam_line = base.mark_line(
                color='#FFB200', strokeWidth=2, strokeDash=[4, 2], interpolate='monotone'
            ).encode(
                y=alt.Y('gdam_cp:Q'),
                tooltip=[
                    alt.Tooltip('Date:T', format='%d %b %Y'),
                    alt.Tooltip('gdam_cp:Q', title='GDAM Capture ₹/kWh', format='.3f'),
                ]
            )

            dam_points = base.mark_circle(color='#00D4FF', size=40).encode(
                y='dam_cp:Q'
            )
            gdam_points = base.mark_circle(color='#FFB200', size=40).encode(
                y='gdam_cp:Q'
            )

            chart = (dam_line + dam_points + gdam_line + gdam_points).properties(
                height=280,
                background='transparent',
            ).configure_view(
                strokeWidth=0,
                fill='transparent',
            ).configure_legend(
                disable=True
            )

            st.altair_chart(chart, use_container_width=True)

            # Mini legend
            st.markdown("""
            <div style="display:flex;gap:20px;margin-top:-8px;margin-bottom:8px;">
              <span style="color:#00D4FF;font-size:12px;">━━ DAM Capture Price</span>
              <span style="color:#FFB200;font-size:12px;">╌╌ GDAM Capture Price</span>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("Not enough daily data to plot.")

    # ── Chart 2: Hour-of-day profile ──────────────────────────
    st.markdown('<div class="chart-header">⏰ Chart 2 — Hour-of-Day Price Profile</div>', unsafe_allow_html=True)
    st.caption("Average price & generation weight per hour. Shows WHEN your plant generates vs when prices are high.")

    hour_agg = (
        merged.groupby('HourOfDay')
        .agg(
            dam_price_avg=('dam_price', 'mean'),
            gdam_price_avg=('gdam_price', 'mean'),
            total_energy=('Energy_MWh', 'sum'),
        )
        .reset_index()
    )

    # Normalize energy to 0-100 for secondary axis feel
    max_energy = hour_agg['total_energy'].max()
    hour_agg['energy_pct'] = (hour_agg['total_energy'] / max_energy * 100) if max_energy > 0 else 0

    if not hour_agg.empty:
        import altair as alt

        base_h = alt.Chart(hour_agg).encode(
            x=alt.X('HourOfDay:O',
                     axis=alt.Axis(labelColor='#8a93a8', tickColor='#8a93a8',
                                   domainColor='rgba(255,255,255,0.1)',
                                   gridColor='rgba(255,255,255,0.05)',
                                   title='Hour of Day (1=midnight, 13=noon)',
                                   titleColor='#8a93a8'))
        )

        # Generation bars (background)
        gen_bars = base_h.mark_bar(
            color='rgba(74,144,226,0.25)',
            cornerRadiusTopLeft=3,
            cornerRadiusTopRight=3,
        ).encode(
            y=alt.Y('energy_pct:Q',
                     title='Generation (normalised %)',
                     axis=alt.Axis(labelColor='rgba(74,144,226,0.6)',
                                   tickColor='rgba(74,144,226,0.4)',
                                   titleColor='rgba(74,144,226,0.7)',
                                   domainColor='rgba(255,255,255,0.05)',
                                   gridColor='rgba(255,255,255,0.03)')),
            tooltip=[
                alt.Tooltip('HourOfDay:O', title='Hour'),
                alt.Tooltip('energy_pct:Q', title='Generation %', format='.1f'),
                alt.Tooltip('total_energy:Q', title='Total Energy MWh', format=',.1f'),
            ]
        )

        dam_line_h = base_h.mark_line(
            color='#00D4FF', strokeWidth=2.5, interpolate='monotone'
        ).encode(
            y=alt.Y('dam_price_avg:Q',
                     title='Avg Price ₹/kWh',
                     axis=alt.Axis(labelColor='#8a93a8', tickColor='#8a93a8',
                                   titleColor='#8a93a8',
                                   domainColor='rgba(255,255,255,0.1)',
                                   gridColor='rgba(255,255,255,0.05)')),
            tooltip=[
                alt.Tooltip('HourOfDay:O', title='Hour'),
                alt.Tooltip('dam_price_avg:Q', title='DAM avg ₹/kWh', format='.3f'),
            ]
        )

        gdam_line_h = base_h.mark_line(
            color='#FFB200', strokeWidth=2.5, strokeDash=[4, 2], interpolate='monotone'
        ).encode(
            y='gdam_price_avg:Q',
            tooltip=[
                alt.Tooltip('HourOfDay:O', title='Hour'),
                alt.Tooltip('gdam_price_avg:Q', title='GDAM avg ₹/kWh', format='.3f'),
            ]
        )

        # Resolve spec — bars on left axis, lines on right (workaround: use layer)
        chart_h = alt.layer(gen_bars, dam_line_h, gdam_line_h).resolve_scale(
            y='independent'
        ).properties(
            height=300,
            background='transparent',
        ).configure_view(
            strokeWidth=0,
            fill='transparent',
        )

        st.altair_chart(chart_h, use_container_width=True)

        st.markdown("""
        <div style="display:flex;gap:20px;margin-top:-8px;margin-bottom:8px;">
          <span style="color:rgba(74,144,226,0.7);font-size:12px;">█ Generation weight (normalised)</span>
          <span style="color:#00D4FF;font-size:12px;">━━ DAM avg price</span>
          <span style="color:#FFB200;font-size:12px;">╌╌ GDAM avg price</span>
        </div>
        """, unsafe_allow_html=True)

    # ── Chart 3: Best / Worst 5 hours table ───────────────────
    st.markdown('<div class="chart-header">🏆 Chart 3 — Best & Worst 5 Hours (DAM)</div>', unsafe_allow_html=True)
    st.caption("Hours ranked by avg DAM price in your generation window. Best = you caught high prices. Worst = price crash.")

    if not hour_agg.empty:
        def _hour_label(h):
            return f"{int(h)-1:02d}:00\u2013{int(h):02d}:00"

        ranked = hour_agg.sort_values('dam_price_avg', ascending=False).copy()
        ranked['Hour Window'] = ranked['HourOfDay'].apply(_hour_label)
        ranked['DAM ₹/kWh']  = ranked['dam_price_avg'].round(3)
        ranked['GDAM ₹/kWh'] = ranked['gdam_price_avg'].round(3)
        ranked['Generation MWh'] = ranked['total_energy'].round(0).astype(int)

        display_cols = ['Hour Window', 'DAM ₹/kWh', 'GDAM ₹/kWh', 'Generation MWh']

        best5  = ranked.head(5)[display_cols].reset_index(drop=True)
        worst5 = ranked.tail(5).sort_values('dam_price_avg')[display_cols].reset_index(drop=True)

        def style_best(df):
            return df.style\
                .format({'DAM ₹/kWh': '₹{:.3f}', 'GDAM ₹/kWh': '₹{:.3f}', 'Generation MWh': '{:,}'})\
                .set_properties(**{'background-color': 'rgba(46,139,87,0.08)', 'color': '#E4E7EB'})\
                .highlight_max(subset=['DAM ₹/kWh'], color='rgba(46,139,87,0.25)')

        def style_worst(df):
            return df.style\
                .format({'DAM ₹/kWh': '₹{:.3f}', 'GDAM ₹/kWh': '₹{:.3f}', 'Generation MWh': '{:,}'})\
                .set_properties(**{'background-color': 'rgba(215,38,61,0.08)', 'color': '#E4E7EB'})\
                .highlight_min(subset=['DAM ₹/kWh'], color='rgba(215,38,61,0.25)')

        col_best, col_worst = st.columns(2)
        with col_best:
            st.markdown("**✦ Best 5 Hours** — highest DAM price during your generation")
            st.dataframe(style_best(best5), use_container_width=True, hide_index=True)

        with col_worst:
            st.markdown("**▼ Worst 5 Hours** — lowest DAM price during your generation")
            st.dataframe(style_worst(worst5), use_container_width=True, hide_index=True)

    # ===========================================================
    # STAGE 3 — HEATMAP (Day × Hour, colour = price)
    # ===========================================================
    st.markdown('<div class="chart-header">🗓️ Chart 4 — Capture Price Heatmap (Day × Hour)</div>', unsafe_allow_html=True)

    heatmap_market = st.radio(
        "Market for heatmap",
        options=["DAM", "GDAM"],
        horizontal=True,
        key="cp_heatmap_market",
    )

    price_col = 'dam_price' if heatmap_market == "DAM" else 'gdam_price'
    price_label = f"{heatmap_market} Price ₹/kWh"

    # Build heatmap dataframe — one row per (Date, HourOfDay)
    hmap_df = merged[['Date', 'HourOfDay', price_col, 'Energy_MWh']].copy()
    hmap_df['Date'] = pd.to_datetime(hmap_df['Date'])
    hmap_df['DateStr'] = hmap_df['Date'].dt.strftime('%d %b')
    hmap_df = hmap_df.rename(columns={price_col: 'Price'})

    # Only include hours with generation
    hmap_df = hmap_df[hmap_df['Energy_MWh'] > 0].copy()

    if hmap_df.empty:
        st.info("No generation data to show heatmap.")
    else:
        n_days_hmap = hmap_df['Date'].nunique()
        # Dynamic cell height — tighter for more days
        cell_h = max(6, min(18, int(500 / n_days_hmap)))
        chart_height = min(8000, n_days_hmap * cell_h + 60)

        import altair as alt

        # Sort dates correctly
        date_order = (
            hmap_df.sort_values('Date')['DateStr'].unique().tolist()
        )

        heatmap = alt.Chart(hmap_df).mark_rect(
            stroke='rgba(0,0,0,0.3)',
            strokeWidth=0.3,
        ).encode(
            x=alt.X('HourOfDay:O',
                     title='Hour of Day (1 = midnight, 13 = noon)',
                     axis=alt.Axis(
                         labelColor='#8a93a8',
                         tickColor='#8a93a8',
                         domainColor='rgba(255,255,255,0.1)',
                         gridColor='rgba(255,255,255,0.0)',
                         titleColor='#8a93a8',
                         labelFontSize=11,
                     )),
            y=alt.Y('DateStr:O',
                     sort=date_order,
                     title=None,
                     axis=alt.Axis(
                         labelColor='#8a93a8',
                         tickColor='rgba(0,0,0,0)',
                         domainColor='rgba(255,255,255,0.05)',
                         labelFontSize=max(7, min(11, cell_h - 1)),
                         labelLimit=80,
                     )),
            color=alt.Color('Price:Q',
                             scale=alt.Scale(
                                 scheme='redyellowgreen',
                                 domainMid=hmap_df['Price'].median(),
                             ),
                             legend=alt.Legend(
                                 title=price_label,
                                 titleColor='#8a93a8',
                                 labelColor='#8a93a8',
                                 gradientLength=200,
                                 orient='right',
                             )),
            tooltip=[
                alt.Tooltip('DateStr:O', title='Date'),
                alt.Tooltip('HourOfDay:O', title='Hour'),
                alt.Tooltip('Price:Q', title=price_label, format='.3f'),
                alt.Tooltip('Energy_MWh:Q', title='Generation MWh', format=',.1f'),
            ]
        ).properties(
            width='container',
            height=chart_height,
            background='transparent',
        ).configure_view(
            strokeWidth=0,
            fill='transparent',
        )

        # Scrollable container
        heatmap_container_height = min(620, chart_height + 40)
        st.markdown(
            f'<div style="overflow-y:auto;max-height:{heatmap_container_height}px;'
            f'border:1px solid rgba(255,255,255,0.06);border-radius:8px;padding:4px;">',
            unsafe_allow_html=True
        )
        st.altair_chart(heatmap, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

        st.caption(
            f"🟢 Green = high price · 🔴 Red = low price · Grey cells = zero generation hours · "
            f"{n_days_hmap} days × up to 24 hours. Scroll to explore."
        )

    st.caption("Stage 3 of 3: All charts complete. 🎉")

else:
    if uploaded_file is None:
        st.info("👆 Pick a period → download blank CSV → fill the Energy_MWh column → upload → click Compute.")


# ============================================================
# Sidebar
# ============================================================
with st.sidebar:
    st.markdown("### 💰 Capture Price")
    st.markdown(f"**Coverage:** {DATA_MIN} → {DATA_MAX}")
    st.markdown(f"**Granularities:** {len(GRANULARITY_LEVELS)}")

    st.markdown("---")
    st.markdown("### 📖 Methodology")
    st.caption("""
    **Capture price** = Σ(energy × hourly price) / Σ(energy)

    **Hour aggregation:** Each Hour 1-24 within a day = simple average of the 4 corresponding 15-min DAM (or GDAM) blocks.

    **Time-avg comparison:** Plain mean of hourly prices (no energy weighting) over the SAME hours that have generation data.

    **Δ (Δ vs time-avg):**
    - Positive → your generation hit higher-priced hours (good timing)
    - Negative → your generation hit lower-priced hours (bad timing / solar oversupply)
    """)

    st.markdown("---")
    st.markdown("### 💡 Use cases")
    st.caption("""
    - **Solar IPP:** Check if your generation profile got hit by midday price crashes
    - **Wind IPP:** See nocturnal value capture
    - **Hybrid:** Compare DAM vs GDAM realized prices
    - **Battery:** Pair with Arbitrage Analysis page for full storage view
    """)
