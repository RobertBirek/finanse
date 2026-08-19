import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.identity.models import Session, User
from app.identity.schemas import UserCreate

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def create_session(db: AsyncSession, user_id: uuid.UUID) -> tuple[str, str, Session]:
    raw_session_token = secrets.token_urlsafe(32)
    raw_csrf_token = secrets.token_urlsafe(32)
    session = Session(
        user_id=user_id,
        token_hash=hash_session_token(raw_session_token),
        csrf_token_hash=hash_session_token(raw_csrf_token),
        expires_at=datetime.now(UTC) + timedelta(minutes=settings.SESSION_EXPIRE_MINUTES),
    )
    db.add(session)
    await db.flush()
    return raw_session_token, raw_csrf_token, session


async def get_active_session(db: AsyncSession, raw_token: str) -> Session | None:
    token_hash = hash_session_token(raw_token)
    result = await db.execute(
        select(Session).where(Session.token_hash == token_hash).with_for_update()
    )
    session = result.scalar_one_or_none()
    if session is None or not hmac.compare_digest(session.token_hash, token_hash):
        return None
    if session.revoked_at is not None or session.expires_at <= datetime.now(UTC):
        return None
    return session


async def revoke_session(db: AsyncSession, raw_token: str) -> bool:
    session = await get_active_session(db, raw_token)
    if session is None:
        return False
    session.revoked_at = datetime.now(UTC)
    await db.flush()
    return True


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def create_user(db: AsyncSession, data: UserCreate) -> User:
    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        display_name=data.display_name,
    )
    db.add(user)
    await db.flush()
    return user


async def authenticate(db: AsyncSession, email: str, password: str) -> User | None:
    user = await get_user_by_email(db, email)
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user
