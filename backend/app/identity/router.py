from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

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
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    session = await get_active_session(db, session_token)
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    user = await get_user_by_id(db, session.user_id)
    if user is None or not user.is_active:
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
async def login(data: UserLogin, response: Response, db: Annotated[AsyncSession, Depends(get_db)]):
    user = await authenticate(db, data.email, data.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )

    session_token, csrf_token, _ = await create_session(db, user.id)
    set_session_cookies(response, session_token, csrf_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
):
    if session_token is not None:
        await revoke_session(db, session_token)
    response.delete_cookie(key=COOKIE_NAME)
    response.delete_cookie(key=CSRF_COOKIE_NAME)


@router.get("/me", response_model=UserResponse)
async def me(current_user: Annotated[User, Depends(get_current_user)]):
    return current_user
