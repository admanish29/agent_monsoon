"""
tools.py — The 8 data-access tools the agent can call.

Each tool is a pure Python function that queries our dataframes
and returns a structured dict. Plus the JSON schemas Claude reads
to know when to use which tool.
"""

import pandas as pd
import numpy as np
from src.data_loader import load_dataframes


# ============================================================
# Load dataframes once at module import time
# ============================================================
_data = load_dataframes()
df_dam_hist  = _data['df_dam_hist']
df_gdam_hist = _data['df_gdam_hist']
df_blocks    = _data['df_blocks']
df_daily     = _data['df_daily']


# ============================================================
# TOOL 1: get_daily_summary
# ============================================================
def tool_get_daily_summary(date: str) -> dict:
    """Returns all key metrics for a specific date."""
    target = pd.to_datetime(date)
    row = df_daily[df_daily['date'] == target]
    if row.empty:
        return {"error": f"No data for {target.date()}"}
    d = row.iloc[0]
    return {
        "date": str(target.date()),
        "day_of_week": target.strftime('%A'),
        "dam_avg_mcp_rs_kwh": round(d['dam_avg_mcp'], 2),
        "dam_peak_mcp_rs_kwh": round(d['dam_peak_mcp'], 2),
        "dam_trough_mcp_rs_kwh": round(d['dam_trough_mcp'], 2),
        "dam_intraday_spread_rs_kwh": round(d['dam_spread'], 2),
        "gdam_avg_mcp_rs_kwh": round(d['gdam_avg_mcp'], 2),
        "gdam_peak_mcp_rs_kwh": round(d['gdam_peak_mcp'], 2),
        "gdam_trough_mcp_rs_kwh": round(d['gdam_trough_mcp'], 2),
        "gdam_intraday_spread_rs_kwh": round(d['gdam_spread'], 2),
        "avg_dam_minus_gdam_premium_rs_kwh": round(d['avg_dam_gdam_premium'], 2),
        "stressed_blocks_out_of_96": int(d['stressed_blocks']),
        "storage_arbitrage_index_rs_kwh": round(d['arbitrage_index'], 2),
        "arbitrage_path": d['arb_path'],
        "arbitrage_buy": f"₹{d['arb_buy_price']:.2f} on {d['arb_buy_market']} at {d['arb_buy_block']}",
        "arbitrage_sell": f"₹{d['arb_sell_price']:.2f} on {d['arb_sell_market']} at {d['arb_sell_block']}",
        "rmti_composite_0_to_100": round(d['rmti_composite'], 1) if pd.notna(d['rmti_composite']) else None,
        "rmti_is_record_day": bool(d['rmti_is_record']) if pd.notna(d['rmti_is_record']) else False,
        "rmti_bpc_pct": round(d['bpc_pct'], 1),
        "rmti_agp_rs_kwh": round(d['agp_rs_kwh'], 2),
        "rmti_ptc_pct": round(d['ptc_pct'], 1),
    }


