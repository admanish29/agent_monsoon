"""
agent.py — The conversational agent loop.

Wraps Anthropic's API + the 8 tools into a multi-turn session.
Features:
  - Domain-aware system prompt (glossary, fiscal calendar, units rule)
  - Dynamic date-context injection (today, data coverage, fiscal proximity)
  - Tool calling with up to 8 turns per query
  - Session-level token + cost tracking
  - Turn log for future "what tools should we add" analysis
"""

import json
import time
from datetime import datetime, timedelta, timezone

import streamlit as st
import anthropic
import pandas as pd

from src.tools import TOOL_FUNCTIONS, TOOL_SCHEMAS, df_daily


# ============================================================
# Anthropic client (key from Streamlit secrets)
# ============================================================
_client = None

def get_client():
    """Lazy-init Anthropic client using Streamlit secrets."""
    global _client
    if _client is None:
        api_key = st.secrets["ANTHROPIC_API_KEY"]
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


# ============================================================
# CURRENT-DATE AWARENESS (IST = UTC+5:30)
# ============================================================
IST = timezone(timedelta(hours=5, minutes=30))


def build_date_context():
    """Build a current-date context block to inject into the system prompt.
    Recomputed on every agent call so date awareness stays fresh."""
    now_ist = datetime.now(IST)
    today = now_ist.date()

    # Data coverage info — based on what's actually in df_daily
    data_start = df_daily['date'].min().date()
    data_end   = df_daily['date'].max().date()
    days_gap   = (today - data_end).days

    # Calendar context
    day_of_week  = now_ist.strftime('%A')
    week_of_year = now_ist.isocalendar()[1]
    month_name   = now_ist.strftime('%B')

    # Days remaining in current month
    if now_ist.month == 12:
        next_month_start = datetime(now_ist.year + 1, 1, 1, tzinfo=IST)
    else:
        next_month_start = datetime(now_ist.year, now_ist.month + 1, 1, tzinfo=IST)
    days_left_in_month = (next_month_start.date() - today).days

    # Fiscal year context (Indian FY: 1 April to 31 March)
    if now_ist.month >= 4:  # April onwards = current FY
        fy_label = f"FY{now_ist.year % 100}-{(now_ist.year + 1) % 100:02d}"
        fy_end   = datetime(now_ist.year + 1, 3, 31, tzinfo=IST).date()
        fy_start = datetime(now_ist.year, 4, 1, tzinfo=IST).date()
    else:  # Jan-Mar = prior FY (ending now)
        fy_label = f"FY{(now_ist.year - 1) % 100}-{now_ist.year % 100:02d}"
        fy_end   = datetime(now_ist.year, 3, 31, tzinfo=IST).date()
        fy_start = datetime(now_ist.year - 1, 4, 1, tzinfo=IST).date()

    days_to_fy_end = (fy_end - today).days
    days_into_fy   = (today - fy_start).days

    # Half-year close (30 September) proximity
    if now_ist.month <= 9:
        h1_close = datetime(now_ist.year, 9, 30, tzinfo=IST).date()
    else:
        h1_close = datetime(now_ist.year + 1, 9, 30, tzinfo=IST).date()
    days_to_h1_close = (h1_close - today).days

    return f"""
CURRENT DATE & CALENDAR CONTEXT (Indian Standard Time):
- Today: {today} ({day_of_week})
- Current time (IST): {now_ist.strftime('%H:%M')}
- Week of year: {week_of_year}
- Month: {month_name} {now_ist.year} — {days_left_in_month} days remaining in month
- Fiscal context: {fy_label} (Indian FY runs 1 Apr → 31 Mar)
  • {days_into_fy} days into the fiscal year
  • {days_to_fy_end} days until FY-end (31 Mar)
  • {days_to_h1_close} days until/from H1 close (30 Sep)

DATA COVERAGE:
- Dataset spans: {data_start} to {data_end}
- Latest data available: {data_end}
- Today vs latest data: {days_gap}-day gap
- IMPORTANT: When the user asks about "today", "yesterday", or recent dates, prefer to answer using the LATEST AVAILABLE date in the dataset ({data_end}). Mention the gap if relevant.
  Example: User asks "what about yesterday?" — if today is {today} but latest data is {data_end}, treat "yesterday" as {data_end}, and tell the user this is the latest data available.
- When the user asks about "this week" or "last week", use ISO weeks (Monday to Sunday) anchored on the latest available data date if today is beyond data coverage.
"""


