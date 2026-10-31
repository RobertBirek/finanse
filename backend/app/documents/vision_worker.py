"""Vision worker with explicit DB/CPU/network phases."""

import asyncio
import hashlib
import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.config import settings
from app.database import async_session_factory
from app.documents.images import ImageNormalizationError, normalize_image
from app.documents.job_service import (
    JobOutcome,
    claim_processing_job,
    finish_processing_job,
    reserve_vision_call,
)
from app.documents.models import Document
from app.documents.service import UPLOAD_DIR, read_verified_document_content
from app.documents.vision_client import VisionProviderError, extract_image_review
from app.documents.vision_config import get_vision_config


async def process_document_job(ctx: dict[str, object], job_id: str) -> None:
    del ctx
    now = datetime.now(UTC)
    async with async_session_factory() as db:
        claim = await claim_processing_job(db, uuid.UUID(job_id), now=now)
        await db.commit()
    if claim is None or claim.kind != "vision":
        return
    config = get_vision_config(settings)
    if config is None:
        async with async_session_factory() as db:
            await finish_processing_job(
                db, claim, JobOutcome(error_code="configuration_missing"), now=now
            )
            await db.commit()
        return
    async with async_session_factory() as db:
        document = (
            await db.execute(select(Document).where(Document.id == claim.document_id))
        ).scalar_one_or_none()
        await db.commit()
    if document is None:
        return
    try:
        source = await asyncio.to_thread(
            read_verified_document_content, UPLOAD_DIR / document.storage_path, document.sha256_hash
        )
        derivative = await normalize_image(
            source,
            document.mime_type,
            max_edge=settings.DOCUMENT_VISION_MAX_EDGE,
            max_output_bytes=settings.DOCUMENT_VISION_MAX_BYTES,
        )
    except (ImageNormalizationError, OSError):
        async with async_session_factory() as db:
            await finish_processing_job(db, claim, JobOutcome(error_code="invalid_image"), now=now)
            await db.commit()
        return
    # The durable quota reservation is the last short transaction before HTTP.
    async with async_session_factory() as db:
        if not await reserve_vision_call(db, claim, now=datetime.now(UTC), config=config):
            await db.commit()
            return
        await db.commit()
    try:
        extraction = await extract_image_review(derivative, config=config)
        outcome = JobOutcome(
            suggestion=extraction.suggestion,
            warnings=extraction.warnings,
            source_sha256=hashlib.sha256(source).hexdigest(),
            derivative_sha256=hashlib.sha256(derivative).hexdigest(),
            provider=config.provider,
            model=config.model,
            prompt_version=config.prompt_version,
            schema_version=config.schema_version,
        )
    except VisionProviderError as error:
        outcome = JobOutcome(error_code=error.code, retryable=error.retryable)
    async with async_session_factory() as db:
        await finish_processing_job(db, claim, outcome, now=datetime.now(UTC))
        await db.commit()
