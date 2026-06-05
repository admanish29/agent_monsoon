"""
pages/2_💬_Ask_Agent.py — Conversational agent (Chat) page.

Session 4.2b: with persistent archive.
- Sidebar lists all past conversations (newest first)
- Click any to resume — restores text history + rebuilds AgentSession
- Auto-save after every agent reply
- Auto-title from first user message
- Delete button per conversation
"""

import streamlit as st
import time

from src.agent import AgentSession
from src.chat_history import (
    list_conversations,
    load_conversation,
    save_conversation,
    delete_conversation,
    new_conversation_id,
    make_title_from_query,
)


# ============================================================
# Page setup
# ============================================================
st.set_page_config(
    page_title="Ask Agent · Agent Monsoon",
    page_icon="💬",
    layout="wide",
)


# ============================================================
# Styling
# ============================================================
st.markdown("""
<style>
    footer {visibility: hidden;}
    #MainMenu {visibility: hidden;}

    .page-title {
        background: linear-gradient(135deg, #00D4FF 0%, #0077B6 50%, #4A90E2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        font-size: 36px;
        font-weight: 800;
        letter-spacing: -1px;
        margin-bottom: 6px;
    }
    .page-subtitle {
        color: #8a93a8;
        font-size: 14px;
        margin-bottom: 24px;
    }
    .msg-stats {
        font-size: 11px;
        color: #6b7387;
        margin-top: 6px;
        padding-top: 6px;
        border-top: 1px solid rgba(31, 42, 68, 0.6);
        letter-spacing: 0.3px;
    }
    .msg-stats .tool-pill {
        display: inline-block;
        background: rgba(0, 212, 255, 0.1);
        color: #00D4FF;
        padding: 2px 8px;
        border-radius: 4px;
        margin-right: 6px;
        border: 1px solid rgba(0, 212, 255, 0.2);
        font-weight: 500;
    }
    /* Sidebar conversation item */
    .conv-item-active {
        color: #00D4FF;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================
# Header
# ============================================================
st.markdown('<div class="page-title">💬 Ask Agent Monsoon</div>', unsafe_allow_html=True)
st.markdown('<p class="page-subtitle">Ask anything about IEX data — dates, blocks, periods, patterns, anomalies. Multi-turn memory enabled, conversations auto-saved.</p>', unsafe_allow_html=True)


# ============================================================
# Session-state initialization
# ============================================================
# active_conv_id  — ID of currently-open conversation (None = new unsaved chat)
# agent_session   — live AgentSession holding the agent's internal multi-turn memory
# messages_display — list of {role, content, stats?} that we render in the UI
# pending_delete  — conv_id queued for deletion (handled at top of next rerun)

if "active_conv_id" not in st.session_state:
    st.session_state.active_conv_id = None
if "agent_session" not in st.session_state:
    st.session_state.agent_session = AgentSession()
if "messages_display" not in st.session_state:
    st.session_state.messages_display = []
if "pending_delete" not in st.session_state:
    st.session_state.pending_delete = None


# ============================================================
# Handle pending delete (must happen before sidebar rebuilds)
# ============================================================
if st.session_state.pending_delete:
    delete_conversation(st.session_state.pending_delete)
    # If user deleted the currently-active conversation, reset state
    if st.session_state.pending_delete == st.session_state.active_conv_id:
        st.session_state.active_conv_id = None
        st.session_state.agent_session = AgentSession()
        st.session_state.messages_display = []
    st.session_state.pending_delete = None
    st.rerun()


# ============================================================
# Helper functions
# ============================================================
def render_stats_footer(stats: dict) -> str:
    tools = stats.get("tools_called", [])
    pills = "".join([f'<span class="tool-pill">{t}</span>' for t in tools]) if tools else '<span style="color:#6b7387;">no tools called</span>'
    return f"""
    <div class="msg-stats">
        🔧 {pills}
        &nbsp;·&nbsp; ⏱️ {stats.get('elapsed_sec', 0):.1f}s
        &nbsp;·&nbsp; 💰 ${stats.get('cost_usd_this_query', 0):.5f}
        &nbsp;·&nbsp; 🔁 {stats.get('turns_used', 0)} turn(s)
    </div>
    """


def save_current_conversation():
    """Persist current conversation to disk. Auto-generates title from first user msg."""
    if not st.session_state.messages_display:
        return  # nothing to save

    # Ensure we have an ID
    if st.session_state.active_conv_id is None:
        st.session_state.active_conv_id = new_conversation_id()

    # Title from first user message
    first_user_msg = next(
        (m["content"] for m in st.session_state.messages_display if m["role"] == "user"),
        "Untitled"
    )
    title = make_title_from_query(first_user_msg)

    # Strip stats from messages before saving (don't need to persist them)
    text_messages = [
        {"role": m["role"], "content": m["content"]}
        for m in st.session_state.messages_display
    ]

    session = st.session_state.agent_session
    stats = {
        "total_cost":       session.total_cost,
        "total_tokens_in":  session.total_tokens_in,
        "total_tokens_out": session.total_tokens_out,
        "turn_log":         session.turn_log[-20:],   # last 20 turns max — keeps file size sane
    }

    save_conversation(
        st.session_state.active_conv_id,
        title,
        text_messages,
        stats,
    )


def start_new_conversation():
    """Reset state for a fresh chat."""
    st.session_state.active_conv_id = None
    st.session_state.agent_session = AgentSession()
    st.session_state.messages_display = []


def load_and_resume_conversation(conv_id: str):
    """Load conversation from disk and rebuild AgentSession history from text."""
    conv = load_conversation(conv_id)
    if conv is None:
        st.error(f"Conversation {conv_id} not found")
        return

    st.session_state.active_conv_id = conv_id
    st.session_state.messages_display = [
        {"role": m["role"], "content": m["content"]} for m in conv["messages"]
    ]

    # Rebuild AgentSession from text messages.
    # Note: Claude doesn't need the original tool_use blocks to continue —
    # the text-only history is enough context for reasonable continuations.
    new_session = AgentSession()
    for m in conv["messages"]:
        new_session.history.append({"role": m["role"], "content": m["content"]})
    # Restore session-level stats
    stats = conv.get("stats", {})
    new_session.total_cost       = stats.get("total_cost", 0.0)
    new_session.total_tokens_in  = stats.get("total_tokens_in", 0)
    new_session.total_tokens_out = stats.get("total_tokens_out", 0)
    st.session_state.agent_session = new_session


# ============================================================
# Render existing conversation in main pane
# ============================================================
for msg in st.session_state.messages_display:
    avatar = "🧑" if msg["role"] == "user" else "⚡"
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and "stats" in msg:
            st.markdown(render_stats_footer(msg["stats"]), unsafe_allow_html=True)


# ============================================================
# Chat input
# ============================================================
user_query = st.chat_input("Ask about a date, block, period, or pattern...")

if user_query:
    st.session_state.messages_display.append({
        "role": "user",
        "content": user_query,
    })

    with st.chat_message("user", avatar="🧑"):
        st.markdown(user_query)

    with st.chat_message("assistant", avatar="⚡"):
        with st.spinner("Thinking..."):
            try:
                result = st.session_state.agent_session.ask(user_query)
                st.markdown(result["answer"])
                st.markdown(render_stats_footer(result), unsafe_allow_html=True)
                st.session_state.messages_display.append({
                    "role": "assistant",
                    "content": result["answer"],
                    "stats": result,
                })

                # Auto-save after every agent reply
                save_current_conversation()

            except Exception as e:
                st.error(f"Agent error: {e}")


# ============================================================
# Sidebar — current session + past conversations
# ============================================================
with st.sidebar:
    # ---- Current Session Stats ----
    st.markdown("### 💬 Current Session")
    session = st.session_state.agent_session
    n_user_msgs = sum(1 for m in st.session_state.messages_display if m["role"] == "user")
    st.markdown(f"**Messages:** {n_user_msgs}")
    st.markdown(f"**Cost:** ${session.total_cost:.5f}")
    st.markdown(f"**Tokens:** {session.total_tokens_in:,} in / {session.total_tokens_out:,} out")

    if st.button("🔄 New Conversation", use_container_width=True, type="primary"):
        start_new_conversation()
        st.rerun()

    st.markdown("---")

    # ---- Past Conversations ----
    st.markdown("### 📚 Past Conversations")

    past = list_conversations()
    if not past:
        st.caption("_No past conversations yet — they'll appear here after your first chat._")
    else:
        st.caption(f"_{len(past)} total · click to resume_")
        for conv in past[:20]:   # show latest 20 to keep sidebar tidy
            is_active = conv["id"] == st.session_state.active_conv_id

            # 2-column layout: title button + delete button
            col_title, col_delete = st.columns([5, 1])
            with col_title:
                # Active conversation gets a different button style via label prefix
                label = f"▶ {conv['title']}" if is_active else conv['title']
                if st.button(
                    label,
                    key=f"load_{conv['id']}",
                    use_container_width=True,
                    help=f"{conv['message_count']} messages · ${conv['total_cost']:.4f}",
                ):
                    load_and_resume_conversation(conv["id"])
                    st.rerun()
            with col_delete:
                if st.button("🗑️", key=f"del_{conv['id']}", help="Delete this conversation"):
                    st.session_state.pending_delete = conv["id"]
                    st.rerun()

    st.markdown("---")
    st.markdown("### 💡 Sample queries")
    st.caption("Try asking:")
    st.markdown("""
    - *"What happened on 5 May 2026?"*
    - *"Which 3 days had the worst RMTI in March 2026?"*
    - *"Compare Q1 2025 vs Q1 2026"*
    - *"Hourly pattern of DAM-GDAM premium in May 2026"*
    """)