"""Category aliases are suggestions, never model-authored UUID authority."""

import importlib
import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.finance.models import Category


@pytest.fixture
def catalog():
    return importlib.import_module("app.documents.category_catalog")


def category(owner, name="Synthetic", **kwargs):
    return Category(
        id=uuid.uuid4(),
        user_id=owner,
        name=name,
        type="expense",
        source="manual",
        is_active=True,
        parent_id=None,
        **kwargs,
    )


def test_alias_catalog_contains_names_but_no_user_or_category_uuid(catalog):
    owner = uuid.uuid4()
    parent = category(owner, "Bills")
    child = category(owner, "Mobile")
    child.parent_id = parent.id
    packet = catalog.build_category_catalog([parent, child], owner)
    public = json.dumps(packet.public, ensure_ascii=False)
    assert "Bills / Mobile" in public
    assert str(owner) not in public
    assert str(child.id) not in public
    assert packet.private_key_map
    assert all(key.startswith("c") for key in packet.private_key_map)


@pytest.mark.parametrize(
    "reason", ["foreign", "inactive", "income", "technical", "cycle", "missing_parent"]
)
def test_invalid_taxonomy_never_becomes_a_model_target(catalog, reason):
    owner = uuid.uuid4()
    item = category(owner)
    if reason == "foreign":
        item.user_id = uuid.uuid4()
    elif reason == "inactive":
        item.is_active = False
    elif reason == "income":
        item.type = "income"
    elif reason == "technical":
        item.source = "opening_balance"
    elif reason == "cycle":
        item.parent_id = item.id
    else:
        item.parent_id = uuid.uuid4()
    assert catalog.build_category_catalog([item], owner).public == []


def test_oversized_taxonomy_abstains_instead_of_truncating_categories(catalog, monkeypatch):
    owner = uuid.uuid4()
    monkeypatch.setattr(catalog.settings, "DOCUMENT_CATEGORY_MAX_CATEGORIES", 1)
    assert catalog.build_category_catalog([category(owner), category(owner)], owner).public == []
    monkeypatch.setattr(catalog.settings, "DOCUMENT_CATEGORY_MAX_BYTES", 10)
    assert catalog.build_category_catalog([category(owner)], owner).public == []


@pytest.mark.asyncio
async def test_unknown_or_deleted_category_cannot_escape_validation(catalog):
    owner = uuid.uuid4()
    item = category(owner)
    packet = catalog.build_category_catalog([item], owner)
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalars=list)))
    assert await catalog.resolve_category(db, owner, packet, "invented-uuid") is None
    assert await catalog.resolve_category(db, owner, packet, None) is None
    assert await catalog.resolve_category(db, owner, packet, "c01") is None


@pytest.mark.asyncio
async def test_valid_alias_is_rechecked_after_network(catalog):
    owner = uuid.uuid4()
    item = category(owner)
    packet = catalog.build_category_catalog([item], owner)
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalars=lambda: [item])))
    assert await catalog.resolve_category(db, owner, packet, "c01") == item.id
    item.name = "Changed while provider was running"
    assert await catalog.resolve_category(db, owner, packet, "c01") is None
