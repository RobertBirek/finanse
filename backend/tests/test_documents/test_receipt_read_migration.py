import importlib.util
from pathlib import Path

import pytest

from app.main import app  # noqa: F401 - complete metadata before schema fixture

TABLES = {
    "receipt_read_policy",
    "receipt_read_streams",
    "receipt_read_jobs",
    "receipt_read_extractions",
    "receipt_read_usage",
    "receipt_read_reservations",
    "receipt_read_lineage",
}


def migration():
    files = list(
        (Path(__file__).resolve().parents[2] / "migrations/versions").glob(
            "*_receipt_item_extraction.py"
        )
    )
    assert len(files) == 1, "Missing additive receipt item extraction migration"
    spec = importlib.util.spec_from_file_location("receipt_read_migration", files[0])
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_receipt_read_upgrade_is_seven_new_tables_only(monkeypatch):
    m = migration()
    calls = []

    class Recorder:
        def f(self, name):
            return name

        def __getattr__(self, name):
            return lambda *args, **kw: calls.append((name, args, kw))

    monkeypatch.setattr(m, "op", Recorder())
    m.upgrade()
    assert m.down_revision == "a3ffcaf427aa"
    assert {args[0] for name, args, _ in calls if name == "create_table"} == TABLES
    for name, args, kw in calls:
        assert name in {"create_table", "create_index", "create_foreign_key"}
        if name == "create_index":
            assert args[1] in TABLES
        if name == "create_foreign_key":
            assert args[1] in TABLES and kw["ondelete"] == "RESTRICT"


def test_populated_receipt_read_downgrade_refuses_before_ddl(monkeypatch):
    m = migration()
    queries = []
    ddl = []

    class Connection:
        def execute(self, q):
            queries.append(str(q))

        def scalar(self, q):
            queries.append(str(q))
            return True

    class Recorder:
        def get_bind(self):
            return Connection()

        def __getattr__(self, name):
            return lambda *args, **kw: ddl.append((name, args))

    monkeypatch.setattr(m, "op", Recorder())
    with pytest.raises(RuntimeError, match="receipt"):
        m.downgrade()
    assert "ACCESS EXCLUSIVE" in queries[0] and all(t in queries[0] for t in TABLES)
    assert ddl == []


def test_receipt_read_head_fk_created_after_both_tables(monkeypatch):
    m = migration()
    calls = []

    class Recorder:
        def f(self, name):
            return name

        def __getattr__(self, name):
            return lambda *args, **kw: calls.append((name, args, kw))

    monkeypatch.setattr(m, "op", Recorder())
    m.upgrade()
    fk = [
        (i, args, kw)
        for i, (name, args, kw) in enumerate(calls)
        if name == "create_foreign_key" and args[0] == "fk_read_stream_head"
    ]
    assert len(fk) == 1
    index, args, kw = fk[0]
    assert all(
        any(name == "create_table" and a[0] == table for name, a, _ in calls[:index])
        for table in ["receipt_read_jobs", "receipt_read_streams"]
    )
    assert (
        args[1:]
        == (
            "receipt_read_streams",
            "receipt_read_jobs",
            ["user_id", "id", "latest_job_id"],
            ["user_id", "stream_id", "id"],
        )
        and kw["ondelete"] == "RESTRICT"
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_lineage_and_stream_head_cannot_reference_foreign_owner(db_session):
    import uuid

    from sqlalchemy.exc import IntegrityError

    from app.documents.models import Document
    from app.documents.receipt_read_models import ReceiptReadJob, ReceiptReadStream
    from app.finance.models import FinanceCommandReceipt, FinancialDocument

    owner = uuid.uuid4()
    bill = FinancialDocument(user_id=owner)
    doc = Document(
        user_id=owner,
        filename="synthetic.png",
        original_name="synthetic.png",
        mime_type="image/png",
        size_bytes=10,
        storage_path="synthetic.png",
        sha256_hash="a" * 64,
    )
    receipt = FinanceCommandReceipt(
        user_id=owner, action="read-test", key="test", request_hash="a" * 64, response_json={}
    )
    db_session.add_all([bill, doc, receipt])
    await db_session.flush()
    stream = ReceiptReadStream(
        user_id=owner, bill_id=bill.id, source_sha256="a" * 64, configuration_fingerprint="b" * 64
    )
    db_session.add(stream)
    await db_session.flush()
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                ReceiptReadJob(
                    user_id=uuid.uuid4(),
                    stream_id=stream.id,
                    bill_id=bill.id,
                    document_id=doc.id,
                    generation=1,
                    source_sha256="a" * 64,
                    header_sha256="b" * 64,
                    configuration_fingerprint="b" * 64,
                    policy_epoch=1,
                    consent_json={},
                    grant_receipt_id=receipt.id,
                )
            )
            await db_session.flush()

    from sqlalchemy import update

    from app.documents.receipt_read_models import ReceiptReadExtraction
    from app.finance.receipt_models import ReceiptItemRevision
    from app.finance.receipt_read_models import ReceiptReadLineage

    other_stream = ReceiptReadStream(
        user_id=owner, bill_id=bill.id, source_sha256="c" * 64, configuration_fingerprint="b" * 64
    )
    db_session.add(other_stream)
    await db_session.flush()
    job = ReceiptReadJob(
        user_id=owner,
        stream_id=other_stream.id,
        bill_id=bill.id,
        document_id=doc.id,
        generation=1,
        source_sha256="c" * 64,
        header_sha256="b" * 64,
        configuration_fingerprint="b" * 64,
        policy_epoch=1,
        consent_json={},
        grant_receipt_id=receipt.id,
    )
    db_session.add(job)
    await db_session.flush()
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await db_session.execute(
                update(ReceiptReadStream)
                .where(ReceiptReadStream.id == stream.id)
                .values(latest_job_id=job.id)
            )
    extraction = ReceiptReadExtraction(
        user_id=owner,
        job_id=job.id,
        bill_id=bill.id,
        document_id=doc.id,
        source_sha256="c" * 64,
        derivative_sha256="d" * 64,
        header_sha256="b" * 64,
        payload_sha256="e" * 64,
        payload_json={},
        proposal_json={},
        problems_json=[],
        quality="partial",
        provider="test",
        model="test",
        prompt_version="v1",
        schema_version="v1",
        normalizer_version="v1",
        configuration_fingerprint="b" * 64,
        policy_epoch=1,
    )
    foreign_revision = ReceiptItemRevision(
        user_id=uuid.uuid4(),
        bill_id=bill.id,
        sequence=1,
        kind="draft",
        header_sha256="a" * 64,
        header_snapshot={},
        body_sha256="b" * 64,
        command_receipt_id=receipt.id,
    )
    db_session.add_all([extraction, foreign_revision])
    await db_session.flush()
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                ReceiptReadLineage(
                    user_id=owner,
                    bill_id=bill.id,
                    item_revision_id=foreign_revision.id,
                    extraction_id=extraction.id,
                    extraction_sha256="e" * 64,
                    body_sha256="f" * 64,
                    line_map={},
                    discount_map={},
                    pending_problem_keys=[],
                    acknowledgements={},
                )
            )
            await db_session.flush()
