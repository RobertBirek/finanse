import hashlib
import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.audit.models import AuditEvent
from app.documents import service as document_service
from app.documents.import_storage import ImportStorageError, store_import_document
from app.documents.job_models import DocumentProcessingJob
from app.documents.lifecycle import DocumentLifecycleError, set_document_archived
from app.documents.models import Document, DocumentExtractionRevision, DocumentText
from app.documents.review_service import prepare_review, request_ocr_retry
from app.finance.bills_schemas import MutationContext
from app.finance.imports import storage as import_storage
from app.finance.imports.errors import ImportError
from app.finance.imports.models import ImportSource
from app.finance.imports.service import create_batch
from app.finance.imports.storage import attach_source, read_import_input
from app.identity.models import User
from app.identity.router import get_current_user
from app.main import app
from tests.test_finance.test_bank_imports.factories import ledger_snapshot, text_pdf_bytes

pytestmark = pytest.mark.integration

CSV = (
    "Rodzaj,Produkt,Data rozpoczęcia,Data zrealizowania,Opis,Kwota,Opłata,Waluta,State,Saldo\n"
    "Płatność kartą,Bieżący,2026-01-02 12:00:00,2026-01-02 12:00:01,Test,-1.00,0.00,PLN,COMPLETED,9.00\n"
).encode()


@pytest.fixture(autouse=True)
def private_upload_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "uploads"
    directory.mkdir()
    monkeypatch.setattr(document_service, "UPLOAD_DIR", directory)
    return directory


async def test_bank_upload_has_no_document_jobs_or_ledger_effect(
    db_session: AsyncSession,
    owner: User,
    private_upload_dir: Path,
) -> None:
    before = await ledger_snapshot(db_session)
    document, duplicate = await store_import_document(
        db_session, owner.id, filename="statement.csv", content=CSV
    )
    assert (
        not duplicate and document.processing_method == "bank_import" and document.status == "done"
    )
    assert (private_upload_dir / document.storage_path).read_bytes() == CSV
    assert document.sha256_hash == hashlib.sha256(CSV).hexdigest()
    for model in [DocumentProcessingJob, DocumentExtractionRevision, DocumentText]:
        assert await db_session.scalar(select(func.count()).select_from(model)) == 0
    assert await ledger_snapshot(db_session) == before


async def test_duplicate_filename_changes_do_not_create_another_document(
    db_session: AsyncSession,
    owner: User,
) -> None:
    first, _ = await store_import_document(db_session, owner.id, filename="a.csv", content=CSV)
    second, duplicate = await store_import_document(
        db_session, owner.id, filename="b.csv", content=CSV
    )
    assert duplicate and second.id == first.id and second.original_name == "a.csv"


async def test_same_bytes_from_other_owner_never_reveal_their_document(
    db_session: AsyncSession,
    owner: User,
    other_owner: User,
) -> None:
    first, _ = await store_import_document(db_session, owner.id, filename="a.csv", content=CSV)
    second, duplicate = await store_import_document(
        db_session, other_owner.id, filename="a.csv", content=CSV
    )
    assert not duplicate and second.id != first.id and second.user_id == other_owner.id


async def test_general_document_upload_still_rejects_csv(
    db_session: AsyncSession, owner: User
) -> None:
    with pytest.raises(document_service.UnsupportedDocumentFormatError):
        await document_service.store_document(
            db_session, owner.id, CSV, "statement.csv", "text/csv"
        )


@pytest.mark.parametrize(
    "content,filename",
    [
        (b"", "empty.csv"),
        (b"wrong,columns\n1,2", "wrong.csv"),
        (b"PK\x03\x04sheet", "statement.xlsx"),
        (b"%PDF-truncated", "statement.pdf"),
        (CSV.replace(b",9.00", b",9.00,unexpected-column"), "bad.csv"),
        (CSV.replace(b"Test", b"bad\x00field"), "bad.csv"),
        (CSV, "not-a-pdf.pdf"),
        (CSV.split(b"\n", 1)[0] + b"\n\n", "header-only.csv"),
    ],
)
async def test_invalid_sources_are_not_stored(
    db_session: AsyncSession,
    owner: User,
    content: bytes,
    filename: str,
) -> None:
    with pytest.raises(ImportStorageError):
        await store_import_document(db_session, owner.id, filename=filename, content=content)
    assert await db_session.scalar(select(func.count()).select_from(Document)) == 0


