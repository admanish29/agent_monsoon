"""
arbitrage.py — Multi-hour battery arbitrage engine (RtE-corrected, vectorized).

Spread metric:
    spread = sell_avg − buy_avg / RTE    (₹ per kWh of energy SOLD)

For a given day's 96 blocks, computes the best buy + cooling + sell window
across 4 durations (1h, 2h, 3h, 4h) and 3 paths (DAM-only, GDAM-only, Cross).

Window structure rules:
  - Each "hour" = 4 contiguous 15-min blocks
  - Between consecutive "hours" within a window: gap of 0 or 1 block (max 15 min)
  - Between buy-window-end and sell-window-start: minimum 1 block cooling

Path rules:
  - DAM-only: buy DAM, sell DAM
  - GDAM-only: buy GDAM, sell GDAM
  - Cross: buy GDAM, sell DAM
"""

from typing import List, Dict, Optional
import pandas as pd
import numpy as np


# ============================================================
# CONSTANTS — edit RTE here to update across the entire app
# ============================================================
RTE              = 0.83   # Battery Round-Trip Efficiency. Re-precompute df_daily if changed.
N_BLOCKS_PER_DAY = 96
BLOCKS_PER_HOUR  = 4
DURATIONS_HOURS  = [1, 2, 3, 4]


# ============================================================
# WINDOW SHAPE ENUMERATION
# ============================================================
def enumerate_window_shapes(n_hours: int) -> List[List[int]]:
    """Return all valid offset-lists for an N-hour window.
    Each shape is a list of N starting blocks for the N "hour groups".
    Within shape: each hour = 4 contiguous blocks, gap between hours = 0 or 1 block."""
    shapes = [[0]]
    for h in range(1, n_hours):
        new_shapes = []
        for shape in shapes:
            prev_hour_end = shape[-1] + BLOCKS_PER_HOUR
            for gap in (0, 1):
                new_shapes.append(shape + [prev_hour_end + gap])
        shapes = new_shapes
    return shapes


def materialize_window(start_block: int, shape: List[int]) -> List[int]:
    """Given a starting block and a window shape, return the list of all block indices."""
    blocks = []
    for hour_offset in shape:
        first_block = start_block + hour_offset
        for b in range(BLOCKS_PER_HOUR):
            blocks.append(first_block + b)
    return blocks


def window_span(shape: List[int]) -> int:
    """Total span of a window in blocks."""
    return shape[-1] + BLOCKS_PER_HOUR


# ============================================================
# VECTORIZED ARBITRAGE COMPUTATION
# ============================================================
def _precompute_all_window_avgs(prices: np.ndarray, n_hours: int):
    """For a given price series and n_hours, return arrays of (avg, start_block, shape_idx, block_indices)
    for every (starting_block, shape) combination.
    Vectorized — avoids inner Python loop over blocks."""
    shapes = enumerate_window_shapes(n_hours)
    all_avgs    = []
    all_starts  = []
    all_shapes  = []
    all_blocks  = []

    for shape_idx, shape in enumerate(shapes):
        span = window_span(shape)
        max_start = N_BLOCKS_PER_DAY - span
        if max_start < 0:
            continue

        starts = np.arange(0, max_start + 1)
        # For each starting block, the window's block indices = start + shape_offsets[i] + [0..3]
        for s in starts:
            block_indices = materialize_window(int(s), shape)
            avg = float(prices[block_indices].mean())
            all_avgs.append(avg)
            all_starts.append(int(s))
            all_shapes.append(shape)
            all_blocks.append(block_indices)

    return {
        'avgs':         np.array(all_avgs),
        'starts':       np.array(all_starts),
        'shapes':       all_shapes,
        'block_indices': all_blocks,
        'last_blocks':  np.array([blocks[-1] for blocks in all_blocks]),
        'first_blocks': np.array([blocks[0]  for blocks in all_blocks]),
    }