# ============================================================
# TOOL 2: get_block_details
# ============================================================
def tool_get_block_details(date: str, time_block: str) -> dict:
    target = pd.to_datetime(date)
    row = df_blocks[(df_blocks['Date'] == target) & (df_blocks['Time Block'] == time_block)]
    if row.empty:
        return {"error": f"No block found for {target.date()} at '{time_block}'. Format must be 'HH:MM - HH:MM'."}
    b = row.iloc[0]
    return {
        "date": str(target.date()),
        "time_block": time_block,
        "hour": int(b['Hour']),
        "dam_mcp_rs_kwh": round(b['DAM_MCP'], 2),
        "gdam_mcp_rs_kwh": round(b['GDAM_MCP'], 2),
        "dam_minus_gdam_premium_rs_kwh": round(b['DAM_GDAM_Premium'], 2),
        "dam_demand_fulfillment_pct": round(b['DAM_Demand_Fulfillment_Pct'], 1),
        "gdam_demand_fulfillment_pct": round(b['GDAM_Demand_Fulfillment_Pct'], 1),
        "dam_bid_coverage_ratio": round(b['DAM_Bid_Coverage_Ratio'], 2),
        "gdam_bid_coverage_ratio": round(b['GDAM_Bid_Coverage_Ratio'], 2),
        "dam_congestion_pct": round(b['DAM_Total_Congestion_Pct'], 2) if pd.notna(b['DAM_Total_Congestion_Pct']) else 0,
        "gdam_congestion_pct": round(b['GDAM_Total_Congestion_Pct'], 2) if pd.notna(b['GDAM_Total_Congestion_Pct']) else 0,
        "gdam_solar_curtailment_pct": round(b['GDAM_Solar_Congestion_Pct'], 2) if pd.notna(b['GDAM_Solar_Congestion_Pct']) else 0,
        "gdam_nonsolar_curtailment_pct": round(b['GDAM_NonSolar_Congestion_Pct'], 2) if pd.notna(b['GDAM_NonSolar_Congestion_Pct']) else 0,
        "gdam_hydro_curtailment_pct": round(b['GDAM_Hydro_Congestion_Pct'], 2) if pd.notna(b['GDAM_Hydro_Congestion_Pct']) else 0,
        "dam_z_score": round(b['DAM_z_score'], 2) if pd.notna(b['DAM_z_score']) else None,
        "gdam_z_score": round(b['GDAM_z_score'], 2) if pd.notna(b['GDAM_z_score']) else None,
        "dam_anomaly": b['DAM_anomaly_direction'] if b['DAM_anomaly_direction'] else "no",
        "gdam_anomaly": b['GDAM_anomaly_direction'] if b['GDAM_anomaly_direction'] else "no",
    }


# ============================================================
# TOOL 3: get_date_range_stats
# ============================================================
def tool_get_date_range_stats(start_date: str, end_date: str) -> dict:
    start, end = pd.to_datetime(start_date), pd.to_datetime(end_date)
    subset = df_daily[(df_daily['date'] >= start) & (df_daily['date'] <= end)]
    if subset.empty:
        return {"error": f"No data in range {start.date()} to {end.date()}"}
    return {
        "start_date": str(start.date()),
        "end_date": str(end.date()),
        "days_in_range": len(subset),
        "dam_avg_mcp_mean_rs_kwh": round(subset['dam_avg_mcp'].mean(), 2),
        "dam_avg_mcp_max_rs_kwh": round(subset['dam_avg_mcp'].max(), 2),
        "dam_avg_mcp_min_rs_kwh": round(subset['dam_avg_mcp'].min(), 2),
        "gdam_avg_mcp_mean_rs_kwh": round(subset['gdam_avg_mcp'].mean(), 2),
        "gdam_avg_mcp_max_rs_kwh": round(subset['gdam_avg_mcp'].max(), 2),
        "gdam_avg_mcp_min_rs_kwh": round(subset['gdam_avg_mcp'].min(), 2),
        "rmti_composite_mean": round(subset['rmti_composite'].mean(), 1) if subset['rmti_composite'].notna().any() else None,
        "rmti_composite_max": round(subset['rmti_composite'].max(), 1) if subset['rmti_composite'].notna().any() else None,
        "rmti_composite_min": round(subset['rmti_composite'].min(), 1) if subset['rmti_composite'].notna().any() else None,
        "arbitrage_mean_rs_kwh": round(subset['arbitrage_index'].mean(), 2),
        "arbitrage_max_rs_kwh": round(subset['arbitrage_index'].max(), 2),
        "stressed_blocks_total": int(subset['stressed_blocks'].sum()),
        "record_days_count": int(subset['rmti_is_record'].sum()) if 'rmti_is_record' in subset.columns else 0,
    }


