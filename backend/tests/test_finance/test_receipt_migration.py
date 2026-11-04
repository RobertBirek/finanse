import importlib.util
from pathlib import Path

import pytest

from app.main import app  # noqa: F401 - register domain metadata before schema fixture

TABLES = {
    "receipt_stores",
    "receipt_item_states",
    "receipt_item_revisions",
    "receipt_item_lines",
    "receipt_item_discounts",
    "receipt_item_discount_shares",
}


def revision():
    paths = list(
        (Path(__file__).resolve().parents[2] / "migrations/versions").glob(
            "*_receipt_item_categorization.py"
        )
    )
    assert len(paths) == 1, "Missing additive receipt item revision"
    spec = importlib.util.spec_from_file_location("receipt_revision", paths[0])
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_receipt_upgrade_only_adds_six_evidence_tables(monkeypatch):
    mod = revision()
    calls = []

    class Recorder:
        def __getattr__(self, name):
            return lambda *args, **kw: calls.append((name, args, kw))

        def f(self, name):
            return name

    monkeypatch.setattr(mod, "op", Recorder())
    mod.upgrade()
    assert {a[0] for n, a, _ in calls if n == "create_table"} == TABLES
    assert mod.down_revision == "243aa1d9461c"
    for name, args, kw in calls:
        assert name in {"create_table", "create_index", "create_foreign_key"}
        if name == "create_index":
            assert args[1] in TABLES
        if name == "create_foreign_key":
            assert args[1] in TABLES and kw.get("ondelete") == "RESTRICT"


def test_populated_receipt_downgrade_refuses_before_destructive_ddl(monkeypatch):
    mod = revision()
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

        def __getattr__(self, n):
            return lambda *args, **kw: ddl.append((n, args))

    monkeypatch.setattr(mod, "op", Recorder())
    with pytest.raises(RuntimeError, match="receipt"):
        mod.downgrade()
    assert "ACCESS EXCLUSIVE" in queries[0] and all(t in queries[0] for t in TABLES)
    assert ddl == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_discount_share_cannot_cross_revision_or_owner(db_session):
    import uuid

    from sqlalchemy.exc import IntegrityError

    from app.finance.models import FinanceCommandReceipt, FinancialDocument
    from app.finance.receipt_models import (
        ReceiptItemDiscount,
        ReceiptItemDiscountShare,
        ReceiptItemLine,
        ReceiptItemRevision,
    )
    from tests.test_finance.test_bill_payments import create_owner

    owner = await create_owner(db_session)
    bill = FinancialDocument(user_id=owner)
    db_session.add(bill)
    await db_session.flush()
    receipt = FinanceCommandReceipt(
        user_id=owner, action="receipt-test", key="one", request_hash="a" * 64, response_json={}
    )
    db_session.add(receipt)
    await db_session.flush()
    revisions = [
        ReceiptItemRevision(
            user_id=owner,
            bill_id=bill.id,
            sequence=n,
            kind="draft",
            header_sha256="a" * 64,
            header_snapshot={},
            body_sha256="b" * 64,
            command_receipt_id=receipt.id,
        )
        for n in (1, 2)
    ]
    db_session.add_all(revisions)
    await db_session.flush()
    line = ReceiptItemLine(
        user_id=owner,
        revision_id=revisions[0].id,
        line_key=uuid.uuid4(),
        position=0,
        name="Product",
        normalized_name="product",
        amount_minor=100,
    )
    discount = ReceiptItemDiscount(
        user_id=owner,
        revision_id=revisions[1].id,
        discount_key=uuid.uuid4(),
        position=0,
        name="Discount",
        amount_minor=10,
    )
    db_session.add_all([line, discount])
    await db_session.flush()
    for bad_owner in [owner, uuid.uuid4()]:
        with pytest.raises(IntegrityError):
            async with db_session.begin_nested():
                db_session.add(
                    ReceiptItemDiscountShare(
                        user_id=bad_owner,
                        revision_id=revisions[1].id,
                        discount_key=discount.discount_key,
                        line_key=line.line_key,
                        amount_minor=10,
                    )
                )
                await db_session.flush()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_approved_revision_requires_nonnull_store_version(db_session):
    from sqlalchemy.exc import IntegrityError

    from app.finance.models import FinanceCommandReceipt, FinancialDocument
    from app.finance.receipt_models import ReceiptItemRevision, ReceiptStore
    from tests.test_finance.test_bill_payments import create_owner

    owner = await create_owner(db_session)
    store = ReceiptStore(user_id=owner, name="Synthetic", normalized_name="synthetic")
    bill = FinancialDocument(user_id=owner)
    receipt = FinanceCommandReceipt(
        user_id=owner, action="receipt-test", key="one", request_hash="a" * 64, response_json={}
    )
    db_session.add_all([store, bill, receipt])
    await db_session.flush()
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                ReceiptItemRevision(
                    user_id=owner,
                    bill_id=bill.id,
                    sequence=1,
                    kind="approved",
                    store_id=store.id,
                    store_version=None,
                    header_sha256="a" * 64,
                    header_snapshot={},
                    body_sha256="b" * 64,
                    command_receipt_id=receipt.id,
                )
            )
            await db_session.flush()
