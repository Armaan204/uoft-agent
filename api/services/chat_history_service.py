from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from auth.user_store import UserStoreError, get_supabase_client


class ChatHistoryServiceError(RuntimeError):
    """Raised when chat history persistence fails."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conversation_title(seed_text: str | None, max_length: int = 80) -> str:
    text = " ".join(str(seed_text or "").split()).strip()
    if not text:
        return "New chat"
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 1].rstrip()}…"


def _require_user_id(user_id: str | int) -> str | int:
    if user_id in (None, ""):
        raise ChatHistoryServiceError("user_id must be provided")
    return user_id


def _require_conversation_id(conversation_id: str) -> str:
    cleaned = str(conversation_id or "").strip()
    if not cleaned:
        raise ChatHistoryServiceError("conversation_id must be provided")
    return cleaned


def ensure_conversation(user_id: str | int, conversation_id: str, title_seed: str | None = None) -> dict[str, Any]:
    user_id = _require_user_id(user_id)
    conversation_id = _require_conversation_id(conversation_id)
    now = _now_iso()

    try:
        existing = (
            get_supabase_client()
            .table("chat_conversations")
            .select("*")
            .eq("id", conversation_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
    except (UserStoreError, Exception) as exc:
        raise ChatHistoryServiceError("Failed to load chat conversation") from exc

    rows = getattr(existing, "data", None) or []
    if rows:
        row = rows[0]
        updates = {
            "updated_at": now,
            "last_message_at": now,
        }
        if not row.get("title"):
            updates["title"] = _conversation_title(title_seed)

        try:
            response = (
                get_supabase_client()
                .table("chat_conversations")
                .update(updates)
                .eq("id", conversation_id)
                .eq("user_id", user_id)
                .execute()
            )
        except (UserStoreError, Exception) as exc:
            raise ChatHistoryServiceError("Failed to update chat conversation") from exc

        updated_rows = getattr(response, "data", None) or []
        return updated_rows[0] if updated_rows else {**row, **updates}

    payload = {
        "id": conversation_id,
        "user_id": user_id,
        "title": _conversation_title(title_seed),
        "updated_at": now,
        "last_message_at": now,
    }
    try:
        response = (
            get_supabase_client()
            .table("chat_conversations")
            .insert(payload)
            .execute()
        )
    except (UserStoreError, Exception) as exc:
        raise ChatHistoryServiceError("Failed to create chat conversation") from exc

    rows = getattr(response, "data", None) or []
    return rows[0] if rows else payload


def save_message(
    conversation_id: str,
    role: str,
    text: str,
    tool_calls: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    conversation_id = _require_conversation_id(conversation_id)
    normalized_role = str(role or "").strip().lower()
    if normalized_role not in {"user", "assistant"}:
        raise ChatHistoryServiceError("role must be either 'user' or 'assistant'")

    message_text = str(text or "").strip()
    if not message_text:
        raise ChatHistoryServiceError("text must be provided")

    payload = {
        "conversation_id": conversation_id,
        "role": normalized_role,
        "text": message_text,
        "tool_calls": tool_calls or [],
    }
    try:
        response = (
            get_supabase_client()
            .table("chat_messages")
            .insert(payload)
            .execute()
        )
    except (UserStoreError, Exception) as exc:
        raise ChatHistoryServiceError("Failed to save chat message") from exc

    rows = getattr(response, "data", None) or []
    return rows[0] if rows else payload


def save_exchange(
    user_id: str | int,
    conversation_id: str,
    user_text: str,
    assistant_text: str,
    tool_calls: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    conversation = ensure_conversation(user_id, conversation_id, title_seed=user_text)
    save_message(conversation_id, "user", user_text)
    save_message(conversation_id, "assistant", assistant_text, tool_calls=tool_calls)
    return conversation


def list_conversations(user_id: str | int, limit: int = 50) -> list[dict[str, Any]]:
    user_id = _require_user_id(user_id)
    try:
        response = (
            get_supabase_client()
            .table("chat_conversations")
            .select("id,title,created_at,updated_at,last_message_at")
            .eq("user_id", user_id)
            .order("last_message_at", desc=True)
            .limit(limit)
            .execute()
        )
    except (UserStoreError, Exception) as exc:
        raise ChatHistoryServiceError("Failed to list chat conversations") from exc

    return getattr(response, "data", None) or []


def get_conversation(user_id: str | int, conversation_id: str) -> dict[str, Any]:
    user_id = _require_user_id(user_id)
    conversation_id = _require_conversation_id(conversation_id)

    try:
        conversation_response = (
            get_supabase_client()
            .table("chat_conversations")
            .select("id,title,created_at,updated_at,last_message_at")
            .eq("id", conversation_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        messages_response = (
            get_supabase_client()
            .table("chat_messages")
            .select("id,conversation_id,role,text,tool_calls,created_at")
            .eq("conversation_id", conversation_id)
            .order("created_at")
            .execute()
        )
    except (UserStoreError, Exception) as exc:
        raise ChatHistoryServiceError("Failed to load chat conversation") from exc

    conversations = getattr(conversation_response, "data", None) or []
    if not conversations:
        raise ChatHistoryServiceError("Chat conversation not found")

    return {
        **conversations[0],
        "messages": getattr(messages_response, "data", None) or [],
    }


def get_conversation_messages(
    user_id: str | int,
    conversation_id: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Return the most recent `limit` messages for a conversation, oldest-first.

    Returns an empty list if the conversation does not exist or belongs to another user.
    """
    user_id = _require_user_id(user_id)
    conversation_id = _require_conversation_id(conversation_id)
    try:
        conv_resp = (
            get_supabase_client()
            .table("chat_conversations")
            .select("id")
            .eq("id", conversation_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if not (getattr(conv_resp, "data", None) or []):
            return []
        msg_resp = (
            get_supabase_client()
            .table("chat_messages")
            .select("role,text")
            .eq("conversation_id", conversation_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
    except (UserStoreError, Exception) as exc:
        raise ChatHistoryServiceError("Failed to load conversation messages") from exc

    msgs = getattr(msg_resp, "data", None) or []
    return list(reversed(msgs))


def delete_conversation(user_id: str | int, conversation_id: str) -> None:
    user_id = _require_user_id(user_id)
    conversation_id = _require_conversation_id(conversation_id)

    try:
        existing = (
            get_supabase_client()
            .table("chat_conversations")
            .select("id")
            .eq("id", conversation_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
    except (UserStoreError, Exception) as exc:
        raise ChatHistoryServiceError("Failed to load chat conversation") from exc

    rows = getattr(existing, "data", None) or []
    if not rows:
        raise ChatHistoryServiceError("Chat conversation not found")

    try:
        (
            get_supabase_client()
            .table("chat_messages")
            .delete()
            .eq("conversation_id", conversation_id)
            .execute()
        )
        (
            get_supabase_client()
            .table("chat_conversations")
            .delete()
            .eq("id", conversation_id)
            .eq("user_id", user_id)
            .execute()
        )
    except (UserStoreError, Exception) as exc:
        raise ChatHistoryServiceError("Failed to delete chat conversation") from exc
