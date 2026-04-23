"""
api/routers/chat.py - Agent chat route.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from agent.agent import run as run_agent
from api.dependencies import get_current_user
from auth.user_store import UserStoreError, get_quercus_token

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    quercus_token: str | None = None


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
            ),
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    return {"answer": answer, "tool_calls": tool_calls}
