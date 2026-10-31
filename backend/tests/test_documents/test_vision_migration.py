import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

import app.main  # noqa: F401 - register complete metadata for integration schema lifecycle


@pytest.mark.integration
@pytest.mark.asyncio
async def test_legacy_rows_remain_text_and_never_create_jobs(test_database) -> None:
    path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/92eef8e8086c_document_vision_jobs.py"
    )
    spec = importlib.util.spec_from_file_location("vision_document_jobs", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    def cycle(connection):
        document_id = "00000000-0000-0000-0000-000000000001"
        user_id = "00000000-0000-0000-0000-000000000002"
        with Operations.context(MigrationContext.configure(connection)):
            module.downgrade()
        connection.execute(
            sa.text(
                """INSERT INTO documents
                (id, user_id, filename, original_name, mime_type, sha256_hash, size_bytes, storage_path)
                VALUES (:id, :user_id, 'receipt.pdf', 'receipt.pdf', 'application/pdf', :sha, 20, 'aa/hash')"""
            ),
            {"id": document_id, "user_id": user_id, "sha": "a" * 64},
        )
        connection.execute(
            sa.text(
                """INSERT INTO document_texts (id, document_id, extracted_text, ocr_engine)
                VALUES ('00000000-0000-0000-0000-000000000003', :document_id, 'legacy', 'ocr')"""
            ),
            {"document_id": document_id},
        )
        connection.execute(
            sa.text(
                """INSERT INTO document_extraction_revisions
                (id, user_id, document_id, revision, status, data, field_provenance)
                VALUES ('00000000-0000-0000-0000-000000000004', :user_id, :document_id, 1,
                        'ready', '{}', '{}')"""
            ),
            {"user_id": user_id, "document_id": document_id},
        )
        legacy = {
            "document": dict(
                connection.execute(
                    sa.text(
                        """SELECT id, user_id, filename, original_name, mime_type, sha256_hash,
                                  size_bytes, storage_path, status, attempt_count, next_attempt_at,
                                  last_error_code, created_at, updated_at
                           FROM documents WHERE id = :document_id"""
                    ),
                    {"document_id": document_id},
                )
                .mappings()
                .one()
            ),
            "text": dict(
                connection.execute(
                    sa.text(
                        """SELECT id, document_id, extracted_text, ocr_engine, extracted_at,
                                  created_at, updated_at
                           FROM document_texts WHERE document_id = :document_id"""
                    ),
                    {"document_id": document_id},
                )
                .mappings()
                .one()
            ),
            "revision": dict(
                connection.execute(
                    sa.text(
                        """SELECT id, user_id, document_id, revision, status, data,
                                  field_provenance, parser_version, error_code, created_at, updated_at
                           FROM document_extraction_revisions WHERE document_id = :document_id"""
                    ),
                    {"document_id": document_id},
                )
                .mappings()
                .one()
            ),
        }
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
        assert (
            dict(
                connection.execute(
                    sa.text(
                        """SELECT id, user_id, filename, original_name, mime_type, sha256_hash,
                              size_bytes, storage_path, status, attempt_count, next_attempt_at,
                              last_error_code, created_at, updated_at
                       FROM documents WHERE id = :document_id"""
                    ),
                    {"document_id": document_id},
                )
                .mappings()
                .one()
            )
            == legacy["document"]
        )
        assert (
            dict(
                connection.execute(
                    sa.text(
                        """SELECT id, document_id, extracted_text, ocr_engine, extracted_at,
                              created_at, updated_at
                       FROM document_texts WHERE document_id = :document_id"""
                    ),
                    {"document_id": document_id},
                )
                .mappings()
                .one()
            )
            == legacy["text"]
        )
        assert (
            dict(
                connection.execute(
                    sa.text(
                        """SELECT id, user_id, document_id, revision, status, data,
                              field_provenance, parser_version, error_code, created_at, updated_at
                       FROM document_extraction_revisions WHERE document_id = :document_id"""
                    ),
                    {"document_id": document_id},
                )
                .mappings()
                .one()
            )
            == legacy["revision"]
        )
        row = connection.execute(
            sa.text(
                """SELECT d.processing_method, d.sha256_hash, r.input_method, r.source_sha256,
                          (SELECT count(*) FROM document_processing_jobs),
                          (SELECT enabled FROM document_vision_policy WHERE id = 1)
                   FROM documents d JOIN document_extraction_revisions r ON r.document_id = d.id"""
            )
        ).one()
        assert tuple(row) == ("legacy_ocr", "a" * 64, "text", None, 0, False)

    async with test_database.begin() as conn:
        await conn.run_sync(cycle)
