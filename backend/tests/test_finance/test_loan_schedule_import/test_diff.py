"""Identity is date plus components, never a mutable bank row number."""

import uuid
from dataclasses import replace
from datetime import date, timedelta

from app.finance.imports.contracts import Check, ParsedSchedule, ScheduleRow, SourcePosition

TODAY = date(2026, 11, 10)


def row(number=1, due=TODAY, principal=10000, interest=1000, fees=0):
    return ScheduleRow(
        bank_number=number,
        due_date=due,
        principal=principal,
        interest=interest,
        fees=fees,
        total=principal + interest + fees,
        balance_after=None,
        position=SourcePosition(page=1, line=number),
    )


def plan(*rows, effective=TODAY, complete=True):
    return ParsedSchedule(
        bank="velo",
        layout="synthetic",
        parser_version="1",
        loan_reference=None,
        effective_date=effective,
        rows=list(rows),
        checks=[Check(code="synthetic", required=True, result="passed")],
        warnings=[],
        complete_tail=complete,
    )


def item(number=1, due=TODAY, principal=10000, interest=1000, fees=0):
    from app.finance.loan_schedule_diff import ScheduleInstallment

    return ScheduleInstallment(
        id=uuid.uuid4(),
        number=number,
        due_date=due,
        principal_pln=principal,
        interest_pln=interest,
        fees_pln=fees,
        superseded_by_revision_id=None,
    )


def state(*items, links=()):
    from app.finance.loan_schedule_diff import ScheduleState

    return ScheduleState(
        loan_id=uuid.uuid4(),
        active_revision_id=None,
        installments=tuple(items),
        payment_links=tuple(links),
        fingerprint="synthetic-state",
    )


def link(installment, amount=100):
    from app.finance.loan_schedule_diff import SchedulePayment

    return SchedulePayment(
        id=uuid.uuid4(),
        installment_id=installment.id,
        transaction_id=uuid.uuid4(),
        amount_pln=amount,
        transaction_date=TODAY,
    )


def test_first_identical_59_rows_and_partial_payment_reuse_existing_uuids():
    from app.finance.loan_schedule_diff import diff_schedule

    old = [item(n, TODAY + timedelta(days=n)) for n in range(1, 60)]
    snapshot = state(*old, links=[link(old[0])])
    result = diff_schedule(
        snapshot, plan(*[row(n, old[n - 1].due_date) for n in range(1, 60)]), today=TODAY
    )
    assert set(result.reused_ids) == {i.id for i in old}
    assert not result.new_rows and not result.superseded_ids and not result.conflicts


def test_shorter_complete_plan_supersedes_entire_unlinked_future_tail():
    from app.finance.loan_schedule_diff import diff_schedule

    first, last = item(10, TODAY + timedelta(days=1)), item(99, TODAY + timedelta(days=100))
    result = diff_schedule(state(first, last), plan(row(1, first.due_date)), today=TODAY)
    assert result.reused_ids == [first.id] and result.superseded_ids == [last.id]
    assert not result.conflicts and not result.new_rows


def test_renumbering_reuses_exact_date_and_components_not_internal_number():
    from app.finance.loan_schedule_diff import diff_schedule

    old = item(45)
    result = diff_schedule(state(old), plan(row(1)), today=TODAY)
    assert result.reused_ids == [old.id] and old.number == 45 and not result.new_rows


def test_changed_future_components_create_new_row_without_editing_old():
    from app.finance.loan_schedule_diff import diff_schedule

    old = item()
    incoming = row(interest=500)
    result = diff_schedule(state(old), plan(incoming), today=TODAY)
    assert result.new_rows == [incoming] and result.superseded_ids == [old.id]
    assert not result.reused_ids and not result.conflicts and old.interest_pln == 1000


def test_linked_future_missing_or_changed_blocks_without_archiving_it():
    from app.finance.loan_schedule_diff import diff_schedule

    old = item()
    for incoming in [row(due=TODAY + timedelta(days=1)), row(interest=500)]:
        result = diff_schedule(state(old, links=[link(old)]), plan(incoming), today=TODAY)
        assert result.conflicts and old.id not in result.superseded_ids


def test_past_paid_and_partial_omitted_rows_stay_addressable_history():
    from app.finance.loan_schedule_diff import diff_schedule

    paid, partial = item(1, TODAY - timedelta(days=2)), item(2, TODAY - timedelta(days=1))
    result = diff_schedule(
        state(paid, partial, links=[link(paid, 11000), link(partial)]), plan(row()), today=TODAY
    )
    assert set(result.retained_history_ids) == {paid.id, partial.id}
    assert not result.conflicts and not result.superseded_ids


def test_past_unpaid_omission_or_changed_history_is_visible_and_blocked():
    from app.finance.loan_schedule_diff import diff_schedule

    old = item(due=TODAY - timedelta(days=1))
    for incoming in [row(), row(due=old.due_date, interest=500)]:
        result = diff_schedule(state(old), plan(incoming), today=TODAY)
        assert result.conflicts and old.id in result.retained_history_ids
        assert old.id not in result.superseded_ids


def test_paid_history_changed_by_incoming_pdf_is_not_silently_carried_forward():
    from app.finance.loan_schedule_diff import diff_schedule

    old = item(due=TODAY - timedelta(days=1))
    result = diff_schedule(
        state(old, links=[link(old)]), plan(row(due=old.due_date, interest=500)), today=TODAY
    )
    assert result.conflicts and not result.superseded_ids


def test_ambiguous_exact_candidates_do_not_pick_one_arbitrarily():
    from app.finance.loan_schedule_diff import diff_schedule

    a, b = item(1), item(2)
    result = diff_schedule(state(a, b), plan(row()), today=TODAY)
    assert result.conflicts and not result.reused_ids
    assert set(result.conflicts[0].installment_ids) == {a.id, b.id}


def test_effective_date_cutover_is_max_of_document_and_activation_day():
    from app.finance.loan_schedule_diff import diff_schedule

    for effective, want in [
        (TODAY - timedelta(days=10), TODAY),
        (TODAY + timedelta(days=10), TODAY + timedelta(days=10)),
    ]:
        result = diff_schedule(state(), plan(row(), effective=effective), today=TODAY)
        assert result.cutover_date == want


def test_first_empty_contract_can_introduce_historical_rows_without_payments():
    from app.finance.loan_schedule_diff import diff_schedule

    incoming = row(due=TODAY - timedelta(days=10))
    result = diff_schedule(state(), plan(incoming), today=TODAY)
    assert result.new_rows == [incoming] and not result.conflicts


def test_invalid_or_incomplete_sources_cannot_propose_mutations():
    from app.finance.loan_schedule_diff import diff_schedule

    for incoming in [
        plan(row(), complete=False),
        plan(row(), effective=None),
        plan(row()).model_copy(
            update={"checks": [Check(code="bad", required=True, result="failed")]}
        ),
    ]:
        result = diff_schedule(state(item()), incoming, today=TODAY)
        assert result.conflicts and not result.new_rows and not result.superseded_ids


def test_superseded_installments_are_never_reused_and_duplicate_dates_block():
    from app.finance.loan_schedule_diff import diff_schedule

    old = replace(item(), superseded_by_revision_id=uuid.uuid4())
    result = diff_schedule(state(old), plan(row()), today=TODAY)
    assert not result.reused_ids and len(result.new_rows) == 1
    result = diff_schedule(state(), plan(row(), row(2)), today=TODAY)
    assert result.conflicts
