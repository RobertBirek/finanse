"""Synthetic source bytes through HTTP, real worker, ledger and a fresh DB session."""

import uuid

import pytest
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.documents import service as documents
from app.finance.entities import create_account, create_category
from app.finance.imports import worker
from app.finance.imports.models import ImportEvidence
from app.finance.models import FinancialTransaction, Posting
from app.finance.schemas import AccountCreate, CategoryCreate
from tests.test_finance.test_account_currency import client_for
from tests.test_finance.test_bank_imports.factories import (
    ledger_snapshot,
    seed_legacy_transfer,
    text_pdf_bytes,
)
from tests.test_finance.test_bank_imports.test_revolut_csv import csv_source
from tests.test_finance.test_bank_imports.test_velo_account import FIRST, HEADER, SECOND, SUMMARY

pytestmark = pytest.mark.integration
ROOT = "/api/finance/imports"


def source_bytes(kind, *, overlap=False):
    if kind == "pdf":
        return text_pdf_bytes(HEADER + FIRST + SECOND + SUMMARY), "synthetic.pdf", "application/pdf"
    rows = [
        {"Kwota": "-10.00", "Saldo": "990.00", "Opis": "Synthetic purchase"},
        {"Kwota": "25.00", "Saldo": "1015.00", "Opis": "Synthetic external receipt"},
    ]
    if overlap:
        rows.append({"Kwota": "-5.00", "Saldo": "1010.00", "Opis": "Synthetic new purchase"})
    return csv_source(*rows).content, "synthetic.csv", "text/csv"


async def stage_and_parse(db, sessions, owner_id, monkeypatch, content, filename, mime):
    async with client_for(db, owner_id) as client:
        created = await client.post(
            ROOT, json={"kind": "statement"}, headers={"Idempotency-Key": uuid.uuid4().hex}
        )
        assert created.status_code == 201, created.text
        batch_id = created.json()["id"]
        uploaded = await client.post(
            f"{ROOT}/{batch_id}/sources",
            files={"file": (filename, content, mime)},
            headers={"Idempotency-Key": uuid.uuid4().hex},
        )
        assert uploaded.status_code == 201, uploaded.text
        source = uploaded.json()["source"]
        prepared = await client.post(
            f"{ROOT}/{batch_id}/sources/{source['id']}/prepare",
            headers={"Idempotency-Key": uuid.uuid4().hex},
        )
        assert prepared.status_code == 200, prepared.text
    await db.commit()
    monkeypatch.setattr(worker, "async_session_factory", sessions)
    await worker.process_import_job({}, prepared.json()["id"])
    return batch_id, source


