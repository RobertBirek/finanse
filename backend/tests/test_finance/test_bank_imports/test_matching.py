import pytest

from app.finance.imports.decisions import save_decisions
from app.finance.imports.matching import get_candidates
from app.finance.imports.schemas import DecisionUpdate
from app.finance.schemas import PostingCreate, TransactionCreate
from app.finance.transactions import create_transaction
from tests.test_finance.test_bank_imports.review_fixtures import review_case

pytestmark = pytest.mark.integration


async def test_possible_actual_duplicate_is_not_an_automatic_link_or_skip(
    db_session, owner, tmp_path
) -> None:
    case = await review_case(db_session, owner.id, tmp_path)
    existing = await create_transaction(
        db_session,
        owner.id,
        TransactionCreate(
            transaction_date="2026-01-03",
            description="Syntetyczny zakup",
            type="expense",
            source="actual",
            postings=[
                PostingCreate(
                    account_id=case.account.id,
                    source_amount=100,
                    base_amount_pln=100,
                    direction="debit",
                ),
                PostingCreate(
                    category_id=case.category.id,
                    source_amount=100,
                    base_amount_pln=100,
                    direction="credit",
                ),
            ],
        ),
    )
    await save_decisions(
        db_session,
        owner.id,
        case.batch_id,
        DecisionUpdate(expected_version=1, decisions=[case.decision]),
    )
    candidates = await get_candidates(db_session, owner.id, case.rows[0].id)
    assert len(candidates) == 1 and candidates[0].transaction_id == existing.id
    assert candidates[0].strength == "possible" and not candidates[0].conflicts
    assert case.decision.action == "create"


async def test_candidates_never_reveal_another_owners_transactions(
    db_session, owner, other_owner, tmp_path
) -> None:
    from app.finance.imports.errors import ImportError

    case = await review_case(db_session, owner.id, tmp_path)
    with pytest.raises(ImportError) as error:
        await get_candidates(db_session, other_owner.id, case.rows[0].id)
    assert error.value.http_status == 404


async def test_strong_reference_conflict_cannot_replace_the_existing_amount(
    db_session, owner, tmp_path
) -> None:
    from app.finance.imports.errors import ImportError
    from app.finance.imports.models import ImportBankIdentity, ImportEvidence, ImportGroup
    from app.finance.models import FinanceCommandReceipt

    case = await review_case(db_session, owner.id, tmp_path)
    case.rows[0].fields = dict(case.rows[0].fields) | {
        "bank_reference": "synthetic-strong-reference"
    }
    existing = await create_transaction(
        db_session,
        owner.id,
        TransactionCreate(
            transaction_date="2026-01-03",
            description="Syntetyczny zakup",
            type="expense",
            source="actual",
            postings=[
                PostingCreate(
                    account_id=case.account.id,
                    source_amount=90,
                    base_amount_pln=90,
                    direction="debit",
                ),
                PostingCreate(
                    category_id=case.category.id,
                    source_amount=90,
                    base_amount_pln=90,
                    direction="credit",
                ),
            ],
        ),
    )
    await save_decisions(
        db_session,
        owner.id,
        case.batch_id,
        DecisionUpdate(expected_version=1, decisions=[case.decision]),
    )
    group = ImportGroup(user_id=owner.id, batch_id=case.batch_id, state="committed")
    receipt = FinanceCommandReceipt(
        user_id=owner.id,
        action="synthetic",
        key="strong-ref",
        request_hash="a" * 64,
        response_json={},
    )
    db_session.add_all([group, receipt])
    await db_session.flush()
    posting = next(item for item in existing.postings if item.account_id == case.account.id)
    db_session.add(
        ImportBankIdentity(
            user_id=owner.id,
            batch_id=case.batch_id,
            group_id=group.id,
            bank="velo",
            account_id=case.account.id,
            currency="PLN",
            strong_reference="synthetic-strong-reference",
        )
    )
    db_session.add(
        ImportEvidence(
            user_id=owner.id,
            batch_id=case.batch_id,
            group_id=group.id,
            row_id=case.rows[1].id,
            transaction_id=existing.id,
            posting_id=posting.id,
            receipt_id=receipt.id,
            component="whole",
            attributed_source_amount=-90,
        )
    )
    await db_session.flush()
    candidates = await get_candidates(db_session, owner.id, case.rows[0].id)
    assert len(candidates) == 1 and candidates[0].strength == "strong"
    assert "amount_mismatch" in candidates[0].conflicts and posting.source_amount == 90
    with pytest.raises(ImportError) as error:
        await save_decisions(
            db_session,
            owner.id,
            case.batch_id,
            DecisionUpdate(
                expected_version=2,
                decisions=[
                    case.decision.model_copy(
                        update={"action": "link", "existing_transaction_id": existing.id}
                    )
                ],
            ),
        )
    assert error.value.code == "link_posting_mismatch" and posting.source_amount == 90


@pytest.mark.parametrize("currency,rate,base", [("PLN", 1, 100), ("EUR", 4, 400)])
async def test_equal_amount_on_another_owned_account_is_not_a_valid_link(
    db_session, owner, tmp_path, currency, rate, base
) -> None:
    from app.finance.entities import create_account
    from app.finance.imports.errors import ImportError
    from app.finance.schemas import AccountCreate

    case = await review_case(db_session, owner.id, tmp_path)
    other = await create_account(
        db_session,
        owner.id,
        AccountCreate(name="Other owned account", type="checking", currency=currency),
    )
    existing = await create_transaction(
        db_session,
        owner.id,
        TransactionCreate(
            transaction_date="2026-01-03",
            description="Syntetyczny zakup",
            type="expense",
            source="actual",
            postings=[
                PostingCreate(
                    account_id=other.id,
                    source_amount=100,
                    source_currency=currency,
                    base_amount_pln=base,
                    fx_rate=rate,
                    direction="debit",
                ),
                PostingCreate(
                    category_id=case.category.id,
                    source_amount=100,
                    source_currency=currency,
                    base_amount_pln=base,
                    fx_rate=rate,
                    direction="credit",
                ),
            ],
        ),
    )
    decision = case.decision.model_copy(
        update={"action": "link", "existing_transaction_id": existing.id}
    )
    with pytest.raises(ImportError) as error:
        await save_decisions(
            db_session,
            owner.id,
            case.batch_id,
            DecisionUpdate(expected_version=1, decisions=[decision]),
        )
    assert error.value.code == "link_posting_mismatch"
