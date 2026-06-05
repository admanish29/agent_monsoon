"""
app.py — Agent Monsoon Home page (v2: animated grid background + polished cards).

Dark-themed energy-sector aesthetic.
Session 3 of 8.
"""

# ============================================================
# PASSWORD GATE — Streamlit Cloud secret-based auth
# ============================================================
import streamlit as st

def _check_password():
    """Returns True if user is authenticated, False otherwise."""
    if st.session_state.get("am_authenticated", False):
        return True

    st.markdown("""
    <div style="text-align:center;margin-top:80px;">
      <h1 style="color:#00D4FF;font-size:42px;font-weight:800;">🌧️ Agent Monsoon</h1>
      <p style="color:#8a93a8;font-size:14px;">IEX Power Market Intelligence · Internal Access Only</p>
    </div>
    """, unsafe_allow_html=True)

    pwd = st.text_input("Enter access password:", type="password", key="am_pwd_input")
    if pwd:
        try:
            expected = st.secrets["app_password"]
        except (KeyError, FileNotFoundError):
            st.error("⚠️ Server misconfiguration: app_password not set in secrets.")
            return False
        if pwd == expected:
            st.session_state.am_authenticated = True
            st.rerun()
        else:
            st.error("❌ Wrong password.")
    return False


if not _check_password():
    st.stop()
# ============================================================
# END password gate
# ============================================================
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo

from src.data_loader import load_dataframes, get_data_summary


# ============================================================
# Page setup
# ============================================================
st.set_page_config(
    page_title="Agent Monsoon",
    page_icon="⚡",
    layout="wide",
)


