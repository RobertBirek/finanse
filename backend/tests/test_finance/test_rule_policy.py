"""Approved rules are future-only authority, never implicit human decisions."""

import uuid

import pytest
from sqlalchemy import func, select

from app.finance import service
from app.finance.models import FinanceCommandReceipt
from app.finance.schemas import CategoryCreate, CategoryUpdate
from tests.test_finance.test_account_currency import client_for
from tests.test_finance.test_bill_payments import create_owner
from tests.test_finance.test_categorization import setup as setup_ledger

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
ROOT = "/api/finance/categorization"


async def mutate(client, method, path, body, key=None):
    return await getattr(client, method)(
        ROOT + path, json=body, headers={"Idempotency-Key": key or uuid.uuid4().hex}
    )


async def configured(db):
    owner, txn, account, marker, target = await setup_ledger(db)
    async with client_for(db, owner) as client:
        response = await mutate(
            client,
            "patch",
            "/settings",
            {
                "expected_version": 0,
                "uncategorized_category_id": str(marker.id),
                "rules_enabled": True,
                "confirm_future_only": True,
            },
        )
        assert response.status_code == 200, response.text
    return owner, txn, account, marker, target


async def draft(client, target, description="  CZYNSZ   mieszkanie  "):
    response = await mutate(
        client,
        "post",
        "/rules",
        {"display_description": description, "target_category_id": str(target)},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def approve(client, rule, key=None):
    p = await client.post(
        f"{ROOT}/rules/{rule['id']}/preview", json={"expected_version": rule["version"]}
    )
    assert p.status_code == 200, p.text
    response = await mutate(
        client,
        "post",
        f"/rules/{rule['id']}/approve",
        {
            "expected_version": rule["version"],
            "preview_snapshot": p.json()["preview_snapshot"],
            "confirm_future_only": True,
        },
        key,
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_marker_is_explicit_and_never_name_inferred(db_session):
    owner, _, _, marker, _ = await setup_ledger(db_session)
    marker.name = "Pozostałe"
    await db_session.flush()
    await db_session.commit()
    async with client_for(db_session, owner) as client:
        result = await client.get(ROOT + "/settings")
        assert result.status_code == 200, result.text
        assert result.json()["version"] == 0 and result.json()["uncategorized_category_id"] is None
        assert result.json()["rules_enabled"] is False
        saved = await mutate(
            client,
            "patch",
            "/settings",
            {
                "expected_version": 0,
                "uncategorized_category_id": str(marker.id),
                "rules_enabled": True,
                "confirm_future_only": True,
            },
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["uncategorized_category_id"] == str(marker.id)


async def test_rule_approval_binds_normalized_exact_pattern_and_target(db_session):
    owner, _, _, _, target = await configured(db_session)
    async with client_for(db_session, owner) as client:
        rule = await draft(client, target.id)
        assert (
            rule["state"] == "draft" and rule["normalized_description_exact"] == "czynsz mieszkanie"
        )
        active = await approve(client, rule)
        assert active["state"] == "active" and active["approved_version"] == active["version"]
        old = active["approval_receipt_id"]
        paused = await mutate(
            client, "post", f"/rules/{active['id']}/pause", {"expected_version": active["version"]}
        )
        assert paused.status_code == 200 and paused.json()["state"] == "paused"
        assert paused.json()["version"] > active["version"]
        receipt = await db_session.get(FinanceCommandReceipt, uuid.UUID(old))
        assert receipt.response_json["grant"]["normalized_description_exact"] == "czynsz mieszkanie"


async def test_preview_is_nonmutating_and_stale_target_rejects_approval(db_session):
    owner, _, _, _, target = await configured(db_session)
    target_id = target.id
    async with client_for(db_session, owner) as client:
        rule = await draft(client, target_id)
        count = await db_session.scalar(select(func.count()).select_from(FinanceCommandReceipt))
        p = await client.post(
            f"{ROOT}/rules/{rule['id']}/preview", json={"expected_version": rule["version"]}
        )
        assert p.status_code == 200, p.text
        assert (
            await db_session.scalar(select(func.count()).select_from(FinanceCommandReceipt))
            == count
        )
        await service.update_category(
            db_session, owner, target_id, CategoryUpdate(name="Nowy sens")
        )
        await db_session.commit()
        result = await mutate(
            client,
            "post",
            f"/rules/{rule['id']}/approve",
            {
                "expected_version": rule["version"],
                "preview_snapshot": p.json()["preview_snapshot"],
                "confirm_future_only": True,
            },
        )
        assert result.status_code == 409, result.text


@pytest.mark.parametrize("category_kind", ["foreign", "inactive", "income", "missing"])
async def test_marker_must_be_owned_active_expense(db_session, category_kind):
    owner, _, _, marker, _ = await setup_ledger(db_session)
    if category_kind == "foreign":
        marker.user_id = await create_owner(db_session)
    if category_kind == "inactive":
        marker.is_active = False
    if category_kind == "income":
        marker.type = "income"
    await db_session.commit()
    category_id = uuid.uuid4() if category_kind == "missing" else marker.id
    async with client_for(db_session, owner) as client:
        result = await mutate(
            client,
            "patch",
            "/settings",
            {
                "expected_version": 0,
                "uncategorized_category_id": str(category_id),
                "rules_enabled": True,
                "confirm_future_only": True,
            },
        )
        assert result.status_code == 422, result.text


async def test_duplicate_active_exact_pattern_conflicts_without_silent_priority(db_session):
    owner, _, _, _, target = await configured(db_session)
    async with client_for(db_session, owner) as client:
        first = await draft(client, target.id)
        await approve(client, first)
        second = await draft(client, target.id, "Czynsz mieszkanie")
        p = await client.post(
            f"{ROOT}/rules/{second['id']}/preview", json={"expected_version": second["version"]}
        )
        assert p.status_code == 200, p.text
        result = await mutate(
            client,
            "post",
            f"/rules/{second['id']}/approve",
            {
                "expected_version": second["version"],
                "preview_snapshot": p.json()["preview_snapshot"],
                "confirm_future_only": True,
            },
        )
        assert result.status_code == 409, result.text


async def test_rule_settings_and_commands_are_owner_scoped_and_receipt_idempotent(db_session):
    owner, _, _, _marker, target = await configured(db_session)
    other = await create_owner(db_session)
    await db_session.commit()
    async with client_for(db_session, owner) as client:
        rule = await draft(client, target.id)
        key = uuid.uuid4().hex
        p = await client.post(
            f"{ROOT}/rules/{rule['id']}/preview", json={"expected_version": rule["version"]}
        )
        assert p.status_code == 200, p.text
        body = {
            "expected_version": rule["version"],
            "preview_snapshot": p.json()["preview_snapshot"],
            "confirm_future_only": True,
        }
        first = await mutate(client, "post", f"/rules/{rule['id']}/approve", body, key)
        again = await mutate(client, "post", f"/rules/{rule['id']}/approve", body, key)
        assert first.status_code == 200 and again.json() == first.json()
    async with client_for(db_session, other) as client:
        assert (
            await client.post(
                f"{ROOT}/rules/{rule['id']}/preview", json={"expected_version": rule["version"]}
            )
        ).status_code == 404
        assert (await client.get(ROOT + "/settings")).json()["version"] == 0


async def test_manual_confirmation_of_unchanged_marker_records_truthful_origin(db_session):
    from app.finance.rule_models import TransactionCategorizationOrigin as Origin
    from tests.test_finance.test_categorization import apply, path, preview

    owner, txn, _, marker, _ = await configured(db_session)
    async with client_for(db_session, owner) as client:
        ctx = (await client.get(path(txn))).json()
        assert ctx.get("assignment_origin") is None
        p = await preview(client, txn, [{"category_id": str(marker.id), "amount_minor": 10000}])
        result = await apply(client, txn, p)
        assert result.status_code == 200, result.text
        assert result.json().get("assignment_origin", {}).get("origin") == "manual"
        origin = await db_session.scalar(select(Origin).where(Origin.transaction_id == txn.id))
        assert origin is not None and origin.rule_id is None and origin.approval_receipt_id is None


async def test_category_referenced_only_by_rule_cannot_be_deleted(db_session):
    owner, _, _, _, _ = await configured(db_session)
    unused = await service.create_category(
        db_session, owner, CategoryCreate(name="Regułowa", type="expense")
    )
    async with client_for(db_session, owner) as client:
        await draft(client, unused.id)
        result = await client.delete(f"/api/finance/categories/{unused.id}")
        assert result.status_code == 409, result.text


@pytest.mark.parametrize("description", [" ", "x" * 501])
async def test_descriptions_are_rejected_without_truncation(db_session, description):
    owner, _, _, _, target = await configured(db_session)
    async with client_for(db_session, owner) as client:
        result = await mutate(
            client,
            "post",
            "/rules",
            {"display_description": description, "target_category_id": str(target.id)},
        )
        assert result.status_code == 422, result.text


@pytest.mark.parametrize(
    "body",
    [
        {"expected_version": 1, "confirm_future_only": True, "approved_by": str(uuid.uuid4())},
        {"expected_version": True},
    ],
)
async def test_rule_commands_reject_spoofed_and_non_strict_inputs(db_session, body):
    owner, _, _, _, target = await configured(db_session)
    async with client_for(db_session, owner) as client:
        rule = await draft(client, target.id)
        result = await mutate(client, "post", f"/rules/{rule['id']}/pause", body)
        assert result.status_code == 422


async def test_active_rule_cannot_replace_grant_at_same_version(db_session):
    owner, _, _, _, target = await configured(db_session)
    async with client_for(db_session, owner) as client:
        rule = await approve(client, await draft(client, target.id))
        p = await client.post(
            f"{ROOT}/rules/{rule['id']}/preview", json={"expected_version": rule["version"]}
        )
        assert p.status_code == 200
        result = await mutate(
            client,
            "post",
            f"/rules/{rule['id']}/approve",
            {
                "expected_version": rule["version"],
                "preview_snapshot": p.json()["preview_snapshot"],
                "confirm_future_only": True,
            },
        )
        assert result.status_code == 409, result.text


async def test_database_active_grant_cannot_have_null_approved_version(db_session):
    from sqlalchemy.exc import IntegrityError

    from app.finance.rule_models import TransactionCategorizationRule as Rule

    owner, _, _, _, target = await configured(db_session)
    async with client_for(db_session, owner) as client:
        active = await approve(client, await draft(client, target.id))
    row = await db_session.get(Rule, uuid.UUID(active["id"]))
    row.approved_version = None
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()
