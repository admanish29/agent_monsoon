"""
brief.py — The daily brief generator.

v1.5: RtE-corrected arbitrage spread + caveat display + removed legacy single-block arbitrage rows.

Generates a styled HTML brief for any date in the dataset with:
  - Main DAM vs GDAM headline-metrics table
  - Cross-Market Indicators mini-table (RMTI only — legacy single-block arbitrage removed)
  - Multi-Hour Battery Arbitrage section (4 sub-tables, 1h/2h/3h/4h × 4 paths) with RtE caveat
  - 4 charts: intraday MCP, premium, RMTI gauge, source curtailment
  - Narrative (Claude-generated, 5 markdown sections)
  - Footnote with RMTI definitions
"""

import matplotlib.pyplot as plt
import io
import base64
import re

import pandas as pd
import streamlit as st

from src.tools import df_blocks, df_daily, df_gdam_hist
from src.agent import get_client
from src.arbitrage import block_indices_to_compact_label, rte_caveat_text


# Solar hours: 10:00 to 15:00 = Hours 11, 12, 13, 14, 15 (IEX 1-indexed)
SOLAR_HOURS = {11, 12, 13, 14, 15}


# ============================================================
# HELPER 1: Extract metrics for a given date
# ============================================================
def get_day_metrics(target_date):
    """Extract all metrics needed for the brief for one date.
    Returns a dict with ~40 keys covering daily aggregates + block-level summaries."""
    target = pd.to_datetime(target_date)

    daily_row = df_daily[df_daily['date'] == target]
    if daily_row.empty:
        raise ValueError(f"No data for {target.date()}")
    d = daily_row.iloc[0]

    blocks = df_blocks[df_blocks['Date'] == target].copy()
    if blocks.empty:
        raise ValueError(f"No block data for {target.date()}")

    # Peak/Trough time blocks
    dam_peak_block    = blocks.loc[blocks['DAM_MCP'].idxmax(),  'Time Block']
    dam_trough_block  = blocks.loc[blocks['DAM_MCP'].idxmin(),  'Time Block']
    gdam_peak_block   = blocks.loc[blocks['GDAM_MCP'].idxmax(), 'Time Block']
    gdam_trough_block = blocks.loc[blocks['GDAM_MCP'].idxmin(), 'Time Block']

    # GDAM source-wise curtailment
    g = df_gdam_hist[df_gdam_hist['Date'] == target]
    solar_curtail    = (g['Solar_Curtailment_MW'].sum()    / g['Solar MCV (MW)'].sum()    * 100) if g['Solar MCV (MW)'].sum() > 0    else 0
    nonsolar_curtail = (g['NonSolar_Curtailment_MW'].sum() / g['Non-Solar MCV (MW)'].sum() * 100) if g['Non-Solar MCV (MW)'].sum() > 0 else 0
    hydro_curtail    = (g['Hydro_Curtailment_MW'].sum()    / g['Hydro MCV (MW)'].sum()    * 100) if g['Hydro MCV (MW)'].sum() > 0    else 0

    # Solar-hour DFR + BCR (10:00-15:00, Hours 11-15)
    solar_blocks = blocks[blocks['Hour'].isin(SOLAR_HOURS)]
    dam_dfr_solar  = round(solar_blocks['DAM_Demand_Fulfillment_Pct'].mean(),  1)
    gdam_dfr_solar = round(solar_blocks['GDAM_Demand_Fulfillment_Pct'].mean(), 1)
    dam_bcr_solar  = round(solar_blocks['DAM_Bid_Coverage_Ratio'].mean(),      2)
    gdam_bcr_solar = round(solar_blocks['GDAM_Bid_Coverage_Ratio'].mean(),     2)

    # Anomalies
    dam_anomalies  = blocks[blocks['DAM_anomaly_flag']  == True]
    gdam_anomalies = blocks[blocks['GDAM_anomaly_flag'] == True]
    blocks['abs_max_z'] = blocks[['DAM_z_score', 'GDAM_z_score']].abs().max(axis=1)
    top_anomalies = blocks.nlargest(3, 'abs_max_z')[
        ['Time Block', 'DAM_MCP', 'GDAM_MCP', 'DAM_z_score', 'GDAM_z_score',
         'DAM_anomaly_direction', 'GDAM_anomaly_direction']
    ]

    # Seasonal context (same month last year)
    last_year_same_month = df_daily[
        (df_daily['date'].dt.year  == target.year - 1) &
        (df_daily['date'].dt.month == target.month)
    ]
    seasonal_avg_rmti = last_year_same_month['rmti_composite'].mean() if not last_year_same_month.empty else None

    # Fiscal calendar proximity
    fiscal_flag = None
    if target.month == 3 and target.day >= 1:
        fiscal_flag = f"{31 - target.day} days from FY-end (31 Mar)"
    elif target.month == 4 and target.day <= 30:
        fiscal_flag = f"{target.day} days into new fiscal year"
    elif target.month == 9 and target.day >= 1:
        fiscal_flag = f"{30 - target.day} days from H1 close (30 Sep)"
    elif target.month == 10 and target.day <= 7:
        fiscal_flag = f"{target.day} days into H2 (post 30 Sep)"

    return {
        'date': target.date(),
        'day_of_week': target.strftime('%A'),
        'is_sunday': target.weekday() == 6,

        # Daily price metrics
        'dam_avg_mcp':       round(d['dam_avg_mcp'], 2),
        'dam_peak_mcp':      round(d['dam_peak_mcp'], 2),
        'dam_peak_block':    dam_peak_block,
        'dam_trough_mcp':    round(d['dam_trough_mcp'], 2),
        'dam_trough_block':  dam_trough_block,
        'dam_spread':        round(d['dam_spread'], 2),
        'gdam_avg_mcp':      round(d['gdam_avg_mcp'], 2),
        'gdam_peak_mcp':     round(d['gdam_peak_mcp'], 2),
        'gdam_peak_block':   gdam_peak_block,
        'gdam_trough_mcp':   round(d['gdam_trough_mcp'], 2),
        'gdam_trough_block': gdam_trough_block,
        'gdam_spread':       round(d['gdam_spread'], 2),

        # Cross-market (premium + stress)
        'avg_premium':     round(d['avg_dam_gdam_premium'], 2),
        'stressed_blocks': int(d['stressed_blocks']),

        # RMTI
        'rmti_bpc':       round(d['bpc_pct'], 1),
        'rmti_agp':       round(d['agp_rs_kwh'], 2),
        'rmti_ptc':       round(d['ptc_pct'], 1),
        'rmti_composite': round(d['rmti_composite'], 1) if pd.notna(d['rmti_composite']) else None,
        'rmti_is_record': bool(d['rmti_is_record']) if pd.notna(d['rmti_is_record']) else False,

        # Liquidity — daily averages
        'dam_dfr_avg':       round(blocks['DAM_Demand_Fulfillment_Pct'].mean(), 1),
        'dam_dfr_min':       round(blocks['DAM_Demand_Fulfillment_Pct'].min(),  1),
        'dam_dfr_min_block': blocks.loc[blocks['DAM_Demand_Fulfillment_Pct'].idxmin(), 'Time Block'],
        'gdam_dfr_avg':      round(blocks['GDAM_Demand_Fulfillment_Pct'].mean(), 1),
        'gdam_dfr_min':      round(blocks['GDAM_Demand_Fulfillment_Pct'].min(),  1),
        'dam_bcr_avg':       round(blocks['DAM_Bid_Coverage_Ratio'].mean(),  2),
        'gdam_bcr_avg':      round(blocks['GDAM_Bid_Coverage_Ratio'].mean(), 2),

        # Solar-hour liquidity
        'dam_dfr_solar':  dam_dfr_solar,
        'gdam_dfr_solar': gdam_dfr_solar,
        'dam_bcr_solar':  dam_bcr_solar,
        'gdam_bcr_solar': gdam_bcr_solar,

        # Congestion
        'dam_congestion_avg':  round(blocks['DAM_Total_Congestion_Pct'].mean(), 2),
        'gdam_congestion_avg': round(blocks['GDAM_Total_Congestion_Pct'].mean(), 2),
        'solar_curtail':    round(solar_curtail, 2),
        'nonsolar_curtail': round(nonsolar_curtail, 2),
        'hydro_curtail':    round(hydro_curtail, 2),

        # Anomalies
        'dam_anomaly_count':  len(dam_anomalies),
        'gdam_anomaly_count': len(gdam_anomalies),
        'top_anomalies':      top_anomalies.to_dict('records'),

        # Context
        'seasonal_avg_rmti_ly': round(seasonal_avg_rmti, 1) if seasonal_avg_rmti is not None else None,
        'fiscal_flag':          fiscal_flag,
    }