@pytest.mark.parametrize("kind", ["pdf", "csv"])
async def test_real_source_to_committed_receipt_replay_and_fresh_read(
    db_session, test_database, owner, tmp_path, monkeypatch, kind
):
    monkeypatch.setattr(documents, "UPLOAD_DIR", tmp_path)
    owner_id = owner.id
    await seed_legacy_transfer(db_session, owner_id)
    account = await create_account(
        db_session,
        owner_id,
        AccountCreate(name="Acceptance account", type="checking", currency="PLN"),
    )
    expense = await create_category(
        db_session, owner_id, CategoryCreate(name="Cost", type="expense")
    )
    income = await create_category(
        db_session, owner_id, CategoryCreate(name="Receipt", type="income")
    )
    account_id, expense_id, income_id = account.id, expense.id, income.id
    baseline = await ledger_snapshot(db_session)
    initial_count = await db_session.scalar(select(func.count()).select_from(FinancialTransaction))
    sessions = async_sessionmaker(test_database, expire_on_commit=False)
    content, filename, mime = source_bytes(kind)
    batch_id, source = await stage_and_parse(
        db_session, sessions, owner_id, monkeypatch, content, filename, mime
    )
    async with sessions() as db:
        assert await ledger_snapshot(db) == baseline
        async with client_for(db, owner_id) as client:
            loaded = await client.get(f"{ROOT}/{batch_id}")
            assert loaded.status_code == 200
            batch = loaded.json()
            assert batch["sources"][0]["processing_state"] == "ready"
            assert all(
                check["result"] == "passed"
                for check in batch["sources"][0]["checks"]
                if check["required"]
            )
            rows = (await client.get(f"{ROOT}/{batch_id}/rows")).json()["items"]
            assert len(rows) == 2
            decisions = [
                {
                    "group_id": str(uuid.uuid4()),
                    "row_ids": [row["id"]],
                    "action": "create",
                    "kind": "expense" if row["bank_fields"]["amount"] < 0 else "income",
                    "account_id": str(account_id),
                    "category_id": str(
                        expense_id if row["bank_fields"]["amount"] < 0 else income_id
                    ),
                    "acknowledgements": [],
                }
                for row in rows
            ]
            saved = await client.put(
                f"{ROOT}/{batch_id}/decisions",
                json={"expected_version": batch["version"], "decisions": decisions},
                headers={"Idempotency-Key": "accept-decisions"},
            )
            assert saved.status_code == 200, saved.text
            preview = await client.post(
                f"{ROOT}/{batch_id}/preview",
                json={
                    "expected_version": saved.json()["version"],
                    "group_ids": [decision["group_id"] for decision in decisions],
                    "acknowledgements": [f"opening_gap:{source['id']}"],
                },
                headers={"Idempotency-Key": "accept-preview"},
            )
            assert preview.status_code == 200, preview.text
            assert await ledger_snapshot(db) == baseline
            body = {
                "preview_id": preview.json()["id"],
                "request_hash": preview.json()["request_hash"],
            }
            result = await client.post(
                f"{ROOT}/{batch_id}/commit", json=body, headers={"Idempotency-Key": "accept-commit"}
            )
            assert result.status_code == 200, result.text
            receipt = result.json()
            assert len(receipt["transaction_ids"]) == 2 and receipt["commit_state"] == "committed"
            assert (
                await client.post(
                    f"{ROOT}/{batch_id}/commit",
                    json=body,
                    headers={"Idempotency-Key": "accept-commit"},
                )
            ).json() == receipt
        await db.commit()
    async with sessions() as db:
        async with client_for(db, owner_id) as client:
            assert (await client.get(f"{ROOT}/{batch_id}/commands/accept-commit")).json() == receipt
            original = await client.get(f"/api/documents/{source['document_id']}/original")
            assert original.status_code == 200 and original.content == content
            duplicate = await client.post(
                f"{ROOT}/{batch_id}/sources",
                files={"file": (filename, content, mime)},
                headers={"Idempotency-Key": "duplicate-source"},
            )
            assert duplicate.status_code == 201 and duplicate.json()["is_duplicate"]
            assert duplicate.json()["existing_batch_id"] == batch_id
        assert (
            await db.scalar(select(func.count()).select_from(FinancialTransaction))
            == initial_count + 2
        )
        assert await db.scalar(select(func.count()).select_from(ImportEvidence)) == 2
        signed = func.sum(
            Posting.base_amount_pln * case((Posting.direction == "debit", 1), else_=-1)
        )
        assert not (
            await db.execute(
                select(Posting.transaction_id).group_by(Posting.transaction_id).having(signed != 0)
            )
        ).all()
        after = await ledger_snapshot(db)
        assert all(
            after[key] == value
            for key, value in baseline.items()
            if key not in {"financial_transactions", "postings"}
        )


@pytest.mark.parametrize(
    "content,filename,mime",
    [
        (b"", "blank.csv", "text/csv"),
        (b"Rodzaj,Produkt,Data", "truncated.csv", "text/csv"),
        (text_pdf_bytes("VeloBank S.A.\nWyciąg nr 1/2026"), "truncated.pdf", "application/pdf"),
    ],
    ids=["blank-csv", "truncated-csv", "truncated-pdf"],
)
async def test_incomplete_source_never_authorizes_a_commit(
    db_session, test_database, owner, tmp_path, monkeypatch, content, filename, mime
):
    monkeypatch.setattr(documents, "UPLOAD_DIR", tmp_path)
    owner_id = owner.id
    baseline = await ledger_snapshot(db_session)
    sessions = async_sessionmaker(test_database, expire_on_commit=False)
    async with client_for(db_session, owner_id) as client:
        batch = (
            await client.post(
                ROOT, json={"kind": "statement"}, headers={"Idempotency-Key": "bad-batch"}
            )
        ).json()
        upload = await client.post(
            f"{ROOT}/{batch['id']}/sources",
            files={"file": (filename, content, mime)},
            headers={"Idempotency-Key": "bad-source"},
        )
        if upload.status_code == 201:
            source = upload.json()["source"]
            job = await client.post(
                f"{ROOT}/{batch['id']}/sources/{source['id']}/prepare",
                headers={"Idempotency-Key": "bad-prepare"},
            )
            assert job.status_code == 200
            await db_session.commit()
            monkeypatch.setattr(worker, "async_session_factory", sessions)
            await worker.process_import_job({}, job.json()["id"])
            db_session.expire_all()
            status = (await client.get(f"{ROOT}/{batch['id']}")).json()["sources"][0]
            assert (
                status["processing_state"] in {"unsupported", "error"}
                or status["validation_state"] == "blocked"
            )
        else:
            assert upload.status_code == 422
        rejected = await client.post(
            f"{ROOT}/{batch['id']}/commit",
            json={"preview_id": str(uuid.uuid4()), "request_hash": "0" * 64},
            headers={"Idempotency-Key": "no-preview"},
        )
        assert rejected.status_code == 404 and rejected.json()["code"] == "preview_not_found"
    assert await ledger_snapshot(db_session) == baseline
    assert await db_session.scalar(select(func.count()).select_from(ImportEvidence)) == 0


