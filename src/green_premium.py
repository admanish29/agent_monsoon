"""
green_premium.py — Green Premium (GP) and Bid Coverage Ratio (BCR) analysis engine.

GP = DAM_MCP − GDAM_MCP  (positive = DAM costlier; negative = GDAM costlier)
DAM BCR = DAM Sell Bid / DAM Buy Bid  (volume-weighted at aggregate level)
GDAM BCR = GDAM Sell Bid / GDAM Buy Bid  (volume-weighted at aggregate level)

For any time period, returns:
  - Aggregate stats: mean, median, std, P10, P50, P90, min, max
  - Daily time-series (for multi-day periods)
  - Block-level distribution (for histogram + normal-fit overlay)
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict, List, Tuple
from datetime import date

from src.tools import df_blocks, df_daily


# ============================================================
# Constants
# ============================================================
GRANULARITY_LEVELS = ["Day", "Day Range", "Month", "Year"]


# ============================================================
# Period resolution — given user inputs, return start & end dates
# ============================================================
def resolve_period(granularity: str, **kwargs) -> Tuple[date, date, str]:
    """Return (start_date, end_date, label) for the selected period.
    kwargs varies by granularity:
      - Day: date
      - Day Range: start_date, end_date
      - Month: year, month
      - Year: year
    """
    if granularity == "Day":
        d = pd.to_datetime(kwargs['date']).date()
        return d, d, f"{d} ({pd.Timestamp(d).strftime('%A')})"

    if granularity == "Day Range":
        s = pd.to_datetime(kwargs['start_date']).date()
        e = pd.to_datetime(kwargs['end_date']).date()
        return s, e, f"{s} to {e} ({(e - s).days + 1} days)"

    if granularity == "Month":
        year, month = int(kwargs['year']), int(kwargs['month'])
        s = date(year, month, 1)
        if month == 12:
            e = date(year + 1, 1, 1) - pd.Timedelta(days=1)
        else:
            e = date(year, month + 1, 1) - pd.Timedelta(days=1)
        e = e.date() if hasattr(e, 'date') else e
        month_name = pd.Timestamp(s).strftime('%B %Y')
        return s, e, month_name

    if granularity == "Year":
        year = int(kwargs['year'])
        s = date(year, 1, 1)
        e = date(year, 12, 31)
        return s, e, f"Year {year}"

    raise ValueError(f"Unknown granularity: {granularity}")


# ============================================================
# Core extractor — get blocks in a period
# ============================================================
def _get_blocks_in_period(start_date, end_date) -> pd.DataFrame:
    """Return df_blocks filtered to the period, clipped to data availability."""
    s = pd.to_datetime(start_date)
    e = pd.to_datetime(end_date)
    sub = df_blocks[(df_blocks['Date'] >= s) & (df_blocks['Date'] <= e)].copy()
    return sub


# ============================================================
# AGGREGATION — compute summary stats for a metric series
# ============================================================
def _summary_stats(series: pd.Series) -> Dict:
    """Return mean / median / std / P10 / P50 / P90 / min / max for a numeric series."""
    clean = series.dropna()
    if clean.empty:
        return {k: None for k in ['mean', 'median', 'std', 'p10', 'p50', 'p90', 'min', 'max', 'n']}
    return {
        'mean':   round(float(clean.mean()),   3),
        'median': round(float(clean.median()), 3),
        'std':    round(float(clean.std()),    3),
        'p10':    round(float(clean.quantile(0.10)), 3),
        'p50':    round(float(clean.quantile(0.50)), 3),
        'p90':    round(float(clean.quantile(0.90)), 3),
        'min':    round(float(clean.min()),    3),
        'max':    round(float(clean.max()),    3),
        'n':      int(len(clean)),
    }


def _volume_weighted_bcr(sell_series: pd.Series, buy_series: pd.Series) -> float:
    """Aggregate BCR = sum(Sell) / sum(Buy). Returns None if denom is 0 or NaN."""
    sell_sum = sell_series.dropna().sum()
    buy_sum  = buy_series.dropna().sum()
    if buy_sum == 0 or pd.isna(buy_sum):
        return None
    return round(float(sell_sum / buy_sum), 3)


# ============================================================
# Top-level: get all stats for one metric over a period
# ============================================================
def get_gp_analysis(start_date, end_date) -> Dict:
    """Full GP analysis for a period.
    Returns: aggregate stats + daily series + raw block distribution."""
    blocks = _get_blocks_in_period(start_date, end_date)
    if blocks.empty:
        return {'error': f"No data between {start_date} and {end_date}"}

    # Aggregate stats from ALL blocks in the period
    agg = _summary_stats(blocks['GP'])

    # Daily series (one row per day)
    daily = blocks.groupby('Date').agg(
        gp_mean=('GP', 'mean'),
        gp_median=('GP', 'median'),
        gp_std=('GP', 'std'),
        gp_min=('GP', 'min'),
        gp_max=('GP', 'max'),
        n_blocks=('GP', 'count'),
    ).reset_index()
    daily['Date'] = pd.to_datetime(daily['Date']).dt.date

    # Block-level distribution (for histogram)
    distribution_values = blocks['GP'].dropna().tolist()

    return {
        'metric_name':     'Green Premium (GP)',
        'unit':            '₹/kWh',
        'aggregate_stats': agg,
        'daily_series':    daily.to_dict('records'),
        'distribution':    distribution_values,
        'n_blocks_total':  len(blocks),
        'n_days':          blocks['Date'].nunique(),
    }


def get_bcr_analysis(start_date, end_date, market: str) -> Dict:
    """Full BCR analysis for one market (DAM or GDAM) over a period.
    Aggregate BCR uses volume-weighted formula: sum(Sell) / sum(Buy)."""
    if market.upper() not in ("DAM", "GDAM"):
        raise ValueError(f"market must be 'DAM' or 'GDAM', got {market}")
    m = market.upper()

    blocks = _get_blocks_in_period(start_date, end_date)
    if blocks.empty:
        return {'error': f"No data between {start_date} and {end_date}"}

    # Column names
    sell_col = "DAM_Sell_Bid" if m == "DAM" else "GDAM_Total_Sell_Bid"
    buy_col  = "DAM_Purchase_Bid" if m == "DAM" else "GDAM_Purchase_Bid"
    ratio_col = f"{m}_Bid_Coverage_Ratio"

    # Aggregate BCR — volume-weighted
    aggregate_bcr = _volume_weighted_bcr(blocks[sell_col], blocks[buy_col])

    # Per-block BCR distribution
    block_bcr = blocks[ratio_col].dropna()
    distribution_values = block_bcr.tolist()

    # Build stats dict — use volume-weighted as the "mean", then standard stats from block-level distribution
    agg = _summary_stats(block_bcr)
    agg['mean_volume_weighted'] = aggregate_bcr   # the headline number

    # Daily series — volume-weighted BCR per day
    daily_rows = []
    for d, day_blocks in blocks.groupby('Date'):
        bcr_d = _volume_weighted_bcr(day_blocks[sell_col], day_blocks[buy_col])
        block_bcrs = day_blocks[ratio_col].dropna()
        daily_rows.append({
            'Date':       pd.to_datetime(d).date(),
            'bcr_vol_wt': bcr_d,
            'bcr_mean':   round(float(block_bcrs.mean()),   3) if not block_bcrs.empty else None,
            'bcr_median': round(float(block_bcrs.median()), 3) if not block_bcrs.empty else None,
            'bcr_min':    round(float(block_bcrs.min()),    3) if not block_bcrs.empty else None,
            'bcr_max':    round(float(block_bcrs.max()),    3) if not block_bcrs.empty else None,
            'n_blocks':   int(len(block_bcrs)),
        })

    return {
        'metric_name':     f'{m} Bid Coverage Ratio (BCR)',
        'unit':            'x (ratio)',
        'aggregate_stats': agg,
        'daily_series':    daily_rows,
        'distribution':    distribution_values,
        'n_blocks_total':  len(blocks),
        'n_days':          blocks['Date'].nunique(),
        'market':          m,
    }


# ============================================================
# Normal curve fit helper — for distribution overlay
# ============================================================
def normal_fit_params(values: List[float]) -> Dict:
    """Return mean & std for fitting a normal curve overlay. Empty → zeros."""
    if not values:
        return {'mean': 0.0, 'std': 1.0, 'n': 0}
    arr = np.array(values, dtype=float)
    arr = arr[~np.isnan(arr)]
    if len(arr) == 0:
        return {'mean': 0.0, 'std': 1.0, 'n': 0}
    return {
        'mean': float(arr.mean()),
        'std':  float(arr.std(ddof=1)) if len(arr) > 1 else 0.0,
        'n':    int(len(arr)),
    }