# ============================================================
# Chart helpers
# ============================================================
def _fig_to_base64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format='png', bbox_inches='tight', dpi=150)
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode('utf-8')


# ============================================================
# Multi-Hour Arbitrage HTML builder (RtE-corrected)
# ============================================================
def build_multihour_arbitrage_table(target_date):
    """Build HTML showing multi-hour arbitrage results (RtE-corrected, per kWh sold).
    Reads precomputed columns from df_daily."""
    target = pd.to_datetime(target_date)
    daily_row = df_daily[df_daily['date'] == target]
    if daily_row.empty:
        return ""
    d = daily_row.iloc[0]

    rte_text = rte_caveat_text(include_formula=False)

    section_html = f"""
    <h4 style="color:#444;margin-top:18px;margin-bottom:5px;">Multi-Hour Battery Arbitrage Analysis</h4>
    <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px;">
      <div style="font-size:12px;color:#666;max-width:70%;">
        Optimal buy + 15-min cooling + sell windows for each duration. Each "hour" = 4 contiguous 15-min blocks; max 1-block (15-min) gap allowed between consecutive hours within the buy or sell window.
      </div>
      <div style="font-size:12px;color:#888;font-style:italic;text-align:right;">
        ({rte_text})
      </div>
    </div>
    """

    for n_h in [1, 2, 3, 4]:
        section_html += f"""
        <div style="margin-top:14px;font-size:13px;font-weight:bold;color:#1F3864;">
          ⚡ {n_h}-Hour Arbitrage
        </div>
        <table style="width:100%;border-collapse:collapse;font-size:12px;margin:4px 0 10px 0;">
          <tr style="background:#4A5568;color:white;">
            <th style="padding:6px 8px;text-align:left;">Path</th>
            <th style="padding:6px 8px;text-align:right;">Buy Avg (₹/kWh)</th>
            <th style="padding:6px 8px;text-align:left;">Buy Blocks</th>
            <th style="padding:6px 8px;text-align:right;">Sell Avg (₹/kWh)</th>
            <th style="padding:6px 8px;text-align:left;">Sell Blocks</th>
            <th style="padding:6px 8px;text-align:right;">Spread (₹/kWh sold)</th>
          </tr>
        """

        for path_key, path_label in [('dam', 'DAM-only'), ('gdam', 'GDAM-only'), ('cross', 'Cross (GDAM→DAM)'), ('best', 'BEST')]:
            spread      = d.get(f'arb_{n_h}h_{path_key}_spread')
            buy_avg     = d.get(f'arb_{n_h}h_{path_key}_buy_avg')
            buy_blocks  = d.get(f'arb_{n_h}h_{path_key}_buy_blocks')
            sell_avg    = d.get(f'arb_{n_h}h_{path_key}_sell_avg')
            sell_blocks = d.get(f'arb_{n_h}h_{path_key}_sell_blocks')

            if spread is None or pd.isna(spread):
                continue

            buy_label   = block_indices_to_compact_label(buy_blocks)  if buy_blocks  is not None else "—"
            sell_label  = block_indices_to_compact_label(sell_blocks) if sell_blocks is not None else "—"

            if path_key == 'best':
                best_path = d.get(f'arb_{n_h}h_best_path', '—')
                path_label_display = f'<strong>BEST</strong> <span style="color:#2E8B57;font-size:11px;">({best_path})</span>'
                row_bg = 'background:#F0FDF4;'
            else:
                path_label_display = path_label
                row_bg = ''

            section_html += f"""
            <tr style="{row_bg}">
              <td style="padding:5px 8px;border-bottom:1px solid #eee;">{path_label_display}</td>
              <td style="padding:5px 8px;text-align:right;border-bottom:1px solid #eee;">{buy_avg:.2f}</td>
              <td style="padding:5px 8px;border-bottom:1px solid #eee;font-size:11px;color:#666;">{buy_label}</td>
              <td style="padding:5px 8px;text-align:right;border-bottom:1px solid #eee;">{sell_avg:.2f}</td>
              <td style="padding:5px 8px;border-bottom:1px solid #eee;font-size:11px;color:#666;">{sell_label}</td>
              <td style="padding:5px 8px;text-align:right;border-bottom:1px solid #eee;font-weight:bold;color:#1F3864;">{spread:.2f}</td>
            </tr>
            """

        section_html += "</table>"

    return section_html