# ============================================================
# TOOL 4: find_extreme_days
# ============================================================
def tool_find_extreme_days(metric: str, direction: str = "max", top_n: int = 5,
                           start_date: str = None, end_date: str = None) -> dict:
    valid_metrics = ['rmti_composite', 'arbitrage_index', 'dam_avg_mcp', 'gdam_avg_mcp',
                     'dam_spread', 'gdam_spread', 'avg_dam_gdam_premium', 'stressed_blocks',
                     'bpc_pct', 'agp_rs_kwh', 'ptc_pct']
    if metric not in valid_metrics:
        return {"error": f"Invalid metric. Pick from: {valid_metrics}"}

    subset = df_daily.dropna(subset=[metric]).copy()
    if start_date:
        subset = subset[subset['date'] >= pd.to_datetime(start_date)]
    if end_date:
        subset = subset[subset['date'] <= pd.to_datetime(end_date)]
    if subset.empty:
        return {"error": "No data matching filters"}

    if direction == "max":
        top = subset.nlargest(top_n, metric)
    elif direction == "min":
        top = subset.nsmallest(top_n, metric)
    else:
        return {"error": "direction must be 'max' or 'min'"}

    return {
        "metric": metric,
        "direction": direction,
        "top_n": top_n,
        "results": [
            {
                "date": str(r['date'].date()),
                "value": round(r[metric], 2),
                "rmti_composite": round(r['rmti_composite'], 1) if pd.notna(r['rmti_composite']) else None,
                "dam_avg_mcp_rs_kwh": round(r['dam_avg_mcp'], 2),
                "gdam_avg_mcp_rs_kwh": round(r['gdam_avg_mcp'], 2),
            }
            for _, r in top.iterrows()
        ]
    }


# ============================================================
# TOOL 5: find_anomalous_blocks
# ============================================================
def tool_find_anomalous_blocks(market: str = "either", direction: str = "either",
                               top_n: int = 10, start_date: str = None, end_date: str = None) -> dict:
    subset = df_blocks.copy()
    if start_date:
        subset = subset[subset['Date'] >= pd.to_datetime(start_date)]
    if end_date:
        subset = subset[subset['Date'] <= pd.to_datetime(end_date)]

    if market == "DAM":
        subset = subset[subset['DAM_anomaly_flag'] == True]
        if direction in ("HIGH", "LOW"):
            subset = subset[subset['DAM_anomaly_direction'] == direction]
        subset['rank_score'] = subset['DAM_z_score'].abs()
    elif market == "GDAM":
        subset = subset[subset['GDAM_anomaly_flag'] == True]
        if direction in ("HIGH", "LOW"):
            subset = subset[subset['GDAM_anomaly_direction'] == direction]
        subset['rank_score'] = subset['GDAM_z_score'].abs()
    else:
        subset = subset[(subset['DAM_anomaly_flag'] == True) | (subset['GDAM_anomaly_flag'] == True)]
        subset['rank_score'] = subset[['DAM_z_score', 'GDAM_z_score']].abs().max(axis=1)

    if subset.empty:
        return {"error": "No anomalies match the filter"}

    top = subset.nlargest(top_n, 'rank_score')
    return {
        "market_filter": market,
        "direction_filter": direction,
        "results": [
            {
                "date": str(r['Date'].date()),
                "time_block": r['Time Block'],
                "dam_mcp_rs_kwh": round(r['DAM_MCP'], 2),
                "gdam_mcp_rs_kwh": round(r['GDAM_MCP'], 2),
                "dam_z_score": round(r['DAM_z_score'], 2) if pd.notna(r['DAM_z_score']) else None,
                "gdam_z_score": round(r['GDAM_z_score'], 2) if pd.notna(r['GDAM_z_score']) else None,
                "dam_anomaly_direction": r['DAM_anomaly_direction'] or "no",
                "gdam_anomaly_direction": r['GDAM_anomaly_direction'] or "no",
            }
            for _, r in top.iterrows()
        ]
    }


