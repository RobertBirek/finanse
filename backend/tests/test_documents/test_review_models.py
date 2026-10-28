import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.documents.models import Document, DocumentExtractionRevision


@pytest.mark.integration
async def test_extraction_revision_is_unique_per_document_revision(db_session):
    user_id = uuid.uuid4()
    document = Document(
        user_id=user_id,
        filename="source.pdf",
        original_name="source.pdf",
        mime_type="application/pdf",
        sha256_hash="1" * 64,
        size_bytes=1,
        storage_path="private/source.pdf",
    )
    db_session.add(document)
    await db_session.flush()
    db_session.add_all(
        [
            DocumentExtractionRevision(
                user_id=user_id,
                document_id=document.id,
                revision=1,
                status="pending",
                data={},
                field_provenance={},
            ),
            DocumentExtractionRevision(
                user_id=user_id,
                document_id=document.id,
                revision=1,
                status="ready",
                data={},
                field_provenance={},
            ),
        ]
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
