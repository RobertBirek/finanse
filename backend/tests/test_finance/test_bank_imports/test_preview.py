import pytest

from app.documents import service as documents
from app.finance.imports.decisions import save_decisions
from app.finance.imports.errors import ImportError
from app.finance.imports.preview import canonical_preview_payload, prepare_preview
from app.finance.imports.schemas import DecisionUpdate, PreviewRequest
from tests.test_finance.test_bank_imports.factories import ledger_snapshot
from tests.test_finance.test_bank_imports.review_fixtures import review_case

pytestmark = pytest.mark.integration


async def test_preview_has_zero_financial_effect_and_opening_gap_requires_acknowledgement(
    db_session, owner, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(documents, "UPLOAD_DIR", tmp_path)
    case = await review_case(db_session, owner.id, tmp_path)
    batch = await save_decisions(
        db_session,
        owner.id,
        case.batch_id,
        DecisionUpdate(expected_version=1, decisions=[case.decision]),
    )
    before = await ledger_snapshot(db_session)
    request = PreviewRequest(expected_version=batch.version, group_ids=[case.decision.group_id])
    with pytest.raises(ImportError) as error:
        await prepare_preview(db_session, owner.id, batch.id, request)
    assert error.value.code == "import_acknowledgement_required"
    request.acknowledgements = [f"opening_gap:{case.source_id}"]
    preview = await prepare_preview(db_session, owner.id, batch.id, request)
    assert preview.new_transaction_count == 1 and len(preview.request_hash) == 64
    payload = await canonical_preview_payload(db_session, owner.id, preview.id)
    assert payload["batch_id"] == str(batch.id)
    assert await ledger_snapshot(db_session) == before


async def test_account_change_invalidates_preview_not_reprices_it(
    db_session, owner, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(documents, "UPLOAD_DIR", tmp_path)
    case = await review_case(db_session, owner.id, tmp_path)
    batch = await save_decisions(
        db_session,
        owner.id,
        case.batch_id,
        DecisionUpdate(expected_version=1, decisions=[case.decision]),
    )
    preview = await prepare_preview(
        db_session,
        owner.id,
        batch.id,
        PreviewRequest(
            expected_version=batch.version,
            group_ids=[case.decision.group_id],
            acknowledgements=[f"opening_gap:{case.source_id}"],
        ),
    )
    case.account.name = "Changed after confirmation"
    await db_session.flush()
    with pytest.raises(ImportError) as error:
        await canonical_preview_payload(db_session, owner.id, preview.id)
    assert error.value.code == "preview_stale"


async def confirmed_case(db_session, owner, tmp_path, monkeypatch, payload=None):
    monkeypatch.setattr(documents, "UPLOAD_DIR", tmp_path)
    case = await review_case(db_session, owner.id, tmp_path, payload)
    batch = await save_decisions(
        db_session,
        owner.id,
        case.batch_id,
        DecisionUpdate(expected_version=1, decisions=[case.decision]),
    )
    request = PreviewRequest(
        expected_version=batch.version,
        group_ids=[case.decision.group_id],
        acknowledgements=[f"opening_gap:{case.source_id}"],
    )
    return case, batch, request


async def test_original_bytes_are_rechecked_before_consuming_a_frozen_preview(
    db_session, owner, tmp_path, monkeypatch
) -> None:
    from app.documents.models import Document
    from app.finance.imports.models import ImportSource

    case, batch, request = await confirmed_case(db_session, owner, tmp_path, monkeypatch)
    preview = await prepare_preview(db_session, owner.id, batch.id, request)
    source = await db_session.get(ImportSource, case.source_id)
    document = await db_session.get(Document, source.document_id)
    (tmp_path / document.storage_path).write_bytes(b"tampered original")
    with pytest.raises(ImportError) as error:
        await canonical_preview_payload(db_session, owner.id, preview.id)
    assert error.value.code == "source_integrity_failed"


async def test_new_cancelling_movements_stale_preview_even_with_unchanged_balance(
    db_session, owner, tmp_path, monkeypatch
) -> None:
    from app.finance.entities import create_category
    from app.finance.schemas import CategoryCreate, PostingCreate, TransactionCreate
    from app.finance.transactions import create_transaction

    case, batch, request = await confirmed_case(db_session, owner, tmp_path, monkeypatch)
    preview = await prepare_preview(db_session, owner.id, batch.id, request)
    income = await create_category(
        db_session, owner.id, CategoryCreate(name="Synthetic offset income", type="income")
    )
    for kind, category_id, direction in [
        ("expense", case.category.id, "debit"),
        ("income", income.id, "credit"),
    ]:
        await create_transaction(
            db_session,
            owner.id,
            TransactionCreate(
                transaction_date="2026-01-03",
                description="Syntetyczny zakup",
                type=kind,
                postings=[
                    PostingCreate(
                        account_id=case.account.id,
                        source_amount=100,
                        base_amount_pln=100,
                        direction=direction,
                    ),
                    PostingCreate(
                        category_id=category_id,
                        source_amount=100,
                        base_amount_pln=100,
                        direction="credit" if direction == "debit" else "debit",
                    ),
                ],
            ),
        )
    with pytest.raises(ImportError) as error:
        await canonical_preview_payload(db_session, owner.id, preview.id)
    assert error.value.code == "preview_stale"


async def test_decision_change_stales_old_preview_instead_of_switching_its_intent(
    db_session, owner, tmp_path, monkeypatch
) -> None:
    case, batch, request = await confirmed_case(db_session, owner, tmp_path, monkeypatch)
    preview = await prepare_preview(db_session, owner.id, batch.id, request)
    await save_decisions(
        db_session,
        owner.id,
        batch.id,
        DecisionUpdate(
            expected_version=batch.version,
            decisions=[case.decision.model_copy(update={"action": "defer"})],
        ),
    )
    with pytest.raises(ImportError) as error:
        await canonical_preview_payload(db_session, owner.id, preview.id)
    assert error.value.code == "preview_stale"


async def test_fee_create_freezes_main_and_fee_once_without_losing_net_source_amount(
    db_session, owner, tmp_path, monkeypatch
) -> None:
    from tests.test_finance.test_bank_imports.test_contracts import parsed_statement, statement_row

    monkeypatch.setattr(documents, "UPLOAD_DIR", tmp_path)
    source = parsed_statement(account_reference=None, rows=[statement_row(amount=-120, fee=20)])
    case = await review_case(db_session, owner.id, tmp_path, source)
    decision = case.decision.model_copy(update={"fee_category_id": case.category.id})
    batch = await save_decisions(
        db_session,
        owner.id,
        case.batch_id,
        DecisionUpdate(expected_version=1, decisions=[decision]),
    )
    preview = await prepare_preview(
        db_session,
        owner.id,
        batch.id,
        PreviewRequest(
            expected_version=batch.version,
            group_ids=[decision.group_id],
            acknowledgements=[f"opening_gap:{case.source_id}"],
        ),
    )
    payload = await canonical_preview_payload(db_session, owner.id, preview.id)
    operations = payload["plans"][0]["operations"]
    assert preview.new_transaction_count == 2
    assert [operation["postings"][0]["source_amount"] for operation in operations] == [100, 20]
    assert [operation["component"] for operation in operations] == ["main", "fee"]


async def test_row_changed_during_external_quote_is_not_hidden_by_identity_map(
    db_session, owner, tmp_path, monkeypatch
) -> None:
    from sqlalchemy import update

    from app.finance.imports import preview as preview_service
    from app.finance.imports.models import ImportRow

    case, batch, request = await confirmed_case(db_session, owner, tmp_path, monkeypatch)
    original = preview_service.freeze_quote

    async def mutate(currency, amount, requested, **kwargs):
        quote = await original(currency, amount, requested, **kwargs)
        fields = dict(case.rows[0].fields) | {"description": "Changed during quote"}
        await db_session.execute(
            update(ImportRow)
            .where(ImportRow.id == case.rows[0].id)
            .values(fields=fields)
            .execution_options(synchronize_session=False)
        )
        return quote

    monkeypatch.setattr(preview_service, "freeze_quote", mutate)
    with pytest.raises(ImportError) as error:
        await prepare_preview(db_session, owner.id, batch.id, request)
    assert error.value.code == "preview_stale"


async def test_link_whole_net_fee_keeps_old_actual_and_never_fetches_a_new_quote(
    db_session, owner, tmp_path, monkeypatch
) -> None:
    from app.finance.imports import preview as preview_service
    from app.finance.schemas import PostingCreate, TransactionCreate
    from app.finance.transactions import create_transaction
    from tests.test_finance.test_bank_imports.test_contracts import parsed_statement, statement_row

    monkeypatch.setattr(documents, "UPLOAD_DIR", tmp_path)
    case = await review_case(
        db_session,
        owner.id,
        tmp_path,
        parsed_statement(account_reference=None, rows=[statement_row(amount=-120, fee=20)]),
    )
    existing = await create_transaction(
        db_session,
        owner.id,
        TransactionCreate(
            transaction_date="2026-01-03",
            description="Old unsplit fee",
            type="expense",
            source="actual",
            postings=[
                PostingCreate(
                    account_id=case.account.id,
                    source_amount=120,
                    base_amount_pln=120,
                    direction="debit",
                ),
                PostingCreate(
                    category_id=case.category.id,
                    source_amount=120,
                    base_amount_pln=120,
                    direction="credit",
                ),
            ],
        ),
    )
    decision = case.decision.model_copy(
        update={"action": "link", "category_id": None, "existing_transaction_id": existing.id}
    )
    batch = await save_decisions(
        db_session,
        owner.id,
        case.batch_id,
        DecisionUpdate(expected_version=1, decisions=[decision]),
    )
    before = await ledger_snapshot(db_session)

    async def forbidden(*args, **kwargs):
        raise AssertionError("Linking Actual must never revalue its postings")

    monkeypatch.setattr(preview_service, "freeze_quote", forbidden)
    preview = await prepare_preview(
        db_session,
        owner.id,
        batch.id,
        PreviewRequest(
            expected_version=batch.version,
            group_ids=[decision.group_id],
            acknowledgements=[f"opening_gap:{case.source_id}"],
        ),
    )
    assert preview.new_transaction_count == 0 and preview.linked_transaction_count == 1
    assert f"cost_split_unreconciled:{case.rows[0].id}" in preview.warnings
    assert await ledger_snapshot(db_session) == before


@pytest.mark.parametrize(
    "out_currency,out_amount,in_currency,in_amount,base,from_rate,to_rate",
    [
        ("PLN", 425, "EUR", 100, 425, "1", "4.25"),
        ("EUR", 100, "USD", 125, 400, "4.0", "3.200000"),
    ],
)
async def test_complete_fx_preview_preserves_both_actual_legs_and_frozen_rates(
    db_session,
    owner,
    tmp_path,
    monkeypatch,
    out_currency,
    out_amount,
    in_currency,
    in_amount,
    base,
    from_rate,
    to_rate,
) -> None:
    from datetime import date
    from decimal import Decimal

    from app.finance.entities import create_account
    from app.finance.nbp_rates import NbpRate, NbpRateProvider
    from app.finance.schemas import AccountCreate
    from tests.test_finance.test_bank_imports.review_fixtures import additional_source
    from tests.test_finance.test_bank_imports.test_contracts import parsed_statement, statement_row

    monkeypatch.setattr(documents, "UPLOAD_DIR", tmp_path)
    calls = []

    async def quote(self, currency, requested):
        calls.append(currency)
        return NbpRate(4.0, date(2026, 1, 2), "nbp_previous_business_day")

    monkeypatch.setattr(NbpRateProvider, "get_rate", quote)
    outgoing = parsed_statement(
        account_reference=None,
        currency=out_currency,
        opening=0,
        rows=[statement_row(amount=-out_amount, currency=out_currency)],
    )
    case = await review_case(db_session, owner.id, tmp_path, outgoing)
    incoming = parsed_statement(
        account_reference=None,
        currency=in_currency,
        opening=0,
        rows=[statement_row(amount=in_amount, currency=in_currency)],
    )
    _source, rows = await additional_source(db_session, owner.id, case.batch_id, tmp_path, incoming)
    other = await create_account(
        db_session,
        owner.id,
        AccountCreate(name="Synthetic destination", type="checking", currency=in_currency),
    )
    decision = case.decision.model_copy(
        update={
            "kind": "exchange",
            "category_id": None,
            "other_account_id": other.id,
            "row_ids": [case.rows[0].id, rows[0].id],
        }
    )
    batch = await save_decisions(
        db_session,
        owner.id,
        case.batch_id,
        DecisionUpdate(expected_version=1, decisions=[decision]),
    )
    before = await ledger_snapshot(db_session)
    preview = await prepare_preview(
        db_session,
        owner.id,
        batch.id,
        PreviewRequest(expected_version=batch.version, group_ids=[decision.group_id]),
    )
    payload = await canonical_preview_payload(db_session, owner.id, preview.id)
    operation = payload["plans"][0]["operations"][0]
    postings = operation["postings"]
    assert [posting["source_amount"] for posting in postings] == [out_amount, in_amount]
    assert [posting["base_amount_pln"] for posting in postings] == [base, base]
    assert [Decimal(posting["fx_rate"]) for posting in postings] == [
        Decimal(from_rate),
        Decimal(to_rate),
    ]
    assert calls == ([] if out_currency == "PLN" else [out_currency])
    assert await ledger_snapshot(db_session) == before


async def test_membership_change_cannot_redirect_a_frozen_group(
    db_session, owner, tmp_path, monkeypatch
) -> None:
    from sqlalchemy import update

    from app.finance.imports.models import ImportGroupRow

    case, batch, request = await confirmed_case(db_session, owner, tmp_path, monkeypatch)
    preview = await prepare_preview(db_session, owner.id, batch.id, request)
    await db_session.execute(
        update(ImportGroupRow)
        .where(ImportGroupRow.group_id == case.decision.group_id)
        .values(row_id=case.rows[1].id)
        .execution_options(synchronize_session=False)
    )
    with pytest.raises(ImportError) as error:
        await canonical_preview_payload(db_session, owner.id, preview.id)
    assert error.value.code == "preview_stale"


async def test_card_header_confirmation_is_frozen_separately_from_new_postings(
    db_session, owner, tmp_path, monkeypatch
) -> None:
    from app.finance.imports.schemas import ImportDecisionInput
    from tests.test_finance.test_bank_imports.test_card_headers import confirmed
    from tests.test_finance.test_bank_imports.test_velo_card import card_statement

    monkeypatch.setattr(documents, "UPLOAD_DIR", tmp_path)
    case = await review_case(db_session, owner.id, tmp_path, card_statement())
    case.account.type = "credit_card"
    await db_session.flush()
    values = case.decision.model_dump(mode="json") | {
        "row_ids": [str(case.rows[1].id)],
        "card_header": confirmed(account_id=str(case.account.id)).model_dump(mode="json"),
    }
    decision = ImportDecisionInput.model_validate(values)
    batch = await save_decisions(
        db_session,
        owner.id,
        case.batch_id,
        DecisionUpdate(expected_version=1, decisions=[decision]),
    )
    preview = await prepare_preview(
        db_session,
        owner.id,
        batch.id,
        PreviewRequest(
            expected_version=batch.version,
            group_ids=[decision.group_id],
            acknowledgements=[f"opening_gap:{case.source_id}"],
        ),
    )
    payload = await canonical_preview_payload(db_session, owner.id, preview.id)
    metadata = payload["plans"][0]["card_statement"]
    assert metadata["source_id"] == str(case.source_id)
    assert metadata["account_id"] == str(case.account.id)
    assert metadata["data"]["debt_pln"] == 92000 and metadata["data"]["minimum_pln"] == 5000
    assert preview.new_transaction_count == 1


@pytest.mark.parametrize(
    "fee,kind,direction", [(20, "expense", "debit"), (-20, "expense_refund", "credit")]
)
async def test_fee_only_charge_or_refund_is_not_lost_when_main_component_is_zero(
    db_session, owner, tmp_path, monkeypatch, fee, kind, direction
) -> None:
    from tests.test_finance.test_bank_imports.test_contracts import parsed_statement, statement_row

    monkeypatch.setattr(documents, "UPLOAD_DIR", tmp_path)
    case = await review_case(
        db_session,
        owner.id,
        tmp_path,
        parsed_statement(account_reference=None, rows=[statement_row(amount=-fee, fee=fee)]),
    )
    decision = case.decision.model_copy(update={"kind": kind, "fee_category_id": case.category.id})
    batch = await save_decisions(
        db_session,
        owner.id,
        case.batch_id,
        DecisionUpdate(expected_version=1, decisions=[decision]),
    )
    preview = await prepare_preview(
        db_session,
        owner.id,
        batch.id,
        PreviewRequest(
            expected_version=batch.version,
            group_ids=[decision.group_id],
            acknowledgements=[f"opening_gap:{case.source_id}"],
        ),
    )
    payload = await canonical_preview_payload(db_session, owner.id, preview.id)
    operations = payload["plans"][0]["operations"]
    assert preview.new_transaction_count == 1 and operations[0]["component"] == "fee"
    assert operations[0]["kind"] == kind and operations[0]["postings"][0]["direction"] == direction
    assert operations[0]["postings"][0]["source_amount"] == 20
