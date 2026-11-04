"""Whole-review regression: independent account reads must carry provenance."""

import pytest

from tests.test_finance.test_account_currency import client_for
from tests.test_finance.test_rule_events import event_for, process, ready

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_account_history_loads_rule_origin_without_a_prior_search_projection(db_session):
    owner, _, account, _, _, rule, txn = await ready(db_session)
    txn_id, account_id = txn.id, account.id
    await process(db_session, await event_for(db_session, txn))
    db_session.expunge_all()  # No earlier list/search/detail cache can hide the missing projection.
    async with client_for(db_session, owner) as client:
        response = await client.get(f"/api/finance/accounts/{account_id}/transactions")
        assert response.status_code == 200, response.text
        item = next(row for row in response.json() if row["id"] == str(txn_id))
        origin = item.get("assignment_origin")
        assert origin is not None and origin["origin"] == "approved_rule"
        assert origin["rule_id"] == rule["id"]
        assert origin["display_description"] == rule["display_description"]
