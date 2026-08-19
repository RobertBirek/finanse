"""Server-side session service tests."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.identity.models import Session, User
from app.identity.service import create_session, get_active_session, revoke_session


@pytest.mark.integration
async def test_create_session_only_persists_hashes_and_active_lookup_uses_constant_time_compare(
    db_session, monkeypatch
):
    user = User(email="session@example.com", password_hash="hash", display_name="Session User")
    db_session.add(user)
    await db_session.flush()
    comparisons: list[tuple[str, str]] = []

    def compare_digest(left: str, right: str) -> bool:
        comparisons.append((left, right))
        return left == right

    monkeypatch.setattr("app.identity.service.hmac.compare_digest", compare_digest)
    raw_token, raw_csrf_token, session = await create_session(db_session, user.id)
    persisted = (
        await db_session.execute(select(Session).where(Session.id == session.id))
    ).scalar_one()

    assert raw_token not in persisted.token_hash
    assert raw_csrf_token not in persisted.csrf_token_hash
    assert persisted.token_hash != raw_token
    assert persisted.csrf_token_hash != raw_csrf_token
    assert await get_active_session(db_session, raw_token) == persisted
    assert comparisons


@pytest.mark.integration
async def test_expired_and_revoked_sessions_are_not_active(db_session):
    user = User(email="inactive@example.com", password_hash="hash", display_name="Inactive User")
    db_session.add(user)
    await db_session.flush()
    raw_expired, _, expired = await create_session(db_session, user.id)
    expired.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    raw_revoked, _, _ = await create_session(db_session, user.id)
    assert await revoke_session(db_session, raw_revoked)

    assert await get_active_session(db_session, raw_expired) is None
    assert await get_active_session(db_session, raw_revoked) is None
    assert not await revoke_session(db_session, "not-a-session")