# ============================================================
# TOOL 6: compare_periods
# ============================================================
def tool_compare_periods(period_a_start: str, period_a_end: str,
                         period_b_start: str, period_b_end: str) -> dict:
    def _agg(s, e):
        sub = df_daily[(df_daily['date'] >= pd.to_datetime(s)) & (df_daily['date'] <= pd.to_datetime(e))]
        if sub.empty:
            return None
        return {
            "days": len(sub),
            "dam_avg_mcp_mean": round(sub['dam_avg_mcp'].mean(), 2),
            "gdam_avg_mcp_mean": round(sub['gdam_avg_mcp'].mean(), 2),
            "rmti_composite_mean": round(sub['rmti_composite'].mean(), 1) if sub['rmti_composite'].notna().any() else None,
            "arbitrage_mean": round(sub['arbitrage_index'].mean(), 2),
            "stressed_blocks_per_day_avg": round(sub['stressed_blocks'].mean(), 1),
            "bpc_pct_mean": round(sub['bpc_pct'].mean(), 1),
            "agp_rs_kwh_mean": round(sub['agp_rs_kwh'].mean(), 2),
        }
    a, b = _agg(period_a_start, period_a_end), _agg(period_b_start, period_b_end)
    if a is None or b is None:
        return {"error": "One or both periods returned no data"}
    delta = {k: round(a[k] - b[k], 2) if isinstance(a[k], (int, float)) and isinstance(b[k], (int, float)) and a[k] is not None and b[k] is not None else None for k in a}
    return {
        "period_a": {"start": period_a_start, "end": period_a_end, "metrics": a},
        "period_b": {"start": period_b_start, "end": period_b_end, "metrics": b},
        "delta_a_minus_b": delta,
    }


# ============================================================
# TOOL 7: get_hourly_pattern
# ============================================================
def tool_get_hourly_pattern(metric: str, start_date: str = None, end_date: str = None) -> dict:
    valid = ['DAM_MCP', 'GDAM_MCP', 'DAM_GDAM_Premium',
             'DAM_Demand_Fulfillment_Pct', 'GDAM_Demand_Fulfillment_Pct',
             'DAM_Total_Congestion_Pct', 'GDAM_Total_Congestion_Pct']
    if metric not in valid:
        return {"error": f"Invalid metric. Pick from: {valid}"}

    subset = df_blocks.copy()
    if start_date:
        subset = subset[subset['Date'] >= pd.to_datetime(start_date)]
    if end_date:
        subset = subset[subset['Date'] <= pd.to_datetime(end_date)]
    if subset.empty:
        return {"error": "No data in range"}

    grp = subset.groupby('Hour')[metric].agg(['mean', 'min', 'max']).round(2)
    return {
        "metric": metric,
        "start_date": start_date or str(subset['Date'].min().date()),
        "end_date": end_date or str(subset['Date'].max().date()),
        "days_in_window": subset['Date'].nunique(),
        "hourly_pattern": [
            {"hour": int(h), "mean": float(r['mean']), "min": float(r['min']), "max": float(r['max'])}
            for h, r in grp.iterrows()
        ]
    }


# ============================================================
# TOOL 8: get_window_around_date
# ============================================================
def tool_get_window_around_date(center_date: str, days_before: int = 3, days_after: int = 3) -> dict:
    center = pd.to_datetime(center_date)
    start = center - pd.Timedelta(days=days_before)
    end = center + pd.Timedelta(days=days_after)
    subset = df_daily[(df_daily['date'] >= start) & (df_daily['date'] <= end)].copy()
    if subset.empty:
        return {"error": f"No data around {center.date()}"}
    return {
        "center_date": str(center.date()),
        "days_before": days_before,
        "days_after": days_after,
        "results": [
            {
                "date": str(r['date'].date()),
                "day_of_week": r['date'].strftime('%A'),
                "is_center": r['date'] == center,
                "dam_avg_mcp_rs_kwh": round(r['dam_avg_mcp'], 2),
                "gdam_avg_mcp_rs_kwh": round(r['gdam_avg_mcp'], 2),
                "rmti_composite": round(r['rmti_composite'], 1) if pd.notna(r['rmti_composite']) else None,
                "stressed_blocks": int(r['stressed_blocks']),
                "arbitrage_rs_kwh": round(r['arbitrage_index'], 2),
                "is_record_day": bool(r['rmti_is_record']) if pd.notna(r['rmti_is_record']) else False,
            }
            for _, r in subset.iterrows()
        ]
    }


