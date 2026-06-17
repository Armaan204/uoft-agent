"""
api/routers/chat.py - Agent chat route.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, validator

from limits import parse as parse_rate
from limits.storage import MemoryStorage
from limits.strategies import FixedWindowRateLimiter

from api.agent.agent import run as run_agent
from api.dependencies import get_current_user

_chat_limiter = FixedWindowRateLimiter(MemoryStorage())
_chat_rate = parse_rate("10/minute")
from api.services.chat_history_service import (
    ChatHistoryServiceError,
    delete_conversation,
    get_conversation,
    get_conversation_messages,
    list_conversations,
    save_exchange,
)
from api.auth.user_store import UserStoreError, get_quercus_token

router = APIRouter(tags=["chat"])
logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str
    quercus_token: str | None = None
    conversation_id: str | None = None

    @validator("message")
    @classmethod
    def message_max_length(cls, v: str) -> str:
        if len(v) > 2000:
            raise ValueError("Message exceeds the 2000-character limit")
        return v


def _resolve_token(quercus_token: str | None, current_user: dict) -> str:
    if quercus_token:
        return quercus_token
    try:
        saved = get_quercus_token(current_user["user_id"])
    except UserStoreError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not saved:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No Quercus token provided and no saved token found.",
        )
    return saved


@router.post("")
async def chat(payload: ChatRequest, current_user: dict = Depends(get_current_user)):
    quercus_token = _resolve_token(payload.quercus_token, current_user)
    if not _chat_limiter.hit(_chat_rate, quercus_token):
        raise HTTPException(status_code=429, detail="Rate limit exceeded — try again in a minute.")
    conversation_id = str(payload.conversation_id or "").strip() or None

    history: list[dict] = []
    if conversation_id:
        try:
            history = get_conversation_messages(current_user["user_id"], conversation_id)
        except ChatHistoryServiceError as exc:
            logger.warning("Failed to load chat history for context user_id=%s conversation_id=%s error=%s",
                           current_user.get("user_id"), conversation_id, exc)

    loop = asyncio.get_event_loop()
    try:
        answer, tool_calls = await loop.run_in_executor(
            None,
            lambda: run_agent(
                payload.message,
                token=quercus_token,
                user_id=current_user["user_id"],
                verbose=False,
                return_tool_calls=True,
                history=history,
            ),
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    if conversation_id:
        try:
            save_exchange(
                current_user["user_id"],
                conversation_id,
                payload.message,
                answer,
                tool_calls=tool_calls,
            )
        except ChatHistoryServiceError as exc:
            logger.warning(
                "Failed to persist chat exchange user_id=%s conversation_id=%s error=%s",
                current_user.get("user_id"),
                conversation_id,
                exc,
            )

    return {"answer": answer, "tool_calls": tool_calls, "conversation_id": conversation_id}


@router.get("/history")
def history(current_user: dict = Depends(get_current_user)):
    try:
        return {"conversations": list_conversations(current_user["user_id"])}
    except ChatHistoryServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/history/{conversation_id}")
def history_detail(conversation_id: str, current_user: dict = Depends(get_current_user)):
    try:
        return get_conversation(current_user["user_id"], conversation_id)
    except ChatHistoryServiceError as exc:
        detail = str(exc)
        status_code = status.HTTP_404_NOT_FOUND if detail == "Chat conversation not found" else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.delete("/history/{conversation_id}")
def history_delete(conversation_id: str, current_user: dict = Depends(get_current_user)):
    try:
        delete_conversation(current_user["user_id"], conversation_id)
    except ChatHistoryServiceError as exc:
        detail = str(exc)
        status_code = status.HTTP_404_NOT_FOUND if detail == "Chat conversation not found" else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=detail) from exc
    return {"status": "deleted"}
