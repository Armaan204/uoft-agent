"""
api/main.py - FastAPI application entrypoint.
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from api.limiter import limiter
from api.routers.acorn import router as acorn_router
from api.routers.auth import router as auth_router
from api.routers.chat import router as chat_router
from api.routers.courses import router as courses_router
from api.routers.graduation import router as graduation_router

app = FastAPI(title="UofT Agent API", version="0.1.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

if os.getenv("ENVIRONMENT") != "production":
    from api.routers.admin import router as admin_router
    app.include_router(admin_router, prefix="/admin")


def _allowed_origins() -> list[str]:
    origins = {
        "http://localhost:5173",
        "http://localhost:3000",
        "https://uoft-agent.com",
    }
    frontend_url = os.getenv("FRONTEND_URL")
    if frontend_url:
        origins.add(frontend_url.rstrip("/"))

    extra_origins = os.getenv("CORS_ORIGINS", "")
    for origin in extra_origins.split(","):
        cleaned = origin.strip().rstrip("/")
        if cleaned:
            origins.add(cleaned)

    return sorted(origins)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/auth")
app.include_router(courses_router, prefix="/api/courses")
app.include_router(chat_router, prefix="/api/chat")
app.include_router(acorn_router, prefix="/api/acorn")
app.include_router(graduation_router, prefix="/api/graduation")


@app.get("/")
def health_check():
    return {"status": "ok"}
