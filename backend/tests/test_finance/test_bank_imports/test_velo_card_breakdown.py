from copy import deepcopy

import pytest
from sqlalchemy import select

from app.finance.imports.contracts import ParsedStatement
from app.finance.imports.models import ImportRevision, ImportSource
from app.finance.imports.parsers.velo_card import parse_velo_card
from app.finance.imports.velo_card_breakdown import velo_card_breakdown
from tests.test_finance.test_account_currency import client_for
from tests.test_finance.test_bank_imports.factories import ledger_snapshot, ready_statement
from tests.test_finance.test_bank_imports.test_velo_card import CARD, COLUMNS, HEADER, source

PLAN = (
    "Uruchomienie Planu Spłat Ratalnych 2026.03.09 "
    "12 000,00 PLN 11 257,81 PLN 17 10,99 %\n„Komfort”\n"
)
PRINCIPAL = (
    "Plan Spłat Ratalnych „Komfort”\nna kwotę -742,19 PLN - Część kapitałowa raty Planu Spłat\n"
    "Ratalnych „Komfort”\n-742,19\n"
)
INTEREST = (
    "Plan Spłat Ratalnych „Komfort”\nna kwotę -27,54 PLN - Część odsetkowa raty Planu Spłat Ratalnych\n"
    "„Komfort”\n-27,54\n"
)


def synthetic_statement_text() -> str:
    header = (
        HEADER.replace("2026.01.01 do 2026.01.31", "2026.02.18 do 2026.03.17")
        .replace("2026.02.15", "2026.04.14")
        .replace("920,00", "810,59")
        .replace("50,00 PLN", "794,39 PLN")
        .replace("1 000,00 PLN", "16,20 PLN")
    )
    plan_dates = "2026.03.17\n2026.03.17\n"
    activation = (
        "2026.03.09\n2026.03.09\nPrzelew na Raty\n-12 000,00\n"
        "2026.03.09\n2026.03.09\nPlan Spłat Ratalnych „Komfort”\n"
        "Uruchomienie planu ratalnego\n12 000,00\n"
    )
    return (
        header
        + CARD
        + COLUMNS
        + activation
        + plan_dates
        + PRINCIPAL
        + plan_dates
        + INTEREST
        + plan_dates
        + "ODSETKI OD TRANSAKCJI GOTOWKOWYCH\n-24,66\n"
        + "SZCZEGÓŁY DOTYCZĄCE PLANÓW RATALNYCH\nPozostały kapitał\n"
        + PLAN
        + "Dane planu na koniec okresu.\nData i godzina: 2026.03.17\n"
    )


def synthetic_statement() -> ParsedStatement:
    return parse_velo_card(source(synthetic_statement_text()))


def test_breakdown_uses_legacy_saved_text_and_statement_rows() -> None:
    result = synthetic_statement().model_dump(mode="json")
    original = deepcopy(result)
    assert result["card_header"]["future_installment_principal_pln"] is None
    breakdown = velo_card_breakdown(result)
    assert breakdown is not None
    assert breakdown.due_date.isoformat() == "2026-04-14"
    assert (breakdown.cycle_debt_pln, breakdown.minimum_pln) == (81059, 79439)
    assert breakdown.installment_original_principal_pln == 1200000
    assert breakdown.future_installment_principal_pln == 1125781
    assert breakdown.komfort_installment.model_dump() == {
        "principal_pln": 74219,
        "interest_pln": 2754,
        "total_pln": 76973,
        "included_in_minimum": True,
    }
    assert not breakdown.unassigned_installment_charges
    assert [(charge.kind, charge.amount_pln) for charge in breakdown.cash_interest_charges] == [
        ("cash_interest", 2466)
    ]
    assert result == original


@pytest.mark.parametrize(
    "case", ["second_plan", "malformed_plan", "different_date", "missing_half"]
)
def test_ambiguous_charge_positions_remain_visible_without_installment_total(case: str) -> None:
    result = synthetic_statement().model_dump(mode="json")
    if case in {"second_plan", "malformed_plan"}:
        result["card_header"]["installment_details_text"].extend(
            (PLAN if case == "second_plan" else "Uruchomienie Planu Spłat Ratalnych").splitlines()
        )
    elif case == "different_date":
        result["rows"][3]["operation_date"] = "2026-03-16"
    else:
        result["rows"].pop(3)
    breakdown = velo_card_breakdown(result)
    assert breakdown is not None and breakdown.komfort_installment is None
    assert [charge.amount_pln for charge in breakdown.unassigned_installment_charges] == (
        [74219] if case == "missing_half" else [74219, 2754]
    )
    assert breakdown.cash_interest_charges[0].amount_pln == 2466
    if case in {"second_plan", "malformed_plan"}:
        assert breakdown.future_installment_principal_pln is None


