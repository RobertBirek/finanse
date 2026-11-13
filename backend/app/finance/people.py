"""Owner-approved person metadata commands, serialized with finance mutations."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import log_event
from app.finance.categorization_context import digest
from app.finance.document_guards import lock_document_mutations
from app.finance.models import Account, FinanceCommandReceipt, FinancialTransaction
from app.finance.person_context import PersonError, get_person_link_context
from app.finance.person_models import FinancePerson, PersonTransactionLink
from app.finance.person_schemas import (
    GiftLinkRequest,
    GiftUnlinkRequest,
    PersonCreate,
    PersonLinkContext,
    PersonResponse,
    PersonUpdate,
)


async def _person(db: AsyncSession, owner: uuid.UUID, person_id: uuid.UUID) -> FinancePerson:
    row = await db.scalar(
        select(FinancePerson)
        .where(
            FinancePerson.id == person_id,
            FinancePerson.user_id == owner,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise LookupError("Person not found")
    return row


async def _reference(
    db: AsyncSession,
    owner: uuid.UUID,
    account_id: uuid.UUID | None,
    person_id: uuid.UUID | None = None,
) -> None:
    if account_id is None:
        return
    account = await db.scalar(
        select(Account).where(Account.id == account_id, Account.user_id == owner)
    )
    if account is None:
        raise LookupError("Account not found")
    if account.is_budget_account:
        raise PersonError("reference_budget_account", "Wybierz konto pozabudżetowe.", 422)
    existing = await db.scalar(
        select(FinancePerson.id).where(FinancePerson.reference_account_id == account_id)
    )
    if existing is not None and existing != person_id:
        raise PersonError("reference_assigned", "Konto ma już przypisaną osobę.")


async def create_person(db: AsyncSession, owner: uuid.UUID, data: PersonCreate) -> PersonResponse:
    data = PersonCreate.model_validate(data.model_dump())
    await lock_document_mutations(db, owner)
    await _reference(db, owner, data.reference_account_id)
    row = FinancePerson(user_id=owner, **data.model_dump())
    db.add(row)
    await db.flush()
    result = PersonResponse.model_validate(row)
    await log_event(
        db,
        owner,
        "finance_person",
        str(row.id),
        "create_finance_person",
        new_state=result.model_dump(mode="json"),
    )
    return result


async def update_person(
    db: AsyncSession, owner: uuid.UUID, person_id: uuid.UUID, data: PersonUpdate
) -> PersonResponse:
    data = PersonUpdate.model_validate(data.model_dump(exclude_unset=True))
    await lock_document_mutations(db, owner)
    row = await _person(db, owner, person_id)
    if row.version != data.expected_version:
        raise PersonError("person_version_conflict", "Person changed; odśwież dane osoby.")
    changes = data.model_dump(exclude_unset=True, exclude={"expected_version"})
    if "reference_account_id" in changes:
        await _reference(db, owner, data.reference_account_id, row.id)
    before = PersonResponse.model_validate(row)
    for key, value in changes.items():
        setattr(row, key, value)
    if any(getattr(before, key) != value for key, value in changes.items()):
        row.version += 1
    await db.flush()
    result = PersonResponse.model_validate(row)
    await log_event(
        db,
        owner,
        "finance_person",
        str(row.id),
        "update_finance_person",
        old_state=before.model_dump(mode="json"),
        new_state=result.model_dump(mode="json"),
    )
    return result


async def _gift_command(
    db: AsyncSession,
    owner: uuid.UUID,
    transaction_id: uuid.UUID,
    data: GiftLinkRequest | GiftUnlinkRequest,
    key: str,
    *,
    unlink: bool,
) -> PersonLinkContext:
    if not key or len(key) > 255:
        raise PersonError("invalid_key", "Nieprawidłowy klucz zapisu.", 422)
    await lock_document_mutations(db, owner)
    # Validate transaction ownership even on replay; do not disclose another owner's UUID.
    if (
        await db.scalar(
            select(FinancialTransaction.id).where(
                FinancialTransaction.id == transaction_id,
                FinancialTransaction.user_id == owner,
            )
        )
        is None
    ):
        raise LookupError("Transaction not found")
    action = "unlink_person_gift_v1" if unlink else "link_person_gift_v1"
    request_hash = digest({"transaction_id": transaction_id, **data.model_dump(mode="json")})
    receipt = await db.scalar(
        select(FinanceCommandReceipt).where(
            FinanceCommandReceipt.user_id == owner,
            FinanceCommandReceipt.action == action,
            FinanceCommandReceipt.key == key,
        )
    )
    if receipt:
        if receipt.request_hash != request_hash:
            raise PersonError("idempotency_key_reused", "idempotency key dotyczy innego zapisu.")
        return PersonLinkContext.model_validate(receipt.response_json)
    existing = await db.scalar(
        select(PersonTransactionLink)
        .where(
            PersonTransactionLink.transaction_id == transaction_id,
            PersonTransactionLink.user_id == owner,
        )
        .execution_options(populate_existing=True)
    )
    target_id = (
        existing.person_id
        if unlink and existing
        else (data.person_id if isinstance(data, GiftLinkRequest) else None)
    )
    person = await _person(db, owner, target_id) if target_id else None
    await db.scalar(
        select(FinancialTransaction)
        .where(
            FinancialTransaction.id == transaction_id,
            FinancialTransaction.user_id == owner,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    ctx = await get_person_link_context(db, owner, transaction_id)
    if ctx.snapshot != data.expected_transaction_snapshot:
        raise PersonError(
            "person_snapshot_conflict", "Transaction changed; odśwież dane transakcji."
        )
    if unlink:
        if existing:
            await db.delete(existing)
    else:
        if not ctx.eligible:
            raise PersonError("invalid_gift", ctx.reason or "Nieprawidłowa darowizna.", 422)
        if person is None:
            raise LookupError("Person not found")
        if not person.is_active:
            raise PersonError("inactive_person", "Person inactive; wybierz aktywną osobę.")
        if existing and existing.person_id != person.id:
            raise PersonError("gift_assigned", "Gift assigned; najpierw odepnij poprzednią osobę.")
        if not existing:
            db.add(
                PersonTransactionLink(
                    user_id=owner, person_id=person.id, transaction_id=transaction_id
                )
            )
    await db.flush()
    result = await get_person_link_context(db, owner, transaction_id)
    await log_event(
        db,
        owner,
        "financial_transaction",
        str(transaction_id),
        action,
        old_state=ctx.model_dump(mode="json"),
        new_state=result.model_dump(mode="json"),
    )
    db.add(
        FinanceCommandReceipt(
            user_id=owner,
            action=action,
            key=key,
            request_hash=request_hash,
            entity_id=transaction_id,
            result_ids=[str(transaction_id)],
            response_json=result.model_dump(mode="json"),
        )
    )
    await db.flush()
    return result


async def link_gift(
    db: AsyncSession,
    owner: uuid.UUID,
    transaction_id: uuid.UUID,
    data: GiftLinkRequest,
    *,
    idempotency_key: str,
) -> PersonLinkContext:
    return await _gift_command(db, owner, transaction_id, data, idempotency_key, unlink=False)


async def unlink_gift(
    db: AsyncSession,
    owner: uuid.UUID,
    transaction_id: uuid.UUID,
    data: GiftUnlinkRequest,
    *,
    idempotency_key: str,
) -> PersonLinkContext:
    return await _gift_command(db, owner, transaction_id, data, idempotency_key, unlink=True)