async def test_same_source_in_another_batch_opens_original_import(
    db_session: AsyncSession,
    owner: User,
) -> None:
    document, _ = await store_import_document(db_session, owner.id, filename="a.csv", content=CSV)
    first = await create_batch(db_session, owner.id, "statement")
    original = await attach_source(db_session, owner.id, first.id, document.id)
    second = await create_batch(db_session, owner.id, "statement")
    duplicate = await attach_source(db_session, owner.id, second.id, document.id)
    assert not original.is_duplicate and duplicate.is_duplicate
    assert duplicate.existing_batch_id == first.id and duplicate.source.id == original.source.id
    assert await db_session.scalar(select(func.count()).select_from(ImportSource)) == 1


async def test_crossowner_attach_is_not_found(
    db_session: AsyncSession,
    owner: User,
    other_owner: User,
) -> None:
    document, _ = await store_import_document(db_session, owner.id, filename="a.csv", content=CSV)
    batch = await create_batch(db_session, other_owner.id, "statement")
    with pytest.raises(ImportError) as error:
        await attach_source(db_session, other_owner.id, batch.id, document.id)
    assert error.value.http_status == 404


async def test_pinned_import_source_cannot_be_archived_or_reprocessed(
    db_session: AsyncSession,
    owner: User,
) -> None:
    document, _ = await store_import_document(db_session, owner.id, filename="a.csv", content=CSV)
    batch = await create_batch(db_session, owner.id, "statement")
    await attach_source(db_session, owner.id, batch.id, document.id)
    for operation in [
        lambda: set_document_archived(db_session, owner.id, document.id, archived=True),
        lambda: document_service.delete_document(db_session, owner.id, document.id),
        lambda: prepare_review(
            db_session,
            owner.id,
            document.id,
            refresh=True,
            context=MutationContext(idempotency_key=str(uuid.uuid4())),
        ),
        lambda: request_ocr_retry(
            db_session,
            owner.id,
            document.id,
            context=MutationContext(idempotency_key=str(uuid.uuid4())),
        ),
    ]:
        with pytest.raises(DocumentLifecycleError) as error:
            await operation()
        assert error.value.code == "document_import_source"
    assert document.archived_at is None
    assert await db_session.scalar(select(func.count()).select_from(DocumentProcessingJob)) == 0


async def test_reused_ready_pdf_retains_original_processing_method(
    db_session: AsyncSession,
    owner: User,
) -> None:
    content = text_pdf_bytes("Bank source\nSynthetic table")
    document, _ = await document_service.store_document(
        db_session, owner.id, content, "old.pdf", "application/pdf"
    )
    document.status = "done"
    await db_session.flush()
    batch = await create_batch(db_session, owner.id, "statement")
    source = await attach_source(db_session, owner.id, batch.id, document.id)
    assert document.processing_method == "legacy_ocr"
    parsed_input = await read_import_input(db_session, owner.id, source.source.id)
    assert parsed_input.content == content and parsed_input.pages is not None
    assert "Synthetic table" in parsed_input.pages[0]


async def test_active_legacy_processing_blocks_attach(
    db_session: AsyncSession, owner: User
) -> None:
    document, _ = await document_service.store_document(
        db_session, owner.id, text_pdf_bytes("Active document"), "active.pdf", "application/pdf"
    )
    batch = await create_batch(db_session, owner.id, "statement")
    with pytest.raises(ImportError) as error:
        await attach_source(db_session, owner.id, batch.id, document.id)
    assert error.value.code == "document_processing_active"


async def test_changed_original_hash_blocks_read_without_replacement(
    db_session: AsyncSession,
    owner: User,
    private_upload_dir: Path,
) -> None:
    document, _ = await store_import_document(db_session, owner.id, filename="a.csv", content=CSV)
    batch = await create_batch(db_session, owner.id, "statement")
    attached = await attach_source(db_session, owner.id, batch.id, document.id)
    path = private_upload_dir / document.storage_path
    path.write_bytes(b"tampered-test-content")
    with pytest.raises(ImportError) as error:
        await read_import_input(db_session, owner.id, attached.source.id)
    assert error.value.code == "source_integrity_failed"
    assert path.read_bytes() == b"tampered-test-content"