# ============================================================
# TOOL_FUNCTIONS dict — used by the agent to dispatch calls
# ============================================================
TOOL_FUNCTIONS = {
    "get_daily_summary":       tool_get_daily_summary,
    "get_block_details":       tool_get_block_details,
    "get_date_range_stats":    tool_get_date_range_stats,
    "find_extreme_days":       tool_find_extreme_days,
    "find_anomalous_blocks":   tool_find_anomalous_blocks,
    "compare_periods":         tool_compare_periods,
    "get_hourly_pattern":      tool_get_hourly_pattern,
    "get_window_around_date":  tool_get_window_around_date,
}


# ============================================================
# TOOL_SCHEMAS — JSON descriptions Claude reads
# ============================================================
TOOL_SCHEMAS = [
    {
        "name": "get_daily_summary",
        "description": "Returns all key metrics for a specific date: DAM/GDAM prices (avg, peak, trough, spread), cross-market premium, RMTI composite + components, arbitrage index with the tradable path (buy/sell market and time blocks), stressed block count. Use this when the user asks about a specific date.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "Date in YYYY-MM-DD format, e.g. '2026-05-05'"}
            },
            "required": ["date"]
        }
    },
    {
        "name": "get_block_details",
        "description": "Returns detailed metrics for ONE specific 15-minute time block on a specific date: DAM/GDAM prices, premium, demand fulfillment, bid coverage, congestion (overall + source-wise), anomaly z-scores and flags. Use when user asks about a specific block (e.g. 'what happened at 18:30 on 5 May?').",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
                "time_block": {"type": "string", "description": "Time block in 'HH:MM - HH:MM' format (with spaces around the dash). Example: '18:30 - 18:45'. Note: 96 blocks per day starting at 00:00 - 00:15, ending at 23:45 - 24:00."}
            },
            "required": ["date", "time_block"]
        }
    },
    {
        "name": "get_date_range_stats",
        "description": "Aggregate statistics over a date range (inclusive). Returns means, max, min for DAM/GDAM prices, RMTI composite, arbitrage; total stressed blocks; count of record days. Use for monthly/quarterly/multi-week summaries.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "Start date in YYYY-MM-DD format"},
                "end_date": {"type": "string", "description": "End date in YYYY-MM-DD format (inclusive)"}
            },
            "required": ["start_date", "end_date"]
        }
    },
    {
        "name": "find_extreme_days",
        "description": "Find the top N days with the highest or lowest value of any daily metric. Use for questions like 'which days had the worst RMTI?', 'top 5 highest arbitrage days', 'days with the lowest DAM prices'. Optionally filter by date range.",
        "input_schema": {
            "type": "object",
            "properties": {
                "metric": {
                    "type": "string",
                    "description": "Which metric to rank by",
                    "enum": ["rmti_composite", "arbitrage_index", "dam_avg_mcp", "gdam_avg_mcp",
                             "dam_spread", "gdam_spread", "avg_dam_gdam_premium", "stressed_blocks",
                             "bpc_pct", "agp_rs_kwh", "ptc_pct"]
                },
                "direction": {"type": "string", "description": "'max' for highest values, 'min' for lowest", "enum": ["max", "min"]},
                "top_n": {"type": "integer", "description": "How many days to return (default: 5)"},
                "start_date": {"type": "string", "description": "Optional. Filter to date range starting YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "Optional. Filter to date range ending YYYY-MM-DD"}
            },
            "required": ["metric", "direction"]
        }
    },
    {
        "name": "find_anomalous_blocks",
        "description": "Find the most extreme anomalous blocks (price deviations >2σ from 30-day same-block baseline). Use for questions about unusual events, price spikes, or crashes. Can filter by market (DAM/GDAM/either), direction (HIGH spike / LOW crash), and date range. Note: when prior 30-day variance is very low, z-scores can become extreme (>20) which may reflect statistical artifact rather than market crisis.",
        "input_schema": {
            "type": "object",
            "properties": {
                "market": {"type": "string", "description": "Which market's anomalies: 'DAM', 'GDAM', or 'either'", "enum": ["DAM", "GDAM", "either"]},
                "direction": {"type": "string", "description": "'HIGH' = price spike, 'LOW' = crash, 'either' = both", "enum": ["HIGH", "LOW", "either"]},
                "top_n": {"type": "integer", "description": "How many anomalous blocks to return (default: 10)"},
                "start_date": {"type": "string", "description": "Optional date filter (YYYY-MM-DD)"},
                "end_date": {"type": "string", "description": "Optional date filter (YYYY-MM-DD)"}
            },
            "required": ["market", "direction"]
        }
    },
    {
        "name": "compare_periods",
        "description": "Compare aggregate metrics between TWO date ranges. Returns metrics for both periods plus delta (period_a minus period_b). Use for questions like 'how did April 2025 compare to April 2026?', 'Q1 vs Q2 2025'. Periods can be any length.",
        "input_schema": {
            "type": "object",
            "properties": {
                "period_a_start": {"type": "string", "description": "Period A start date (YYYY-MM-DD)"},
                "period_a_end":   {"type": "string", "description": "Period A end date (YYYY-MM-DD)"},
                "period_b_start": {"type": "string", "description": "Period B start date (YYYY-MM-DD)"},
                "period_b_end":   {"type": "string", "description": "Period B end date (YYYY-MM-DD)"}
            },
            "required": ["period_a_start", "period_a_end", "period_b_start", "period_b_end"]
        }
    },
    {
        "name": "get_hourly_pattern",
        "description": "Aggregate a block-level metric by Hour-of-day across a date range. Reveals time-of-day patterns (e.g. 'is GDAM always costlier than DAM in pre-dawn hours?'). Returns mean/min/max for each of 24 hours. Hour 1 = 00:00-01:00, Hour 13 = 12:00-13:00 (solar peak), Hour 20 = 19:00-20:00 (evening peak).",
        "input_schema": {
            "type": "object",
            "properties": {
                "metric": {
                    "type": "string",
                    "description": "Which block-level metric to aggregate by hour",
                    "enum": ["DAM_MCP", "GDAM_MCP", "DAM_GDAM_Premium",
                             "DAM_Demand_Fulfillment_Pct", "GDAM_Demand_Fulfillment_Pct",
                             "DAM_Total_Congestion_Pct", "GDAM_Total_Congestion_Pct"]
                },
                "start_date": {"type": "string", "description": "Optional start date (YYYY-MM-DD). Default: full dataset"},
                "end_date": {"type": "string", "description": "Optional end date (YYYY-MM-DD). Default: full dataset"}
            },
            "required": ["metric"]
        }
    },
    {
        "name": "get_window_around_date",
        "description": "Returns daily summaries for N days before and N days after a center date. Useful for putting an event in context — see how metrics evolved leading into and out of a significant day.",
        "input_schema": {
            "type": "object",
            "properties": {
                "center_date": {"type": "string", "description": "The focal date in YYYY-MM-DD format"},
                "days_before": {"type": "integer", "description": "How many days before to include (default: 3)"},
                "days_after": {"type": "integer", "description": "How many days after to include (default: 3)"}
            },
            "required": ["center_date"]
        }
    }
]