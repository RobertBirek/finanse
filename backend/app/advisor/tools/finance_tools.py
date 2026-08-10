FINANCE_TOOLS = [
    {
        "name": "get_financial_summary",
        "description": "Get current month financial summary: account balances, income/expense totals",
        "autonomy_level": 0,
    },
    {
        "name": "get_accounts",
        "description": "List all user financial accounts with balances",
        "autonomy_level": 0,
    },
    {
        "name": "get_upcoming_obligations",
        "description": "Get list of upcoming financial obligations (placeholders for future implementation)",
        "autonomy_level": 0,
    },
    {
        "name": "create_transaction",
        "description": "Create a new financial transaction with double-entry postings",
        "autonomy_level": 2,
        "requires_authorization": True,
    },
    {
        "name": "get_transactions",
        "description": "List recent financial transactions",
        "autonomy_level": 0,
    },
]


def get_finance_tool_schemas() -> list[dict]:
    return FINANCE_TOOLS


async def execute_get_financial_summary(db, user_id: str) -> dict:
    from app.finance.service import get_financial_summary
    summary = await get_financial_summary(db, user_id)
    return summary.model_dump()


async def execute_get_accounts(db, user_id: str) -> dict:
    from app.finance.service import get_accounts
    accounts = await get_accounts(db, user_id)
    return {
        "accounts": [
            {"id": str(a.id), "name": a.name, "type": a.type, "currency": a.currency, "is_active": a.is_active}
            for a in accounts
        ]
    }


async def execute_get_upcoming_obligations(db, user_id: str) -> dict:
    return {"obligations": [], "message": "Upcoming obligations tracking not yet implemented"}
