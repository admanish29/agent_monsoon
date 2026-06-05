"""
pages/3_🔍_Data_Explorer.py — Data Explorer (v4 — smart-grouped charts).

Session 6.3 + grouping refinement:
- Session-state persistence (selectors survive page-switches)
- View selector dropdown (📊 Recommended / Big Number / Table / Line / Bar / Multi-line)
- mixed_day shape: chart on top + daily scalar cards below
- Smart chart grouping by scale (Hybrid C: same unit + 10x split rule)
- CSV + Excel download buttons
"""

import streamlit as st
import pandas as pd
import io
from datetime import date, timedelta

from src.data_loader import load_dataframes
from src.explorer import (
    METRIC_LIBRARY,
    GRANULARITIES,
    is_valid,
    invalid_reason,
    time_block_options,
    query_data,
    recommend_view,
)


# ============================================================
# Page setup
# ============================================================
st.set_page_config(
    page_title="Data Explorer · Agent Monsoon",
    page_icon="🔍",
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
    .selector-label {
        color: #00D4FF;
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        margin-bottom: 6px;
    }
    .reco-pill {
        display: inline-block;
        background: rgba(0, 212, 255, 0.1);
        color: #00D4FF;
        border: 1px solid rgba(0, 212, 255, 0.3);
        padding: 4px 12px;
        border-radius: 6px;
        font-size: 12px;
        font-weight: 600;
        letter-spacing: 0.5px;
    }
    .invalid-warning {
        background: rgba(255, 165, 0, 0.08);
        border-left: 3px solid orange;
        padding: 10px 14px;
        border-radius: 6px;
        margin: 10px 0;
        font-size: 13px;
        color: #d4a574;
    }
    .big-number-card {
        background: linear-gradient(135deg, rgba(19, 24, 38, 0.85) 0%, rgba(26, 33, 56, 0.85) 100%);
        border: 1px solid rgba(31, 42, 68, 0.8);
        border-left: 4px solid #00D4FF;
        border-radius: 12px;
        padding: 24px 28px;
        margin: 12px 0;
    }
    .big-number-label {
        color: #8a93a8;
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        font-weight: 600;
        margin-bottom: 8px;
    }
    .big-number-value {
        font-size: 42px;
        font-weight: 700;
        color: #E4E7EB;
        font-family: 'SF Mono', 'Menlo', 'Consolas', monospace;
        line-height: 1.1;
    }
    .big-number-unit {
        color: #00D4FF;
        font-size: 18px;
        font-weight: 500;
        margin-left: 8px;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================
# SMART CHART GROUPING
# ============================================================
# Rule (Hybrid C):
#   - Group by unit (₹/kWh, MW, %, x, σ, "")
#   - Within a unit, split into separate sub-groups if max-spread > 10x
# ============================================================
def _smart_chart_groups(df, metric_columns_with_units):
    """Return [{unit, columns, displays, max_value}, ...]"""
    by_unit = {}
    for entry in metric_columns_with_units:
        col = entry["col"]
        if col not in df.columns or not pd.api.types.is_numeric_dtype(df[col]):
            continue
        col_max = df[col].abs().max()
        if pd.isna(col_max) or col_max == 0:
            col_max = 1e-9
        by_unit.setdefault(entry["unit"], []).append({
            "col": col,
            "display": entry["display"],
            "max": col_max,
        })

    groups = []
    for unit, entries in by_unit.items():
        entries_sorted = sorted(entries, key=lambda e: e["max"])
        current_bucket = [entries_sorted[0]]
        current_max = entries_sorted[0]["max"]
        for e in entries_sorted[1:]:
            if e["max"] / current_max > 10:
                groups.append({
                    "unit": unit,
                    "columns": [c["col"] for c in current_bucket],
                    "displays": [c["display"] for c in current_bucket],
                    "max_value": current_max,
                })
                current_bucket = [e]
                current_max = e["max"]
            else:
                current_bucket.append(e)
                current_max = max(current_max, e["max"])
        groups.append({
            "unit": unit,
            "columns": [c["col"] for c in current_bucket],
            "displays": [c["display"] for c in current_bucket],
            "max_value": current_max,
        })

    return groups


def _render_grouped_charts(df, metric_columns_with_units, x_col, chart_type="line"):
    """Render one chart per smart-chart group. chart_type = 'line' or 'bar'."""
    groups = _smart_chart_groups(df, metric_columns_with_units)
    if not groups:
        st.info("No numeric data to chart.")
        return

    chart_fn = st.line_chart if chart_type == "line" else st.bar_chart

    # Force date columns to string format so Altair treats them as discrete categories
    # (prevents "12 PM" interpolation labels and ensures every date gets a tick)
    df_for_chart = df.copy()
    if x_col == "Date":
        df_for_chart[x_col] = pd.to_datetime(df_for_chart[x_col]).dt.strftime('%Y-%m-%d')

    if len(groups) == 1:
        g = groups[0]
        unit_label = f" ({g['unit']})" if g['unit'] else ""
        st.markdown(f"**Metrics{unit_label}**")
        chart_fn(df_for_chart.set_index(x_col)[g["columns"]], use_container_width=True)
    else:
        for i, g in enumerate(groups, start=1):
            unit_label = f" ({g['unit']})" if g['unit'] else ""
            metric_list = ", ".join(g["displays"])
            st.markdown(f"**Chart {i} of {len(groups)}{unit_label}** — {metric_list}")
            chart_fn(df_for_chart.set_index(x_col)[g["columns"]], use_container_width=True)


def _columns_with_units_from_result(df_result, metric_keys):
    """Build [{col, unit, display}, ...] from valid metric keys + result df."""
    out = []
    for mk in metric_keys:
        m = METRIC_LIBRARY[mk]
        if m["display"] in df_result.columns:
            out.append({"col": m["display"], "unit": m["unit"], "display": m["display"]})
    return out


# ============================================================
# Header
# ============================================================
st.markdown('<div class="page-title">🔍 Data Explorer</div>', unsafe_allow_html=True)
st.markdown('<p class="page-subtitle">Slice and dice raw IEX data. Pick a time granularity, choose metrics, get the answer. All prices in ₹/kWh.</p>', unsafe_allow_html=True)


# ============================================================
# Load data + bounds
# ============================================================
data = load_dataframes()
df_daily = data['df_daily']

DATA_MIN = df_daily['date'].min().date()
DATA_MAX = df_daily['date'].max().date()

DEFAULT_DATE        = DATA_MAX
DEFAULT_RANGE_START = max(DATA_MIN, DATA_MAX - timedelta(days=6))
DEFAULT_RANGE_END   = DATA_MAX
_default_week_anchor = DATA_MAX - timedelta(days=DATA_MAX.weekday())
DEFAULT_WEEK_START   = max(DATA_MIN, _default_week_anchor)


# ============================================================
# SESSION-STATE PERSISTENCE
# ============================================================
ss = st.session_state

if "exp_initialized" not in ss:
    ss.exp_initialized       = True
    ss.exp_granularity       = "Day"
    ss.exp_date              = DEFAULT_DATE
    ss.exp_end_date          = DEFAULT_RANGE_END
    ss.exp_range_start       = DEFAULT_RANGE_START
    ss.exp_week_anchor       = DEFAULT_WEEK_START
    ss.exp_block_single      = "18:30 - 18:45"
    ss.exp_block_range       = ("10:00 - 10:15", "14:45 - 15:00")
    ss.exp_br_mode           = "aggregated"
    ss.exp_selected_displays = []
    ss.exp_last_result       = None
    ss.exp_view_override     = None


# ============================================================
# Helper: metrics by category
# ============================================================
def metrics_by_category():
    cats = {}
    for k, m in METRIC_LIBRARY.items():
        cats.setdefault(m["category"], []).append((k, m["display"]))
    return cats


# ============================================================
# Granularity selector
# ============================================================
st.markdown('<div class="selector-label">⏱️ TIME GRANULARITY</div>', unsafe_allow_html=True)
granularity = st.radio(
    "Granularity",
    options=GRANULARITIES,
    horizontal=True,
    label_visibility="collapsed",
    index=GRANULARITIES.index(ss.exp_granularity),
    key="exp_granularity_widget",
    help="Block = single 15-min slot · Block Range = part of a day · Day = full 96 blocks · Day Range = multiple days · Week = Mon-Sun"
)
ss.exp_granularity = granularity


# ============================================================
# Time-window selectors
# ============================================================
st.markdown("---")
st.markdown('<div class="selector-label">📅 TIME WINDOW</div>', unsafe_allow_html=True)

selected_date = None
selected_end_date = None
selected_block_start = None
selected_block_end = None
selected_week_start = None
br_mode = "aggregated"

if granularity == "Block":
    col_a, col_b = st.columns([1, 2])
    with col_a:
        selected_date = st.date_input("Date", value=ss.exp_date,
                                       min_value=DATA_MIN, max_value=DATA_MAX, key="exp_date_block")
        ss.exp_date = selected_date
    with col_b:
        blocks = time_block_options()
        try:
            default_idx = blocks.index(ss.exp_block_single)
        except ValueError:
            default_idx = blocks.index("18:30 - 18:45")
        selected_block_start = st.select_slider(
            "Time Block", options=blocks, value=blocks[default_idx],
            help="96 blocks per day, each 15 minutes",
            key="exp_block_slider"
        )
        ss.exp_block_single = selected_block_start

elif granularity == "Block Range":
    col_a, col_b = st.columns([1, 2])
    with col_a:
        selected_date = st.date_input("Date", value=ss.exp_date,
                                       min_value=DATA_MIN, max_value=DATA_MAX, key="exp_date_br")
        ss.exp_date = selected_date
    with col_b:
        blocks = time_block_options()
        try:
            stored_start, stored_end = ss.exp_block_range
            blocks.index(stored_start); blocks.index(stored_end)
            range_default = (stored_start, stored_end)
        except (ValueError, TypeError):
            range_default = ("10:00 - 10:15", "14:45 - 15:00")
        block_range = st.select_slider(
            "Block range", options=blocks, value=range_default,
            help="Drag both handles to select a sub-day window",
            key="exp_br_slider"
        )
        selected_block_start, selected_block_end = block_range
        ss.exp_block_range = block_range

    br_mode = st.radio(
        "View mode",
        options=["aggregated", "raw"],
        format_func=lambda x: {"aggregated": "📊 Aggregated (one row, averaged across blocks)",
                                "raw": "📋 Raw blocks (one row per 15-min block)"}[x],
        index=0 if ss.exp_br_mode == "aggregated" else 1,
        horizontal=True,
        key="exp_br_mode_widget"
    )
    ss.exp_br_mode = br_mode

elif granularity == "Day":
    selected_date = st.date_input("Date", value=ss.exp_date,
                                   min_value=DATA_MIN, max_value=DATA_MAX, key="exp_date_day",
                                   help=f"Pick any date in the dataset ({DATA_MIN} to {DATA_MAX})")
    ss.exp_date = selected_date

elif granularity == "Day Range":
    col_a, col_b = st.columns(2)
    with col_a:
        selected_date = st.date_input("Start date", value=ss.exp_range_start,
                                       min_value=DATA_MIN, max_value=DATA_MAX, key="exp_dr_start")
        ss.exp_range_start = selected_date
    with col_b:
        selected_end_date = st.date_input("End date", value=ss.exp_end_date,
                                           min_value=DATA_MIN, max_value=DATA_MAX, key="exp_dr_end")
        ss.exp_end_date = selected_end_date
    if selected_end_date < selected_date:
        st.warning("⚠️ End date is before start date. Please correct.")

elif granularity == "Week":
    col_a, col_b = st.columns([1, 2])
    with col_a:
        picked = st.date_input("Pick any date in the week", value=ss.exp_week_anchor,
                                min_value=DATA_MIN, max_value=DATA_MAX, key="exp_wk_anchor",
                                help="The week will be Mon-Sun containing this date.")
        ss.exp_week_anchor = picked
    monday = picked - timedelta(days=picked.weekday())
    sunday = monday + timedelta(days=6)
    with col_b:
        st.info(f"📆 Week: **{monday}** (Mon) to **{sunday}** (Sun)")
    selected_week_start = monday


# ============================================================
# Metrics multiselect
# ============================================================
st.markdown("---")
st.markdown('<div class="selector-label">📊 METRICS</div>', unsafe_allow_html=True)

all_metric_displays = []
display_to_key = {}
for category, metric_list in metrics_by_category().items():
    for key, display in metric_list:
        if is_valid(key, granularity):
            label = f"[{category}] {display}"
        else:
            label = f"⚠️ [{category}] {display}"
        all_metric_displays.append(label)
        display_to_key[label] = key

if not ss.exp_selected_displays:
    default = [lbl for lbl in all_metric_displays if "DAM MCP (₹/kWh)" in lbl and not lbl.startswith("⚠️")]
    ss.exp_selected_displays = default

# Match stored selection back to current option labels (granularity change may have re-labeled)
valid_stored = [d for d in ss.exp_selected_displays if d in all_metric_displays]
if len(valid_stored) < len(ss.exp_selected_displays):
    stored_keys = set()
    for old_label in ss.exp_selected_displays:
        for new_label, k in display_to_key.items():
            old_clean = old_label.replace("⚠️ ", "").split("] ", 1)[-1] if "] " in old_label else old_label
            new_clean = new_label.replace("⚠️ ", "").split("] ", 1)[-1] if "] " in new_label else new_label
            if old_clean == new_clean:
                stored_keys.add(new_label)
                break
    valid_stored = list(stored_keys) or default

selected_displays = st.multiselect(
    "Pick one or more metrics",
    options=all_metric_displays,
    default=valid_stored,
    help="Categories: Pricing · Volumes · Liquidity · Congestion · Anomaly · RMTI · Arbitrage. ⚠️ = not valid for current granularity.",
    key="exp_metrics_widget"
)
ss.exp_selected_displays = selected_displays
selected_metric_keys = [display_to_key[d] for d in selected_displays]


# ============================================================
# Validity warnings
# ============================================================
invalid_picks = [k for k in selected_metric_keys if not is_valid(k, granularity)]
valid_picks   = [k for k in selected_metric_keys if is_valid(k, granularity)]

if invalid_picks:
    warnings_html = ""
    for k in invalid_picks:
        reason = invalid_reason(k, granularity)
        warnings_html += f"<div class='invalid-warning'>⚠️ <b>{METRIC_LIBRARY[k]['display']}</b> — {reason}</div>"
    st.markdown(warnings_html, unsafe_allow_html=True)


# ============================================================
# Run button
# ============================================================
st.markdown("---")
col_run, col_spacer = st.columns([1, 3])
with col_run:
    run_query = st.button("⚡ Run Query", type="primary", use_container_width=True,
                           disabled=(len(valid_picks) == 0))


# ============================================================
# Execute query
# ============================================================
if run_query and valid_picks:
    kwargs = {}
    if granularity == "Block":
        kwargs = {"date": str(selected_date), "block_start": selected_block_start}
    elif granularity == "Block Range":
        kwargs = {"date": str(selected_date), "block_start": selected_block_start,
                  "block_end": selected_block_end, "br_mode": br_mode}
    elif granularity == "Day":
        kwargs = {"date": str(selected_date)}
    elif granularity == "Day Range":
        kwargs = {"date": str(selected_date), "end_date": str(selected_end_date)}
    elif granularity == "Week":
        kwargs = {"week_start": str(selected_week_start)}

    result = query_data(granularity, selected_metric_keys, **kwargs)
    ss.exp_last_result = {
        "result": result,
        "granularity": granularity,
        "n_valid_metrics": len(valid_picks),
        "br_mode": br_mode,
        "metric_keys": valid_picks,
    }
    ss.exp_view_override = None


# ============================================================
# Render last result
# ============================================================
if ss.exp_last_result is not None:
    cached = ss.exp_last_result
    result = cached["result"]
    g = cached["granularity"]
    n_metrics = cached["n_valid_metrics"]
    br_mode_used = cached["br_mode"]
    metric_keys = cached["metric_keys"]
    df_result = result["df"]

    if df_result.empty:
        st.warning(f"No data returned. {result.get('description', '')}")
    else:
        # ----------------------------------------------------
        # SPECIAL: mixed_day shape
        # ----------------------------------------------------
        if result["shape"] == "mixed_day":
            st.markdown(f"### 📋 Query Result")
            st.caption(result["description"])

            st.markdown("#### 📈 Intraday metrics (block-level)")
            x_col = "Time Block"
            metric_cols_units = _columns_with_units_from_result(
                df_result,
                [k for k in metric_keys if METRIC_LIBRARY[k]["source"] == "block"]
            )
            if metric_cols_units:
                _render_grouped_charts(df_result, metric_cols_units, x_col, chart_type="line")
            else:
                st.dataframe(df_result, use_container_width=True, hide_index=True)

            daily_df = result.get("daily_df")
            if daily_df is not None and not daily_df.empty:
                st.markdown("#### 📊 Daily-level metrics (one value per day)")
                ncards = len(daily_df)
                cols = st.columns(min(ncards, 4))
                for idx, (_, row) in enumerate(daily_df.iterrows()):
                    with cols[idx % len(cols)]:
                        val = row.get("Value")
                        unit = row.get("Unit", "")
                        val_str = f"{val:,.2f}" if isinstance(val, (int, float)) else (str(val) if val is not None else "—")
                        st.markdown(f"""
                        <div class="big-number-card">
                            <div class="big-number-label">{row['Metric']}</div>
                            <div class="big-number-value">{val_str}<span class="big-number-unit">{unit}</span></div>
                        </div>
                        """, unsafe_allow_html=True)

            st.caption(f"Shape: `mixed_day` · Intraday rows: {len(df_result)} · Daily metrics: {len(daily_df) if daily_df is not None else 0}")

            st.markdown("---")
            st.markdown('<div class="selector-label">💾 EXPORT</div>', unsafe_allow_html=True)
            col_csv, col_xlsx, col_spacer = st.columns([1, 1, 3])
            with col_csv:
                csv_bytes = df_result.to_csv(index=False).encode("utf-8")
                st.download_button("📄 Download CSV (intraday)", data=csv_bytes,
                                   file_name=f"agent_monsoon_intraday_{g.lower().replace(' ', '_')}.csv",
                                   mime="text/csv", use_container_width=True, key="csv_mixed")
            with col_xlsx:
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                    df_result.to_excel(writer, sheet_name="Intraday", index=False)
                    if daily_df is not None:
                        daily_df.to_excel(writer, sheet_name="Daily", index=False)
                st.download_button("📊 Download Excel (both)", data=buffer.getvalue(),
                                   file_name=f"agent_monsoon_mixed_{g.lower().replace(' ', '_')}.xlsx",
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                   use_container_width=True, key="xlsx_mixed")

            st.stop()

        # ----------------------------------------------------
        # Standard pipeline
        # ----------------------------------------------------
        st.markdown(f"### 📋 Query Result")
        st.caption(result["description"])

        recommended = recommend_view(g, n_metrics, result["shape"], br_mode_used)

        view_options_list = ["📊 Recommended", "Big Number", "Table", "Line Chart", "Bar Chart", "Multi-line Chart"]
        view_label_to_key = {
            "📊 Recommended": recommended,
            "Big Number":      "big_number",
            "Table":           "table",
            "Line Chart":      "line_chart",
            "Bar Chart":       "bar_chart",
            "Multi-line Chart":"multi_line",
        }
        col_view, col_reco = st.columns([1, 2])
        with col_view:
            picked_view_label = st.selectbox(
                "🎨 Change view",
                options=view_options_list,
                index=0,
                key="exp_view_picker"
            )
            view_to_render = view_label_to_key[picked_view_label]
        with col_reco:
            st.markdown(
                f"<div style='text-align:right;padding-top:30px;'>"
                f"🎯 Recommended: <span class='reco-pill'>{recommended.upper().replace('_', ' ')}</span>"
                f"</div>",
                unsafe_allow_html=True
            )

        try:
            if view_to_render == "big_number":
                if result["shape"] == "scalar":
                    for _, row in df_result.iterrows():
                        val = row.get("Value")
                        unit = row.get("Unit", "")
                        val_str = f"{val:,.2f}" if isinstance(val, (int, float)) else (str(val) if val is not None else "—")
                        st.markdown(f"""
                        <div class="big-number-card">
                            <div class="big-number-label">{row['Metric']}</div>
                            <div class="big-number-value">{val_str}<span class="big-number-unit">{unit}</span></div>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.info("Big Number view is best for single-block or single-day-scalar queries. Showing table instead.")
                    st.dataframe(df_result, use_container_width=True, hide_index=True)

            elif view_to_render == "line_chart":
                if result["shape"] in ("block_series", "day_series"):
                    x_col = "Time Block" if result["shape"] == "block_series" else "Date"
                    metric_cols_units = _columns_with_units_from_result(df_result, metric_keys)
                    if metric_cols_units:
                        _render_grouped_charts(df_result, metric_cols_units, x_col, chart_type="line")
                    else:
                        st.info("No numeric columns to plot. Showing table.")
                        st.dataframe(df_result, use_container_width=True, hide_index=True)
                else:
                    st.info("Line chart needs a time-series result. Showing table instead.")
                    st.dataframe(df_result, use_container_width=True, hide_index=True)

            elif view_to_render == "bar_chart":
                if result["shape"] in ("block_series", "day_series"):
                    x_col = "Time Block" if result["shape"] == "block_series" else "Date"
                    metric_cols_units = _columns_with_units_from_result(df_result, metric_keys)
                    if metric_cols_units:
                        _render_grouped_charts(df_result, metric_cols_units, x_col, chart_type="bar")
                    else:
                        st.info("No numeric columns to plot. Showing table.")
                        st.dataframe(df_result, use_container_width=True, hide_index=True)
                else:
                    st.info("Bar chart needs a series. Showing table instead.")
                    st.dataframe(df_result, use_container_width=True, hide_index=True)

            elif view_to_render == "multi_line":
                if result["shape"] in ("block_series", "day_series"):
                    x_col = "Time Block" if result["shape"] == "block_series" else "Date"
                    metric_cols_units = _columns_with_units_from_result(df_result, metric_keys)
                    if metric_cols_units:
                        _render_grouped_charts(df_result, metric_cols_units, x_col, chart_type="line")
                    else:
                        st.info("No numeric columns. Showing table.")
                        st.dataframe(df_result, use_container_width=True, hide_index=True)
                else:
                    st.info("Multi-line needs a series with multiple metrics. Showing table.")
                    st.dataframe(df_result, use_container_width=True, hide_index=True)

            else:  # "table" or fallback
                st.dataframe(df_result, use_container_width=True, hide_index=True)

        except Exception as e:
            st.error(f"Render error ({view_to_render}): {e}")
            st.dataframe(df_result, use_container_width=True, hide_index=True)

        st.caption(f"Shape: `{result['shape']}` · Rows: {len(df_result)} · Columns: {len(df_result.columns)}")

        # ----------------------------------------------------
        # Download buttons
        # ----------------------------------------------------
        st.markdown("---")
        st.markdown('<div class="selector-label">💾 EXPORT</div>', unsafe_allow_html=True)
        col_csv, col_xlsx, col_spacer = st.columns([1, 1, 3])

        with col_csv:
            csv_bytes = df_result.to_csv(index=False).encode("utf-8")
            st.download_button(
                "📄 Download CSV",
                data=csv_bytes,
                file_name=f"agent_monsoon_export_{g.replace(' ', '_').lower()}.csv",
                mime="text/csv",
                use_container_width=True,
                key="csv_main",
            )

        with col_xlsx:
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                df_result.to_excel(writer, sheet_name="Data", index=False)
            st.download_button(
                "📊 Download Excel",
                data=buffer.getvalue(),
                file_name=f"agent_monsoon_export_{g.replace(' ', '_').lower()}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key="xlsx_main",
            )

else:
    if len(valid_picks) == 0:
        st.info("👆 Pick at least one valid metric, then click **Run Query**.")
    else:
        st.info("👆 Adjust selectors above, then click **Run Query** to see results.")


# ============================================================
# Sidebar
# ============================================================
with st.sidebar:
    st.markdown("### 🔍 Data Explorer")
    st.markdown(f"**Coverage:** {DATA_MIN} → {DATA_MAX}")
    st.markdown(f"**Metrics:** {len(METRIC_LIBRARY)}")
    st.markdown(f"**Granularities:** {len(GRANULARITIES)}")

    st.markdown("---")

    if st.button("🔄 Reset all selectors", use_container_width=True):
        for k in list(ss.keys()):
            if k.startswith("exp_"):
                del ss[k]
        st.rerun()

    st.markdown("---")
    st.markdown("### 💡 Tips")
    st.caption("""
    - All prices in **₹/kWh**
    - **RMTI** & **Arbitrage** = Day/DR/Week only
    - **Block Range** has Raw / Aggregated toggle
    - Selections persist across page switches
    - Charts auto-split by scale (no flat lines)
    """)