# ============================================================
# CHART FUNCTIONS
# ============================================================
def chart_intraday_mcp(blocks):
    fig, ax = plt.subplots(figsize=(8, 3.2))
    x = range(len(blocks))
    ax.plot(x, blocks['DAM_MCP'],  color='#1F3864', linewidth=1.8, label='DAM')
    ax.plot(x, blocks['GDAM_MCP'], color='#2E8B57', linewidth=1.8, label='GDAM')
    ax.fill_between(x, blocks['DAM_MCP'], blocks['GDAM_MCP'],
                    where=blocks['GDAM_MCP'] > blocks['DAM_MCP'],
                    color='#D7263D', alpha=0.18, label='GDAM > DAM (stressed)')
    ax.set_title('Intraday MCP Curve (₹/kWh)', fontsize=11, fontweight='bold')
    ax.set_xlabel('Time Block (00:00 → 24:00)', fontsize=9)
    ax.set_ylabel('₹/kWh', fontsize=9)
    ax.set_xticks([0, 24, 48, 72, 95])
    ax.set_xticklabels(['00:00','06:00','12:00','18:00','24:00'], fontsize=8)
    ax.legend(loc='upper left', fontsize=8, framealpha=0.9)
    ax.grid(True, alpha=0.3)
    return _fig_to_base64(fig)


