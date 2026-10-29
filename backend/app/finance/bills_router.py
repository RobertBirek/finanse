import uuid
from datetime import date
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.finance.bill_coverage import decide_coverage, get_coverage_candidates, unlink_coverage
from app.finance.bill_payments import (
    allocate_payment,
    get_payment_candidates,
    record_bill_payment,
    unlink_payment,
)
from app.finance.bills import (
    approve_bill,
    attach_source,
    find_duplicate_bills,
    get_bill,
    list_bills,
    prepare_bill,
    set_bill_lifecycle,
    update_bill,
)
from app.finance.bills_schemas import (
    AllocationCreate,
    BillApprove,
    BillCandidatePage,
    BillFilters,
    BillLifecycleUpdate,
    BillPage,
    BillPaymentCreate,
    BillResponse,
    BillUpdate,
    CoverageDecision,
    DuplicateCandidate,
    MutationContext,
)
from app.identity.models import User
from app.identity.router import get_current_user

router = APIRouter(prefix="/bills")


def _context(key: str) -> MutationContext:
    return MutationContext(idempotency_key=key)


def _error(error: Exception) -> HTTPException:
    if isinstance(error, LookupError):
        return HTTPException(404, "Bill or linked record not found")
    if isinstance(error, RuntimeError) or str(error) == "idempotency_key_reused":
        return HTTPException(409, "Version or idempotency conflict")
    return HTTPException(422, str(error))


@router.post(
    "/prepare/{document_id}", response_model=BillResponse, status_code=status.HTTP_201_CREATED
)
async def prepare_bill_endpoint(
    document_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
):
    try:
        response = await prepare_bill(
            db, current_user.id, document_id, context=_context(idempotency_key)
        )
        await db.commit()
        return response
    except (LookupError, RuntimeError, ValueError) as error:
        await db.rollback()
        raise _error(error)


@router.get("", response_model=BillPage)
async def list_bills_endpoint(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    kind: str | None = None,
    review: str | None = None,
    declaration: str | None = None,
    lifecycle: str | None = None,
):
    return await list_bills(
        db,
        current_user.id,
        limit=limit,
        offset=offset,
        filters=BillFilters.model_validate(
            {"kind": kind, "review": review, "declaration": declaration, "lifecycle": lifecycle}
        ),
    )


