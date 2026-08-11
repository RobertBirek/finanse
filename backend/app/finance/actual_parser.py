import sqlite3
import re
from datetime import date
from pathlib import Path
from sqlite3 import Row
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
        self._warnings: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def get_warnings(self) -> list[str]:
        return self._warnings

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

            if amount == 0:
                continue

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
                "date": self._parse_date(r["date"]),
                "description": description,
                "postings": postings,
            })

        return result


    def get_transfers(self) -> list[TransactionDict]:
        acct_rows = self._conn.execute(
            "SELECT id, name FROM accounts WHERE tombstone=0 AND closed=0"
        ).fetchall()
        acct_names = {r["id"]: r["name"] for r in acct_rows}

        rows = self._conn.execute(
            "SELECT id, acct, amount, date, transferred_id "
            "FROM transactions "
            "WHERE tombstone=0 AND isParent=0 AND isChild=0 AND transferred_id IS NOT NULL "
            "ORDER BY transferred_id, amount"
        ).fetchall()

        pairs: dict[str, list[Row]] = {}
        for r in rows:
            tid = r["transferred_id"]
            if tid not in pairs:
                pairs[tid] = []
            pairs[tid].append(r)

        result = []
        for tid, pair in pairs.items():
            if len(pair) != 2:
                self._warnings.append(f"Skipping transfer {tid}: {len(pair)} rows (expected 2)")
                continue

            source_row = pair[0] if pair[0]["amount"] < 0 else pair[1]
            dest_row = pair[1] if pair[1]["amount"] > 0 else pair[0]

            if source_row["amount"] >= 0 or dest_row["amount"] <= 0:
                self._warnings.append(f"Skipping transfer {tid}: both rows same sign")
                continue

            abs_amount = abs(source_row["amount"])
            source_name = acct_names.get(source_row["acct"], "?")
            dest_name = acct_names.get(dest_row["acct"], "?")

            postings: list[PostingDict] = [
                {
                    "account_actual_id": source_row["acct"],
                    "category_actual_id": None,
                    "source_amount": abs_amount,
                    "source_currency": "PLN",
                    "direction": "credit",
                },
                {
                    "account_actual_id": dest_row["acct"],
                    "category_actual_id": None,
                    "source_amount": abs_amount,
                    "source_currency": "PLN",
                    "direction": "debit",
                },
            ]

            result.append({
                "actual_id": tid,
                "type": "transfer",
                "date": self._parse_date(source_row["date"]),
                "description": f"Transfer: {source_name} → {dest_name}",
                "postings": postings,
            })

        return result

    def get_splits(self) -> list[TransactionDict]:
        parents = self._conn.execute(
            "SELECT id, acct, amount, date FROM transactions "
            "WHERE tombstone=0 AND isParent=1 AND isChild=0"
        ).fetchall()

        if not parents:
            return []

        parent_ids = [p["id"] for p in parents]
        placeholders = ",".join("?" for _ in parent_ids)
        children = self._conn.execute(
            f"SELECT id, parent_id, acct, category, amount "
            f"FROM transactions "
            f"WHERE tombstone=0 AND isChild=1 AND parent_id IN ({placeholders}) "
            f"ORDER BY parent_id, amount",
            parent_ids,
        ).fetchall()

        children_by_parent: dict[str, list[sqlite3.Row]] = {}
        for c in children:
            pid = c["parent_id"]
            if pid not in children_by_parent:
                children_by_parent[pid] = []
            children_by_parent[pid].append(c)

        result = []
        for p in parents:
            pid = p["id"]
            child_list = children_by_parent.get(pid, [])
            if not child_list:
                self._warnings.append(f"Skipping split {pid}: no children found")
                continue

            abs_parent_amount = abs(p["amount"])
            postings: list[PostingDict] = [
                {
                    "account_actual_id": p["acct"],
                    "category_actual_id": None,
                    "source_amount": abs_parent_amount,
                    "source_currency": "PLN",
                    "direction": "credit",
                }
            ]

            for c in child_list:
                postings.append({
                    "account_actual_id": c["acct"],
                    "category_actual_id": c["category"],
                    "source_amount": abs(c["amount"]),
                    "source_currency": "PLN",
                    "direction": "debit",
                })

            result.append({
                "actual_id": pid,
                "type": "expense",
                "date": self._parse_date(p["date"]),
                "description": f"Split transaction ({len(child_list)} parts)",
                "postings": postings,
            })

        return result

    @staticmethod
    def _parse_date(actual_date: int | None) -> date:
        if not actual_date:
            return date(1970, 1, 1)
        s = str(actual_date)
        if len(s) != 8:
            return date(1970, 1, 1)
        return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
