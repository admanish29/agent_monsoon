"""
capture_price.py — Effective Capture Price engine.

Computes the energy-weighted average price (₹/kWh) that an asset would have realized
on DAM and GDAM exchanges, given an hourly generation profile uploaded by the user.

Formula:
    Capture price = Σ(energy_MWh × hourly_price_₹/kWh) / Σ(energy_MWh)

Hour mapping: Hour 1 = blocks [00:00-00:15, 00:15-00:30, 00:30-00:45, 00:45-01:00]
              The 4 block MCPs are simple-averaged to produce one hourly price.

Period hour numbering: Hour 1 is the first hour of the FIRST day in the period.
For a 30-day period, hours run from 1 to 720 (= 30 × 24).
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from datetime import date, timedelta
from io import BytesIO

from src.tools import df_blocks


# ============================================================
# Constants
# ============================================================
GRANULARITY_LEVELS = ["Day", "Day Range", "Month", "Year"]


# ============================================================
# Period resolution (mirrors green_premium.py)
# ============================================================
def resolve_period(granularity: str, **kwargs) -> Tuple[date, date, str]:
    """Return (start_date, end_date, label) for the selected period."""
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
            e_ts = pd.Timestamp(year + 1, 1, 1) - pd.Timedelta(days=1)
        else:
            e_ts = pd.Timestamp(year, month + 1, 1) - pd.Timedelta(days=1)
        e = e_ts.date()
        month_name = pd.Timestamp(s).strftime('%B %Y')
        return s, e, month_name

    if granularity == "Year":
        year = int(kwargs['year'])
        s = date(year, 1, 1)
        e = date(year, 12, 31)
        return s, e, f"Year {year}"

    raise ValueError(f"Unknown granularity: {granularity}")


# ============================================================
# Build hourly prices from block data
# ============================================================
def build_hourly_prices(start_date, end_date) -> pd.DataFrame:
    """For the given period, return a DataFrame with hourly DAM + GDAM MCP.

    Each Hour 1-24 within each day = avg of 4 corresponding 15-min blocks.

    Returns columns: Date, HourOfDay, dam_hourly, gdam_hourly, period_hour
      - period_hour: 1-indexed running counter (1 to N_hours_in_period)
    """
    s = pd.to_datetime(start_date)
    e = pd.to_datetime(end_date)
    sub = df_blocks[(df_blocks['Date'] >= s) & (df_blocks['Date'] <= e)].copy()

    if sub.empty:
        return pd.DataFrame()

    # Group by Date + Hour and average DAM_MCP / GDAM_MCP
    hourly = sub.groupby(['Date', 'Hour']).agg(
        dam_hourly=('DAM_MCP', 'mean'),
        gdam_hourly=('GDAM_MCP', 'mean'),
        n_blocks=('DAM_MCP', 'count'),
    ).reset_index()

    hourly = hourly.rename(columns={'Hour': 'HourOfDay'})
    hourly['Date'] = pd.to_datetime(hourly['Date']).dt.date
    hourly = hourly.sort_values(['Date', 'HourOfDay']).reset_index(drop=True)

    # Add period_hour: running counter 1, 2, ..., N
    hourly['period_hour'] = np.arange(1, len(hourly) + 1)

    # Round prices to 3 decimals for cleanliness
    hourly['dam_hourly']  = hourly['dam_hourly'].round(3)
    hourly['gdam_hourly'] = hourly['gdam_hourly'].round(3)

    return hourly


# ============================================================
# Generate blank CSV template for the selected period
# ============================================================
def generate_blank_csv(start_date, end_date) -> bytes:
    """Generate a blank CSV with Hour, Date, Energy_MWh columns.

    The CSV starts with comment lines (using #) explaining the hour mapping.
    Energy_MWh column is blank for user to fill in.

    Returns bytes (CSV-encoded) suitable for st.download_button.
    """
    hourly = build_hourly_prices(start_date, end_date)
    if hourly.empty:
        return b""

    # Build the data portion
    out_df = pd.DataFrame({
        'Hour':       hourly['period_hour'],
        'Date':       hourly['Date'].astype(str),
        'HourOfDay':  hourly['HourOfDay'],
        'Energy_MWh': [''] * len(hourly),
    })

    # Header notes (CSV comments)
    s_str = str(start_date)
    e_str = str(end_date)
    n_hours = len(hourly)
    header_notes = (
        f"# Effective Capture Price — Energy profile template\n"
        f"# Period: {s_str} to {e_str} ({n_hours} hours)\n"
        f"# Hour 1 of each day = blocks 00:00-00:15, 00:15-00:30, 00:30-00:45, 00:45-01:00 (averaged)\n"
        f"# Fill in the Energy_MWh column. Save and upload.\n"
        f"# Do NOT change Hour, Date, or HourOfDay columns.\n"
        f"#\n"
    )

    csv_str = header_notes + out_df.to_csv(index=False)
    return csv_str.encode('utf-8')


# ============================================================
# Parse uploaded CSV — strict mode
# ============================================================
def parse_uploaded_csv(file_bytes: bytes, expected_start, expected_end) -> Dict:
    """Parse user-uploaded CSV. Strict validation against expected period.

    Returns dict with:
      - parsed_df: cleaned DataFrame with Hour, Date, Energy_MWh
      - n_filled: count of rows with non-NaN Energy_MWh > 0
      - n_expected: total expected hours in the period
      - coverage_pct: 100 * n_filled / n_expected
      - missing_hours: list of period_hour values that are missing
      - errors: list of validation errors (empty if OK)
    """
    # Decode bytes → string, then skip comment lines starting with '#'
    try:
        text = file_bytes.decode('utf-8')
    except UnicodeDecodeError:
        text = file_bytes.decode('latin-1')

    # Find first non-comment line
    lines = text.split('\n')
    data_lines = [ln for ln in lines if not ln.strip().startswith('#') and ln.strip()]
    csv_text = '\n'.join(data_lines)

    try:
        df = pd.read_csv(pd.io.common.StringIO(csv_text))
    except Exception as ex:
        return {
            'parsed_df': None,
            'errors': [f"Failed to parse CSV: {ex}"],
        }

    # Required columns
    required = {'Hour', 'Date', 'Energy_MWh'}
    missing_cols = required - set(df.columns)
    if missing_cols:
        return {
            'parsed_df': None,
            'errors': [f"Missing required column(s): {missing_cols}. Required: Hour, Date, Energy_MWh."],
        }

    # Validate Hour numbering matches expected
    expected_hourly = build_hourly_prices(expected_start, expected_end)
    n_expected = len(expected_hourly)
    if n_expected == 0:
        return {
            'parsed_df': None,
            'errors': [f"No block data available between {expected_start} and {expected_end}."],
        }

    # Strict check: row count must match expected
    if len(df) != n_expected:
        return {
            'parsed_df': None,
            'errors': [
                f"Row count mismatch. Expected {n_expected} hours, "
                f"got {len(df)}. Please use the downloaded template."
            ],
        }

    # Strict check: Hour column must be 1..N_expected
    expected_hours = list(range(1, n_expected + 1))
    if df['Hour'].tolist() != expected_hours:
        return {
            'parsed_df': None,
            'errors': [
                "Hour column doesn't match expected sequence (1, 2, ..., N). "
                "Please use the downloaded template — don't reorder rows."
            ],
        }

    # Clean Energy_MWh: convert to numeric, treat blanks as NaN
    df['Energy_MWh'] = pd.to_numeric(df['Energy_MWh'], errors='coerce')

    # Count filled (non-NaN AND > 0; treat 0 as "user explicitly said no generation")
    # Actually, 0 means valid data point with 0 energy. NaN = missing.
    n_filled    = int(df['Energy_MWh'].notna().sum())
    coverage    = 100.0 * n_filled / n_expected if n_expected > 0 else 0.0
    missing_idx = df.index[df['Energy_MWh'].isna()].tolist()
    missing_hours = df.loc[missing_idx, 'Hour'].tolist()

    return {
        'parsed_df':     df,
        'n_filled':      n_filled,
        'n_expected':    n_expected,
        'coverage_pct':  round(coverage, 2),
        'missing_hours': missing_hours,
        'errors':        [],
    }


# ============================================================
# Compute capture price (HEADLINE numbers only — Stage 1)
# ============================================================
def compute_capture_price(parsed_df: pd.DataFrame, start_date, end_date) -> Dict:
    """Given parsed uploaded CSV + period, compute capture prices.

    Returns dict with:
      - dam_capture:    energy-weighted avg DAM price (₹/kWh)
      - gdam_capture:   energy-weighted avg GDAM price (₹/kWh)
      - dam_time_avg:   simple time-averaged DAM price (for comparison)
      - gdam_time_avg:  simple time-averaged GDAM price
      - dam_capture_loss:  dam_capture − dam_time_avg (negative = lost; positive = gained)
      - gdam_capture_loss: same for GDAM
      - total_energy_mwh:  total energy used in computation
      - n_hours_used:      number of hours with valid energy data
      - merged_df:         per-hour merged data (for downstream charts)
    """
    # Build hourly prices for the period
    hourly = build_hourly_prices(start_date, end_date)
    if hourly.empty:
        return {'error': f"No block data available for {start_date} to {end_date}"}

    # Merge by period_hour
    merged = hourly.merge(
        parsed_df[['Hour', 'Energy_MWh']].rename(columns={'Hour': 'period_hour'}),
        on='period_hour',
        how='left',
    )

    # Keep only rows with valid energy
    valid = merged.dropna(subset=['Energy_MWh']).copy()
    if valid.empty or valid['Energy_MWh'].sum() == 0:
        return {'error': "No valid hours with positive energy. Cannot compute capture price."}

    total_energy = float(valid['Energy_MWh'].sum())

    # Energy-weighted capture price
    dam_capture  = float((valid['Energy_MWh'] * valid['dam_hourly']).sum() / total_energy)
    gdam_capture = float((valid['Energy_MWh'] * valid['gdam_hourly']).sum() / total_energy)

    # Reference: simple time-averaged price (across the SAME hours that have data)
    dam_time_avg  = float(valid['dam_hourly'].mean())
    gdam_time_avg = float(valid['gdam_hourly'].mean())

    return {
        'dam_capture':       round(dam_capture, 3),
        'gdam_capture':      round(gdam_capture, 3),
        'dam_time_avg':      round(dam_time_avg, 3),
        'gdam_time_avg':     round(gdam_time_avg, 3),
        'dam_capture_loss':  round(dam_capture - dam_time_avg, 3),
        'gdam_capture_loss': round(gdam_capture - gdam_time_avg, 3),
        'total_energy_mwh':  round(total_energy, 3),
        'n_hours_used':      int(len(valid)),
        'merged_df':         merged,  # for Stage 2 charts
    }