# ============================================================
# SYSTEM PROMPT — domain glossary + core rules
# ============================================================
SYSTEM_PROMPT = """You are Agent Monsoon — an analyst specializing in the Indian Energy Exchange (IEX) day-ahead market (DAM) and green day-ahead market (GDAM). You have access to 17 months of block-level data (Jan 2025 to mid-May 2026) via the tools provided.

DOMAIN GLOSSARY (memorize these — users will use these terms interchangeably):
- DAM = Day-Ahead Market (conventional/grey power)
- GDAM = Green Day-Ahead Market (only renewable-sourced power)
- MCP = Market Clearing Price
- MCV = Market Clearing Volume
- FSV = Final Scheduled Volume (post-grid-constraint dispatch)
- RMTI = RPO Market Tightness Index — a composite 0-100 score measuring how stressed the green market is relative to DAM. When users say "RPO market tightness", "RPO stress", "green market stress", "green tightness", "renewable purchase obligation tightness", or just "tightness", they almost always mean RMTI.
- BPC = Block Premium Count (% of 96 blocks where GDAM > DAM) — the FREQUENCY component of RMTI
- AGP = Average Green Premium (avg ₹/kWh by which GDAM exceeded DAM on stressed blocks) — the SEVERITY component of RMTI
- PTC = Peak-hour Tightness Concentration (% of stressed blocks in evening 18:00-24:00 window) — the CONCENTRATION component of RMTI
- DFR = Demand Fulfillment Ratio (MCV / Purchase Bid × 100)
- BCR = Bid Coverage Ratio (Sell Bid / Purchase Bid)
- Storage Arbitrage Index = the biggest tradable buy-low / sell-high opportunity on a day, accounting for temporal ordering. Reports the path (DAM-only / GDAM-only / Cross), buy block, sell block.

CORE RULES:
1. ALWAYS call a tool before answering factual questions about the data. Never invent numbers.
2. Use ₹/kWh as the price unit consistently. Never use "paise". A value of 0.50 ₹/kWh means fifty paise — write it as "₹0.50/kWh".
3. Be concise and analytical. No fluff. Numbers embedded in prose.
4. Date parsing: treat date strings naturally — "5 May 2026" → "2026-05-05", "March 2026" → start "2026-03-01" end "2026-03-31", "Q1 2025" → "2025-01-01" to "2025-03-31".
5. Contextualize findings when relevant: seasonal patterns (winter Nov-Jan is structurally tightest), fiscal calendar (FY-end 31 Mar, H1 close 30 Sep, FY-start 1 Apr), structural patterns (pre-dawn 4-7 AM is structurally weak in GDAM, evening 18:00-22:00 is the demand peak vs solar collapse window).
6. Only ask clarifying questions when multiple distinct interpretations would lead to very different tool calls (e.g., "show me last week's data" — but the user's current date is unclear). If a query maps to a reasonable default interpretation, proceed with it and briefly mention the assumption.
7. If a tool returns an error, acknowledge it briefly and either try a different approach or ask the user."""


# ============================================================
# AGENT SESSION CLASS — manages multi-turn conversation
# ============================================================
class AgentSession:
    def __init__(self, max_turns=8, model='claude-haiku-4-5-20251001'):
        self.history = []
        self.max_turns = max_turns
        self.model = model
        self.total_cost = 0.0
        self.total_tokens_in = 0
        self.total_tokens_out = 0
        self.turn_log = []   # For "what tools should we add" analysis later

    def reset(self):
        self.history = []
        self.turn_log = []

    def ask(self, user_query: str, verbose=False):
        """Send a query, run the agent loop, return the final answer."""
        client = get_client()
        self.history.append({"role": "user", "content": user_query})

        turn_start_time = time.time()
        tools_called_this_query = []
        turns_used = 0

        for turn_idx in range(self.max_turns):
            turns_used = turn_idx + 1

            if verbose:
                print(f"\n--- Turn {turns_used} ---")

            # Call Claude — date context refreshed every call
            response = client.messages.create(
                model=self.model,
                max_tokens=1500,
                system=SYSTEM_PROMPT + build_date_context(),
                tools=TOOL_SCHEMAS,
                messages=self.history,
            )

            self.total_tokens_in  += response.usage.input_tokens
            self.total_tokens_out += response.usage.output_tokens

            # Append Claude's response
            self.history.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "tool_use":
                # Claude wants to call one or more tools
                tool_results_content = []
                for block in response.content:
                    if block.type == "tool_use":
                        tool_name = block.name
                        tool_input = block.input
                        tool_use_id = block.id
                        tools_called_this_query.append(tool_name)

                        if verbose:
                            print(f"   → Calling: {tool_name}({tool_input})")

                        if tool_name in TOOL_FUNCTIONS:
                            try:
                                result = TOOL_FUNCTIONS[tool_name](**tool_input)
                                result_str = json.dumps(result, default=str)
                            except Exception as e:
                                result_str = json.dumps({"error": f"Tool execution failed: {str(e)}"})
                        else:
                            result_str = json.dumps({"error": f"Unknown tool: {tool_name}"})

                        tool_results_content.append({
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": result_str
                        })

                self.history.append({"role": "user", "content": tool_results_content})

            elif response.stop_reason == "end_turn":
                # Claude has its final answer
                final_text = ""
                for block in response.content:
                    if hasattr(block, 'text'):
                        final_text += block.text

                elapsed = time.time() - turn_start_time
                cost = (self.total_tokens_in * 1.0 + self.total_tokens_out * 5.0) / 1_000_000
                cost_this_query = cost - self.total_cost
                self.total_cost = cost

                self.turn_log.append({
                    'query': user_query,
                    'tools_called': tools_called_this_query,
                    'turns_used': turns_used,
                    'elapsed_sec': round(elapsed, 2),
                    'cost_usd': round(cost_this_query, 5),
                })

                return {
                    'answer': final_text.strip(),
                    'tools_called': tools_called_this_query,
                    'turns_used': turns_used,
                    'elapsed_sec': round(elapsed, 2),
                    'cost_usd_this_query': round(cost_this_query, 5),
                    'cost_usd_session_total': round(self.total_cost, 5),
                }

            else:
                return {
                    'answer': f"[Agent stopped unexpectedly: {response.stop_reason}]",
                    'tools_called': tools_called_this_query,
                    'turns_used': turns_used,
                    'elapsed_sec': round(time.time() - turn_start_time, 2),
                }

        # Hit max_turns without resolution
        return {
            'answer': f"[Agent exceeded max_turns ({self.max_turns}). Tools called: {tools_called_this_query}]",
            'tools_called': tools_called_this_query,
            'turns_used': self.max_turns,
            'elapsed_sec': round(time.time() - turn_start_time, 2),
        }


# ============================================================
# Convenience function
# ============================================================
def ask_agent(query: str, verbose=False):
    """Single-shot helper that creates a fresh session and asks one query."""
    session = AgentSession()
    return session.ask(query, verbose=verbose)