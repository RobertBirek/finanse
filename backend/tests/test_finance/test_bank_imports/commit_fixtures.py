from app.documents import service as documents
from app.finance.imports.decisions import save_decisions
from app.finance.imports.preview import prepare_preview
from app.finance.imports.schemas import CommitRequest, DecisionUpdate, PreviewRequest
from tests.test_finance.test_bank_imports.review_fixtures import review_case


async def confirmed_import(db, owner, directory, monkeypatch, payload=None, **changes):
    monkeypatch.setattr(documents, "UPLOAD_DIR", directory)
    case = await review_case(db, owner, directory, payload)
    decision = case.decision.model_copy(update=changes)
    batch = await save_decisions(
        db, owner, case.batch_id, DecisionUpdate(expected_version=1, decisions=[decision])
    )
    preview = await prepare_preview(
        db,
        owner,
        case.batch_id,
        PreviewRequest(
            expected_version=batch.version,
            group_ids=[decision.group_id],
            acknowledgements=[f"opening_gap:{case.source_id}"],
        ),
    )
    return case, CommitRequest(preview_id=preview.id, request_hash=preview.request_hash)
