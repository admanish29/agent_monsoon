"""
weekly.py — Weekly Brief metrics extractor + 4 chart functions + narrative.

v1.6: Cross-Market table now uses RtE-corrected multi-hour arbitrage (2h + 4h best days).
      Legacy single-block arbitrage references removed.
"""

import matplotlib.pyplot as plt
import io
import base64
import numpy as np
import pandas as pd
from datetime import timedelta
import re

from src.tools import df_blocks, df_daily
from src.agent import get_client
from src.arbitrage import block_indices_to_compact_label, rte_caveat_text


SOLAR_HOURS = {11, 12, 13, 14, 15}


def _fig_to_base64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format='png', bbox_inches='tight', dpi=150, facecolor='white')
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode('utf-8')


# ============================================================
# Main metrics extractor
# ============================================================
def get_week_metrics(week_start_date, df_weekly):
    """Extract all metrics for the Mon-Sun week starting on week_start_date.
    Returns ~40 keys covering weekly aggregates + day-level highlights + RtE-corrected best-arb days."""

    week_start = pd.to_datetime(week_start_date)
    week_row = df_weekly[df_weekly['week_start'] == week_start.date()]
    if week_row.empty:
        raise ValueError(f"No data for week starting {week_start.date()}")
    w = week_row.iloc[0]

    week_end = week_start + pd.Timedelta(days=6)

    # Pull 7 days of daily data + ~672 blocks
    week_daily = df_daily[
        (df_daily['date'] >= week_start) & (df_daily['date'] <= week_end)
    ].sort_values('date').copy()
    week_blocks = df_blocks[
        (df_blocks['Date'] >= week_start) & (df_blocks['Date'] <= week_end)
    ].sort_values(['Date', 'Hour']).copy()

    week_daily['dow'] = week_daily['date'].dt.strftime('%a %d')

    # RMTI best/worst
    worst_rmti_idx = week_daily['rmti_composite'].idxmax() if week_daily['rmti_composite'].notna().any() else None
    best_rmti_idx  = week_daily['rmti_composite'].idxmin() if week_daily['rmti_composite'].notna().any() else None

    # Top 3 anomalies
    week_blocks['abs_max_z'] = week_blocks[['DAM_z_score', 'GDAM_z_score']].abs().max(axis=1)
    top_anomalies = week_blocks.nlargest(3, 'abs_max_z')[
        ['Date', 'Time Block', 'DAM_MCP', 'GDAM_MCP', 'DAM_z_score', 'GDAM_z_score',
         'DAM_anomaly_direction', 'GDAM_anomaly_direction']
    ].to_dict('records')

    # Prior-week comparison
    prior_week_start = week_start - pd.Timedelta(days=7)
    prior_week_row = df_weekly[df_weekly['week_start'] == prior_week_start.date()]
    if not prior_week_row.empty:
        prior_w = prior_week_row.iloc[0]
        rmti_delta = round(float(w['rmti_avg']) - float(prior_w['rmti_avg']), 1) if pd.notna(w['rmti_avg']) and pd.notna(prior_w['rmti_avg']) else None
        dam_delta  = round(float(w['dam_avg_mcp']) - float(prior_w['dam_avg_mcp']), 2)
    else:
        rmti_delta = dam_delta = None

    # ──────────────────────────────────────────
    # NEW: Best 2h and 4h arbitrage days (RtE-corrected, from df_daily)
    # ──────────────────────────────────────────
    valid_2h = week_daily.dropna(subset=['arb_2h_best_spread'])
    valid_4h = week_daily.dropna(subset=['arb_4h_best_spread'])

    if not valid_2h.empty:
        b2 = valid_2h.loc[valid_2h['arb_2h_best_spread'].idxmax()]
        best_2h = {
            'day':         b2['date'].date(),
            'spread':      float(b2['arb_2h_best_spread']),
            'path':        b2['arb_2h_best_path'],
            'buy_avg':     float(b2['arb_2h_best_buy_avg']),
            'sell_avg':    float(b2['arb_2h_best_sell_avg']),
            'buy_blocks':  b2['arb_2h_best_buy_blocks'],
            'sell_blocks': b2['arb_2h_best_sell_blocks'],
        }
    else:
        best_2h = None

    if not valid_4h.empty:
        b4 = valid_4h.loc[valid_4h['arb_4h_best_spread'].idxmax()]
        best_4h = {
            'day':         b4['date'].date(),
            'spread':      float(b4['arb_4h_best_spread']),
            'path':        b4['arb_4h_best_path'],
            'buy_avg':     float(b4['arb_4h_best_buy_avg']),
            'sell_avg':    float(b4['arb_4h_best_sell_avg']),
            'buy_blocks':  b4['arb_4h_best_buy_blocks'],
            'sell_blocks': b4['arb_4h_best_sell_blocks'],
        }
    else:
        best_4h = None

    return {
        # Identifiers
        'week_start':    w['week_start'],
        'week_end':      w['week_end'],
        'iso_year':      int(w['iso_year']),
        'iso_week':      int(w['iso_week']),
        'days_covered':  int(w['days_covered']),

        # Headline aggregates
        'dam_avg_mcp':              w['dam_avg_mcp'],
        'gdam_avg_mcp':             w['gdam_avg_mcp'],
        'dam_weekly_peak':          w['dam_weekly_peak'],
        'dam_peak_date':            w['dam_peak_date'],
        'dam_peak_block':           w['dam_peak_block'],
        'dam_weekly_trough':        w['dam_weekly_trough'],
        'dam_trough_date':          w['dam_trough_date'],
        'dam_trough_block':         w['dam_trough_block'],
        'gdam_weekly_peak':         w['gdam_weekly_peak'],
        'gdam_peak_date':           w['gdam_peak_date'],
        'gdam_peak_block':          w['gdam_peak_block'],
        'gdam_weekly_trough':       w['gdam_weekly_trough'],

        'dam_avg_intraday_spread':  w['dam_avg_intraday_spread'],
        'gdam_avg_intraday_spread': w['gdam_avg_intraday_spread'],

        # RMTI
        'rmti_avg':           w['rmti_avg'],
        'rmti_max':           w['rmti_max'],
        'rmti_max_day':       w['rmti_max_day'],
        'rmti_min':           w['rmti_min'],
        'rmti_min_day':       w['rmti_min_day'],
        'record_days_count':  int(w['record_days_count']),

        # Cross-market
        'avg_dam_gdam_premium':  w['avg_dam_gdam_premium'],
        'stressed_blocks_total': int(w['stressed_blocks_total']),

        # NEW: Best 2h / 4h arbitrage days
        'best_2h_arb': best_2h,
        'best_4h_arb': best_4h,

        # Anomalies
        'anomaly_blocks_count': int(w['anomaly_blocks_count']),
        'anomaly_high_count':   int(w['anomaly_high_count']),
        'anomaly_low_count':    int(w['anomaly_low_count']),

        # Curtailment
        'solar_curtail_avg':    w['solar_curtail_avg'],
        'nonsolar_curtail_avg': w['nonsolar_curtail_avg'],
        'hydro_curtail_avg':    w['hydro_curtail_avg'],

        # Highlights
        'worst_rmti_day': week_daily.loc[worst_rmti_idx, 'date'].date() if worst_rmti_idx is not None else None,
        'best_rmti_day':  week_daily.loc[best_rmti_idx, 'date'].date()  if best_rmti_idx is not None else None,

        # Notable anomalies
        'top_anomalies': top_anomalies,

        # Daily series
        'daily_series': week_daily[[
            'date', 'dow', 'dam_avg_mcp', 'gdam_avg_mcp',
            'dam_spread', 'gdam_spread', 'rmti_composite',
            'stressed_blocks'
        ]].to_dict('records'),

        # Prior-week deltas
        'rmti_delta_vs_prior_week': rmti_delta,
        'dam_delta_vs_prior_week':  dam_delta,
    }