async def test_overlapping_real_csv_links_old_rows_and_creates_only_the_explicit_new_one(
    db_session, test_database, owner, other_owner, tmp_path, monkeypatch
):
    monkeypatch.setattr(documents, "UPLOAD_DIR", tmp_path)
    owner_id, foreign_id = owner.id, other_owner.id
    account = await create_account(
        db_session, owner_id, AccountCreate(name="Overlap account", type="checking", currency="PLN")
    )
    expense = await create_category(
        db_session, owner_id, CategoryCreate(name="Overlap cost", type="expense")
    )
    income = await create_category(
        db_session, owner_id, CategoryCreate(name="Overlap receipt", type="income")
    )
    account_id, expense_id, income_id = str(account.id), str(expense.id), str(income.id)
    sessions = async_sessionmaker(test_database, expire_on_commit=False)
    old_ids = []
    for index, overlap in enumerate([False, True]):
        batch_id, source = await stage_and_parse(
            db_session, sessions, owner_id, monkeypatch, *source_bytes("csv", overlap=overlap)
        )
        async with sessions() as db:
            async with client_for(db, owner_id) as client:
                batch = (await client.get(f"{ROOT}/{batch_id}")).json()
                rows = (await client.get(f"{ROOT}/{batch_id}/rows")).json()["items"]
                assert len(rows) == (3 if overlap else 2)
                decisions = []
                for ordinal, row in enumerate(rows):
                    kind = "expense" if row["bank_fields"]["amount"] < 0 else "income"
                    decision = {
                        "group_id": str(uuid.uuid4()),
                        "row_ids": [row["id"]],
                        "action": "create",
                        "kind": kind,
                        "account_id": account_id,
                        "category_id": expense_id if kind == "expense" else income_id,
                        "acknowledgements": [],
                    }
                    if overlap and ordinal < 2:
                        candidates = (
                            await client.get(f"{ROOT}/{batch_id}/rows/{row['id']}/candidates")
                        ).json()
                        candidate = next(
                            candidate
                            for candidate in candidates
                            if candidate["transaction_id"] in old_ids
                        )
                        decision.update(
                            action="link",
                            existing_transaction_id=candidate["transaction_id"],
                            category_id=None,
                        )
                    decisions.append(decision)
                saved = await client.put(
                    f"{ROOT}/{batch_id}/decisions",
                    json={"expected_version": batch["version"], "decisions": decisions},
                    headers={"Idempotency-Key": f"overlap-decisions-{index}"},
                )
                assert saved.status_code == 200, saved.text
                preview = await client.post(
                    f"{ROOT}/{batch_id}/preview",
                    json={
                        "expected_version": saved.json()["version"],
                        "group_ids": [decision["group_id"] for decision in decisions],
                        "acknowledgements": [f"opening_gap:{source['id']}"],
                    },
                    headers={"Idempotency-Key": f"overlap-preview-{index}"},
                )
                assert preview.status_code == 200, preview.text
                assert preview.json()["new_transaction_count"] == (1 if overlap else 2)
                response = await client.post(
                    f"{ROOT}/{batch_id}/commit",
                    json={
                        "preview_id": preview.json()["id"],
                        "request_hash": preview.json()["request_hash"],
                    },
                    headers={"Idempotency-Key": f"overlap-commit-{index}"},
                )
                assert response.status_code == 200, response.text
                if not overlap:
                    old_ids = response.json()["transaction_ids"]
                else:
                    assert len(response.json()["transaction_ids"]) == 1
                    assert len(response.json()["linked_row_ids"]) == 2
                    assert (
                        await db.scalar(select(func.count()).select_from(FinancialTransaction)) == 3
                    )
                    assert await db.scalar(select(func.count()).select_from(ImportEvidence)) == 5
            await db.commit()
        async with sessions() as db, client_for(db, foreign_id) as client:
            for suffix in ["", "/rows", f"/commands/overlap-commit-{index}"]:
                assert (await client.get(f"{ROOT}/{batch_id}{suffix}")).status_code == 404
            assert (
                await client.get(f"/api/documents/{source['document_id']}/original")
            ).status_code == 404
