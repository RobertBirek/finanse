import uuid
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEvent
from app.finance import service
from app.finance.currency_correction import apply_correction, preview_correction
from app.finance.models import Posting
from app.finance.nbp_rates import NbpRate, NbpRateProvider
from app.finance.schemas import AccountCreate, CategoryCreate, PostingCreate, TransactionCreate
from app.identity.models import User

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


class Rates(NbpRateProvider):
    async def get_rate(self, currency: str, rate_date: date) -> NbpRate | None:
        assert currency == "EUR"
        return NbpRate(rate=4.1234, effective_date=rate_date, source="nbp")


@pytest.fixture(autouse=True)
def official_rates(monkeypatch):
    # The external official-rate boundary is deterministic in integration tests.
    monkeypatch.setattr(NbpRateProvider, "get_rate", Rates.get_rate)


async def setup(db: AsyncSession):
    owner = uuid.uuid4()
    db.add(
        User(
            id=owner,
            email=f"{owner}@example.invalid",
            password_hash="unused",
            display_name="Synthetic",
        )
    )
    await db.flush()
    account = await service.create_account(
        db, owner, AccountCreate(name="Synthetic EUR", type="checking")
    )
    account.source = "actual"
    category = await service.create_category(
        db, owner, CategoryCreate(name="Synthetic cost", type="expense")
    )
    transaction = await service.create_transaction(
        db,
        owner,
        TransactionCreate(
            description="Synthetic expense",
            type="expense",
            transaction_date=date(2026, 1, 5),
            postings=[
                PostingCreate(
                    account_id=account.id, source_amount=101, base_amount_pln=101, direction="debit"
                ),
                PostingCreate(
                    category_id=category.id,
                    source_amount=101,
                    base_amount_pln=101,
                    direction="credit",
                ),
            ],
        ),
    )
    return owner, account, transaction


async def test_preview_is_read_only_and_apply_preserves_source_values_and_audits(db_session):
    owner, account, transaction = await setup(db_session)
    before_ids = set((await db_session.scalars(select(Posting.id))).all())
    plan = await preview_correction(db_session, owner, account.id, Rates())
    assert account.currency == "PLN"
    assert all(p.source_currency == "PLN" for p in transaction.postings)
    await apply_correction(db_session, owner, plan, approved_digest=plan.digest())
    assert account.currency == "EUR"
    for p in transaction.postings:
        assert p.source_currency == "EUR" and p.source_amount == 101
        assert p.base_amount_pln == 416
        assert str(p.fx_rate) == "4.123400"
        assert p.fx_rate_source == "nbp:2026-01-05"
    assert set((await db_session.scalars(select(Posting.id))).all()) == before_ids
    events = (await db_session.scalars(select(AuditEvent))).all()
    assert len(events) == 1 and events[0].action == "correct_source_currency"
    assert events[0].old_state["account"]["currency"] == "PLN"
    assert events[0].new_state["account"]["currency"] == "EUR"


async def test_apply_rejects_unapproved_plan_and_drift(db_session):
    owner, account, transaction = await setup(db_session)
    plan = await preview_correction(db_session, owner, account.id, Rates())
    with pytest.raises(ValueError, match="approval"):
        await apply_correction(db_session, owner, plan, approved_digest="")
    transaction.description = "Changed after preview"
    await db_session.flush()
    with pytest.raises(ValueError, match="changed"):
        await apply_correction(db_session, owner, plan, approved_digest=plan.digest())
    assert account.currency == "PLN"


async def test_foreign_owner_cannot_preview_or_apply(db_session):
    owner, account, _transaction = await setup(db_session)
    with pytest.raises(LookupError):
        await preview_correction(db_session, uuid.uuid4(), account.id, Rates())
    plan = await preview_correction(db_session, owner, account.id, Rates())
    with pytest.raises(LookupError):
        await apply_correction(db_session, uuid.uuid4(), plan, approved_digest=plan.digest())


async def test_missing_rate_fails_without_mutation(db_session):
    class Missing(Rates):
        async def get_rate(self, currency: str, rate_date: date) -> None:
            return None

    owner, account, _transaction = await setup(db_session)
    with pytest.raises(ValueError, match="NBP"):
        await preview_correction(db_session, owner, account.id, Missing())
    assert account.currency == "PLN"


