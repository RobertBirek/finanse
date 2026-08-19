"""Server-side session service tests."""

import asyncio
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.identity.models import Session, User
from app.identity.service import create_session, get_active_session, revoke_session
from app.work.schemas import ProjectCreate
from app.work.service import create_project

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


async def get_session_schema(
    db_session: AsyncSession,
) -> tuple[dict[str, tuple[str, str, int | None]], set[str]]:
    columns = {
        row.column_name: (row.data_type, row.is_nullable, row.character_maximum_length)
        for row in (
            await db_session.execute(
                text(
                    "SELECT column_name, data_type, is_nullable, character_maximum_length "
                    "FROM information_schema.columns "
                    "WHERE table_schema = current_schema() AND table_name = 'sessions'"
                )
            )
        )
    }
    indexes = {
        row.indexname
        for row in (
            await db_session.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE schemaname = current_schema() AND tablename = 'sessions'"
                )
            )
        )
    }
    return columns, indexes


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
async def test_authenticated_transaction_holds_session_lock_until_domain_mutation_commits(
    test_database,
):
    session_factory = async_sessionmaker(test_database, expire_on_commit=False)
    async with session_factory() as setup_session:
        user = User(email="locked@example.com", password_hash="hash", display_name="Locked User")
        setup_session.add(user)
        await setup_session.flush()
        raw_token, _, _ = await create_session(setup_session, user.id)
        await setup_session.commit()

    authenticated = asyncio.Event()
    revoke_started = asyncio.Event()
    revoke_lock_attempted = asyncio.Event()
    allow_commit = asyncio.Event()
    revoked = asyncio.Event()
    loop = asyncio.get_running_loop()

    def observe_revoke_lock(
        connection, cursor, statement, parameters, context, executemany
    ) -> None:
        if "FROM sessions" in statement and "FOR UPDATE" in statement:
            loop.call_soon_threadsafe(revoke_lock_attempted.set)

    async def protected_mutation() -> None:
        async with session_factory() as protected_session:
            session = await get_active_session(protected_session, raw_token)
            assert session is not None
            await create_project(
                protected_session, session.user_id, ProjectCreate(name="Locked project")
            )
            authenticated.set()
            await allow_commit.wait()
            await protected_session.commit()

    async def logout() -> None:
        await authenticated.wait()
        revoke_started.set()
        async with session_factory() as logout_session:
            assert await revoke_session(logout_session, raw_token)
            await logout_session.commit()
        revoked.set()

    protected_task = asyncio.create_task(protected_mutation())
    await asyncio.wait_for(authenticated.wait(), timeout=1)
    event.listen(test_database.sync_engine, "before_cursor_execute", observe_revoke_lock)
    logout_task = asyncio.create_task(logout())
    try:
        await asyncio.wait_for(revoke_started.wait(), timeout=1)
        await asyncio.wait_for(revoke_lock_attempted.wait(), timeout=1)
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(revoked.wait(), timeout=0.1)
    finally:
        allow_commit.set()
        await asyncio.wait_for(asyncio.gather(protected_task, logout_task), timeout=1)
        event.remove(test_database.sync_engine, "before_cursor_execute", observe_revoke_lock)

    async with session_factory() as verification_session:
        assert await get_active_session(verification_session, raw_token) is None


@pytest.mark.integration
async def test_server_side_session_migration_backfills_legacy_rows_and_cycles(db_session):
    run_alembic("stamp", SESSION_REVISION)
    run_alembic("downgrade", SESSION_PREDECESSOR)
    predecessor_columns, predecessor_indexes = await get_session_schema(db_session)
    assert predecessor_columns["token_hash"] == ("character varying", "NO", 255)
    assert "csrf_token_hash" not in predecessor_columns
    assert "revoked_at" not in predecessor_columns
    assert "last_seen_at" not in predecessor_columns
    assert "ix_sessions_token_hash" not in predecessor_indexes

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
    upgraded_columns, upgraded_indexes = await get_session_schema(db_session)
    assert upgraded_columns["token_hash"] == ("character varying", "NO", 64)
    assert upgraded_columns["csrf_token_hash"] == ("character varying", "NO", 64)
    assert upgraded_columns["revoked_at"] == ("timestamp with time zone", "YES", None)
    assert upgraded_columns["last_seen_at"] == ("timestamp with time zone", "YES", None)
    assert "ix_sessions_token_hash" in upgraded_indexes

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
    downgraded_columns, downgraded_indexes = await get_session_schema(db_session)
    assert downgraded_columns["token_hash"] == ("character varying", "NO", 255)
    assert "csrf_token_hash" not in downgraded_columns
    assert "revoked_at" not in downgraded_columns
    assert "last_seen_at" not in downgraded_columns
    assert "ix_sessions_token_hash" not in downgraded_indexes

    run_alembic("upgrade", SESSION_REVISION)
    upgraded_again_columns, upgraded_again_indexes = await get_session_schema(db_session)
    assert upgraded_again_columns["token_hash"] == ("character varying", "NO", 64)
    assert upgraded_again_columns["csrf_token_hash"] == ("character varying", "NO", 64)
    assert upgraded_again_columns["revoked_at"] == ("timestamp with time zone", "YES", None)
    assert upgraded_again_columns["last_seen_at"] == ("timestamp with time zone", "YES", None)
    assert "ix_sessions_token_hash" in upgraded_again_indexes
    assert (
        await db_session.execute(text("SELECT count(*) FROM sessions WHERE revoked_at IS NOT NULL"))
    ).scalar_one() == 2
