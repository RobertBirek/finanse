import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.documents.lifecycle import DocumentLifecycleError
from app.documents.review_schemas import ReviewResponse
from app.documents.review_service import (
    get_review,
    prepare_review,
    prepare_vision_review,
    request_ocr_retry,
)
from app.finance.bills_schemas import MutationContext
from app.identity.models import User
from app.identity.router import get_current_user
from app.security.rate_limit import limit_document_processing_action

router = APIRouter()
logger = logging.getLogger(__name__)
processing_action_rate_limit = limit_document_processing_action(get_current_user)


@router.get("/{document_id}/review", response_model=ReviewResponse)
async def get_document_review(
    document_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    review = await get_review(db, current_user.id, document_id)
    if review is None:
        return JSONResponse(content={"detail": "Review not found"}, status_code=404)
    return review


@router.post("/{document_id}/review/prepare", response_model=ReviewResponse, status_code=202)
async def prepare_document_review(
    document_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    refresh: bool = False,
):
    try:
        revision = await prepare_review(
            db,
            current_user.id,
            document_id,
            refresh=refresh,
            context=MutationContext(idempotency_key=idempotency_key),
        )
    except DocumentLifecycleError as error:
        return JSONResponse(content={"detail": error.code, "code": error.code}, status_code=409)
    except LookupError:
        return JSONResponse(content={"detail": "Document not found"}, status_code=404)
    except ValueError as error:
        detail = (
            "use_vision_action" if str(error) == "use_vision_action" else "Idempotency key conflict"
        )
        return JSONResponse(content={"detail": detail}, status_code=409)
    await db.commit()
    await db.refresh(revision)
    if revision.status == "pending":
        from app.worker import enqueue_prepare_document_review

        await enqueue_prepare_document_review(str(revision.id))
    review = await get_review(db, current_user.id, document_id)
    assert review is not None
    return review


@router.post("/{document_id}/vision/prepare", response_model=ReviewResponse, status_code=202)
async def prepare_document_vision(
    document_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    _limit: Annotated[None, Depends(processing_action_rate_limit)],
):
    try:
        revision, job_id, is_new = await prepare_vision_review(
            db,
            current_user.id,
            document_id,
            context=MutationContext(idempotency_key=idempotency_key),
        )
    except DocumentLifecycleError as error:
        return JSONResponse(content={"detail": error.code, "code": error.code}, status_code=409)
    except LookupError:
        return JSONResponse(content={"detail": "Document not found"}, status_code=404)
    except ValueError as error:
        detail = str(error)
        return JSONResponse(
            content={"detail": detail},
            status_code=422 if detail == "vision_requires_image" else 409,
        )
    await db.commit()
    if is_new:
        from app.worker import enqueue_process_document_job

        try:
            await enqueue_process_document_job(str(job_id))
        except (OSError, TimeoutError, RedisError):
            logger.warning("Vision review %s awaits queue recovery", revision.id)
    review = await get_review(db, current_user.id, document_id)
    assert review is not None
    return review


@router.post("/{document_id}/retry-ocr", status_code=202)
async def retry_document_ocr(
    document_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    _limit: Annotated[None, Depends(processing_action_rate_limit)],
):
    try:
        result = await request_ocr_retry(
            db,
            current_user.id,
            document_id,
            context=MutationContext(idempotency_key=idempotency_key),
        )
    except DocumentLifecycleError as error:
        return JSONResponse(content={"detail": error.code, "code": error.code}, status_code=409)
    except LookupError:
        return JSONResponse(content={"detail": "Document not found"}, status_code=404)
    except ValueError:
        return JSONResponse(content={"detail": "Idempotency key conflict"}, status_code=409)
    await db.commit()
    if result.is_new:
        from app.worker import enqueue_process_document, enqueue_process_document_job

        try:
            if result.document.processing_method == "vision":
                job_id = result.response_json["job_id"]
                await enqueue_process_document_job(str(job_id))
            else:
                await enqueue_process_document(str(result.document.id))
        except (OSError, TimeoutError, RedisError):
            # The committed pending document is recovered by the periodic dispatcher.
            logger.warning("Document %s awaits retry OCR queue recovery", result.document.id)
    return result.response_json