@router.get("/{bill_id}", response_model=BillResponse)
async def get_bill_endpoint(
    bill_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    response = await get_bill(db, current_user.id, bill_id)
    if response is None:
        raise HTTPException(404, "Bill not found")
    return response


@router.get("/{bill_id}/candidates", response_model=BillCandidatePage)
async def payment_candidates_endpoint(
    bill_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    query: Annotated[str | None, Query(max_length=200)] = None,
    date_from: date | None = None,
    date_to: date | None = None,
    include_older: bool = False,
):
    try:
        return await get_payment_candidates(
            db,
            current_user.id,
            bill_id,
            limit=limit,
            offset=offset,
            query=query,
            date_from=date_from,
            date_to=date_to,
            include_older=include_older,
        )
    except LookupError as error:
        raise _error(error)


@router.get("/{bill_id}/coverage-candidates")
async def coverage_candidates_endpoint(
    bill_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        return await get_coverage_candidates(db, current_user.id, bill_id)
    except LookupError as error:
        raise _error(error)


@router.post("/{bill_id}/coverage", response_model=BillResponse)
async def decide_coverage_endpoint(
    bill_id: uuid.UUID,
    data: CoverageDecision,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
):
    try:
        response = await decide_coverage(
            db, current_user.id, bill_id, data, context=_context(idempotency_key)
        )
        await db.commit()
        return response
    except (LookupError, RuntimeError, ValueError) as error:
        await db.rollback()
        raise _error(error)


@router.delete("/{bill_id}/coverage", response_model=BillResponse)
async def unlink_coverage_endpoint(
    bill_id: uuid.UUID,
    expected_version: int,
    confirm_unlink: bool,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
):
    try:
        response = await unlink_coverage(
            db,
            current_user.id,
            bill_id,
            expected_version,
            confirm_unlink=confirm_unlink,
            context=_context(idempotency_key),
        )
        await db.commit()
        return response
    except (LookupError, RuntimeError, ValueError) as error:
        await db.rollback()
        raise _error(error)


@router.post("/{bill_id}/allocations", response_model=BillResponse)
@router.put("/{bill_id}/allocations", response_model=BillResponse)
async def allocate_payment_endpoint(
    bill_id: uuid.UUID,
    data: AllocationCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
):
    try:
        response = await allocate_payment(
            db, current_user.id, bill_id, data, context=_context(idempotency_key)
        )
        await db.commit()
        return response
    except (LookupError, RuntimeError, ValueError) as error:
        await db.rollback()
        raise _error(error)


@router.delete("/{bill_id}/allocations/{allocation_id}", response_model=BillResponse)
async def unlink_payment_endpoint(
    bill_id: uuid.UUID,
    allocation_id: uuid.UUID,
    expected_version: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
):
    try:
        response = await unlink_payment(
            db,
            current_user.id,
            bill_id,
            allocation_id,
            expected_version,
            context=_context(idempotency_key),
        )
        await db.commit()
        return response
    except (LookupError, RuntimeError, ValueError) as error:
        await db.rollback()
        raise _error(error)


@router.post("/{bill_id}/payments", response_model=BillResponse)
async def record_payment_endpoint(
    bill_id: uuid.UUID,
    data: BillPaymentCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
):
    try:
        response = await record_bill_payment(
            db, current_user.id, bill_id, data, context=_context(idempotency_key)
        )
        await db.commit()
        return response
    except (LookupError, RuntimeError, ValueError) as error:
        await db.rollback()
        raise _error(error)


@router.post("/{bill_id}/approve", response_model=BillResponse)
async def approve_bill_endpoint(
    bill_id: uuid.UUID,
    data: BillApprove,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
):
    try:
        response = await approve_bill(
            db, current_user.id, bill_id, data, context=_context(idempotency_key)
        )
        await db.commit()
        return response
    except (LookupError, RuntimeError, ValueError) as error:
        await db.rollback()
        raise _error(error)


@router.patch("/{bill_id}", response_model=BillResponse)
async def update_bill_endpoint(
    bill_id: uuid.UUID,
    data: BillUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
):
    try:
        response = await update_bill(
            db, current_user.id, bill_id, data, context=_context(idempotency_key)
        )
        await db.commit()
        return response
    except (LookupError, RuntimeError, ValueError) as error:
        await db.rollback()
        raise _error(error)


@router.get("/{bill_id}/duplicates", response_model=list[DuplicateCandidate])
async def duplicate_candidates(
    bill_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    bill = await get_bill(db, current_user.id, bill_id)
    if bill is None:
        raise HTTPException(404, "Bill not found")
    if None in (bill.kind, bill.supplier_name, bill.description, bill.total_minor, bill.currency):
        return []
    return await find_duplicate_bills(
        db,
        current_user.id,
        BillApprove(
            version=bill.version,
            kind=cast(Any, bill.kind),
            supplier_name=cast(Any, bill.supplier_name),
            description=cast(Any, bill.description),
            supplier_tax_id=bill.supplier_tax_id,
            number=bill.number,
            issue_date=bill.issue_date,
            sale_date=bill.sale_date,
            due_date=bill.due_date,
            payee_iban=bill.payee_iban,
            category_id=bill.category_id,
            payment_account_id=bill.payment_account_id,
            total_minor=cast(Any, bill.total_minor),
            currency=cast(Any, bill.currency),
            declaration=bill.declaration,
        ),
    )


@router.post("/{bill_id}/sources/{document_id}", response_model=BillResponse)
async def attach_source_endpoint(
    bill_id: uuid.UUID,
    document_id: uuid.UUID,
    expected_version: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
):
    try:
        response = await attach_source(
            db,
            current_user.id,
            bill_id,
            document_id,
            expected_version,
            context=_context(idempotency_key),
        )
        await db.commit()
        return response
    except (LookupError, RuntimeError, ValueError) as error:
        await db.rollback()
        raise _error(error)


@router.post("/{bill_id}/lifecycle", response_model=BillResponse)
async def lifecycle_endpoint(
    bill_id: uuid.UUID,
    data: BillLifecycleUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
):
    try:
        response = await set_bill_lifecycle(
            db,
            current_user.id,
            bill_id,
            data.lifecycle,
            data.expected_version,
            context=_context(idempotency_key),
        )
        await db.commit()
        return response
    except (LookupError, RuntimeError, ValueError) as error:
        await db.rollback()
        raise _error(error)