def _best_arbitrage_for_path(
    buy_prices: np.ndarray,
    sell_prices: np.ndarray,
    n_hours: int,
) -> Optional[Dict]:
    """Find the best RtE-corrected arbitrage spread for given buy/sell price series.

    spread = sell_avg − buy_avg / RTE   (per kWh-sold)

    Returns dict: buy_blocks, buy_avg, sell_blocks, sell_avg, spread.
    """
    buy_data  = _precompute_all_window_avgs(buy_prices,  n_hours)
    sell_data = _precompute_all_window_avgs(sell_prices, n_hours)

    if len(buy_data['avgs']) == 0 or len(sell_data['avgs']) == 0:
        return None

    best_spread = -np.inf
    best_result = None

    for i in range(len(buy_data['avgs'])):
        buy_last  = buy_data['last_blocks'][i]
        buy_avg   = buy_data['avgs'][i]

        # Filter valid sell windows: must start >= buy_last + 2 (1 block cooling)
        valid_mask = sell_data['first_blocks'] >= buy_last + 2
        if not valid_mask.any():
            continue

        # Compute RtE-corrected spread for all valid sell windows (vectorized)
        sell_avgs_valid = sell_data['avgs'][valid_mask]
        spreads = sell_avgs_valid - buy_avg / RTE

        best_idx_in_valid = int(np.argmax(spreads))
        best_spread_here = float(spreads[best_idx_in_valid])

        if best_spread_here > best_spread:
            # Find the corresponding sell window index in the full array
            valid_indices = np.where(valid_mask)[0]
            sell_idx = int(valid_indices[best_idx_in_valid])

            best_spread = best_spread_here
            best_result = {
                'buy_blocks':  buy_data['block_indices'][i],
                'buy_avg':     float(buy_avg),
                'sell_blocks': sell_data['block_indices'][sell_idx],
                'sell_avg':    float(sell_data['avgs'][sell_idx]),
                'spread':      float(best_spread_here),
            }

    return best_result


def compute_multi_hour_arbitrage(blocks_df_for_day: pd.DataFrame) -> Dict:
    """Compute multi-hour arbitrage across 4 durations × 3 paths for one day.
    Stores raw float precision; rounding happens at display layer."""
    if len(blocks_df_for_day) != N_BLOCKS_PER_DAY:
        return {}

    sorted_df = blocks_df_for_day.sort_values(['Hour']).reset_index(drop=True)
    dam_prices  = sorted_df['DAM_MCP'].values
    gdam_prices = sorted_df['GDAM_MCP'].values

    result = {}
    for n_h in DURATIONS_HOURS:
        dam_internal  = _best_arbitrage_for_path(dam_prices,  dam_prices,  n_h)
        gdam_internal = _best_arbitrage_for_path(gdam_prices, gdam_prices, n_h)
        cross         = _best_arbitrage_for_path(gdam_prices, dam_prices,  n_h)

        for path_name, path_result in [('dam', dam_internal), ('gdam', gdam_internal), ('cross', cross)]:
            if path_result:
                result[f'arb_{n_h}h_{path_name}_spread']      = path_result['spread']
                result[f'arb_{n_h}h_{path_name}_buy_avg']     = path_result['buy_avg']
                result[f'arb_{n_h}h_{path_name}_buy_blocks']  = path_result['buy_blocks']
                result[f'arb_{n_h}h_{path_name}_sell_avg']    = path_result['sell_avg']
                result[f'arb_{n_h}h_{path_name}_sell_blocks'] = path_result['sell_blocks']
            else:
                result[f'arb_{n_h}h_{path_name}_spread']      = None
                result[f'arb_{n_h}h_{path_name}_buy_avg']     = None
                result[f'arb_{n_h}h_{path_name}_buy_blocks']  = None
                result[f'arb_{n_h}h_{path_name}_sell_avg']    = None
                result[f'arb_{n_h}h_{path_name}_sell_blocks'] = None

        # Best of 3 paths
        candidates = []
        if dam_internal:  candidates.append(('DAM-only',  dam_internal))
        if gdam_internal: candidates.append(('GDAM-only', gdam_internal))
        if cross:         candidates.append(('Cross',     cross))

        if candidates:
            best_path_name, best_result = max(candidates, key=lambda x: x[1]['spread'])
            result[f'arb_{n_h}h_best_path']        = best_path_name
            result[f'arb_{n_h}h_best_spread']      = best_result['spread']
            result[f'arb_{n_h}h_best_buy_avg']     = best_result['buy_avg']
            result[f'arb_{n_h}h_best_buy_blocks']  = best_result['buy_blocks']
            result[f'arb_{n_h}h_best_sell_avg']    = best_result['sell_avg']
            result[f'arb_{n_h}h_best_sell_blocks'] = best_result['sell_blocks']
        else:
            result[f'arb_{n_h}h_best_path']        = None
            result[f'arb_{n_h}h_best_spread']      = None
            result[f'arb_{n_h}h_best_buy_avg']     = None
            result[f'arb_{n_h}h_best_buy_blocks']  = None
            result[f'arb_{n_h}h_best_sell_avg']    = None
            result[f'arb_{n_h}h_best_sell_blocks'] = None

    return result


