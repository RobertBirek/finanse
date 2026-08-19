from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import log_security_event
from app.config import settings
from app.database import get_db
from app.identity.models import User
from app.identity.schemas import UserCreate, UserLogin, UserResponse
from app.identity.service import (
    authenticate,
    create_session,
    create_user,
    get_active_session,
    get_user_by_email,
    get_user_by_id,
    revoke_session,
)
from app.security.rate_limit import RateLimitUnavailable, check_rate_limit

router = APIRouter()

COOKIE_NAME = "advisor_session"
CSRF_COOKIE_NAME = "advisor_csrf"


def set_session_cookies(response: Response, session_token: str, csrf_token: str) -> None:
    secure = settings.ENVIRONMENT == "production"
    max_age = settings.SESSION_EXPIRE_MINUTES * 60
    response.set_cookie(
        key=COOKIE_NAME,
        value=session_token,
        httponly=True,
        secure=secure,
        samesite="strict",
        max_age=max_age,
        path="/",
    )
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        httponly=False,
        secure=secure,
        samesite="strict",
        max_age=max_age,
        path="/",
    )


async def get_current_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    session_token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> User:
    if session_token is None:
        await log_security_event("session_rejected", "missing-session")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    session = await get_active_session(db, session_token)
    if session is None:
        from app.identity.service import hash_session_token

        await log_security_event("session_rejected", hash_session_token(session_token))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    user = await get_user_by_id(db, session.user_id)
    if user is None or not user.is_active:
        await log_security_event("session_rejected", str(session.id))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    session.last_seen_at = datetime.now(UTC)
    await db.flush()
    return user


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    data: UserCreate, response: Response, db: Annotated[AsyncSession, Depends(get_db)]
):
    if not settings.registration_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    existing = await get_user_by_email(db, data.email)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = await create_user(db, data)
    session_token, csrf_token, _ = await create_session(db, user.id)
    set_session_cookies(response, session_token, csrf_token)

    return user


@router.post("/login", status_code=status.HTTP_204_NO_CONTENT)
async def login(
    data: UserLogin,
    response: Response,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    client_ip = request.client.host if request.client is not None else "unknown"
    identifier = f"{client_ip}|{data.email.strip().lower()}"
    try:
        limit = await check_rate_limit(
            "login",
            identifier,
            settings.LOGIN_RATE_LIMIT,
            settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS,
        )
    except RateLimitUnavailable:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Service unavailable"
        )
    if not limit.allowed:
        await log_security_event(
            "rate_limited",
            limit.identifier_hash,
            state={"scope": "login", "identifier_hash": limit.identifier_hash},
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Request limit exceeded",
            headers={"Retry-After": str(limit.retry_after)},
        )

    user = await authenticate(db, data.email, data.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )

    session_token, csrf_token, _ = await create_session(db, user.id)
    set_session_cookies(response, session_token, csrf_token)
    await log_security_event("login_success", str(user.id), user_id=user.id)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
):
    if session_token is not None:
        session = await get_active_session(db, session_token)
        await revoke_session(db, session_token)
        if session is not None:
            await log_security_event("logout", str(session.user_id), user_id=session.user_id)
    response.delete_cookie(key=COOKIE_NAME)
    response.delete_cookie(key=CSRF_COOKIE_NAME)


@router.get("/me", response_model=UserResponse)
async def me(current_user: Annotated[User, Depends(get_current_user)]):
    return current_user
