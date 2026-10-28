import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.documents.review_schemas import ReviewResponse
from app.documents.review_service import get_review, prepare_review, request_ocr_retry
from app.finance.bills_schemas import MutationContext
from app.identity.models import User
from app.identity.router import get_current_user

router = APIRouter()


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
    except LookupError:
        return JSONResponse(content={"detail": "Document not found"}, status_code=404)
    except ValueError:
        return JSONResponse(content={"detail": "Idempotency key conflict"}, status_code=409)
    await db.commit()
    await db.refresh(revision)
    if revision.status == "pending":
        from app.worker import enqueue_prepare_document_review

        await enqueue_prepare_document_review(str(revision.id))
    review = await get_review(db, current_user.id, document_id)
    assert review is not None
    return review


@router.post("/{document_id}/retry-ocr", status_code=202)
async def retry_document_ocr(
    document_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
):
    try:
        document = await request_ocr_retry(
            db,
            current_user.id,
            document_id,
            context=MutationContext(idempotency_key=idempotency_key),
        )
    except LookupError:
        return JSONResponse(content={"detail": "Document not found"}, status_code=404)
    await db.commit()
    from app.worker import enqueue_process_document

    await enqueue_process_document(str(document.id))
    return {"id": str(document.id), "status": "pending"}