def chart_premium(blocks):
    fig, ax = plt.subplots(figsize=(8, 3.2))
    x = range(len(blocks))
    colors = ['#D7263D' if p < 0 else '#2E8B57' for p in blocks['DAM_GDAM_Premium']]
    ax.bar(x, blocks['DAM_GDAM_Premium'], color=colors, width=1.0)
    ax.axhline(0, color='black', linewidth=0.6)
    ax.set_title('DAM − GDAM Premium per Block (red = GDAM costlier)', fontsize=11, fontweight='bold')
    ax.set_xlabel('Time Block', fontsize=9)
    ax.set_ylabel('Premium (₹/kWh)', fontsize=9)
    ax.set_xticks([0, 24, 48, 72, 95])
    ax.set_xticklabels(['00:00','06:00','12:00','18:00','24:00'], fontsize=8)
    ax.grid(True, alpha=0.3)
    return _fig_to_base64(fig)


def chart_rmti_gauge(metrics):
    fig, ax = plt.subplots(figsize=(8, 3.2))
    components = ['BPC\n(Frequency)', 'AGP\n(Severity)', 'PTC\n(Concentration)', 'Composite\nRMTI']
    agp_visual = min(metrics['rmti_agp'] / 2.0 * 100, 100)
    values = [metrics['rmti_bpc'], agp_visual, metrics['rmti_ptc'],
              metrics['rmti_composite'] if metrics['rmti_composite'] else 0]
    colors = ['#5B9BD5', '#5B9BD5', '#5B9BD5', '#1F3864']
    bars = ax.barh(components, values, color=colors, alpha=0.85)
    ax.axvline(50, color='gray', linestyle=':', alpha=0.6)
    ax.axvline(75, color='orange', linestyle=':', alpha=0.6)
    ax.set_xlim(0, 110)
    ax.set_title('RMTI Composite & Components (0-100 scale)', fontsize=11, fontweight='bold')
    ax.set_xlabel('Score', fontsize=9)
    raw_labels = [f"{metrics['rmti_bpc']:.1f}%",
                  f"₹{metrics['rmti_agp']:.2f}/kWh",
                  f"{metrics['rmti_ptc']:.1f}%",
                  f"{metrics['rmti_composite']:.1f}" if metrics['rmti_composite'] else "N/A"]
    for bar, label in zip(bars, raw_labels):
        ax.text(bar.get_width() + 2, bar.get_y() + bar.get_height()/2,
                label, va='center', fontsize=9, fontweight='bold')
    ax.grid(True, alpha=0.3, axis='x')
    return _fig_to_base64(fig)


