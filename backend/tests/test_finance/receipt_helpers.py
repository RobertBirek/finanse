import uuid

from sqlalchemy import inspect

from app.finance.models import Category, FinancialDocument
from tests.test_finance.test_rule_policy import configured

ROOT = "/api/finance"
A, B, D = (str(uuid.UUID(int=n)) for n in (101, 102, 103))


async def ready(db):
    owner, txn, account, marker, home = await configured(db)
    for posting in txn.postings:
        posting.source_amount = posting.base_amount_pln = 9000
    food = Category(user_id=owner, name="Spożywka", type="expense")
    bill = FinancialDocument(
        user_id=owner,
        kind="receipt",
        supplier_name="Sklep",
        description="Paragon",
        total_minor=9000,
        currency="PLN",
        review="approved",
    )
    db.add_all([food, bill])
    await db.commit()
    await db.refresh(txn, ["postings"])
    return owner, bill, txn, account, marker, food, home


def payload(food, home, store=None):
    return {
        "store_id": store["id"] if store else None,
        "store_version": store["version"] if store else None,
        "lines": [
            {
                "line_key": A,
                "name": "MLEKO 2%",
                "amount_minor": 8000,
                "category_id": str(inspect(food).identity[0]),
                "hint": None,
            },
            {
                "line_key": B,
                "name": "Płyn",
                "amount_minor": 2000,
                "category_id": str(inspect(home).identity[0]),
                "hint": None,
            },
        ],
        "discounts": [
            {
                "discount_key": D,
                "name": "Kupon",
                "amount_minor": 1000,
                "shares": [
                    {"line_key": A, "amount_minor": 800},
                    {"line_key": B, "amount_minor": 200},
                ],
            }
        ],
    }


async def mutate(client, path, body, *, method="post", key=None):
    return await client.request(
        method, ROOT + path, json=body, headers={"Idempotency-Key": key or uuid.uuid4().hex}
    )


async def store_for(client, name="Sklep osiedlowy"):
    r = await mutate(client, "/receipt-stores", {"name": name})
    assert r.status_code == 200, r.text
    return r.json()


async def save(client, bill, body, version=0):
    bill_id = inspect(bill).identity[0]
    canonical = await client.get(f"{ROOT}/bills/{bill_id}/items")
    assert canonical.status_code == 200, canonical.text
    r = await mutate(
        client,
        f"/bills/{bill_id}/items/draft",
        {
            "expected_version": version,
            "expected_bill_version": canonical.json()["bill_version"],
            "body": body,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


async def approve_items(client, bill_id, draft, key=None):
    r = await mutate(
        client,
        f"/bills/{bill_id}/items/approve",
        {
            "expected_version": draft["state_version"],
            "draft_revision_id": draft["draft"]["id"],
            "expected_body_sha256": draft["draft"]["body_sha256"],
            "confirmed": True,
        },
        key=key,
    )
    assert r.status_code == 200, r.text
    return r.json()
