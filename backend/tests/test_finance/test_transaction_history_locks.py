import pytest

from tests.test_finance.test_account_currency import client_for
from tests.test_finance.test_bill_payments import create_owner
from tests.test_finance.test_transaction_search import seed


@pytest.mark.integration
@pytest.mark.asyncio
async def test_history_matches_editor_without_inventing_a_source_link(db_session):
    owner = await create_owner(db_session)
    transaction, account, _ = await seed(db_session, owner)
    transaction.source = "bank_import"
    await db_session.flush()
    async with client_for(db_session, owner) as client:
        editor = await client.get(f"/api/finance/transactions/{transaction.id}/editor")
        history = await client.get(
            "/api/finance/transactions/search", params={"account_id": str(account.id)}
        )
        account_history = await client.get(f"/api/finance/accounts/{account.id}/transactions")
    assert editor.status_code == history.status_code == account_history.status_code == 200
    for item in (history.json()["items"][0], account_history.json()[0]):
        assert item["id"] == str(transaction.id)
        assert item["ledger_editable"] is editor.json()["ledger_editable"] is False
        assert item["ledger_lock_reason"] == editor.json()["ledger_lock_reason"] == "Import bankowy"
        assert item["import_batch_id"] is None
        assert item["financial_document_ids"] == []