async def test_pdf_parsing_does_not_hold_the_owner_ledger_mutation_lock(
    db_session: AsyncSession,
    owner: User,
    test_database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document, _ = await store_import_document(
        db_session, owner.id, filename="source.pdf", content=text_pdf_bytes("Synthetic bank table")
    )
    batch = await create_batch(db_session, owner.id, "statement")
    original = import_storage._parser_input

    async def checked_input(source_document: Document):
        async with async_sessionmaker(test_database)() as probe:
            available = await probe.scalar(
                select(
                    func.pg_try_advisory_xact_lock(
                        func.hashtext(f"bill-allocation:{owner.id}"),
                    )
                )
            )
        assert available is True, "Bounded parser must finish before the owner mutation lock"
        return await original(source_document)

    monkeypatch.setattr(import_storage, "_parser_input", checked_input)
    attached = await attach_source(db_session, owner.id, batch.id, document.id)
    assert attached.source.document_id == document.id


async def test_duplicate_upload_does_not_repair_missing_original_silently(
    db_session: AsyncSession,
    owner: User,
    private_upload_dir: Path,
) -> None:
    document, _ = await store_import_document(
        db_session, owner.id, filename="source.csv", content=CSV
    )
    path = private_upload_dir / document.storage_path
    path.unlink()
    with pytest.raises(ImportStorageError) as error:
        await store_import_document(db_session, owner.id, filename="again.csv", content=CSV)
    assert error.value.code == "source_integrity_failed" and not path.exists()


async def test_document_source_path_cannot_escape_upload_storage(
    db_session: AsyncSession,
    owner: User,
) -> None:
    document, _ = await store_import_document(
        db_session, owner.id, filename="source.csv", content=CSV
    )
    document.storage_path = "/etc/passwd"
    with pytest.raises(ImportStorageError) as error:
        await store_import_document(db_session, owner.id, filename="again.csv", content=CSV)
    assert error.value.code == "source_integrity_failed"


async def test_formula_description_is_original_text_not_evaluated(
    db_session: AsyncSession,
    owner: User,
    private_upload_dir: Path,
) -> None:
    content = CSV.replace(b",Test,", b",=SUM(1+2),")
    document, _ = await store_import_document(
        db_session, owner.id, filename="source.csv", content=content
    )
    assert (private_upload_dir / document.storage_path).read_bytes() == content


async def test_configured_csv_row_limit_blocks_admission(
    db_session: AsyncSession,
    owner: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "FINANCE_IMPORT_MAX_CSV_ROWS", 1)
    header, row = CSV.split(b"\n", 1)
    content = header + b"\n" + row + row
    with pytest.raises(ImportStorageError) as error:
        await store_import_document(db_session, owner.id, filename="source.csv", content=content)
    assert error.value.code == "csv_row_limit" and error.value.http_status == 413


async def test_source_attachment_is_audited_once_without_replaying_finance(
    db_session: AsyncSession,
    owner: User,
) -> None:
    document, _ = await store_import_document(
        db_session, owner.id, filename="source.csv", content=CSV
    )
    batch = await create_batch(db_session, owner.id, "statement")
    source = await attach_source(db_session, owner.id, batch.id, document.id)
    await attach_source(db_session, owner.id, batch.id, document.id)
    events = (
        await db_session.scalars(
            select(AuditEvent).where(
                AuditEvent.user_id == owner.id,
                AuditEvent.entity_type == "bank_import_source",
                AuditEvent.entity_id == str(source.source.id),
            )
        )
    ).all()
    assert len(events) == 1 and events[0].action == "attach_source"
    assert events[0].new_state is not None
    assert events[0].new_state["document_id"] == str(document.id)
    assert events[0].new_state["sha256"] == hashlib.sha256(CSV).hexdigest()


async def test_pinned_source_http_guards_keep_original_private_and_downloadable(
    db_session: AsyncSession,
    owner: User,
    other_owner: User,
    async_client: AsyncClient,
) -> None:
    document, _ = await store_import_document(
        db_session, owner.id, filename="source.csv", content=CSV
    )
    batch = await create_batch(db_session, owner.id, "statement")
    await attach_source(db_session, owner.id, batch.id, document.id)
    app.dependency_overrides[get_current_user] = lambda: owner
    base = f"/api/documents/{document.id}"
    for method, path in [
        ("DELETE", base),
        ("POST", base + "/archive"),
        ("POST", base + "/review/prepare"),
    ]:
        result = await async_client.request(
            method, path, headers={"Idempotency-Key": str(uuid.uuid4())}
        )
        assert result.status_code == 409 and result.json()["code"] == "document_import_source"
    original = await async_client.get(base + "/original")
    assert original.status_code == 200 and original.content == CSV
    assert "no-store" in original.headers["cache-control"]
    assert original.headers["x-content-type-options"] == "nosniff"
    assert original.headers["content-disposition"].startswith("attachment;")
    app.dependency_overrides[get_current_user] = lambda: other_owner
    missing = await async_client.get(base + "/original")
    assert missing.status_code == 404 and CSV not in missing.content
