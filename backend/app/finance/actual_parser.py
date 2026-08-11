import sqlite3
import re
from datetime import date
from pathlib import Path
from typing import TypedDict


class AccountDict(TypedDict):
    actual_id: str
    name: str
    type: str
    currency: str


class CategoryDict(TypedDict):
    actual_id: str
    name: str
    type: str


class PostingDict(TypedDict):
    account_actual_id: str
    category_actual_id: str | None
    source_amount: int
    source_currency: str
    direction: str


class TransactionDict(TypedDict):
    actual_id: str
    type: str
    date: date
    description: str
    postings: list[PostingDict]


class ActualParser:
    def __init__(self, db_path: Path | str):
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def close(self):
        self._conn.close()

    def _detect_currency(self, name: str | None) -> str:
        if not name:
            return "PLN"
        if re.search(r"\beur\b", name, re.IGNORECASE):
            return "EUR"
        if re.search(r"\busd\b", name, re.IGNORECASE):
            return "USD"
        return "PLN"

    def get_accounts(self) -> list[AccountDict]:
        rows = self._conn.execute(
            "SELECT id, name, offbudget FROM accounts WHERE tombstone=0 AND closed=0 ORDER BY name"
        ).fetchall()
        return [
            {
                "actual_id": r["id"],
                "name": r["name"],
                "type": "savings" if r["offbudget"] else "checking",
                "currency": self._detect_currency(r["name"]),
            }
            for r in rows
        ]

    def get_categories(self) -> list[CategoryDict]:
        rows = self._conn.execute(
            "SELECT id, name, is_income FROM categories WHERE tombstone=0 ORDER BY name"
        ).fetchall()
        return [
            {
                "actual_id": r["id"],
                "name": r["name"],
                "type": "income" if r["is_income"] else "expense",
            }
            for r in rows
        ]

    def get_transactions(self) -> list[TransactionDict]:
        payee_rows = self._conn.execute(
            "SELECT pm.id AS mapping_id, p.name FROM payee_mapping pm "
            "JOIN payees p ON p.id = pm.payeeId"
        ).fetchall()
        payee_map = {r["mapping_id"]: r["name"] for r in payee_rows}

        rows = self._conn.execute(
            "SELECT id, acct, category, amount, description, notes, date "
            "FROM transactions "
            "WHERE tombstone=0 AND isParent=0 AND isChild=0 AND transferred_id IS NULL "
            "ORDER BY date, id"
        ).fetchall()

        result = []
        for r in rows:
            amount = r["amount"]
            abs_amount = abs(amount)

            if amount < 0:
                txn_type = "expense"
                posting1_direction = "credit"
                posting2_direction = "debit"
            else:
                txn_type = "income"
                posting1_direction = "debit"
                posting2_direction = "credit"

            payee_name = payee_map.get(r["description"], "") if r["description"] else ""
            desc_parts = [payee_name] if payee_name else []
            if r["notes"]:
                desc_parts.append(r["notes"])
            description = " — ".join(desc_parts) if desc_parts else "(no description)"

            postings: list[PostingDict] = [
                {
                    "account_actual_id": r["acct"],
                    "category_actual_id": None,
                    "source_amount": abs_amount,
                    "source_currency": "PLN",
                    "direction": posting1_direction,
                },
                {
                    "account_actual_id": r["acct"],
                    "category_actual_id": r["category"],
                    "source_amount": abs_amount,
                    "source_currency": "PLN",
                    "direction": posting2_direction,
                },
            ]

            result.append({
                "actual_id": r["id"],
                "type": txn_type,
                "date": _parse_date(r["date"]),
                "description": description,
                "postings": postings,
            })

        return result


def _parse_date(actual_date: int) -> date:
    s = str(actual_date)
    return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
