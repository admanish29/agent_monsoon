"""
explorer.py — Data Explorer engine.

v1.8: API matches what pages/1_🔍_Data_Explorer.py expects.
      Storage Arbitrage Index REMOVED (users should use 🔋 Arbitrage Analysis page instead).

Exports:
  - METRIC_LIBRARY: 32 metrics (was 33, removed Storage Arbitrage Index)
  - GRANULARITIES: list of granularity names
  - is_valid(metric_key, granularity): bool
  - invalid_reason(metric_key, granularity): str
  - time_block_options(): list of 96 block labels
  - query_data(granularity, metric_keys, **kwargs): returns dict
  - recommend_view(granularity, n_metrics, shape, br_mode): str
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional

from src.tools import df_blocks, df_daily


# ============================================================
# METRIC LIBRARY
# ============================================================
# Each entry has:
#   display:  human-friendly name with unit suffix
#   column:   pandas column name in df_blocks or df_daily
#   source:   "block" (lives in df_blocks) | "day" (lives in df_daily)
#   category: group label for UI
#   unit:     measurement unit (₹/kWh, MW, %, x, σ, 0-100, count, bool, "")
#   agg:      default aggregation when rolling up (mean, sum, max, min)
#   scope:    "block" | "day" — minimum valid granularity
# ============================================================
METRIC_LIBRARY = {
    # ─── PRICING ───────────────────────────────────────────────
    "dam_mcp":             {"display": "DAM MCP (₹/kWh)",                       "column": "DAM_MCP",         "source": "block", "category": "Pricing", "unit": "₹/kWh", "agg": "mean", "scope": "block"},
    "gdam_mcp":            {"display": "GDAM MCP (₹/kWh)",                      "column": "GDAM_MCP",        "source": "block", "category": "Pricing", "unit": "₹/kWh", "agg": "mean", "scope": "block"},
    "dam_avg_mcp":         {"display": "DAM Avg MCP (₹/kWh)",                   "column": "dam_avg_mcp",     "source": "day",   "category": "Pricing", "unit": "₹/kWh", "agg": "mean", "scope": "day"},
    "dam_peak_mcp":        {"display": "DAM Peak MCP (₹/kWh)",                  "column": "dam_peak_mcp",    "source": "day",   "category": "Pricing", "unit": "₹/kWh", "agg": "max",  "scope": "day"},
    "dam_trough_mcp":      {"display": "DAM Trough MCP (₹/kWh)",                "column": "dam_trough_mcp",  "source": "day",   "category": "Pricing", "unit": "₹/kWh", "agg": "min",  "scope": "day"},
    "dam_spread":          {"display": "DAM Intraday Spread (peak−trough, ₹/kWh)","column": "dam_spread",    "source": "day",   "category": "Pricing", "unit": "₹/kWh", "agg": "mean", "scope": "day"},
    "gdam_avg_mcp":        {"display": "GDAM Avg MCP (₹/kWh)",                  "column": "gdam_avg_mcp",    "source": "day",   "category": "Pricing", "unit": "₹/kWh", "agg": "mean", "scope": "day"},
    "gdam_peak_mcp":       {"display": "GDAM Peak MCP (₹/kWh)",                 "column": "gdam_peak_mcp",   "source": "day",   "category": "Pricing", "unit": "₹/kWh", "agg": "max",  "scope": "day"},
    "gdam_trough_mcp":     {"display": "GDAM Trough MCP (₹/kWh)",               "column": "gdam_trough_mcp", "source": "day",   "category": "Pricing", "unit": "₹/kWh", "agg": "min",  "scope": "day"},
    "gdam_spread":         {"display": "GDAM Intraday Spread (peak−trough, ₹/kWh)","column": "gdam_spread",  "source": "day",   "category": "Pricing", "unit": "₹/kWh", "agg": "mean", "scope": "day"},

    # ─── VOLUMES ──────────────────────────────────────────────
    "dam_mcv":             {"display": "DAM MCV (MW)",                "column": "DAM_MCV",             "source": "block", "category": "Volumes", "unit": "MW", "agg": "mean", "scope": "block"},
    "dam_sell_bid":        {"display": "DAM Sell Bid (MW)",           "column": "DAM_Sell_Bid",        "source": "block", "category": "Volumes", "unit": "MW", "agg": "mean", "scope": "block"},
    "dam_purchase_bid":    {"display": "DAM Purchase Bid (MW)",       "column": "DAM_Purchase_Bid",    "source": "block", "category": "Volumes", "unit": "MW", "agg": "mean", "scope": "block"},
    "gdam_total_mcv":      {"display": "GDAM Total MCV (MW)",         "column": "GDAM_Total_MCV",      "source": "block", "category": "Volumes", "unit": "MW", "agg": "mean", "scope": "block"},
    "gdam_total_sell_bid": {"display": "GDAM Total Sell Bid (MW)",    "column": "GDAM_Total_Sell_Bid", "source": "block", "category": "Volumes", "unit": "MW", "agg": "mean", "scope": "block"},
    "gdam_purchase_bid":   {"display": "GDAM Purchase Bid (MW)",      "column": "GDAM_Purchase_Bid",   "source": "block", "category": "Volumes", "unit": "MW", "agg": "mean", "scope": "block"},
    "gdam_solar_mcv":      {"display": "GDAM Solar MCV (MW)",         "column": "GDAM_Solar_MCV",      "source": "block", "category": "Volumes", "unit": "MW", "agg": "mean", "scope": "block"},
    "gdam_nonsolar_mcv":   {"display": "GDAM Non-Solar MCV (MW)",     "column": "GDAM_NonSolar_MCV",   "source": "block", "category": "Volumes", "unit": "MW", "agg": "mean", "scope": "block"},
    "gdam_hydro_mcv":      {"display": "GDAM Hydro MCV (MW)",         "column": "GDAM_Hydro_MCV",      "source": "block", "category": "Volumes", "unit": "MW", "agg": "mean", "scope": "block"},

    # ─── LIQUIDITY ────────────────────────────────────────────
    "dam_dfr":             {"display": "DAM Demand Fulfillment Ratio (DFR, %)",  "column": "DAM_Demand_Fulfillment_Pct",  "source": "block", "category": "Liquidity", "unit": "%", "agg": "mean", "scope": "block"},
    "gdam_dfr":            {"display": "GDAM Demand Fulfillment Ratio (DFR, %)", "column": "GDAM_Demand_Fulfillment_Pct", "source": "block", "category": "Liquidity", "unit": "%", "agg": "mean", "scope": "block"},
    "dam_bcr":             {"display": "DAM Bid Coverage Ratio (BCR, x)",        "column": "DAM_Bid_Coverage_Ratio",      "source": "block", "category": "Liquidity", "unit": "x", "agg": "mean", "scope": "block"},
    "gdam_bcr":            {"display": "GDAM Bid Coverage Ratio (BCR, x)",       "column": "GDAM_Bid_Coverage_Ratio",     "source": "block", "category": "Liquidity", "unit": "x", "agg": "mean", "scope": "block"},

    # ─── CROSS-MARKET ────────────────────────────────────────
    "dam_gdam_premium":      {"display": "DAM−GDAM Premium (₹/kWh)",                "column": "DAM_GDAM_Premium",      "source": "block", "category": "Cross-Market", "unit": "₹/kWh", "agg": "mean", "scope": "block"},
    "stressed_blocks":       {"display": "Stressed Blocks Count",                   "column": "stressed_blocks",       "source": "day",   "category": "Cross-Market", "unit": "count", "agg": "sum",  "scope": "day"},
    "avg_dam_gdam_premium":  {"display": "Avg DAM−GDAM Premium daily (₹/kWh)",      "column": "avg_dam_gdam_premium",  "source": "day",   "category": "Cross-Market", "unit": "₹/kWh", "agg": "mean", "scope": "day"},

    # ─── RMTI ────────────────────────────────────────────────
    "rmti_composite": {"display": "RMTI Composite (0-100)",                "column": "rmti_composite", "source": "day", "category": "RMTI", "unit": "0-100", "agg": "mean", "scope": "day"},
    "bpc_pct":        {"display": "BPC — Block Premium Count (%)",          "column": "bpc_pct",        "source": "day", "category": "RMTI", "unit": "%",     "agg": "mean", "scope": "day"},
    "agp_rs_kwh":     {"display": "AGP — Avg Green Premium (₹/kWh)",        "column": "agp_rs_kwh",     "source": "day", "category": "RMTI", "unit": "₹/kWh", "agg": "mean", "scope": "day"},
    "ptc_pct":        {"display": "PTC — Peak Tightness Concentration (%)", "column": "ptc_pct",        "source": "day", "category": "RMTI", "unit": "%",     "agg": "mean", "scope": "day"},

    # ─── GRID CONGESTION ─────────────────────────────────────
    "dam_total_congestion":      {"display": "DAM Total Congestion (%)",      "column": "DAM_Total_Congestion_Pct",        "source": "block", "category": "Grid", "unit": "%", "agg": "mean", "scope": "block"},
    "gdam_total_congestion":     {"display": "GDAM Total Congestion (%)",     "column": "GDAM_Total_Congestion_Pct",       "source": "block", "category": "Grid", "unit": "%", "agg": "mean", "scope": "block"},
    "gdam_solar_congestion":     {"display": "GDAM Solar Congestion (%)",     "column": "GDAM_Solar_Congestion_Pct",       "source": "block", "category": "Grid", "unit": "%", "agg": "mean", "scope": "block"},
    "gdam_nonsolar_congestion":  {"display": "GDAM Non-Solar Congestion (%)", "column": "GDAM_NonSolar_Congestion_Pct",    "source": "block", "category": "Grid", "unit": "%", "agg": "mean", "scope": "block"},
    "gdam_hydro_congestion":     {"display": "GDAM Hydro Congestion (%)",     "column": "GDAM_Hydro_Congestion_Pct",       "source": "block", "category": "Grid", "unit": "%", "agg": "mean", "scope": "block"},

    # ─── ANOMALIES ───────────────────────────────────────────
    "dam_z_score":      {"display": "DAM z-score (σ)",   "column": "DAM_z_score",       "source": "block", "category": "Anomalies", "unit": "σ",    "agg": "mean", "scope": "block"},
    "gdam_z_score":     {"display": "GDAM z-score (σ)",  "column": "GDAM_z_score",      "source": "block", "category": "Anomalies", "unit": "σ",    "agg": "mean", "scope": "block"},
    "dam_anomaly_flag": {"display": "DAM anomaly flag",  "column": "DAM_anomaly_flag",  "source": "block", "category": "Anomalies", "unit": "bool", "agg": "sum",  "scope": "block"},
    "gdam_anomaly_flag":{"display": "GDAM anomaly flag", "column": "GDAM_anomaly_flag", "source": "block", "category": "Anomalies", "unit": "bool", "agg": "sum",  "scope": "block"},
}


# ============================================================
# CONSTANTS
# ============================================================
GRANULARITIES = ["Block", "Block Range", "Day", "Day Range", "Week"]


# ============================================================
# UI HELPERS
# ============================================================
def time_block_options() -> List[str]:
    """Return the list of 96 time block labels."""
    blocks = []
    for h in range(24):
        for q in range(4):
            start_min = q * 15
            end_h     = h if q < 3 else h + 1
            end_min   = (q + 1) * 15 % 60
            blocks.append(f"{h:02d}:{start_min:02d} - {end_h:02d}:{end_min:02d}")
    return blocks


# ============================================================
# VALIDITY
# ============================================================
def is_valid(metric_key: str, granularity: str) -> bool:
    """Return True if a metric can be queried at the given granularity."""
    meta = METRIC_LIBRARY.get(metric_key)
    if not meta:
        return False
    scope = meta["scope"]
    if scope == "block":
        return True   # block-source metrics can be aggregated up to any granularity
    if scope == "day":
        return granularity in ("Day", "Day Range", "Week")
    return False


def invalid_reason(metric_key: str, granularity: str) -> str:
    """Return a human-readable reason why the metric is invalid at this granularity."""
    meta = METRIC_LIBRARY.get(metric_key)
    if not meta:
        return f"Unknown metric: {metric_key}"
    if is_valid(metric_key, granularity):
        return ""
    scope = meta["scope"]
    if scope == "day":
        return f"This is a daily-level metric — requires Day, Day Range, or Week granularity (not {granularity})."
    return f"Not available at {granularity} granularity."


# ============================================================
# QUERY ROUTER
# ============================================================
def query_data(granularity: str, metric_keys: List[str], **kwargs) -> Dict:
    """Execute a query. Returns a dict with: df, shape, description, optionally daily_df.

    Shape values:
      - scalar       : 1 row, multiple metric columns (or 1 row in df with Metric/Value/Unit cols)
      - block_series : 96 rows (or sub-range), x-axis = Time Block
      - day_series   : N rows, x-axis = Date
      - mixed_day    : day-level query with both block-source AND day-source metrics

    kwargs by granularity:
      Block:        date, block_start
      Block Range:  date, block_start, block_end, br_mode ("aggregated" or "raw")
      Day:          date
      Day Range:    date (start), end_date
      Week:         week_start
    """
    valid_keys = [k for k in metric_keys if k in METRIC_LIBRARY and is_valid(k, granularity)]
    if not valid_keys:
        return {
            "df": pd.DataFrame(),
            "shape": "scalar",
            "description": "No valid metrics selected for this granularity.",
        }

    if granularity == "Block":
        return _query_block(valid_keys, kwargs["date"], kwargs["block_start"])
    if granularity == "Block Range":
        return _query_block_range(
            valid_keys, kwargs["date"], kwargs["block_start"],
            kwargs["block_end"], kwargs.get("br_mode", "aggregated")
        )
    if granularity == "Day":
        return _query_day(valid_keys, kwargs["date"])
    if granularity == "Day Range":
        return _query_day_range(valid_keys, kwargs["date"], kwargs["end_date"])
    if granularity == "Week":
        return _query_week(valid_keys, kwargs["week_start"])

    return {"df": pd.DataFrame(), "shape": "scalar", "description": f"Unknown granularity: {granularity}"}


def _query_block(metric_keys, date, block_start):
    """Single block — return scalar dataframe with one row of Metric/Value/Unit."""
    target = pd.to_datetime(date)
    sub = df_blocks[(df_blocks['Date'] == target) & (df_blocks['Time Block'] == block_start)]
    if sub.empty:
        return {"df": pd.DataFrame(), "shape": "scalar", "description": f"No data for {target.date()} at {block_start}"}
    row = sub.iloc[0]
    rows = []
    for k in metric_keys:
        m = METRIC_LIBRARY[k]
        col = m["column"]
        if m["source"] == "block" and col in row.index:
            val = row[col]
            if pd.isna(val):
                val = None
            rows.append({"Metric": m["display"], "Value": val, "Unit": m["unit"]})
    return {
        "df": pd.DataFrame(rows),
        "shape": "scalar",
        "description": f"Block: {target.date()} {block_start}",
    }


def _query_block_range(metric_keys, date, block_start, block_end, br_mode):
    """Range of blocks within one day. br_mode = 'aggregated' or 'raw'."""
    target = pd.to_datetime(date)
    blocks_today = df_blocks[df_blocks['Date'] == target].sort_values('Hour').reset_index(drop=True)
    if blocks_today.empty:
        return {"df": pd.DataFrame(), "shape": "scalar", "description": f"No data for {target.date()}"}

    start_idx = blocks_today[blocks_today['Time Block'] == block_start].index
    end_idx   = blocks_today[blocks_today['Time Block'] == block_end].index
    if start_idx.empty or end_idx.empty:
        return {"df": pd.DataFrame(), "shape": "scalar", "description": f"Block(s) not found in {target.date()}"}
    si, ei = int(start_idx[0]), int(end_idx[0])
    if ei < si:
        si, ei = ei, si

    sub = blocks_today.iloc[si:ei+1].copy()

    if br_mode == "raw":
        out = sub[['Time Block']].copy()
        for k in metric_keys:
            m = METRIC_LIBRARY[k]
            if m["source"] == "block" and m["column"] in sub.columns:
                out[m["display"]] = sub[m["column"]].values
        return {
            "df": out,
            "shape": "block_series",
            "description": f"Block range (raw): {target.date()} from {block_start} to {block_end} — {len(sub)} blocks",
        }
    else:
        rows = []
        for k in metric_keys:
            m = METRIC_LIBRARY[k]
            if m["source"] == "block" and m["column"] in sub.columns:
                agg = m["agg"]
                vals = sub[m["column"]].dropna()
                if vals.empty:
                    val = None
                elif agg == "mean":
                    val = round(float(vals.mean()), 3)
                elif agg == "sum":
                    val = round(float(vals.sum()), 3)
                elif agg == "max":
                    val = round(float(vals.max()), 3)
                elif agg == "min":
                    val = round(float(vals.min()), 3)
                else:
                    val = round(float(vals.mean()), 3)
                rows.append({"Metric": m["display"], "Value": val, "Unit": m["unit"]})
        return {
            "df": pd.DataFrame(rows),
            "shape": "scalar",
            "description": f"Block range (aggregated): {target.date()} from {block_start} to {block_end} — {len(sub)} blocks averaged",
        }


def _query_day(metric_keys, date):
    """Day granularity. Returns block_series, scalar, or mixed_day depending on metric sources."""
    target = pd.to_datetime(date)
    block_keys = [k for k in metric_keys if METRIC_LIBRARY[k]["source"] == "block"]
    day_keys   = [k for k in metric_keys if METRIC_LIBRARY[k]["source"] == "day"]

    if block_keys and not day_keys:
        return _build_block_series_for_day(target, block_keys)

    if day_keys and not block_keys:
        return _build_day_scalar(target, day_keys)

    # Mixed: both block-source AND day-source metrics
    series_result = _build_block_series_for_day(target, block_keys)
    daily_scalar  = _build_day_scalar(target, day_keys)
    return {
        "df": series_result["df"],
        "shape": "mixed_day",
        "description": f"Day: {target.date()} — intraday metrics + daily-level metrics",
        "daily_df": daily_scalar["df"],
    }


def _build_block_series_for_day(target, block_keys):
    sub = df_blocks[df_blocks['Date'] == target].sort_values('Hour').reset_index(drop=True)
    out = sub[['Time Block']].copy()
    for k in block_keys:
        m = METRIC_LIBRARY[k]
        if m["column"] in sub.columns:
            out[m["display"]] = sub[m["column"]].values
    return {
        "df": out,
        "shape": "block_series",
        "description": f"Day intraday series: {target.date()} — 96 blocks",
    }


def _build_day_scalar(target, day_keys):
    row = df_daily[df_daily['date'] == target]
    if row.empty:
        return {"df": pd.DataFrame(), "shape": "scalar", "description": f"No daily data for {target.date()}"}
    r = row.iloc[0]
    rows = []
    for k in day_keys:
        m = METRIC_LIBRARY[k]
        val = r[m["column"]] if m["column"] in r.index else None
        if pd.isna(val):
            val = None
        rows.append({"Metric": m["display"], "Value": val, "Unit": m["unit"]})
    return {
        "df": pd.DataFrame(rows),
        "shape": "scalar",
        "description": f"Day daily metrics: {target.date()}",
    }


def _query_day_range(metric_keys, start_date, end_date):
    """Day range — aggregate each metric to one value per day, return day_series."""
    s = pd.to_datetime(start_date)
    e = pd.to_datetime(end_date)
    if e < s:
        s, e = e, s

    out = pd.DataFrame({'Date': pd.date_range(s, e)})
    out['Date'] = pd.to_datetime(out['Date'])

    for k in metric_keys:
        m = METRIC_LIBRARY[k]
        col = m["column"]
        agg = m["agg"]
        if m["source"] == "block":
            sub = df_blocks[(df_blocks['Date'] >= s) & (df_blocks['Date'] <= e)]
            if col in sub.columns:
                grouped = sub.groupby('Date')[col].agg(agg).reset_index().rename(columns={col: m["display"]})
                grouped['Date'] = pd.to_datetime(grouped['Date'])
                out = out.merge(grouped, on='Date', how='left')
        else:
            sub = df_daily[(df_daily['date'] >= s) & (df_daily['date'] <= e)]
            if col in sub.columns:
                slice_ = sub[['date', col]].rename(columns={'date': 'Date', col: m["display"]})
                slice_['Date'] = pd.to_datetime(slice_['Date'])
                out = out.merge(slice_, on='Date', how='left')

    return {
        "df": out,
        "shape": "day_series",
        "description": f"Day range: {s.date()} to {e.date()} — {len(out)} days",
    }


def _query_week(metric_keys, week_start):
    """7 days Mon-Sun starting from week_start."""
    s = pd.to_datetime(week_start)
    e = s + pd.Timedelta(days=6)
    result = _query_day_range(metric_keys, s, e)
    result["description"] = f"Week: {s.date()} (Mon) to {e.date()} (Sun)"
    return result


# ============================================================
# VIEW RECOMMENDATION
# ============================================================
def recommend_view(granularity: str, n_metrics: int, shape: str, br_mode: str = "aggregated") -> str:
    """Recommend a visualization view based on query shape and metric count.
    Returns one of: 'big_number', 'table', 'line_chart', 'bar_chart', 'multi_line'.
    """
    if shape == "scalar":
        if n_metrics == 1:
            return "big_number"
        else:
            return "table"

    if shape == "block_series":
        if n_metrics == 1:
            return "line_chart"
        else:
            return "multi_line"

    if shape == "day_series":
        if n_metrics == 1:
            return "line_chart"
        else:
            return "multi_line"

    if shape == "mixed_day":
        return "line_chart"   # the intraday part renders as a line chart; daily cards below

    return "table"