def chart_source_curtailment(metrics):
    fig, ax = plt.subplots(figsize=(8, 3.2))
    sources = ['Solar', 'Non-Solar', 'Hydro']
    values  = [metrics['solar_curtail'], metrics['nonsolar_curtail'], metrics['hydro_curtail']]
    total   = sum(values)
    if total == 0:
        ax.text(0.5, 0.5, 'No curtailment today\n(transmission not binding across any renewable source)',
                ha='center', va='center', fontsize=12, color='#666',
                style='italic', transform=ax.transAxes)
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_title('Source-wise Curtailment (GDAM)', fontsize=11, fontweight='bold')
        for spine in ax.spines.values():
            spine.set_visible(False)
    else:
        colors = ['#F4B400', '#0F9D58', '#4285F4']
        bars = ax.bar(sources, values, color=colors, alpha=0.85, width=0.55)
        ax.set_title('Source-wise Curtailment (GDAM)', fontsize=11, fontweight='bold')
        ax.set_ylabel('Curtailment (% of cleared volume)', fontsize=9)
        ax.set_ylim(0, max(max(values) * 1.25, 1))
        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(values) * 0.03,
                    f'{val:.2f}%', ha='center', va='bottom', fontsize=10, fontweight='bold')
        ax.grid(True, alpha=0.3, axis='y')
    return _fig_to_base64(fig)


