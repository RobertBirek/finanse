"""Short DB phases separated from bounded local decoding and one non-retried HTTP."""

import asyncio
import hashlib
import math
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, cast

from sqlalchemy import or_, select

from app.advisor.ai_provider import elapsed_ms, record_usage
from app.config import settings
from app.database import async_session_factory
from app.documents.images import ImageNormalizationError, normalize_image
from app.documents.models import Document
from app.documents.receipt_read_client import extract_receipt_items
from app.documents.receipt_read_config import get_receipt_read_config, owner_receipt_config
from app.documents.receipt_read_jobs import (
    ReceiptReadPrepared,
    claim_receipt_read,
    fail_receipt_read_preparation,
    finish_receipt_read,
    recover_receipt_reads,
    reserve_receipt_read_dispatch,
)
from app.documents.receipt_read_models import ReceiptReadJob
from app.documents.receipt_read_policy import reconcile_receipt_read_policy
from app.documents.service import UPLOAD_DIR, read_verified_document_content


class ReadQueue(Protocol):
    async def enqueue_job(self, function: str, *args: str, _job_id: str) -> object: ...


async def process_receipt_read(ctx: dict[str, object], job_id: str) -> None:
    del ctx
    config = get_receipt_read_config(settings)
    parsed = uuid.UUID(job_id)
    async with async_session_factory() as db:
        await reconcile_receipt_read_policy(db, config)
        locator = await db.get(ReceiptReadJob, parsed)
        if config and locator:
            config = await owner_receipt_config(db, locator.user_id, config, linearize=True)
        claim = (
            await claim_receipt_read(db, parsed, now=datetime.now(UTC), config=config)
            if config
            else None
        )
        path: Path | None = None
        mime = ""
        if claim:
            doc = await db.get(Document, claim.document_id)
            assert doc is not None
            path = UPLOAD_DIR / doc.storage_path
            mime = doc.mime_type
        await db.commit()
    if not claim or not config or path is None:
        return
    try:
        original = await asyncio.to_thread(
            read_verified_document_content, path, claim.source_sha256
        )
        edge = min(config.max_edge, math.isqrt(config.max_pixels))
        jpeg = await normalize_image(
            original, mime, max_edge=edge, max_output_bytes=config.max_bytes
        )
        prepared = ReceiptReadPrepared(jpeg, hashlib.sha256(jpeg).hexdigest(), edge**2)
    except (OSError, ImageNormalizationError) as error:
        async with async_session_factory() as db:
            await fail_receipt_read_preparation(
                db,
                claim,
                now=datetime.now(UTC),
                config=config,
                retryable=isinstance(error, OSError),
            )
            await db.commit()
        return
    async with async_session_factory() as db:
        current = get_receipt_read_config(settings)
        await reconcile_receipt_read_policy(db, current)
        if current:
            current = await owner_receipt_config(db, claim.user_id, current, linearize=True)
        reserved = (
            await reserve_receipt_read_dispatch(
                db, claim, prepared, now=datetime.now(UTC), config=current
            )
            if current
            else False
        )
        await db.commit()
    if not reserved or current is None:
        return
    start = time.monotonic()
    outcome = await extract_receipt_items(prepared.jpeg, config=current)
    await record_usage(
        claim.user_id,
        current.model,
        "operation",
        "provider_error" if outcome.error_code else "ok",
        elapsed_ms(start),
        None,
        purpose="receipt",
        input_tokens=outcome.input_tokens,
        output_tokens=outcome.output_tokens,
    )
    async with async_session_factory() as db:
        current = get_receipt_read_config(settings)
        await reconcile_receipt_read_policy(db, current)
        if current:
            current = await owner_receipt_config(db, claim.user_id, current, linearize=True)
            await finish_receipt_read(
                db, claim, outcome, prepared, now=datetime.now(UTC), config=current
            )
        await db.commit()


async def dispatch_receipt_reads(ctx: dict[str, object]) -> None:
    now = datetime.now(UTC)
    async with async_session_factory() as db:
        await reconcile_receipt_read_policy(db, get_receipt_read_config(settings))
        await recover_receipt_reads(
            db, now=now, limit=settings.DOCUMENT_RECEIPT_ITEMS_DISPATCH_BATCH
        )
        ids = list(
            (
                await db.scalars(
                    select(ReceiptReadJob.id)
                    .where(
                        ReceiptReadJob.state == "pending",
                        or_(
                            ReceiptReadJob.next_attempt_at.is_(None),
                            ReceiptReadJob.next_attempt_at <= now,
                        ),
                    )
                    .order_by(ReceiptReadJob.created_at, ReceiptReadJob.id)
                    .limit(settings.DOCUMENT_RECEIPT_ITEMS_DISPATCH_BATCH)
                )
            ).all()
        )
        await db.commit()
    redis = cast(ReadQueue, ctx["redis"])
    for ident in ids:
        await redis.enqueue_job("process_receipt_read", str(ident), _job_id=f"receipt-read:{ident}")