# ============================================================
# CSS — animated grid background + polished cards
# ============================================================
st.markdown("""
<style>
    /* Hide Streamlit default chrome */
    footer {visibility: hidden;}
    #MainMenu {visibility: hidden;}

    /* ====== ANIMATED GRID BACKGROUND (home only) ====== */
    .stApp::before {
        content: "";
        position: fixed;
        top: 0; left: 0;
        width: 100%; height: 100%;
        background-image:
            linear-gradient(rgba(0, 212, 255, 0.04) 1px, transparent 1px),
            linear-gradient(90deg, rgba(0, 212, 255, 0.04) 1px, transparent 1px);
        background-size: 50px 50px;
        z-index: 0;
        pointer-events: none;
    }

    /* Radial glow behind hero */
    .stApp::after {
        content: "";
        position: fixed;
        top: -200px; left: 50%;
        transform: translateX(-50%);
        width: 800px; height: 600px;
        background: radial-gradient(ellipse at center,
            rgba(0, 212, 255, 0.12) 0%,
            rgba(0, 212, 255, 0.04) 30%,
            transparent 70%);
        z-index: 0;
        pointer-events: none;
    }

    /* Horizontal pulse line — sweeps across the screen */
    .pulse-line {
        position: fixed;
        left: 0;
        width: 100%;
        height: 1px;
        background: linear-gradient(90deg,
            transparent 0%,
            transparent 20%,
            rgba(0, 212, 255, 0.6) 50%,
            transparent 80%,
            transparent 100%);
        z-index: 0;
        pointer-events: none;
        opacity: 0;
    }
    .pulse-line.p1 { top: 25%; animation: pulse-sweep 7s ease-in-out infinite; animation-delay: 0s; }
    .pulse-line.p2 { top: 60%; animation: pulse-sweep 9s ease-in-out infinite; animation-delay: 3s; }
    .pulse-line.p3 { top: 80%; animation: pulse-sweep 11s ease-in-out infinite; animation-delay: 6s; }

    @keyframes pulse-sweep {
        0%   { opacity: 0; transform: translateX(-100%); }
        20%  { opacity: 1; }
        80%  { opacity: 1; }
        100% { opacity: 0; transform: translateX(100%); }
    }

    /* Ensure content sits above the background */
    .main .block-container {
        position: relative;
        z-index: 1;
    }

    /* ====== HERO ====== */
    .hero-title {
        background: linear-gradient(135deg, #00D4FF 0%, #0077B6 50%, #4A90E2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        font-size: 52px;
        font-weight: 800;
        letter-spacing: -1.5px;
        margin-bottom: 8px;
        text-shadow: 0 0 40px rgba(0, 212, 255, 0.3);
    }
    .hero-subtitle {
        color: #8a93a8;
        font-size: 16px;
        font-weight: 400;
        margin-bottom: 0;
        letter-spacing: 0.5px;
    }

    /* ====== METRIC CARDS (polished) ====== */
    .metric-card {
        background: linear-gradient(135deg, rgba(19, 24, 38, 0.85) 0%, rgba(26, 33, 56, 0.85) 100%);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        border: 1px solid rgba(31, 42, 68, 0.8);
        border-radius: 14px;
        padding: 20px 22px;
        height: 100%;
        transition: all 0.25s ease;
        position: relative;
        overflow: hidden;
    }
    /* Inner glow at top */
    .metric-card::after {
        content: "";
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 60%;
        background: linear-gradient(180deg, rgba(0, 212, 255, 0.05) 0%, transparent 100%);
        pointer-events: none;
        border-radius: 14px 14px 0 0;
    }
    .metric-card:hover {
        border-color: rgba(0, 212, 255, 0.6);
        box-shadow:
            0 0 30px rgba(0, 212, 255, 0.2),
            inset 0 0 20px rgba(0, 212, 255, 0.05);
        transform: translateY(-3px);
    }
    .metric-card:hover .metric-icon {
        color: #4DDFFF;
        filter: drop-shadow(0 0 8px rgba(0, 212, 255, 0.6));
    }
    .metric-card::before {
        content: "";
        position: absolute;
        top: 0; left: 0;
        width: 3px; height: 100%;
        background: linear-gradient(180deg, #00D4FF 0%, #0077B6 100%);
        opacity: 0.85;
        box-shadow: 0 0 12px rgba(0, 212, 255, 0.6);
    }

    .metric-icon {
        color: #00D4FF;
        margin-bottom: 10px;
        transition: all 0.25s ease;
        position: relative;
        z-index: 1;
    }
    .metric-label {
        font-size: 11px;
        font-weight: 600;
        color: #8a93a8;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        margin-bottom: 8px;
        position: relative;
        z-index: 1;
    }
    .metric-value {
        font-size: 30px;
        font-weight: 700;
        color: #E4E7EB;
        font-family: 'SF Mono', 'Menlo', 'Consolas', monospace;
        margin-bottom: 4px;
        line-height: 1.1;
        text-shadow: 0 0 20px rgba(0, 212, 255, 0.15);
        position: relative;
        z-index: 1;
    }
    .metric-subtitle {
        font-size: 12px;
        color: #6b7387;
        font-weight: 400;
        position: relative;
        z-index: 1;
    }

    /* ====== Section headers ====== */
    .section-header {
        color: #00D4FF;
        font-size: 13px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 2px;
        margin-top: 36px;
        margin-bottom: 18px;
        border-bottom: 1px solid rgba(0, 212, 255, 0.15);
        padding-bottom: 10px;
        text-shadow: 0 0 10px rgba(0, 212, 255, 0.3);
    }

    /* ====== Feature list ====== */
    .feature-item {
        background: rgba(19, 24, 38, 0.7);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        border: 1px solid rgba(31, 42, 68, 0.8);
        border-radius: 10px;
        padding: 16px 20px;
        margin-bottom: 10px;
        display: flex;
        align-items: center;
        gap: 16px;
        transition: all 0.2s ease;
    }
    .feature-item:hover {
        border-color: rgba(0, 212, 255, 0.4);
        background: rgba(19, 24, 38, 0.9);
    }
    .feature-icon {
        color: #00D4FF;
        flex-shrink: 0;
    }
    .feature-title {
        font-weight: 600;
        color: #E4E7EB;
        font-size: 14px;
    }
    .feature-desc {
        color: #8a93a8;
        font-size: 13px;
        margin-top: 2px;
    }
    .feature-coming {
        font-size: 10px;
        background: rgba(0, 212, 255, 0.1);
        color: #00D4FF;
        padding: 3px 10px;
        border-radius: 4px;
        margin-left: 10px;
        font-weight: 600;
        letter-spacing: 0.5px;
        border: 1px solid rgba(0, 212, 255, 0.2);
    }
</style>

<!-- Animated pulse lines -->
<div class="pulse-line p1"></div>
<div class="pulse-line p2"></div>
<div class="pulse-line p3"></div>
""", unsafe_allow_html=True)


# ============================================================
# Lucide SVG icons (inline — no library dependency)
# ============================================================
ICONS = {
    "calendar":   '<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg>',
    "database":   '<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="12" cy="5" rx="9" ry="3"></ellipse><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"></path><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"></path></svg>',
    "layers":     '<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2"></polygon><polyline points="2 17 12 22 22 17"></polyline><polyline points="2 12 12 17 22 12"></polyline></svg>',
    "alert":      '<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>',
    "zap":        '<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg>',
    "trending":   '<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"></polyline><polyline points="17 6 23 6 23 12"></polyline></svg>',
    "trophy":     '<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6"></path><path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18"></path><path d="M4 22h16"></path><path d="M10 14.66V17c0 .55-.47.98-.97 1.21C7.85 18.75 7 20.24 7 22"></path><path d="M14 14.66V17c0 .55.47.98.97 1.21C16.15 18.75 17 20.24 17 22"></path><path d="M18 2H6v7a6 6 0 0 0 12 0V2Z"></path></svg>',
    "messages":   '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"></path></svg>',
    "search":     '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>',
    "book":       '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path></svg>',
    "weekly":     '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"></rect><path d="M16 2v4"></path><path d="M8 2v4"></path><path d="M3 10h18"></path><path d="M8 14h.01"></path><path d="M12 14h.01"></path><path d="M16 14h.01"></path><path d="M8 18h.01"></path><path d="M12 18h.01"></path><path d="M16 18h.01"></path></svg>',
}