# ============================================================
# PROMPT BUILDER
# ============================================================
def build_brief_prompt_v3(metrics):
    seasonal_context = (
        f"Same month last year ({metrics['date'].year - 1}-{metrics['date'].month:02d}) average RMTI: {metrics['seasonal_avg_rmti_ly']}"
        if metrics['seasonal_avg_rmti_ly'] is not None
        else "No same-month-last-year data available"
    )
    fiscal_context = metrics['fiscal_flag'] if metrics['fiscal_flag'] else "No fiscal milestone within 30 days"
    sunday_note = " [SUNDAY — anomaly flags may be partly structural due to lower industrial demand]" if metrics['is_sunday'] else ""

    anomalous_block_times = [a['Time Block'] for a in metrics['top_anomalies']
                              if a['DAM_anomaly_direction'] or a['GDAM_anomaly_direction']]

    anomalies_text = ""
    if metrics['top_anomalies']:
        anomalies_text = "\nTop anomalous blocks today (Metric 4):\n"
        for a in metrics['top_anomalies']:
            anomalies_text += f"  - {a['Time Block']}: DAM ₹{a['DAM_MCP']:.2f}/kWh (z={a['DAM_z_score']:.2f}, {a['DAM_anomaly_direction']}), GDAM ₹{a['GDAM_MCP']:.2f}/kWh (z={a['GDAM_z_score']:.2f}, {a['GDAM_anomaly_direction']})\n"

    prompt = f"""You are a power-market analyst writing a daily brief for an Indian renewable-energy strategy professional. Markets: IEX day-ahead (DAM) and green day-ahead (GDAM).

**CRITICAL UNITS RULE:** All prices in ₹/kWh (rupees per kilowatt-hour). "₹3.19/kWh" means 3 rupees 19 paise per unit, not 3.19 paise. Always use "₹/kWh" — NEVER use the word "paise". Wrong: "9.8 paise". Right: "₹9.8/kWh".

**ANOMALY HIGHLIGHTING RULE:** In Section 5 (Notable Blocks), wrap any anomalous block time in <span style="color:#D7263D;font-weight:bold;">...</span> tags. Example: <span style="color:#D7263D;font-weight:bold;">06:30 - 06:45</span>.

Anomalous blocks today: {anomalous_block_times if anomalous_block_times else 'None'}

DATA FOR {metrics['date']} ({metrics['day_of_week']}){sunday_note}:

PRICING (₹/kWh):
- DAM:  Avg ₹{metrics['dam_avg_mcp']}  |  Peak ₹{metrics['dam_peak_mcp']} ({metrics['dam_peak_block']})  |  Trough ₹{metrics['dam_trough_mcp']} ({metrics['dam_trough_block']})  |  Spread ₹{metrics['dam_spread']}
- GDAM: Avg ₹{metrics['gdam_avg_mcp']}  |  Peak ₹{metrics['gdam_peak_mcp']} ({metrics['gdam_peak_block']})  |  Trough ₹{metrics['gdam_trough_mcp']} ({metrics['gdam_trough_block']})  |  Spread ₹{metrics['gdam_spread']}

CROSS-MARKET:
- Avg DAM−GDAM premium: ₹{metrics['avg_premium']}/kWh (negative = GDAM costlier)
- Stressed blocks (GDAM > DAM): {metrics['stressed_blocks']}/96

LIQUIDITY:
- DAM DFR (MCV/Buy Bid):  daily avg {metrics['dam_dfr_avg']}%   | solar hours (10-15) {metrics['dam_dfr_solar']}%   | min {metrics['dam_dfr_min']}% ({metrics['dam_dfr_min_block']})
- GDAM DFR:                daily avg {metrics['gdam_dfr_avg']}% | solar hours {metrics['gdam_dfr_solar']}%       | min {metrics['gdam_dfr_min']}%
- DAM BCR (Sell/Buy):     daily avg {metrics['dam_bcr_avg']}x  | solar hours {metrics['dam_bcr_solar']}x
- GDAM BCR:                daily avg {metrics['gdam_bcr_avg']}x | solar hours {metrics['gdam_bcr_solar']}x

GRID CONGESTION:
- DAM avg: {metrics['dam_congestion_avg']}%  |  GDAM avg: {metrics['gdam_congestion_avg']}%
- GDAM source-wise curtailment: Solar {metrics['solar_curtail']}%, Non-Solar {metrics['nonsolar_curtail']}%, Hydro {metrics['hydro_curtail']}%

RMTI (RPO Market Tightness — cross-market metric):
- BPC: {metrics['rmti_bpc']}% (frequency of GDAM>DAM blocks)
- AGP: ₹{metrics['rmti_agp']}/kWh (severity during stressed blocks)
- PTC: {metrics['rmti_ptc']}% (concentration of stress in evening peak)
- Composite: {metrics['rmti_composite']}/100
- Record-setting day: {metrics['rmti_is_record']}

ANOMALIES (Metric 4 — MCP > 2σ from 30-day same-block baseline):
- DAM anomalies: {metrics['dam_anomaly_count']}  |  GDAM anomalies: {metrics['gdam_anomaly_count']}
{anomalies_text}

CONTEXT:
- Seasonal: {seasonal_context}
- Fiscal: {fiscal_context}

INSTRUCTIONS:
Write a concise brief in 5 markdown sections (using ## headings). ~250-300 words.

## Headline
ONE sharp sentence summarizing the day with a key number.

## Market Dynamics
Synthesize price levels, cross-market premium, and liquidity. Mention solar-hour DFR/BCR vs daily averages if they diverge meaningfully. Interpret, don't list.

## RMTI Verdict
Interpret composite + 3 components together. Use seasonal context: is today *typical* or *anomalous*?

## Grid & Curtailment
ONE paragraph. If zero across all sources, say so and move on.

## Notable Blocks
2-3 bullets. REMEMBER: wrap anomalous block times in red-bold span per the rule above.

TONE: Analytical, sharp, no fluff. Use ₹/kWh consistently."""
    return prompt


