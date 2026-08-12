import hashlib
import uuid

import pytest

from app.documents.service import compute_sha256, get_document, get_documents, upload_document


class TestComputeSha256:
    def test_computes_hash(self):
        content = b"hello world"
        expected = hashlib.sha256(content).hexdigest()
        result = compute_sha256(content)
        assert result == expected
        assert len(result) == 64

    def test_different_content_different_hash(self):
        assert compute_sha256(b"a") != compute_sha256(b"b")


class TestDocumentService:
    @pytest.mark.asyncio
    async def test_upload_creates_document(self, db_session):
        user_id = uuid.uuid4()
        doc = await upload_document(db_session, user_id, b"%PDF-1.4 test", "test.pdf", "application/pdf")
        assert doc.id is not None
        assert doc.original_name == "test.pdf"
        assert doc.mime_type == "application/pdf"
        assert doc.size_bytes == 13
        assert doc.status == "pending"

    @pytest.mark.asyncio
    async def test_upload_deduplicates_same_hash(self, db_session):
        user_id = uuid.uuid4()
        content = b"same content"
        doc1 = await upload_document(db_session, user_id, content, "a.pdf", "application/pdf")
        doc2 = await upload_document(db_session, user_id, content, "b.pdf", "application/pdf")
        assert doc1.id == doc2.id

    @pytest.mark.asyncio
    async def test_list_returns_by_user(self, db_session):
        a, b = uuid.uuid4(), uuid.uuid4()
        await upload_document(db_session, a, b"a", "a.pdf", "application/pdf")
        await upload_document(db_session, b, b"b", "b.pdf", "application/pdf")
        assert len(await get_documents(db_session, a)) == 1
        assert len(await get_documents(db_session, b)) == 1

    @pytest.mark.asyncio
    async def test_get_document_by_id(self, db_session):
        user_id = uuid.uuid4()
        doc = await upload_document(db_session, user_id, b"test", "doc.pdf", "application/pdf")
        found = await get_document(db_session, user_id, doc.id)
        assert found is not None and found.id == doc.id
        assert await get_document(db_session, user_id, uuid.uuid4()) is None
