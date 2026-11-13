"""The database must not permit a cross-owner person, account or gift relation."""

import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from app.database import Base
from app.finance.models import Account, FinancialTransaction
from app.main import app  # noqa: F401 - register the full test schema

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_people_are_separate_from_financial_accounts(db_session):
    assert "finance_people" in Base.metadata.tables
    assert "person_transaction_links" in Base.metadata.tables


async def records(db):
    from app.finance.person_models import FinancePerson

    owner, other = uuid.uuid4(), uuid.uuid4()
    account = Account(user_id=owner, name="Reference", type="checking", is_budget_account=False)
    txn = FinancialTransaction(user_id=owner, description="Gift", type="income")
    person = FinancePerson(user_id=owner, name="Person")
    foreign = FinancePerson(user_id=other, name="Person")
    db.add_all([account, txn, person, foreign])
    await db.flush()
    return owner, other, account, txn, person, foreign


@pytest.mark.parametrize("foreign_side", ["person", "transaction", "account"])
async def test_person_composite_foreign_keys_reject_foreign_owner(db_session, foreign_side):
    from app.finance.person_models import FinancePerson, PersonTransactionLink

    owner, other, account, txn, _person, foreign = await records(db_session)
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            if foreign_side == "account":
                db_session.add(
                    FinancePerson(
                        user_id=other, name="Foreign ref", reference_account_id=account.id
                    )
                )
            else:
                db_session.add(
                    PersonTransactionLink(
                        user_id=other if foreign_side == "transaction" else owner,
                        person_id=foreign.id,
                        transaction_id=txn.id,
                    )
                )
            await db_session.flush()


async def test_one_gift_and_one_account_shortcut_cannot_be_duplicated(db_session):
    from app.finance.person_models import FinancePerson, PersonTransactionLink

    owner, _, account, txn, person, _ = await records(db_session)
    person.reference_account_id = account.id
    db_session.add(PersonTransactionLink(user_id=owner, person_id=person.id, transaction_id=txn.id))
    await db_session.flush()
    for row in [
        FinancePerson(user_id=owner, name="Same", reference_account_id=account.id),
        PersonTransactionLink(user_id=owner, person_id=person.id, transaction_id=txn.id),
    ]:
        with pytest.raises(IntegrityError):
            async with db_session.begin_nested():
                db_session.add(row)
                await db_session.flush()
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await db_session.execute(
                delete(FinancialTransaction).where(FinancialTransaction.id == txn.id)
            )


async def test_equal_person_names_do_not_merge_identities(db_session):
    from app.finance.person_models import FinancePerson

    owner = uuid.uuid4()
    first, second = [FinancePerson(user_id=owner, name="Person") for _ in range(2)]
    db_session.add_all([first, second])
    await db_session.flush()
    assert first.id != second.id


async def test_person_input_normalizes_and_rejects_invalid_nulls(db_session):
    from app.finance.person_schemas import PersonCreate, PersonUpdate

    assert PersonCreate(name="  Person  ").name == "Person"
    assert PersonUpdate(expected_version=1, reference_account_id=None).reference_account_id is None
    for data in [
        {"name": " "},
        {"name": "x" * 201},
        {"name": "x\0"},
        {"name": "x", "user_id": str(uuid.uuid4())},
    ]:
        with pytest.raises(ValidationError):
            PersonCreate.model_validate(data)
    for field in ["name", "is_active"]:
        with pytest.raises(ValidationError):
            PersonUpdate.model_validate({"expected_version": 1, field: None})
