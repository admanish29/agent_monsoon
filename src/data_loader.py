"""
data_loader.py — Single source of truth for loading IEX dataframes.

Reads the pickle file at data/iex_dataframes.pkl and exposes:
  - df_dam_hist  : block-level DAM data (~48k rows)
  - df_gdam_hist : block-level GDAM data (~48k rows)
  - df_blocks    : unified DAM + GDAM block data with cross-market metrics + VOLUME COLUMNS + GP alias
  - df_daily     : daily aggregates with RMTI composite, multi-hour arbitrage (84 cols), etc.
  - df_weekly    : Mon-Sun weekly aggregates
  - metadata     : dataset version, last_saved timestamp, rte_last_precomputed, etc.

Uses Streamlit's cache_resource so the pickle loads once per session.

NOTE: ENRICHES df_blocks with:
  - 12 volume columns (MCV, Sell Bid, Purchase Bid for DAM + GDAM total + GDAM source-wise)
  - GP alias column (= DAM_GDAM_Premium, clearer naming for Green Premium page)

Also performs RtE consistency check: if src/arbitrage.py:RTE differs from the value
stored in metadata['rte_last_precomputed'], shows a warning prompting re-precompute.
"""

import pickle
from pathlib import Path
import streamlit as st


PICKLE_PATH = Path(__file__).parent.parent / "data" / "iex_dataframes.pkl"


def _enrich_df_blocks(df_blocks, df_dam_hist, df_gdam_hist):
    """Add 12 volume cols + GP alias to df_blocks via merge on (Date, Time Block)."""
    # DAM merge (3 cols)
    dam_cols = {
        'MCV (MW)':          'DAM_MCV',
        'Sell Bid (MW)':     'DAM_Sell_Bid',
        'Purchase Bid (MW)': 'DAM_Purchase_Bid',
    }
    dam_slice = df_dam_hist[['Date', 'Time Block'] + list(dam_cols.keys())].rename(columns=dam_cols)
    df_blocks = df_blocks.merge(dam_slice, on=['Date', 'Time Block'], how='left')

    # GDAM merge (9 cols: 3 totals + 6 source-wise)
    gdam_cols = {
        'Total MCV (MW)':          'GDAM_Total_MCV',
        'Total Sell Bid (MW)':     'GDAM_Total_Sell_Bid',
        'Purchase Bid (MW)':       'GDAM_Purchase_Bid',
        'Solar MCV (MW)':          'GDAM_Solar_MCV',
        'Non-Solar MCV (MW)':      'GDAM_NonSolar_MCV',
        'Hydro MCV (MW)':          'GDAM_Hydro_MCV',
        'Solar Bid (MW)':          'GDAM_Solar_Sell_Bid',
        'Non-Solar Sell Bid (MW)': 'GDAM_NonSolar_Sell_Bid',
        'Hydro Sell Bid (MW)':     'GDAM_Hydro_Sell_Bid',
    }
    gdam_slice = df_gdam_hist[['Date', 'Time Block'] + list(gdam_cols.keys())].rename(columns=gdam_cols)
    df_blocks = df_blocks.merge(gdam_slice, on=['Date', 'Time Block'], how='left')

    # Green Premium alias — same as DAM_GDAM_Premium, clearer naming for Green Premium page
    # GP > 0 = DAM costlier (green discount); GP < 0 = GDAM costlier (green stress)
    df_blocks['GP'] = df_blocks['DAM_GDAM_Premium']

    return df_blocks


def _check_rte_consistency(metadata):
    """Warn if the RTE used at last precompute differs from current code's RTE.
    Called once per session (inside cached load_dataframes)."""
    try:
        from src.arbitrage import RTE as current_rte
    except ImportError:
        return

    stored_rte = metadata.get('rte_last_precomputed')
    if stored_rte is None:
        return   # legacy pickle, no RTE tracked — silent skip

    if abs(stored_rte - current_rte) > 0.0001:
        st.warning(
            f"⚠️ **RtE mismatch detected.** Current code uses **{current_rte} ({int(current_rte*100)}%)**, "
            f"but `df_daily` was last precomputed with **{stored_rte} ({int(stored_rte*100)}%)**. "
            f"Arbitrage spreads shown in the app are based on the OLD RtE. "
            f"To refresh, run: `python recompute_arb_with_rte.py` in your terminal."
        )


@st.cache_resource
def load_dataframes():
    """Load all dataframes from the pickle file. Cached per-session.
    Auto-enriches df_blocks with volume cols + GP alias.
    Performs RtE consistency check (warns if code's RTE != pickle's stored RTE)."""

    if not PICKLE_PATH.exists():
        raise FileNotFoundError(
            f"Pickle file not found at {PICKLE_PATH}. "
            "Make sure 'data/iex_dataframes.pkl' is in your project."
        )

    with open(PICKLE_PATH, 'rb') as f:
        bundle = pickle.load(f)

    df_dam_hist  = bundle['df_dam_hist']
    df_gdam_hist = bundle['df_gdam_hist']
    df_blocks    = bundle['df_blocks']
    df_daily     = bundle['df_daily']
    df_weekly    = bundle.get('df_weekly')

    # Enrich df_blocks with volume cols + GP alias
    df_blocks = _enrich_df_blocks(df_blocks, df_dam_hist, df_gdam_hist)

    # RtE consistency check (issues st.warning if mismatch)
    _check_rte_consistency(bundle['metadata'])

    return {
        'df_dam_hist':  df_dam_hist,
        'df_gdam_hist': df_gdam_hist,
        'df_blocks':    df_blocks,
        'df_daily':     df_daily,
        'df_weekly':    df_weekly,
        'metadata':     bundle['metadata'],
    }


def get_data_summary():
    """Quick summary of the loaded data — useful for the Home page."""
    data = load_dataframes()
    df_daily  = data['df_daily']
    df_blocks = data['df_blocks']
    metadata  = data['metadata']

    return {
        'total_days':       df_daily['date'].nunique(),
        'total_blocks':     len(df_blocks),
        'date_range_start': df_daily['date'].min().date(),
        'date_range_end':   df_daily['date'].max().date(),
        'last_saved':       metadata.get('last_saved'),
        'version':          metadata.get('version', 'unknown'),
        'rte':              metadata.get('rte_last_precomputed'),
    }