# ============================================================
# MAIN FUNCTION
# ============================================================
def generate_daily_brief_v2(target_date):
    """Returns (html_string, info_dict)."""
    metrics = get_day_metrics(target_date)
    blocks  = df_blocks[df_blocks['Date'] == pd.to_datetime(target_date)].copy()

    # Charts
    chart1 = chart_intraday_mcp(blocks)
    chart2 = chart_premium(blocks)
    chart3 = chart_rmti_gauge(metrics)
    chart4 = chart_source_curtailment(metrics)

    # Narrative via Claude
    prompt = build_brief_prompt_v3(metrics)
    client = get_client()
    response = client.messages.create(
        model='claude-haiku-4-5-20251001',
        max_tokens=1200,
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

    # MAIN TABLE — DAM vs GDAM
    formula_style = 'font-size:11px;color:#888;font-style:italic;'
    main_table = f"""
    <table style="width:100%;border-collapse:collapse;font-size:14px;margin:10px 0;">
      <tr style="background:#1F3864;color:white;">
        <th style="padding:8px;text-align:left;">Metric</th>
        <th style="padding:8px;text-align:right;">DAM</th>
        <th style="padding:8px;text-align:right;">GDAM</th>
      </tr>
      <tr><td style="padding:6px 8px;border-bottom:1px solid #eee;">Avg MCP (₹/kWh)</td><td style="padding:6px 8px;text-align:right;border-bottom:1px solid #eee;">{metrics['dam_avg_mcp']}</td><td style="padding:6px 8px;text-align:right;border-bottom:1px solid #eee;">{metrics['gdam_avg_mcp']}</td></tr>
      <tr><td style="padding:6px 8px;border-bottom:1px solid #eee;">Peak MCP (₹/kWh)</td><td style="padding:6px 8px;text-align:right;border-bottom:1px solid #eee;">{metrics['dam_peak_mcp']} <span style="font-size:11px;color:#888;">({metrics['dam_peak_block']})</span></td><td style="padding:6px 8px;text-align:right;border-bottom:1px solid #eee;">{metrics['gdam_peak_mcp']} <span style="font-size:11px;color:#888;">({metrics['gdam_peak_block']})</span></td></tr>
      <tr><td style="padding:6px 8px;border-bottom:1px solid #eee;">Trough MCP (₹/kWh)</td><td style="padding:6px 8px;text-align:right;border-bottom:1px solid #eee;">{metrics['dam_trough_mcp']} <span style="font-size:11px;color:#888;">({metrics['dam_trough_block']})</span></td><td style="padding:6px 8px;text-align:right;border-bottom:1px solid #eee;">{metrics['gdam_trough_mcp']} <span style="font-size:11px;color:#888;">({metrics['gdam_trough_block']})</span></td></tr>
      <tr><td style="padding:6px 8px;border-bottom:1px solid #eee;">Intraday Spread (₹/kWh)</td><td style="padding:6px 8px;text-align:right;border-bottom:1px solid #eee;">{metrics['dam_spread']}</td><td style="padding:6px 8px;text-align:right;border-bottom:1px solid #eee;">{metrics['gdam_spread']}</td></tr>
      <tr><td style="padding:6px 8px;border-bottom:1px solid #eee;">
        Demand Fulfillment Ratio<br/><span style="{formula_style}">= MCV / Purchase Bid</span>
      </td><td style="padding:6px 8px;text-align:right;border-bottom:1px solid #eee;">{metrics['dam_dfr_avg']}% <span style="font-size:11px;color:#888;">(solar: {metrics['dam_dfr_solar']}%)</span></td>
         <td style="padding:6px 8px;text-align:right;border-bottom:1px solid #eee;">{metrics['gdam_dfr_avg']}% <span style="font-size:11px;color:#888;">(solar: {metrics['gdam_dfr_solar']}%)</span></td></tr>
      <tr><td style="padding:6px 8px;border-bottom:1px solid #eee;">
        Bid Coverage Ratio<br/><span style="{formula_style}">= Sell Bids / Buy Bids</span>
      </td><td style="padding:6px 8px;text-align:right;border-bottom:1px solid #eee;">{metrics['dam_bcr_avg']}x <span style="font-size:11px;color:#888;">(solar: {metrics['dam_bcr_solar']}x)</span></td>
         <td style="padding:6px 8px;text-align:right;border-bottom:1px solid #eee;">{metrics['gdam_bcr_avg']}x <span style="font-size:11px;color:#888;">(solar: {metrics['gdam_bcr_solar']}x)</span></td></tr>
      <tr><td style="padding:6px 8px;">Grid Congestion (avg)</td><td style="padding:6px 8px;text-align:right;">{metrics['dam_congestion_avg']}%</td><td style="padding:6px 8px;text-align:right;">{metrics['gdam_congestion_avg']}%</td></tr>
    </table>
    """

    # MINI TABLE — Cross-Market Indicators (legacy single-block arbitrage REMOVED in v1.5)
    rmti_str = f"{metrics['rmti_composite']:.1f}/100" if metrics['rmti_composite'] else "N/A"
    record_badge = ' 🔴 RECORD' if metrics['rmti_is_record'] else ''

    cross_table = f"""
    <table style="width:100%;border-collapse:collapse;font-size:14px;margin:10px 0;">
      <tr style="background:#4A5568;color:white;">
        <th style="padding:8px;text-align:left;">Cross-Market Indicator</th>
        <th style="padding:8px;text-align:left;">Value</th>
      </tr>
      <tr><td style="padding:8px;border-bottom:1px solid #eee;font-weight:bold;">RMTI Composite</td><td style="padding:8px;border-bottom:1px solid #eee;">{rmti_str}{record_badge}</td></tr>
      <tr><td style="padding:8px;border-bottom:1px solid #eee;">  • BPC (Frequency)</td><td style="padding:8px;border-bottom:1px solid #eee;">{metrics['rmti_bpc']}%</td></tr>
      <tr><td style="padding:8px;border-bottom:1px solid #eee;">  • AGP (Severity)</td><td style="padding:8px;border-bottom:1px solid #eee;">₹{metrics['rmti_agp']}/kWh</td></tr>
      <tr><td style="padding:8px;">  • PTC (Concentration)</td><td style="padding:8px;">{metrics['rmti_ptc']}%</td></tr>
    </table>
    """

    # FOOTNOTE
    footnote_html = """
    <div style="margin-top:18px;padding:12px;background:#FAFAFA;border-left:3px solid #1F3864;font-size:12px;color:#444;">
      <strong style="color:#1F3864;">📖 RMTI — RPO Market Tightness Index</strong><br/>
      A composite cross-market indicator (0-100 scale) measuring how stressed the green power market (GDAM) is relative to the conventional market (DAM). Higher = greater RPO compliance pressure.<br/><br/>
      <strong>Components:</strong><br/>
      • <strong>BPC</strong> (Block Premium Count, weight 0.4) — % of 96 blocks where GDAM_MCP > DAM_MCP. Measures <em>frequency</em> of tightness.<br/>
      • <strong>AGP</strong> (Average Green Premium, weight 0.4) — Mean GDAM premium over DAM during stressed blocks (₹/kWh). Measures <em>severity</em>.<br/>
      • <strong>PTC</strong> (Peak-hour Tightness Concentration, weight 0.2) — % of stressed blocks falling in evening peak (18:00–24:00). Measures <em>concentration</em>.<br/><br/>
      <strong>Composite formula:</strong> RMTI = 0.4 × BPC_norm + 0.4 × AGP_norm + 0.2 × PTC_norm. Each component normalized against rolling 30-day max.
    </div>
    """

    # Build multi-hour arbitrage section
    multihour_arb_section = build_multihour_arbitrage_table(target_date)

    # ASSEMBLE FINAL HTML
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:850px;border:1px solid #ddd;padding:20px;border-radius:8px;background:white;">
      <h2 style="color:#1F3864;margin-top:0;border-bottom:2px solid #1F3864;padding-bottom:8px;">
        ⚡ IEX Daily Brief — {metrics['date']} ({metrics['day_of_week']})
      </h2>

      <h4 style="color:#444;margin-bottom:5px;">Headline Metrics — DAM vs GDAM</h4>
      {main_table}

      <h4 style="color:#444;margin-bottom:5px;margin-top:15px;">Cross-Market Indicators</h4>
      {cross_table}

      {multihour_arb_section}

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

    return html, {'tokens_in': tokens_in, 'tokens_out': tokens_out, 'cost_usd': cost_usd}