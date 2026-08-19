"""Server-side session service tests."""

import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.identity.models import Session, User
from app.identity.service import create_session, get_active_session, revoke_session

BACKEND_DIR = Path(__file__).resolve().parents[2]
SESSION_REVISION = "c9d8e7f6a5b4"
SESSION_PREDECESSOR = "1dbfe88dfb1b"


def run_alembic(*arguments: str) -> None:
    environment = os.environ | {"DATABASE_URL": os.environ["TEST_DATABASE_URL"]}
    subprocess.run(
        [str(BACKEND_DIR / ".venv/bin/alembic"), *arguments],
        cwd=BACKEND_DIR,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )


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


@pytest.mark.integration
async def test_server_side_session_migration_backfills_legacy_rows_and_cycles(db_session):
    run_alembic("stamp", SESSION_REVISION)
    run_alembic("downgrade", SESSION_PREDECESSOR)

    await db_session.execute(
        text(
            "INSERT INTO users (id, email, password_hash, display_name, is_active) "
            "VALUES ('11111111-1111-1111-1111-111111111111', 'legacy@example.com', "
            "'hash', 'Legacy User', true)"
        )
    )
    for session_id in (
        "22222222-2222-2222-2222-222222222222",
        "33333333-3333-3333-3333-333333333333",
    ):
        await db_session.execute(
            text(
                "INSERT INTO sessions (id, user_id, token_hash, expires_at) VALUES "
                "(:id, '11111111-1111-1111-1111-111111111111', 'legacy-token', now())"
            ),
            {"id": session_id},
        )
    await db_session.commit()

    run_alembic("upgrade", SESSION_REVISION)
    rows = (
        await db_session.execute(
            text("SELECT token_hash, csrf_token_hash, revoked_at FROM sessions ORDER BY id")
        )
    ).all()
    assert len(rows) == 2
    assert {row.token_hash for row in rows} != {"legacy-token"}
    assert len({row.token_hash for row in rows}) == 2
    assert all(row.csrf_token_hash and row.revoked_at for row in rows)

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO sessions (id, user_id, token_hash, csrf_token_hash, expires_at) "
                    "VALUES ('44444444-4444-4444-4444-444444444444', "
                    "'11111111-1111-1111-1111-111111111111', :token_hash, 'csrf', now())"
                ),
                {"token_hash": rows[0].token_hash},
            )

    await db_session.rollback()
    run_alembic("downgrade", SESSION_PREDECESSOR)
    run_alembic("upgrade", SESSION_REVISION)
    assert (
        await db_session.execute(text("SELECT count(*) FROM sessions WHERE revoked_at IS NOT NULL"))
    ).scalar_one() == 2
