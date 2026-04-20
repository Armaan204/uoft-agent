"""
api/routers/chat.py - Agent chat route.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from agent.agent import run as run_agent
from api.dependencies import get_current_user

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    quercus_token: str


@router.post("")
async def chat(payload: ChatRequest, current_user: dict = Depends(get_current_user)):
    del current_user
    loop = asyncio.get_event_loop()
    try:
        answer, tool_calls = await loop.run_in_executor(
            None,
            lambda: run_agent(
                payload.message,
                token=payload.quercus_token,
                verbose=False,
                return_tool_calls=True,
            ),
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    return {"answer": answer, "tool_calls": tool_calls}
