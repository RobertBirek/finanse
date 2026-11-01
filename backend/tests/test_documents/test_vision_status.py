import pytest
from sqlalchemy import event

from app.documents import service
from app.documents.job_models import DocumentProcessingJob
from app.documents.models import DocumentExtractionRevision
from app.identity.models import User
from test_documents.fixtures import valid_jpeg_bytes


@pytest.mark.integration
async def test_document_mapper_uses_batched_latest_review_and_text_existence(
    db_session, tmp_path, monkeypatch
):
    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path)
    user = User(email="vision-status@example.com", password_hash="hash", display_name="Vision")
    db_session.add(user)
    await db_session.flush()
    documents = []
    for number in range(50):
        document = service.Document(
            user_id=user.id,
            filename=f"{number}.jpg",
            original_name=f"{number}.jpg",
            mime_type="image/jpeg",
            sha256_hash=f"{number:064d}",
            size_bytes=1,
            storage_path=f"{number}",
        )
        db_session.add(document)
        await db_session.flush()
        documents.append(document)
        db_session.add(
            DocumentExtractionRevision(
                user_id=user.id,
                document_id=document.id,
                revision=1,
                status="incomplete",
                data={
                    "document_type": "other",
                    "fields": {},
                    "provenance": {},
                    "parser_version": None,
                },
                field_provenance={},
                input_method="image",
                error_code="vision_disabled",
            )
        )
    await service.save_extracted_text(db_session, documents[0].id, "text")
    db_session.add(
        DocumentExtractionRevision(
            user_id=user.id,
            document_id=documents[0].id,
            revision=2,
            status="ready",
            data={"document_type": "other", "fields": {}, "provenance": {}, "parser_version": None},
            field_provenance={},
            input_method="image",
        )
    )
    await db_session.flush()

    loaded = await service.get_documents(db_session, user.id)
    statements: list[str] = []
    engine = db_session.bind.sync_engine

    def count_sql(*args):
        statements.append(args[2])

    event.listen(engine, "before_cursor_execute", count_sql)
    try:
        responses = await service.document_responses(db_session, user.id, loaded)
    finally:
        event.remove(engine, "before_cursor_execute", count_sql)

    assert len(responses) == 50
    assert responses[0].has_extracted_text is True
    assert all("storage_path" not in item.model_dump() for item in responses)
    assert all(item.review is not None for item in responses)
    assert len(statements) <= 4
    assert next(item for item in responses if item.id == documents[0].id).review.revision == 2


@pytest.mark.integration
async def test_summary_is_owner_scoped_and_vision_incomplete_is_not_ocr_success(
    db_session, tmp_path, monkeypatch
):
    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path)
    owner = User(email="owner-status@example.com", password_hash="hash", display_name="Owner")
    other = User(email="other-status@example.com", password_hash="hash", display_name="Other")
    db_session.add_all([owner, other])
    await db_session.flush()
    document, _ = await service.store_document(
        db_session, owner.id, valid_jpeg_bytes(), "a.jpg", "image/jpeg"
    )
    revision = DocumentExtractionRevision(
        user_id=owner.id,
        document_id=document.id,
        revision=1,
        status="incomplete",
        data={"document_type": "other", "fields": {}, "provenance": {}, "parser_version": None},
        field_provenance={},
        input_method="image",
        error_code="vision_failed",
    )
    db_session.add(revision)
    await db_session.flush()
    db_session.add(
        DocumentProcessingJob(
            user_id=owner.id,
            document_id=document.id,
            revision_id=revision.id,
            kind="vision",
            intent_key="x",
            request_hash="x",
            state="failed",
            error_code="vision_failed",
        )
    )
    responses = await service.document_responses(db_session, owner.id, [document])
    assert responses[0].review is not None
    assert responses[0].review.status == "incomplete"
    assert responses[0].has_extracted_text is False
    assert await service.get_document(db_session, other.id, document.id) is None
