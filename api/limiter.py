"""
api/limiter.py - Shared rate limiter for FastAPI routers.

Keys by user_id extracted from the JWT Bearer token so each authenticated user
gets their own quota.  Falls back to remote IP when no valid token is present.

The module also exposes a `limit()` decorator that wraps slowapi's decorator but
gracefully skips rate-checking when no Request object is available — this keeps
unit tests (which call handlers directly without a Request) working unchanged.
"""

from __future__ import annotations

import os
from functools import wraps

from jose import JWTError, jwt
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request


def _user_key(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        secret = os.getenv("JWT_SECRET", "")
        if secret:
            try:
                payload = jwt.decode(token, secret, algorithms=["HS256"])
                user_id = payload.get("user_id")
                if user_id is not None:
                    return str(user_id)
            except JWTError:
                pass
    return get_remote_address(request)


limiter = Limiter(key_func=_user_key)


def limit(limit_value: str):
    """Rate-limit decorator that skips gracefully when no Request is available."""
    slowapi_decorator = limiter.limit(limit_value)

    def decorator(func):
        limited = slowapi_decorator(func)

        @wraps(func)
        async def wrapper(*args, **kwargs):
            has_request = isinstance(kwargs.get("request"), Request) or any(
                isinstance(a, Request) for a in args
            )
            if has_request:
                return await limited(*args, **kwargs)
            return await func(*args, **kwargs)

        return wrapper

    return decorator
