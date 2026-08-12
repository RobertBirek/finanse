import re
import sqlite3
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
        self._warnings: list[str] = []

        tables = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') AND name='v_transactions'"
        ).fetchall()
        self._use_view = len(tables) > 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def get_warnings(self) -> list[str]:
        return self._warnings

    def close(self):
        self._conn.close()

    @property
    def _txn_table(self) -> str:
        return "v_transactions" if self._use_view else "transactions"

    @property
    def _txn_col_acct(self) -> str:
        return "account" if self._use_view else "acct"

    @property
    def _txn_col_transfer_id(self) -> str:
        return "transfer_id" if self._use_view else "transferred_id"

    @property
    def _txn_col_is_parent(self) -> str:
        return "is_parent" if self._use_view else "isParent"

    @property
    def _txn_col_is_child(self) -> str:
        return "is_child" if self._use_view else "isChild"

    @property
    def _txn_col_parent_id(self) -> str:
        return "parent_id"

    def _detect_currency(self, name: str | None) -> str:
        if not name:
            return "PLN"
        if re.search(r"\beur\b", name, re.IGNORECASE):
            return "EUR"
        if re.search(r"\busd\b", name, re.IGNORECASE):
            return "USD"
        return "PLN"

    def _get_account_currency_map(self) -> dict[str, str]:
        rows = self._conn.execute(
            "SELECT id, name FROM accounts WHERE tombstone=0 AND closed=0"
        ).fetchall()
        return {r["id"]: self._detect_currency(r["name"]) for r in rows}

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
        acct_currency = self._get_account_currency_map()

        txn_table = self._txn_table
        col_acct = self._txn_col_acct
        col_transfer_id = self._txn_col_transfer_id
        col_is_parent = self._txn_col_is_parent
        col_is_child = self._txn_col_is_child

        if self._use_view:
            # Build payee name lookup (payee column in v_transactions is UUID)
            payee_rows = self._conn.execute(
                "SELECT id, name FROM payees"
            ).fetchall()
            payee_map = {r["id"]: r["name"] for r in payee_rows}

            # Build category name lookup for fallback descriptions
            cat_rows = self._conn.execute(
                "SELECT id, name FROM categories"
            ).fetchall()
            cat_map = {r["id"]: r["name"] for r in cat_rows}

            rows = self._conn.execute(
                "SELECT id, account, category, amount, payee, notes, date "
                f"FROM {txn_table} "
                f"WHERE tombstone=0 AND {col_is_parent}={0} AND {col_is_child}={0} AND {col_transfer_id} IS NULL "
                "ORDER BY date, id"
            ).fetchall()
        else:
            payee_rows = self._conn.execute(
                "SELECT pm.id AS mapping_id, p.name FROM payee_mapping pm "
                "JOIN payees p ON p.id = pm.payeeId"
            ).fetchall()
            payee_map = {r["mapping_id"]: r["name"] for r in payee_rows}

            rows = self._conn.execute(
                "SELECT id, acct, category, amount, description, notes, date "
                f"FROM {txn_table} "
                f"WHERE tombstone=0 AND {col_is_parent}={0} AND {col_is_child}={0} AND {col_transfer_id} IS NULL "
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

            if self._use_view:
                payee_uuid = r["payee"] or ""
                payee_name = payee_map.get(payee_uuid, "") if payee_uuid else ""
                desc_parts = [payee_name] if payee_name else []
                if r["notes"]:
                    desc_parts.append(r["notes"])
                if not desc_parts:
                    # Fallback: use category name
                    cat_name = cat_map.get(r["category"], "") if r["category"] else ""
                    desc_parts = [cat_name] if cat_name else []
                description = " — ".join(desc_parts) if desc_parts else "(no description)"
            else:
                payee_name = payee_map.get(r["description"], "") if r["description"] else ""
                desc_parts = [payee_name] if payee_name else []
                if r["notes"]:
                    desc_parts.append(r["notes"])
                description = " — ".join(desc_parts) if desc_parts else "(no description)"

            account_actual_id = r[col_acct]
            currency = acct_currency.get(account_actual_id, "PLN")

            postings: list[PostingDict] = [
                {
                    "account_actual_id": account_actual_id,
                    "category_actual_id": None,
                    "source_amount": abs_amount,
                    "source_currency": currency,
                    "direction": posting1_direction,
                },
                {
                    "account_actual_id": account_actual_id,
                    "category_actual_id": r["category"],
                    "source_amount": abs_amount,
                    "source_currency": currency,
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
        """Reconstruct transfer transactions from paired transfer_id rows (mutual reference)."""
        acct_rows = self._conn.execute(
            "SELECT id, name FROM accounts WHERE tombstone=0 AND closed=0"
        ).fetchall()
        acct_names = {r["id"]: r["name"] for r in acct_rows}

        table = self._txn_table
        col_acct = self._txn_col_acct
        col_is_parent = self._txn_col_is_parent
        col_is_child = self._txn_col_is_child

        # Self-join: find pairs where t1.transfer_id = t2.id
        # Use t1.id < t2.id to avoid duplicates
        query = (
            f"SELECT t1.id as id1, t1.{col_acct} as acct1, t1.amount as amount1, t1.date as date1, "
            f"       t2.id as id2, t2.{col_acct} as acct2, t2.amount as amount2 "
            f"FROM {table} t1 "
            f"JOIN {table} t2 ON t1.{self._txn_col_transfer_id} = t2.id "
            f"WHERE t1.tombstone = 0 AND t1.{col_is_parent} = 0 AND t1.{col_is_child} = 0 "
            f"  AND t1.{self._txn_col_transfer_id} IS NOT NULL "
            f"  AND t2.tombstone = 0 AND t2.{col_is_parent} = 0 AND t2.{col_is_child} = 0 "
            f"  AND t1.id < t2.id "
            f"ORDER BY t1.date, t1.id"
        )
        rows = self._conn.execute(query).fetchall()

        result = []
        for r in rows:
            # Determine source (negative) and destination (positive)
            if r["amount1"] < 0:
                source_acct, source_amount = r["acct1"], abs(r["amount1"])
                dest_acct, dest_amount = r["acct2"], abs(r["amount2"])
            else:
                source_acct, source_amount = r["acct2"], abs(r["amount2"])
                dest_acct, dest_amount = r["acct1"], abs(r["amount1"])

            source_name = acct_names.get(source_acct, "?")
            dest_name = acct_names.get(dest_acct, "?")

            # Verify amounts match
            if source_amount != dest_amount:
                self._warnings.append(
                    f"Transfer amounts mismatch for pair ({r['id1'][:8]}.../{r['id2'][:8]}...): "
                    f"{source_amount} vs {dest_amount}"
                )

            postings: list[PostingDict] = [
                {
                    "account_actual_id": source_acct,
                    "category_actual_id": None,
                    "source_amount": source_amount,
                    "source_currency": "PLN",
                    "direction": "credit",
                },
                {
                    "account_actual_id": dest_acct,
                    "category_actual_id": None,
                    "source_amount": source_amount,
                    "source_currency": "PLN",
                    "direction": "debit",
                },
            ]

            result.append({
                "actual_id": r["id1"],  # use first ID as reference
                "type": "transfer",
                "date": self._parse_date(r["date1"]),
                "description": f"Transfer: {source_name} -> {dest_name}",
                "postings": postings,
            })

        return result

    def get_splits(self) -> list[TransactionDict]:
        acct_currency = self._get_account_currency_map()

        txn_table = self._txn_table
        col_acct = self._txn_col_acct
        col_is_parent = self._txn_col_is_parent
        col_is_child = self._txn_col_is_child
        col_parent_id = self._txn_col_parent_id

        parents = self._conn.execute(
            f"SELECT id, {col_acct}, amount, date FROM {txn_table} "
            f"WHERE tombstone=0 AND {col_is_parent}=1 AND {col_is_child}=0"
        ).fetchall()

        if not parents:
            return []

        parent_ids = [p["id"] for p in parents]
        placeholders = ",".join("?" for _ in parent_ids)
        children = self._conn.execute(
            f"SELECT id, {col_parent_id}, {col_acct}, category, amount "
            f"FROM {txn_table} "
            f"WHERE tombstone=0 AND {col_is_child}=1 AND {col_parent_id} IN ({placeholders}) "
            f"ORDER BY {col_parent_id}, amount",
            parent_ids,
        ).fetchall()

        children_by_parent: dict[str, list[sqlite3.Row]] = {}
        for c in children:
            pid = c[col_parent_id]
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
            child_sum = sum(abs(c["amount"]) for c in child_list)
            if child_sum != abs_parent_amount:
                self._warnings.append(
                    f"Split {pid}: children sum ({child_sum}) != parent amount ({abs_parent_amount})"
                )

            if p["amount"] < 0:
                txn_type = "expense"
                posting1_direction = "credit"
                children_direction = "debit"
            else:
                txn_type = "income"
                posting1_direction = "debit"
                children_direction = "credit"

            parent_acct_id = p[col_acct]
            postings: list[PostingDict] = [
                {
                    "account_actual_id": parent_acct_id,
                    "category_actual_id": None,
                    "source_amount": abs_parent_amount,
                    "source_currency": acct_currency.get(parent_acct_id, "PLN"),
                    "direction": posting1_direction,
                }
            ]

            for c in child_list:
                child_acct_id = c[col_acct]
                postings.append({
                    "account_actual_id": child_acct_id,
                    "category_actual_id": c["category"],
                    "source_amount": abs(c["amount"]),
                    "source_currency": acct_currency.get(child_acct_id, "PLN"),
                    "direction": children_direction,
                })

            result.append({
                "actual_id": pid,
                "type": txn_type,
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