def metric_card(icon_key, label, value, subtitle=""):
    return f"""
    <div class="metric-card">
        <div class="metric-icon">{ICONS[icon_key]}</div>
        <div class="metric-label">{label}</div>
        <div class="metric-value">{value}</div>
        <div class="metric-subtitle">{subtitle}</div>
    </div>
    """


# ============================================================
# Hero
# ============================================================
st.markdown('<div class="hero-title">⚡ Agent Monsoon</div>', unsafe_allow_html=True)
st.markdown('<p class="hero-subtitle">IEX Market Intelligence · Powered by Claude</p>', unsafe_allow_html=True)


# ============================================================
# Load data
# ============================================================
data = load_dataframes()
df_daily  = data['df_daily']
df_blocks = data['df_blocks']
summary   = get_data_summary()


# ============================================================
# Status row
# ============================================================
st.markdown('<div class="section-header">SYSTEM STATUS</div>', unsafe_allow_html=True)

now_ist = datetime.now(ZoneInfo("Asia/Kolkata"))
days_gap = (now_ist.date() - summary['date_range_end']).days

col1, col2, col3 = st.columns(3)
with col1:
    st.markdown(metric_card("calendar", "Today (IST)",
                             now_ist.strftime('%Y-%m-%d'),
                             now_ist.strftime('%A · %H:%M')), unsafe_allow_html=True)
with col2:
    st.markdown(metric_card("database", "Latest Data",
                             str(summary['date_range_end']),
                             f"{days_gap} days behind today"), unsafe_allow_html=True)
with col3:
    st.markdown(metric_card("layers", "Coverage",
                             f"{summary['total_days']} days",
                             f"{summary['total_blocks']:,} blocks"), unsafe_allow_html=True)


# ============================================================
# Dataset highlights
# ============================================================
st.markdown('<div class="section-header">DATASET HIGHLIGHTS</div>', unsafe_allow_html=True)

worst_rmti_day     = df_daily.loc[df_daily['rmti_composite'].idxmax()]
best_arbitrage_day = df_daily.loc[df_daily['arbitrage_index'].idxmax()]
highest_dam_day    = df_daily.loc[df_daily['dam_avg_mcp'].idxmax()]
record_days_count  = int(df_daily['rmti_is_record'].sum())

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.markdown(metric_card("alert", "Worst RMTI",
                             f"{worst_rmti_day['rmti_composite']:.1f}",
                             str(worst_rmti_day['date'].date())), unsafe_allow_html=True)
with col2:
    st.markdown(metric_card("zap", "Best Arbitrage",
                             f"₹{best_arbitrage_day['arbitrage_index']:.2f}",
                             str(best_arbitrage_day['date'].date())), unsafe_allow_html=True)
with col3:
    st.markdown(metric_card("trending", "Highest DAM Avg",
                             f"₹{highest_dam_day['dam_avg_mcp']:.2f}",
                             str(highest_dam_day['date'].date())), unsafe_allow_html=True)
with col4:
    st.markdown(metric_card("trophy", "Record Days",
                             f"{record_days_count}",
                             "new 30-day RMTI highs"), unsafe_allow_html=True)


# ============================================================
# Feature list
# ============================================================
st.markdown('<div class="section-header">NAVIGATION</div>', unsafe_allow_html=True)

features = [
    ("calendar",  "Daily Brief",       "Pick any date for a full IEX market brief with charts and AI analysis",   None),
    ("messages",  "Ask Agent Monsoon", "Free-form questions about any date, period, or market pattern",            "Session 4"),
    ("search",    "Data Explorer",     "Slice and dice raw block-level data with full query control",              "Session 5-6"),
    ("weekly",    "Weekly Brief",      "Mon-Sun analytical brief with cross-day pattern detection",                "Session 7"),
    ("book",      "About",             "Framework, metric definitions, methodology, limitations",                  "Session 8"),
]

for icon_key, title, desc, coming in features:
    coming_badge = f'<span class="feature-coming">{coming}</span>' if coming else ''
    st.markdown(f"""
    <div class="feature-item">
        <div class="feature-icon">{ICONS[icon_key]}</div>
        <div>
            <div class="feature-title">{title}{coming_badge}</div>
            <div class="feature-desc">{desc}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)


# ============================================================
# Sidebar
# ============================================================
with st.sidebar:
    st.markdown("### ⚡ Build Info")
    st.markdown(f"Streamlit `{st.__version__}`")
    st.markdown("Session **3 of 8**")
    st.markdown(f"Pickle: `{summary.get('version', 'unknown')}`")
    last_saved = summary.get('last_saved')
    if last_saved is not None:
        st.markdown(f"Last saved: {pd.Timestamp(last_saved).strftime('%Y-%m-%d %H:%M')}")