def test_missing_header_fields_stay_unknown_and_smaller_minimum_is_not_confirmed() -> None:
    result = synthetic_statement().model_dump(mode="json")
    result["card_header"]["minimum_pln"] = 5000
    breakdown = velo_card_breakdown(result)
    assert breakdown is not None and breakdown.komfort_installment is not None
    assert breakdown.komfort_installment.included_in_minimum is False

    result["card_header"] = {"due_date": "bad date", "minimum_pln": True}
    breakdown = velo_card_breakdown(result)
    assert breakdown is not None
    assert breakdown.due_date is breakdown.minimum_pln is breakdown.cycle_debt_pln is None
    assert breakdown.future_installment_principal_pln is None
    assert breakdown.komfort_installment is None
    assert velo_card_breakdown({**result, "layout": "velo_account_v1"}) is None


@pytest.mark.integration
async def test_batch_reads_only_the_owners_active_revision_without_writes(
    db_session, owner, other_owner
) -> None:
    statement = synthetic_statement()
    batch_id = await ready_statement(db_session, owner.id, statement)
    current_source = await db_session.scalar(
        select(ImportSource).where(ImportSource.batch_id == batch_id)
    )
    assert current_source is not None and current_source.current_revision_id is not None
    current = await db_session.get(ImportRevision, current_source.current_revision_id)
    assert current is not None
    candidate_result = deepcopy(current.result)
    candidate_result["card_header"]["minimum_pln"] = 123456
    candidate = ImportRevision(
        user_id=owner.id,
        source_id=current_source.id,
        batch_id=batch_id,
        number=2,
        source_sha256=current.source_sha256,
        result=candidate_result,
        checks=current.checks,
        warnings=["reparse_requires_comparison"],
    )
    db_session.add(candidate)
    await db_session.flush()
    before = await ledger_snapshot(db_session)

    async with client_for(db_session, owner.id) as client:
        response = await client.get(f"/api/finance/imports/{batch_id}")
    assert response.status_code == 200
    response_source = response.json()["sources"][0]
    assert response_source["candidate_revision_id"] == str(candidate.id)
    assert response_source["current_revision_id"] == str(current.id)
    assert response_source["velo_card_breakdown"]["minimum_pln"] == 79439
    assert "installment_details_text" not in response_source["velo_card_breakdown"]
    async with client_for(db_session, other_owner.id) as client:
        response = await client.get(f"/api/finance/imports/{batch_id}")
    assert response.status_code == 404
    await db_session.refresh(current_source)
    assert current_source.current_revision_id == current.id
    assert await ledger_snapshot(db_session) == before


@pytest.mark.integration
async def test_card_plan_observation_is_owner_scoped_read_only_and_uses_current_revision(
    db_session, owner, other_owner
) -> None:
    statement = synthetic_statement()
    batch_id = await ready_statement(db_session, owner.id, statement)
    source_entry = await db_session.scalar(
        select(ImportSource).where(ImportSource.batch_id == batch_id)
    )
    assert source_entry is not None
    current = await db_session.get(ImportRevision, source_entry.current_revision_id)
    assert current is not None and current.result is not None
    candidate_result = deepcopy(current.result)
    candidate_result["card_header"]["installment_details_text"] = []
    db_session.add(
        ImportRevision(
            user_id=owner.id, source_id=source_entry.id, batch_id=batch_id,
            number=2, source_sha256=current.source_sha256, result=candidate_result,
            checks=current.checks, warnings=["reparse_requires_comparison"],
        )
    )
    await db_session.flush()
    before = await ledger_snapshot(db_session)
    async with client_for(db_session, owner.id) as client:
        response = await client.get("/api/finance/loans/card-statement-plans")
    assert response.status_code == 200
    observed = response.json()
    assert len(observed) == 1 and observed[0]["batch_id"] == str(batch_id)
    assert observed[0]["breakdown"]["installment_original_principal_pln"] == 1200000
    assert observed[0]["breakdown"]["komfort_installment"]["total_pln"] == 76973
    assert "account_reference" not in str(observed)
    async with client_for(db_session, other_owner.id) as client:
        response = await client.get("/api/finance/loans/card-statement-plans")
    assert response.json() == []
    assert await ledger_snapshot(db_session) == before
