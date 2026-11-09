import pytest

from app.finance.imports.decisions import save_decisions
from app.finance.imports.errors import ImportError
from app.finance.imports.models import ImportRevision, ImportSource
from app.finance.imports.schemas import DecisionUpdate
from tests.test_finance.test_bank_imports.review_fixtures import review_case

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("changed", [False, True])
async def test_reparse_candidate_needs_explicit_exact_comparison_before_unpaid_rows_continue(
    db_session, owner, tmp_path, changed
) -> None:
    case = await review_case(db_session, owner.id, tmp_path)
    source = await db_session.get(ImportSource, case.source_id)
    old = await db_session.get(ImportRevision, source.current_revision_id)
    result = dict(old.result)
    result["rows"] = [dict(value) for value in result["rows"]]
    if changed:
        result["rows"][0]["amount"] = -101
    candidate = ImportRevision(
        user_id=owner.id,
        batch_id=case.batch_id,
        source_id=source.id,
        number=2,
        source_sha256=old.source_sha256,
        parser_version="candidate-v2",
        result=result,
        checks=old.checks,
        warnings=["reparse_requires_comparison"],
    )
    db_session.add(candidate)
    source.validation_state = "needs_review"
    await db_session.flush()
    with pytest.raises(ImportError) as error:
        await save_decisions(
            db_session,
            owner.id,
            case.batch_id,
            DecisionUpdate(expected_version=1, decisions=[case.decision]),
        )
    assert error.value.code == "reparse_comparison_required"
    decision = case.decision.model_copy(
        update={"acknowledgements": [f"reparse_comparison:{source.id}:{candidate.id}"]}
    )
    if changed:
        with pytest.raises(ImportError) as error:
            await save_decisions(
                db_session,
                owner.id,
                case.batch_id,
                DecisionUpdate(expected_version=1, decisions=[decision]),
            )
        assert error.value.code == "reparse_row_conflict"
    else:
        batch = await save_decisions(
            db_session,
            owner.id,
            case.batch_id,
            DecisionUpdate(expected_version=1, decisions=[decision]),
        )
        assert batch.version == 2 and batch.sources[0].candidate_revision_id == candidate.id
    assert source.current_revision_id == old.id


async def test_candidate_rows_can_be_compared_privately_without_promoting_them(
    db_session, owner, other_owner, tmp_path
) -> None:
    from app.finance.imports.models import ImportRow
    from app.finance.imports.service import list_rows

    case = await review_case(db_session, owner.id, tmp_path)
    source = await db_session.get(ImportSource, case.source_id)
    old = await db_session.get(ImportRevision, source.current_revision_id)
    candidate = ImportRevision(
        user_id=owner.id,
        batch_id=case.batch_id,
        source_id=source.id,
        number=2,
        source_sha256=old.source_sha256,
        parser_version="candidate-v2",
        result=old.result,
        checks=old.checks,
        warnings=["reparse_requires_comparison"],
    )
    db_session.add(candidate)
    await db_session.flush()
    row = ImportRow(
        user_id=owner.id,
        batch_id=case.batch_id,
        source_id=source.id,
        revision_id=candidate.id,
        kind="statement",
        ordinal=1,
        source_key=case.rows[0].source_key,
        row_hash=case.rows[0].row_hash,
        fields=case.rows[0].fields,
    )
    db_session.add(row)
    await db_session.flush()
    page = await list_rows(
        db_session,
        owner.id,
        case.batch_id,
        source_id=source.id,
        revision_id=candidate.id,
        offset=0,
        limit=10,
    )
    assert page.total == 1 and page.items[0].id == row.id
    current = await list_rows(
        db_session, owner.id, case.batch_id, source_id=source.id, offset=0, limit=10
    )
    assert current.total == 2 and row.id not in {item.id for item in current.items}
    with pytest.raises(ImportError) as error:
        await list_rows(
            db_session,
            other_owner.id,
            case.batch_id,
            source_id=source.id,
            revision_id=candidate.id,
            offset=0,
            limit=10,
        )
    assert error.value.http_status == 404
