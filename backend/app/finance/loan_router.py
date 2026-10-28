import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.finance import loans
from app.finance.loan_schemas import (
    LoanCreate,
    LoanDetailResponse,
    LoanInstallmentCreate,
    LoanInstallmentResponse,
    LoanInstallmentUpdate,
    LoanPaymentCandidatesResponse,
    LoanPaymentCreate,
    LoanResponse,
    LoanUpdate,
)
from app.identity.models import User
from app.identity.router import get_current_user

router = APIRouter(prefix="/loans")


def _error(error: Exception) -> HTTPException:
    if isinstance(error, IntegrityError):
        return HTTPException(409, "Loan record conflicts with an existing record")
    if isinstance(error, LookupError):
        return HTTPException(404, str(error))
    return HTTPException(
        409
        if "linked" in str(error).lower()
        or "already" in str(error).lower()
        or "exceeds" in str(error).lower()
        else 422,
        str(error),
    )


@router.get("", response_model=list[LoanResponse])
async def list_loans(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[LoanResponse]:
    return await loans.get_loans(db, current_user.id)


@router.post("", response_model=LoanDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_loan(
    data: LoanCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LoanDetailResponse:
    try:
        loan = await loans.create_loan(db, current_user.id, data)
        return await loans.get_loan(db, current_user.id, loan.id)  # type: ignore[return-value]
    except (ValueError, LookupError, IntegrityError) as error:
        raise _error(error)


@router.get("/{loan_id}", response_model=LoanDetailResponse)
async def get_loan(
    loan_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LoanDetailResponse:
    loan = await loans.get_loan(db, current_user.id, loan_id)
    if loan is None:
        raise HTTPException(404, "Loan not found")
    return loan


@router.patch("/{loan_id}", response_model=LoanDetailResponse)
async def update_loan(
    loan_id: uuid.UUID,
    data: LoanUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LoanDetailResponse:
    try:
        loan = await loans.update_loan(db, current_user.id, loan_id, data)
    except ValueError as error:
        raise _error(error)
    if loan is None:
        raise HTTPException(404, "Loan not found")
    return await loans.get_loan(db, current_user.id, loan.id)  # type: ignore[return-value]


@router.post(
    "/{loan_id}/installments",
    response_model=LoanInstallmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_installment(
    loan_id: uuid.UUID,
    data: LoanInstallmentCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LoanInstallmentResponse:
    try:
        installment = await loans.create_loan_installment(db, current_user.id, loan_id, data)
    except (ValueError, LookupError, IntegrityError) as error:
        raise _error(error)
    detail = await loans.get_loan(db, current_user.id, loan_id)
    return next(row for row in detail.installments if row.id == installment.id)  # type: ignore[union-attr]


@router.patch("/{loan_id}/installments/{installment_id}", response_model=LoanInstallmentResponse)
async def update_installment(
    loan_id: uuid.UUID,
    installment_id: uuid.UUID,
    data: LoanInstallmentUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LoanInstallmentResponse:
    try:
        installment = await loans.update_loan_installment(
            db, current_user.id, loan_id, installment_id, data
        )
    except (ValueError, IntegrityError) as error:
        raise _error(error)
    if installment is None:
        raise HTTPException(404, "Installment not found")
    detail = await loans.get_loan(db, current_user.id, loan_id)
    return next(row for row in detail.installments if row.id == installment.id)  # type: ignore[union-attr]


@router.delete("/{loan_id}/installments/{installment_id}", status_code=204)
async def delete_installment(
    loan_id: uuid.UUID,
    installment_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    try:
        deleted = await loans.delete_loan_installment(db, current_user.id, loan_id, installment_id)
    except ValueError as error:
        raise _error(error)
    if not deleted:
        raise HTTPException(404, "Installment not found")
    return Response(status_code=204)


@router.post("/{loan_id}/installments/{installment_id}/payments", response_model=LoanDetailResponse)
async def link_payment(
    loan_id: uuid.UUID,
    installment_id: uuid.UUID,
    data: LoanPaymentCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LoanDetailResponse:
    try:
        detail = await loans.link_loan_payment(
            db, current_user.id, loan_id, installment_id, data.transaction_id
        )
    except (ValueError, LookupError, IntegrityError) as error:
        raise _error(error)
    if detail is None:
        raise HTTPException(404, "Loan or installment not found")
    return detail


@router.get(
    "/{loan_id}/installments/{installment_id}/payment-candidates",
    response_model=LoanPaymentCandidatesResponse,
)
async def candidates(
    loan_id: uuid.UUID,
    installment_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> LoanPaymentCandidatesResponse:
    result = await loans.get_loan_payment_candidates(
        db, current_user.id, loan_id, installment_id, limit, offset
    )
    if result is None:
        raise HTTPException(404, "Loan or installment not found")
    return result


@router.delete("/{loan_id}/payments/{link_id}", status_code=204)
async def unlink_payment(
    loan_id: uuid.UUID,
    link_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    if not await loans.unlink_loan_payment(db, current_user.id, loan_id, link_id):
        raise HTTPException(404, "Payment link not found")
    return Response(status_code=204)
