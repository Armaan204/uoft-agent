"""
api/main.py - FastAPI application entrypoint.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers.acorn import router as acorn_router
from api.routers.auth import router as auth_router
from api.routers.chat import router as chat_router
from api.routers.courses import router as courses_router

app = FastAPI(title="UofT Agent API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "https://uoft-agent.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/auth")
app.include_router(courses_router, prefix="/api/courses")
app.include_router(chat_router, prefix="/api/chat")
app.include_router(acorn_router, prefix="/api/acorn")


@app.get("/")
def health_check():
    return {"status": "ok"}