# ============================================================
# BATCH PROCESSING
# ============================================================
def compute_for_all_days(df_blocks: pd.DataFrame, verbose: bool = True) -> pd.DataFrame:
    """Compute multi-hour arbitrage for every date in df_blocks."""
    rows = []
    dates = sorted(df_blocks['Date'].unique())
    total = len(dates)

    for i, d in enumerate(dates):
        day_blocks = df_blocks[df_blocks['Date'] == d]
        if len(day_blocks) != N_BLOCKS_PER_DAY:
            if verbose:
                print(f"  ⚠️ Skipping {pd.Timestamp(d).date()}: {len(day_blocks)} blocks (expected 96)")
            continue
        row = compute_multi_hour_arbitrage(day_blocks)
        row['date'] = pd.Timestamp(d)
        rows.append(row)
        if verbose and (i + 1) % 50 == 0:
            print(f"  Processed {i+1}/{total} days...")

    out = pd.DataFrame(rows).set_index('date')
    if verbose:
        print(f"  ✅ Done. {len(out)} days computed, {len(out.columns)} columns each.")
    return out


# ============================================================
# HELPERS — block label formatting
# ============================================================
def block_index_to_time_label(idx: int) -> str:
    """Convert block index (0-95) to time label '12:00 - 12:15'."""
    h = idx // 4
    q = idx % 4
    start_min = q * 15
    end_h = h if q < 3 else h + 1
    end_min = (q + 1) * 15 % 60
    return f"{h:02d}:{start_min:02d} - {end_h:02d}:{end_min:02d}"


def block_indices_to_compact_label(indices) -> str:
    """Convert list of block indices to compact time-range label.
    e.g. [12, 13, 14, 15] → '03:00-04:00'"""
    if indices is None:
        return "—"
    if isinstance(indices, np.ndarray):
        indices = indices.tolist()
    if not indices or len(indices) == 0:
        return "—"

    groups = []
    current_group = [indices[0]]
    for i in indices[1:]:
        if i == current_group[-1] + 1:
            current_group.append(i)
        else:
            groups.append(current_group)
            current_group = [i]
    groups.append(current_group)

    labels = []
    for g in groups:
        start_label = block_index_to_time_label(g[0])
        end_label   = block_index_to_time_label(g[-1])
        start_time = start_label.split(' - ')[0]
        end_time   = end_label.split(' - ')[1]
        labels.append(f"{start_time}-{end_time}")
    return ", ".join(labels)


# ============================================================
# RTE caveat for UI display
# ============================================================
def rte_caveat_text(include_formula: bool = False) -> str:
    """Return human-readable RtE caveat string for UI."""
    pct = int(round(RTE * 100))
    base = f"BESS RtE assumed at {pct}%"
    if include_formula:
        base += " · Spread = sell_avg − buy_avg / RtE (₹ per kWh sold)"
    return base