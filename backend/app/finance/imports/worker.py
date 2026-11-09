"""ARQ is delivery only; durable preparation and lease recovery live in PostgreSQL."""

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Protocol, cast

from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from app.database import async_session_factory
from app.documents.import_storage import ImportStorageError
from app.finance.imports.contracts import ImportFailure, ParsedImport
from app.finance.imports.errors import ImportError
from app.finance.imports.jobs import (
    claim_import_job,
    finish_import_job,
    load_import_document,
    recover_import_jobs,
)
from app.finance.imports.parsers.registry import parse_import
from app.finance.imports.storage import _parser_input


class ImportQueue(Protocol):
    async def enqueue_job(self, function: str, *args: str, _job_id: str) -> object: ...


async def dispatch_import_jobs(ctx: dict[str, object]) -> None:
    async with async_session_factory() as db:
        ids = await recover_import_jobs(db, datetime.now(UTC))
        await db.commit()
    queue = cast(ImportQueue, ctx["redis"])
    for job_id in ids:
        try:
            await queue.enqueue_job(
                "process_import_job", str(job_id), _job_id=f"finance-import:{job_id}"
            )
        except (RedisError, OSError, RuntimeError):
            # The committed queued/expired intent remains available to the next dispatch.
            continue


async def process_import_job(ctx: dict[str, object], job_id: str) -> None:
    try:
        identifier = uuid.UUID(job_id)
    except ValueError:
        return
    try:
        async with async_session_factory() as db:
            claim = await claim_import_job(db, identifier, datetime.now(UTC))
            await db.commit()
        if claim is None:
            return
        async with async_session_factory() as db:
            packet = await load_import_document(db, claim)
            await db.commit()
        if packet is None:
            return
    except SQLAlchemyError:
        # A failed/uncertain claim never authorizes parsing; its lease is recoverable.
        return
    document, kind = packet
    outcome: ParsedImport | ImportFailure
    try:
        data = await _parser_input(document)
        outcome = await asyncio.to_thread(parse_import, data, kind)
    except (ImportError, ImportStorageError) as error:
        outcome = ImportFailure(error.code, retryable=False)
    except (OSError, TimeoutError):
        outcome = ImportFailure("source_unavailable", retryable=True)
    except ValueError:
        outcome = ImportFailure("parser_invalid_output", retryable=False)
    async with async_session_factory() as db:
        await finish_import_job(db, claim, outcome)
        await db.commit()
