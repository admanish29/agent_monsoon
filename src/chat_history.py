"""
chat_history.py — Persistence layer for chat conversations.

Stores conversations in a single JSON file at data/chat_history.json.
Each conversation has:
  - id (timestamp-based, unique)
  - title (auto-generated from first user message)
  - messages (list of {role, content} — text only, simplified for storage)
  - stats (turns_used, total_cost, tools_called_summary)
  - created_at, updated_at (ISO timestamps)

NOTE: We store TEXT messages, not raw Anthropic content blocks.
When resuming a conversation, we rebuild the agent's history from text.
Claude doesn't need the original tool_use blocks to continue meaningfully.
"""

import json
import uuid
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional


HISTORY_PATH = Path(__file__).parent.parent / "data" / "chat_history.json"


def _ensure_file_exists():
    """Create empty history file if it doesn't exist."""
    if not HISTORY_PATH.exists():
        HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        HISTORY_PATH.write_text("[]", encoding="utf-8")


def list_conversations() -> List[Dict]:
    """Return summaries of all stored conversations, newest first."""
    _ensure_file_exists()
    try:
        raw = HISTORY_PATH.read_text(encoding="utf-8")
        all_convs = json.loads(raw)
    except (json.JSONDecodeError, FileNotFoundError):
        return []

    all_convs.sort(key=lambda c: c.get("updated_at", ""), reverse=True)

    return [
        {
            "id":            c["id"],
            "title":         c.get("title", "Untitled"),
            "message_count": len(c.get("messages", [])),
            "created_at":    c.get("created_at"),
            "updated_at":    c.get("updated_at"),
            "total_cost":    c.get("stats", {}).get("total_cost", 0.0),
        }
        for c in all_convs
    ]


def load_conversation(conv_id: str) -> Optional[Dict]:
    """Return the full conversation dict by ID, or None if not found."""
    _ensure_file_exists()
    all_convs = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    for c in all_convs:
        if c["id"] == conv_id:
            return c
    return None


def save_conversation(conv_id: str, title: str, messages: List[Dict], stats: Dict) -> str:
    """Insert or update a conversation. Returns the conversation ID."""
    _ensure_file_exists()
    all_convs = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))

    now_iso = datetime.now().isoformat(timespec="seconds")

    existing_idx = next((i for i, c in enumerate(all_convs) if c["id"] == conv_id), None)
    if existing_idx is not None:
        all_convs[existing_idx]["title"]      = title
        all_convs[existing_idx]["messages"]   = messages
        all_convs[existing_idx]["stats"]      = stats
        all_convs[existing_idx]["updated_at"] = now_iso
    else:
        all_convs.append({
            "id":         conv_id,
            "title":      title,
            "messages":   messages,
            "stats":      stats,
            "created_at": now_iso,
            "updated_at": now_iso,
        })

    HISTORY_PATH.write_text(json.dumps(all_convs, indent=2, ensure_ascii=False), encoding="utf-8")
    return conv_id


def delete_conversation(conv_id: str) -> bool:
    """Remove a conversation by ID. Returns True if deleted, False if not found."""
    _ensure_file_exists()
    all_convs = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    new_list = [c for c in all_convs if c["id"] != conv_id]
    if len(new_list) == len(all_convs):
        return False
    HISTORY_PATH.write_text(json.dumps(new_list, indent=2, ensure_ascii=False), encoding="utf-8")
    return True


def new_conversation_id() -> str:
    """Generate a unique conversation ID."""
    return f"conv_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"


def make_title_from_query(query: str, max_words: int = 8) -> str:
    """Auto-generate a clean title from the first user query."""
    words = query.strip().split()
    if not words:
        return "Untitled"
    title = " ".join(words[:max_words])
    if len(words) > max_words:
        title += "…"
    return title