# ============================================================
# CHARTS
# ============================================================
def chart_weekly_mcp_timeline(week_blocks):
    fig, ax = plt.subplots(figsize=(10, 3.5))
    week_blocks_sorted = week_blocks.sort_values(['Date', 'Hour']).reset_index(drop=True)
    x = range(len(week_blocks_sorted))

    ax.plot(x, week_blocks_sorted['DAM_MCP'],  color='#1F3864', linewidth=1.2, label='DAM', alpha=0.9)
    ax.plot(x, week_blocks_sorted['GDAM_MCP'], color='#2E8B57', linewidth=1.2, label='GDAM', alpha=0.9)

    n_blocks_per_day = 96
    day_starts = list(range(0, len(week_blocks_sorted), n_blocks_per_day))
    for ds in day_starts[1:]:
        ax.axvline(ds, color='gray', linestyle=':', alpha=0.4, linewidth=0.8)

    unique_dates = sorted(week_blocks_sorted['Date'].unique())
    day_label_positions = [(i * n_blocks_per_day) + (n_blocks_per_day // 2) for i in range(len(unique_dates))]
    day_labels = [pd.Timestamp(d).strftime('%a %d') for d in unique_dates]
    ax.set_xticks(day_label_positions)
    ax.set_xticklabels(day_labels, fontsize=9)

    ax.set_title('Weekly Intraday MCP — DAM vs GDAM (₹/kWh)', fontsize=12, fontweight='bold')
    ax.set_ylabel('₹/kWh', fontsize=9)
    ax.legend(loc='upper left', fontsize=9, framealpha=0.9)
    ax.grid(True, alpha=0.3, axis='y')
    return _fig_to_base64(fig)


def chart_weekly_rmti_evolution(week_daily):
    fig, ax = plt.subplots(figsize=(10, 3.2))
    week_daily_sorted = week_daily.sort_values('date').reset_index(drop=True)
    x_labels = [d.strftime('%a %d') for d in pd.to_datetime(week_daily_sorted['date'])]
    rmti_vals = week_daily_sorted['rmti_composite']

    bars = ax.bar(x_labels, rmti_vals, color='#1F3864', alpha=0.85, edgecolor='#0F1D38', linewidth=0.5)

    if 'rmti_is_record' in week_daily_sorted.columns:
        for bar, is_rec in zip(bars, week_daily_sorted['rmti_is_record']):
            if is_rec:
                bar.set_color('#D7263D')
                bar.set_alpha(0.9)

    for bar, val in zip(bars, rmti_vals):
        if pd.notna(val):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1.5,
                    f'{val:.0f}', ha='center', va='bottom', fontsize=9, fontweight='bold', color='#1F3864')

    ax.axhline(50, color='gray', linestyle=':', alpha=0.5, label='Moderate (50)')
    ax.axhline(75, color='orange', linestyle=':', alpha=0.5, label='Tight (75)')
    ax.set_title('RMTI Evolution Across the Week (red = new 30-day record)', fontsize=12, fontweight='bold')
    ax.set_ylabel('RMTI (0-100)', fontsize=9)
    max_y = max(rmti_vals.max() if rmti_vals.notna().any() else 100, 100)
    ax.set_ylim(0, max_y * 1.15)
    ax.legend(loc='upper right', fontsize=8, framealpha=0.9)
    ax.grid(True, alpha=0.3, axis='y')
    return _fig_to_base64(fig)


def chart_weekly_spread_lines(week_daily):
    fig, ax = plt.subplots(figsize=(10, 3.2))
    week_daily_sorted = week_daily.sort_values('date').reset_index(drop=True)
    x_labels = [d.strftime('%a %d') for d in pd.to_datetime(week_daily_sorted['date'])]

    ax.plot(x_labels, week_daily_sorted['dam_spread'],  color='#1F3864', linewidth=2.2,
            marker='o', markersize=7, label='DAM intraday spread')
    ax.plot(x_labels, week_daily_sorted['gdam_spread'], color='#2E8B57', linewidth=2.2,
            marker='s', markersize=7, label='GDAM intraday spread')

    for i, val in enumerate(week_daily_sorted['dam_spread']):
        if pd.notna(val):
            ax.annotate(f'₹{val:.1f}', (i, val), textcoords="offset points", xytext=(0, 8),
                        ha='center', fontsize=8, color='#1F3864', fontweight='bold')
    for i, val in enumerate(week_daily_sorted['gdam_spread']):
        if pd.notna(val):
            ax.annotate(f'₹{val:.1f}', (i, val), textcoords="offset points", xytext=(0, -12),
                        ha='center', fontsize=8, color='#2E8B57', fontweight='bold')

    ax.set_title('Intraday Volatility (Peak − Trough) Evolution Across the Week', fontsize=12, fontweight='bold')
    ax.set_ylabel('Spread (₹/kWh)', fontsize=9)
    ax.legend(loc='best', fontsize=9, framealpha=0.9)
    ax.grid(True, alpha=0.3, axis='y')
    return _fig_to_base64(fig)


def chart_weekly_hour_heatmap(week_blocks):
    fig, ax = plt.subplots(figsize=(10, 3.5))
    week_blocks = week_blocks.copy()
    pivot = week_blocks.pivot_table(index='Date', columns='Hour', values='DAM_GDAM_Premium', aggfunc='mean')
    pivot = pivot.sort_index()
    vmax = max(abs(pivot.values.min()), abs(pivot.values.max()))

    im = ax.imshow(pivot.values, aspect='auto', cmap='RdYlGn', vmin=-vmax, vmax=vmax, interpolation='nearest')

    n_rows, n_cols = pivot.shape
    ax.set_xticks([i - 0.5 for i in range(1, n_cols)], minor=True)
    ax.set_yticks([i - 0.5 for i in range(1, n_rows)], minor=True)
    ax.grid(which='minor', color='white', linewidth=0.6)
    ax.tick_params(which='minor', length=0)

    y_labels = [pd.Timestamp(d).strftime('%a %d') for d in pivot.index]
    ax.set_yticks(range(len(y_labels)))
    ax.set_yticklabels(y_labels, fontsize=9)

    ax.set_xticks([0, 3, 6, 9, 12, 15, 18, 21])
    ax.set_xticklabels(['00:00', '03:00', '06:00', '09:00', '12:00', '15:00', '18:00', '21:00'], fontsize=8)
    ax.set_title('DAM − GDAM Premium by Hour-of-Day (red = GDAM costlier, green = solar discount)',
                 fontsize=11, fontweight='bold')

    cbar = plt.colorbar(im, ax=ax, shrink=0.85)
    cbar.set_label('Premium (₹/kWh)', fontsize=8)
    cbar.ax.tick_params(labelsize=7)

    buf = io.BytesIO()
    fig.savefig(buf, format='png', bbox_inches='tight', dpi=300, facecolor='white')
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode('utf-8')


# ============================================================
# NARRATIVE
# ============================================================
def build_weekly_prompt(metrics):
    daily_lines = []
    for d in metrics['daily_series']:
        rmti = d.get('rmti_composite')
        rmti_str = f"{rmti:.1f}" if pd.notna(rmti) else "N/A"
        daily_lines.append(
            f"  - {d['dow']}: DAM ₹{d['dam_avg_mcp']:.2f}/kWh, "
            f"GDAM ₹{d['gdam_avg_mcp']:.2f}/kWh, "
            f"intraday spread DAM ₹{d['dam_spread']:.2f} GDAM ₹{d['gdam_spread']:.2f}, "
            f"RMTI {rmti_str}, "
            f"{int(d['stressed_blocks'])}/96 stressed blocks"
        )
    daily_series_text = "\n".join(daily_lines)

    anomalies_text = "\n  Top 3 anomalous blocks this week (Metric 4):\n"
    for a in metrics['top_anomalies']:
        date_str = pd.Timestamp(a['Date']).strftime('%a %d')
        anomalies_text += (
            f"    - {date_str} {a['Time Block']}: "
            f"DAM ₹{a['DAM_MCP']:.2f}/kWh (z={a['DAM_z_score']:.2f}, {a['DAM_anomaly_direction']}), "
            f"GDAM ₹{a['GDAM_MCP']:.2f}/kWh (z={a['GDAM_z_score']:.2f}, {a['GDAM_anomaly_direction']})\n"
        )

    if metrics['rmti_delta_vs_prior_week'] is not None:
        wow_text = (
            f"WEEK-OVER-WEEK CHANGES (vs prior week):\n"
            f"  - RMTI delta: {metrics['rmti_delta_vs_prior_week']:+.1f} points\n"
            f"  - DAM avg MCP delta: ₹{metrics['dam_delta_vs_prior_week']:+.2f}/kWh\n"
        )
    else:
        wow_text = "WEEK-OVER-WEEK CHANGES: No prior-week data available.\n"

    # Arbitrage context for prompt
    arb_text = ""
    if metrics.get('best_2h_arb'):
        b2 = metrics['best_2h_arb']
        arb_text += f"  - Best 2h arbitrage: ₹{b2['spread']:.2f}/kWh sold on {b2['day']} via {b2['path']}\n"
    if metrics.get('best_4h_arb'):
        b4 = metrics['best_4h_arb']
        arb_text += f"  - Best 4h arbitrage: ₹{b4['spread']:.2f}/kWh sold on {b4['day']} via {b4['path']}\n"

    prompt = f"""You are a power-market analyst writing a WEEKLY brief for an Indian renewable-energy strategy professional. Markets: IEX day-ahead (DAM) and green day-ahead (GDAM).

**CRITICAL UNITS RULE:** All prices in ₹/kWh. Always use "₹/kWh" — NEVER use "paise".

**HIGHLIGHTING RULE:** In Section 4 (Notable Days & Blocks), wrap day names in <span style="color:#1F3864;font-weight:bold;">...</span>. For anomalous block TIMES use <span style="color:#D7263D;font-weight:bold;">...</span>.

WEEK: {metrics['week_start']} (Mon) to {metrics['week_end']} (Sun) — ISO {metrics['iso_year']}-W{metrics['iso_week']}

PRICING (₹/kWh):
- DAM weekly avg: ₹{metrics['dam_avg_mcp']}
- DAM weekly peak: ₹{metrics['dam_weekly_peak']} on {metrics['dam_peak_date']} at {metrics['dam_peak_block']}
- DAM weekly trough: ₹{metrics['dam_weekly_trough']} on {metrics['dam_trough_date']}
- GDAM weekly avg: ₹{metrics['gdam_avg_mcp']}
- GDAM weekly peak: ₹{metrics['gdam_weekly_peak']} on {metrics['gdam_peak_date']}

INTRADAY VOLATILITY:
- DAM avg intraday spread: ₹{metrics['dam_avg_intraday_spread']}/kWh
- GDAM avg intraday spread: ₹{metrics['gdam_avg_intraday_spread']}/kWh

CROSS-MARKET:
- Avg DAM−GDAM premium: ₹{metrics['avg_dam_gdam_premium']}/kWh
- Stressed blocks this week: {metrics['stressed_blocks_total']}/{metrics['days_covered']*96}

RMTI:
- Weekly avg: {metrics['rmti_avg']}
- Worst day: {metrics['rmti_max']} on {metrics['rmti_max_day']}
- Record-setting days: {metrics['record_days_count']}

BATTERY ARBITRAGE (RtE-corrected, per kWh sold):
{arb_text}

ANOMALIES:
- Total anomalous blocks: {metrics['anomaly_blocks_count']}
- HIGH: {metrics['anomaly_high_count']}, LOW: {metrics['anomaly_low_count']}
{anomalies_text}

CURTAILMENT (GDAM):
- Solar: {metrics['solar_curtail_avg']}%, Non-Solar: {metrics['nonsolar_curtail_avg']}%, Hydro: {metrics['hydro_curtail_avg']}%

DAILY SERIES (Mon → Sun):
{daily_series_text}

{wow_text}

INSTRUCTIONS:
Write a concise WEEKLY brief in 5 markdown sections (## headings). ~280-320 words.

## Headline
ONE sharp sentence with the key number defining the week.

## Weekly Dynamics
Synthesize price levels, cross-market premium, intraday spread evolution.

## RMTI Verdict
Interpret weekly avg + worst day + record-setting days.

## Notable Days & Blocks
2-3 bullets. Day-name spans (blue-bold) + anomalous block-time spans (red-bold).

## Curtailment & Anomalies
ONE paragraph. Interpret HIGH vs LOW anomaly balance.

TONE: Analytical, sharp. Use ₹/kWh consistently."""
    return prompt


def generate_weekly_brief(week_start_date, df_weekly):
    """Generate the full HTML weekly brief. Returns (html_string, info_dict)."""

    metrics = get_week_metrics(week_start_date, df_weekly)

    week_start = pd.to_datetime(metrics['week_start'])
    week_end   = pd.to_datetime(metrics['week_end'])
    week_blocks_data = df_blocks[
        (df_blocks['Date'] >= week_start) & (df_blocks['Date'] <= week_end)
    ]
    week_daily_data = df_daily[
        (df_daily['date'] >= week_start) & (df_daily['date'] <= week_end)
    ]

    # Charts
    chart1 = chart_weekly_mcp_timeline(week_blocks_data)
    chart2 = chart_weekly_rmti_evolution(week_daily_data)
    chart3 = chart_weekly_spread_lines(week_daily_data)
    chart4 = chart_weekly_hour_heatmap(week_blocks_data)

    # Narrative
    prompt = build_weekly_prompt(metrics)
    client = get_client()
    response = client.messages.create(
        model='claude-haiku-4-5-20251001',
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )
    narrative = response.content[0].text
    tokens_in, tokens_out = response.usage.input_tokens, response.usage.output_tokens
    cost_usd = (tokens_in * 1.0 + tokens_out * 5.0) / 1_000_000

    # Markdown → HTML
    narrative_html = narrative
    narrative_html = re.sub(r'^## (.+)$', r'<h3 style="color:#1F3864;margin-top:18px;margin-bottom:8px;">\1</h3>', narrative_html, flags=re.MULTILINE)
    narrative_html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', narrative_html)
    narrative_html = re.sub(r'^- (.+)$', r'<li style="margin-left:18px;">\1</li>', narrative_html, flags=re.MULTILINE)
    narrative_html = narrative_html.replace('\n\n', '</p><p style="margin:6px 0;">')
    narrative_html = '<p style="margin:6px 0;">' + narrative_html + '</p>'

    # HEADLINE TABLE
    main_table = f"""
    <table style="width:100%;border-collapse:collapse;font-size:14px;margin:10px 0;">
      <tr style="background:#1F3864;color:white;">
        <th style="padding:8px;text-align:left;">Weekly Metric</th>
        <th style="padding:8px;text-align:right;">DAM</th>
        <th style="padding:8px;text-align:right;">GDAM</th>
      </tr>
      <tr><td style="padding:6px 8px;border-bottom:1px solid #eee;">Avg MCP (₹/kWh)</td>
          <td style="padding:6px 8px;text-align:right;border-bottom:1px solid #eee;">{metrics['dam_avg_mcp']}</td>
          <td style="padding:6px 8px;text-align:right;border-bottom:1px solid #eee;">{metrics['gdam_avg_mcp']}</td></tr>
      <tr><td style="padding:6px 8px;border-bottom:1px solid #eee;">Weekly Peak (₹/kWh)</td>
          <td style="padding:6px 8px;text-align:right;border-bottom:1px solid #eee;">{metrics['dam_weekly_peak']} <span style="font-size:11px;color:#888;">({metrics['dam_peak_date']} {metrics['dam_peak_block']})</span></td>
          <td style="padding:6px 8px;text-align:right;border-bottom:1px solid #eee;">{metrics['gdam_weekly_peak']} <span style="font-size:11px;color:#888;">({metrics['gdam_peak_date']} {metrics['gdam_peak_block']})</span></td></tr>
      <tr><td style="padding:6px 8px;border-bottom:1px solid #eee;">Weekly Trough (₹/kWh)</td>
          <td style="padding:6px 8px;text-align:right;border-bottom:1px solid #eee;">{metrics['dam_weekly_trough']} <span style="font-size:11px;color:#888;">({metrics['dam_trough_date']})</span></td>
          <td style="padding:6px 8px;text-align:right;border-bottom:1px solid #eee;">{metrics['gdam_weekly_trough']}</td></tr>
      <tr><td style="padding:6px 8px;">Avg Intraday Spread (₹/kWh)</td>
          <td style="padding:6px 8px;text-align:right;">{metrics['dam_avg_intraday_spread']}</td>
          <td style="padding:6px 8px;text-align:right;">{metrics['gdam_avg_intraday_spread']}</td></tr>
    </table>
    """

    # WoW deltas
    if metrics['rmti_delta_vs_prior_week'] is not None:
        rmti_d = metrics['rmti_delta_vs_prior_week']
        dam_d  = metrics['dam_delta_vs_prior_week']
        def color_for(v, reverse=False):
            if v == 0: return '#888'
            if reverse:
                return '#2E8B57' if v > 0 else '#D7263D'
            return '#D7263D' if v > 0 else '#2E8B57'
        wow_html = f"""
        <div style="display:flex;gap:14px;margin:14px 0;">
          <div style="flex:1;padding:10px;background:#fafafa;border-left:3px solid {color_for(rmti_d)};border-radius:4px;">
            <div style="font-size:11px;color:#888;text-transform:uppercase;">RMTI vs Prior Week</div>
            <div style="font-size:20px;font-weight:bold;color:{color_for(rmti_d)};">{rmti_d:+.1f}</div>
          </div>
          <div style="flex:1;padding:10px;background:#fafafa;border-left:3px solid {color_for(dam_d)};border-radius:4px;">
            <div style="font-size:11px;color:#888;text-transform:uppercase;">DAM MCP vs Prior Week</div>
            <div style="font-size:20px;font-weight:bold;color:{color_for(dam_d)};">₹{dam_d:+.2f}/kWh</div>
          </div>
        </div>
        """
    else:
        wow_html = ""

    # Cross-market table with new 2h + 4h best arbitrage rows
    rmti_avg_str = f"{metrics['rmti_avg']:.1f}/100" if metrics['rmti_avg'] is not None else "N/A"
    rmti_max_str = f"{metrics['rmti_max']:.1f}" if metrics['rmti_max'] is not None else "N/A"
    record_badge = f' 🔴 {metrics["record_days_count"]} record-setting day(s)' if metrics['record_days_count'] > 0 else ''

    if metrics.get('best_2h_arb'):
        b2 = metrics['best_2h_arb']
        row_2h = f"""<tr><td style="padding:8px;border-bottom:1px solid #eee;font-weight:bold;">Best 2-Hour Arbitrage Day</td>
          <td style="padding:8px;border-bottom:1px solid #eee;">
            ₹{b2['spread']:.2f}/kWh sold on {b2['day']} via <strong>{b2['path']}</strong><br/>
            <span style="font-size:12px;color:#666;">Buy ₹{b2['buy_avg']:.2f} ({block_indices_to_compact_label(b2['buy_blocks'])}) → Sell ₹{b2['sell_avg']:.2f} ({block_indices_to_compact_label(b2['sell_blocks'])})</span>
          </td></tr>"""
    else:
        row_2h = ""

    if metrics.get('best_4h_arb'):
        b4 = metrics['best_4h_arb']
        row_4h = f"""<tr><td style="padding:8px;border-bottom:1px solid #eee;font-weight:bold;">Best 4-Hour Arbitrage Day</td>
          <td style="padding:8px;border-bottom:1px solid #eee;">
            ₹{b4['spread']:.2f}/kWh sold on {b4['day']} via <strong>{b4['path']}</strong><br/>
            <span style="font-size:12px;color:#666;">Buy ₹{b4['buy_avg']:.2f} ({block_indices_to_compact_label(b4['buy_blocks'])}) → Sell ₹{b4['sell_avg']:.2f} ({block_indices_to_compact_label(b4['sell_blocks'])})</span>
          </td></tr>"""
    else:
        row_4h = ""

    cross_table = f"""
    <table style="width:100%;border-collapse:collapse;font-size:14px;margin:10px 0;">
      <tr style="background:#4A5568;color:white;">
        <th style="padding:8px;text-align:left;">Cross-Market Indicator</th>
        <th style="padding:8px;text-align:left;">Value</th>
      </tr>
      <tr><td style="padding:8px;border-bottom:1px solid #eee;font-weight:bold;">RMTI Composite (avg / max)</td>
          <td style="padding:8px;border-bottom:1px solid #eee;">{rmti_avg_str} avg &nbsp;·&nbsp; max {rmti_max_str} on {metrics['rmti_max_day']}{record_badge}</td></tr>
      <tr><td style="padding:8px;border-bottom:1px solid #eee;">Avg DAM−GDAM Premium</td>
          <td style="padding:8px;border-bottom:1px solid #eee;">₹{metrics['avg_dam_gdam_premium']}/kWh</td></tr>
      <tr><td style="padding:8px;border-bottom:1px solid #eee;">Stressed Blocks (GDAM &gt; DAM)</td>
          <td style="padding:8px;border-bottom:1px solid #eee;">{metrics['stressed_blocks_total']} / {metrics['days_covered']*96} ({100*metrics['stressed_blocks_total']/(metrics['days_covered']*96):.0f}%)</td></tr>
      {row_2h}
      {row_4h}
      <tr><td style="padding:8px;">Anomaly Blocks (Metric 4)</td>
          <td style="padding:8px;">{metrics['anomaly_blocks_count']} total &nbsp;·&nbsp; {metrics['anomaly_high_count']} HIGH spikes, {metrics['anomaly_low_count']} LOW crashes</td></tr>
    </table>
    <div style="font-size:11px;color:#888;font-style:italic;text-align:right;margin-top:-6px;margin-bottom:10px;">
      ({rte_caveat_text()})
    </div>
    """

    # Footnote
    footnote_html = """
    <div style="margin-top:18px;padding:12px;background:#FAFAFA;border-left:3px solid #1F3864;font-size:12px;color:#444;">
      <strong style="color:#1F3864;">📖 Weekly brief methodology</strong><br/>
      Aggregates 7 days of block-level IEX data (Mon-Sun ISO week). Charts show <strong>continuous intraday MCP</strong>, <strong>RMTI evolution</strong>, <strong>intraday spread trend</strong>, and a <strong>day × hour heatmap</strong> of DAM−GDAM premium.<br/><br/>
      <strong>RMTI</strong> = 0.4×BPC + 0.4×AGP + 0.2×PTC, normalized to 30-day rolling max.<br/>
      <strong>Record day</strong> = new 30-day RMTI high.<br/>
      <strong>Stressed block</strong> = GDAM_MCP > DAM_MCP.<br/>
      <strong>Anomaly</strong> = block where MCP deviated &gt;2σ from 30-day same-block baseline.<br/>
      <strong>Best 2h / 4h arbitrage</strong> = highest RtE-corrected spread (₹ per kWh sold) achievable on a single day in the week, using exhaustive search across DAM/GDAM/Cross paths.
    </div>
    """

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:900px;border:1px solid #ddd;padding:24px;border-radius:8px;background:white;">
      <h2 style="color:#1F3864;margin-top:0;border-bottom:2px solid #1F3864;padding-bottom:8px;">
        📆 IEX Weekly Brief — {metrics['week_start']} to {metrics['week_end']}
        <span style="font-size:14px;color:#888;font-weight:normal;">&nbsp;· ISO {metrics['iso_year']}-W{metrics['iso_week']}</span>
      </h2>

      {wow_html}

      <h4 style="color:#444;margin-bottom:5px;">Headline Metrics — Weekly Aggregates</h4>
      {main_table}

      <h4 style="color:#444;margin-top:18px;margin-bottom:5px;">Cross-Market Indicators</h4>
      {cross_table}

      <h4 style="color:#444;margin-top:18px;margin-bottom:5px;">Charts</h4>
      <img src="data:image/png;base64,{chart1}" style="width:100%;margin-bottom:8px;"/>
      <img src="data:image/png;base64,{chart2}" style="width:100%;margin-bottom:8px;"/>
      <img src="data:image/png;base64,{chart3}" style="width:100%;margin-bottom:8px;"/>
      <img src="data:image/png;base64,{chart4}" style="width:100%;margin-bottom:8px;"/>

      <h4 style="color:#444;margin-top:18px;margin-bottom:5px;">Analysis</h4>
      {narrative_html}

      {footnote_html}

      <div style="margin-top:18px;padding-top:8px;border-top:1px solid #eee;font-size:11px;color:#888;">
        Generated by Agent Monsoon · {tokens_in + tokens_out} tokens · ${cost_usd:.5f}
      </div>
    </div>
    """

    return html, {'tokens_in': tokens_in, 'tokens_out': tokens_out, 'cost_usd': cost_usd, 'metrics': metrics}