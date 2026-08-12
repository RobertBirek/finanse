import socket

import asyncpg
from conftest import (
    DEFAULT_TEST_DATABASE_URL,
    is_connection_unavailable_error,
    is_safe_test_database_url,
)
from sqlalchemy.exc import OperationalError


def test_default_test_database_url_keeps_approved_fallback():
    assert DEFAULT_TEST_DATABASE_URL == (
        "postgresql+asyncpg://finanse:finanse@localhost:5432/finanse_test"
    )


def test_docker_test_database_url_is_safe():
    assert is_safe_test_database_url(
        "postgresql+asyncpg://finanse:finanse@127.0.0.1:55432/finanse_test"
    )


def test_production_database_url_is_not_safe_for_schema_cleanup():
    assert not is_safe_test_database_url(
        "postgresql+asyncpg://finanse:secret@localhost:5432/finanse"
    )


def test_remote_test_named_database_is_not_safe_for_schema_cleanup():
    assert not is_safe_test_database_url(
        "postgresql+asyncpg://finanse:secret@db.internal:5432/finanse_test"
    )


def test_malformed_database_url_is_not_safe_for_schema_cleanup():
    assert not is_safe_test_database_url("not-a-database-url")


def test_connection_error_is_skippable_when_wrapped_by_sqlalchemy():
    error = OperationalError(
        "connect",
        {},
        asyncpg.exceptions.ConnectionDoesNotExistError("database unavailable"),
    )
    assert is_connection_unavailable_error(error)


def test_os_connection_error_is_skippable():
    assert is_connection_unavailable_error(ConnectionRefusedError("connection refused"))


def test_wrapped_os_error_with_connection_refused_contents_is_skippable():
    error = OperationalError(
        "connect",
        {},
        OSError("Multiple exceptions: ConnectionRefusedError: [Errno 111] connection failed"),
    )
    assert is_connection_unavailable_error(error)


def test_database_not_ready_error_is_skippable():
    assert is_connection_unavailable_error(asyncpg.exceptions.CannotConnectNowError())


def test_permission_os_error_is_not_skippable():
    assert not is_connection_unavailable_error(PermissionError("permission denied"))


def test_dns_error_is_skippable():
    assert is_connection_unavailable_error(socket.gaierror("name resolution failed"))


def test_permission_error_is_not_skippable_when_wrapped_by_sqlalchemy():
    error = OperationalError(
        "create schema",
        {},
        asyncpg.exceptions.InsufficientPrivilegeError("permission denied"),
    )
    assert not is_connection_unavailable_error(error)