async def test_recomputed_digest_cannot_authorize_forged_nbp_rate(db_session):
    from decimal import Decimal

    owner, account, _transaction = await setup(db_session)
    plan = await preview_correction(db_session, owner, account.id, Rates())
    plan.quotes[0].rate = Decimal(5)
    with pytest.raises(ValueError, match="NBP"):
        await apply_correction(db_session, owner, plan, approved_digest=plan.digest())
    assert account.currency == "PLN"


@pytest.mark.parametrize("invalid", ["currency", "transfer", "rate", "source", "pending"])
async def test_nonmatching_history_is_rejected(db_session, invalid):
    owner, account, transaction = await setup(db_session)
    if invalid == "currency":
        transaction.postings[0].source_currency = "USD"
    elif invalid == "transfer":
        transaction.type = "transfer"
    elif invalid == "rate":
        transaction.postings[0].fx_rate = 2
    elif invalid == "source":
        account.source = "manual"
    else:
        transaction.is_pending = True
    await db_session.flush()
    with pytest.raises(ValueError):
        await preview_correction(db_session, owner, account.id, Rates())
    assert account.currency == "PLN"


async def test_audit_failure_rolls_back_the_whole_correction(db_session, monkeypatch):
    import app.finance.currency_correction as correction

    owner, account, transaction = await setup(db_session)
    account_id, transaction_id = account.id, transaction.id
    plan = await preview_correction(db_session, owner, account_id, Rates())

    async def fail_audit(*args, **kwargs):
        raise RuntimeError("Synthetic audit failure")

    monkeypatch.setattr(correction, "log_event", fail_audit)
    with pytest.raises(RuntimeError, match="audit failure"):
        await apply_correction(db_session, owner, plan, approved_digest=plan.digest())
    # The caller may still commit its transaction: the savepoint must have
    # undone every correction field before control returns to it.
    await db_session.commit()
    result = await service.get_account(db_session, owner, account_id)
    assert result.currency == "PLN"
    rows = (
        await db_session.scalars(select(Posting).where(Posting.transaction_id == transaction_id))
    ).all()
    assert all(p.source_currency == "PLN" and p.base_amount_pln == 101 for p in rows)
    assert not (await db_session.scalars(select(AuditEvent))).all()


@pytest.mark.parametrize("dependency", ["loan", "schedule"])
async def test_account_dependencies_block_operator_correction(db_session, dependency):
    from app.finance.loan_schemas import LoanCreate
    from app.finance.schemas import ScheduledFinanceItemCreate

    owner, account, transaction = await setup(db_session)
    if dependency == "loan":
        payer = await service.create_account(
            db_session, owner, AccountCreate(name="Payer", type="cash")
        )
        await service.create_loan(
            db_session,
            owner,
            LoanCreate(name="Loan", account_id=account.id, payment_account_id=payer.id),
        )
    else:
        category_id = next(p.category_id for p in transaction.postings if p.category_id is not None)
        await service.create_scheduled_item(
            db_session,
            owner,
            ScheduledFinanceItemCreate(
                name="Schedule",
                type="expense",
                account_id=account.id,
                category_id=category_id,
                currency="PLN",
                due_day=1,
                amount_method="fixed",
                fixed_amount_pln=100,
            ),
        )
    with pytest.raises(ValueError, match="dependencies"):
        await preview_correction(db_session, owner, account.id, Rates())


async def test_correction_serializes_with_transaction_edit(db_session):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.finance.schemas import TransactionUpdate

    owner, account, transaction = await setup(db_session)
    plan = await preview_correction(db_session, owner, account.id, Rates())
    await db_session.commit()
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)
    async with sessions() as editor, sessions() as corrector:
        await service.update_transaction(
            editor, owner, transaction.id, TransactionUpdate(description="Changed concurrently")
        )
        await corrector.execute(text("SET LOCAL lock_timeout = '200ms'"))
        with pytest.raises(DBAPIError, match="lock timeout"):
            await apply_correction(corrector, owner, plan, approved_digest=plan.digest())
        await corrector.rollback()
        await editor.commit()
        with pytest.raises(ValueError, match="changed"):
            await apply_correction(corrector, owner, plan, approved_digest=plan.digest())
