from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.documents import service as document_service
from app.documents.import_storage import store_import_document
from app.documents.job_models import DocumentProcessingJob
from app.finance.imports import worker as import_worker
from app.finance.imports.jobs import request_prepare
from app.finance.imports.service import create_batch, get_batch, list_rows
from app.finance.imports.storage import attach_source
from app.identity.models import User
from tests.test_finance.test_bank_imports.factories import ledger_snapshot, seed_legacy_transfer

pytestmark = pytest.mark.integration


async def test_real_revolut_pipeline_stages_fee_without_mutating_ledger_or_enqueuing_ai(
    db_session: AsyncSession,
    owner: User,
    test_database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(document_service, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(
        import_worker,
        "async_session_factory",
        async_sessionmaker(test_database, expire_on_commit=False),
    )
    await seed_legacy_transfer(db_session, owner.id)
    before = await ledger_snapshot(db_session)
    content = (Path(__file__).parent / "fixtures/revolut_fee_excluded.csv").read_bytes()
    document, _ = await store_import_document(
        db_session, owner.id, filename="source.csv", content=content
    )
    batch = await create_batch(db_session, owner.id, "statement")
    attached = await attach_source(db_session, owner.id, batch.id, document.id)
    job = await request_prepare(
        db_session, owner.id, attached.source.id, key="real-revolut-pipeline"
    )
    owner_id, batch_id = owner.id, batch.id
    await db_session.commit()
    await import_worker.process_import_job({}, str(job.id))
    db_session.expire_all()
    restored = await get_batch(db_session, owner_id, batch_id)
    assert restored is not None
    source = restored.sources[0]
    assert source.bank == "revolut" and source.processing_state == "ready"
    assert source.validation_state == "needs_review" and "opening_derived" in source.warnings
    page = await list_rows(db_session, owner_id, batch_id, source_id=source.id, offset=0, limit=10)
    assert page.total == 2
    row = page.items[1].bank_fields
    assert row is not None and (row.amount, row.fee) == (-120, 20)
    assert await db_session.scalar(select(func.count()).select_from(DocumentProcessingJob)) == 0
    assert await ledger_snapshot(db_session) == before
