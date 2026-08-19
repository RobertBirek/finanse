import hmac
from typing import Annotated, NoReturn

from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import log_security_event
from app.config import settings
from app.database import get_db
from app.identity.service import get_active_session
from app.identity.service import hash_session_token as hash_secret

SESSION_COOKIE_NAME = "advisor_session"
CSRF_COOKIE_NAME = "advisor_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
PUBLIC_AUTH_PATHS = {"/api/auth/login", "/api/auth/register"}


async def _forbidden(session_token: str | None) -> NoReturn:
    opaque_session_id = hash_secret(session_token) if session_token else "missing-session"
    await log_security_event("csrf_rejected", opaque_session_id)
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


async def require_csrf(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
    csrf_cookie: Annotated[str | None, Cookie(alias=CSRF_COOKIE_NAME)] = None,
) -> None:
    if settings.ENVIRONMENT != "production" or request.method in SAFE_METHODS:
        return

    if request.headers.get("origin") not in settings.trusted_origins:
        await _forbidden(session_token)

    if request.url.path in PUBLIC_AUTH_PATHS:
        return

    csrf_header = request.headers.get(CSRF_HEADER_NAME)
    if not session_token or not csrf_cookie or not csrf_header:
        await _forbidden(session_token)
    if not hmac.compare_digest(csrf_header, csrf_cookie):
        await _forbidden(session_token)

    session = await get_active_session(db, session_token)
    if session is None or not hmac.compare_digest(
        session.csrf_token_hash, hash_secret(csrf_header)
    ):
        await _forbidden(session_token)
