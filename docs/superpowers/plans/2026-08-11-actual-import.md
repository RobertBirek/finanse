# Actual Budget Import — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** CLI script that migrates 18 accounts, 54 categories, 866 transactions from Actual Budget SQLite to Personal Advisor double-entry ledger.

**Architecture:** Python script (`backend/scripts/migrate_actual.py`) orchestrating three modules: `actual_parser.py` (reads Actual SQLite via sqlite3), `nbp_rates.py` (fetches historical FX), and existing PA finance services (writes to PostgreSQL).

**Tech Stack:** Python 3.12+, sqlite3 (stdlib), httpx (async NBP API), Pydantic v2, SQLAlchemy 2.x async, pytest

---

## File Map

| File | Responsibility |
|------|---------------|
| `backend/app/finance/actual_parser.py` | Read Actual SQLite, produce PA schemas (pure functions, no DB) |
| `backend/app/finance/nbp_rates.py` | Fetch and cache NBP mid-rates per currency+date |
| `backend/scripts/migrate_actual.py` | CLI entry point, orchestrates pipeline, writes to DB via PA services |
| `backend/tests/test_finance/test_actual_import.py` | All tests: parser, reconstruction, NBP, dry-run |

---

### Task 1: ActualParser — read accounts and categories

**Files:**
- Create: `backend/app/finance/actual_parser.py`
- Create: `backend/tests/test_finance/test_actual_import.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_finance/test_actual_import.py
import sqlite3
import tempfile
from pathlib import Path
from datetime import date

from app.finance.actual_parser import ActualParser


def _make_actual_db(schema_sql: str, inserts: list[str]) -> Path:
    """Helper: create in-memory SQLite, dump to temp file."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(schema_sql)
    for stmt in inserts:
        conn.execute(stmt)
    conn.commit()
    tmp = Path(tempfile.mktemp(suffix=".sqlite"))
    src = sqlite3.connect(str(tmp))
    conn.backup(src)
    conn.close()
    src.close()
    return tmp


class TestActualParserAccounts:
    def test_reads_active_accounts(self):
        schema = """
        CREATE TABLE accounts (id TEXT, name TEXT, offbudget INTEGER, closed INTEGER, tombstone INTEGER);
        """
        inserts = [
            "INSERT INTO accounts VALUES ('a1', 'ING', 0, 0, 0)",
            "INSERT INTO accounts VALUES ('a2', 'Gotowka', 1, 0, 0)",
            "INSERT INTO accounts VALUES ('a3', 'Zamkniete', 0, 1, 0)",  # closed
            "INSERT INTO accounts VALUES ('a4', 'Usuniete', 0, 0, 1)",   # tombstone
        ]
        db_path = _make_actual_db(schema, inserts)

        parser = ActualParser(db_path)
        result = parser.get_accounts()

        assert len(result) == 2  # only active, non-tombstone
        assert result[0]["name"] == "ING"
        assert result[0]["type"] == "checking"  # offbudget=0
        assert result[1]["name"] == "Gotowka"
        assert result[1]["type"] == "savings"   # offbudget=1


class TestActualParserCategories:
    def test_reads_categories_with_groups(self):
        schema = """
        CREATE TABLE categories (id TEXT, name TEXT, is_income INTEGER, cat_group TEXT, tombstone INTEGER);
        CREATE TABLE category_groups (id TEXT, name TEXT);
        """
        inserts = [
            "INSERT INTO category_groups VALUES ('g1', 'Wydatki biezace')",
            "INSERT INTO category_groups VALUES ('g2', 'Przychody')",
            "INSERT INTO categories VALUES ('c1', 'Jedzenie', 0, 'g1', 0)",
            "INSERT INTO categories VALUES ('c2', 'Pensja', 1, 'g2', 0)",
            "INSERT INTO categories VALUES ('c3', 'Ukryta', 0, 'g1', 1)",  # tombstone
        ]
        db_path = _make_actual_db(schema, inserts)

        parser = ActualParser(db_path)
        result = parser.get_categories()

        assert len(result) == 2
        assert result[0]["name"] == "Jedzenie"
        assert result[0]["type"] == "expense"
        assert result[1]["name"] == "Pensja"
        assert result[1]["type"] == "income"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_finance/test_actual_import.py::TestActualParserAccounts -v
```
Expected: `ModuleNotFoundError: No module named 'app.finance.actual_parser'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/finance/actual_parser.py
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


class ActualParser:
    def __init__(self, db_path: Path | str):
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row

    def _detect_currency(self, name: str) -> str:
        name_lower = name.lower()
        if "eu" in name_lower or "eur" in name_lower:
            return "EUR"
        if "usd" in name_lower:
            return "USD"
        return "PLN"

    def get_accounts(self) -> list[AccountDict]:
        rows = self._conn.execute(
            "SELECT id, name, offbudget FROM accounts WHERE tombstone=0 AND closed=0"
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
            "SELECT id, name, is_income FROM categories WHERE tombstone=0"
        ).fetchall()
        return [
            {
                "actual_id": r["id"],
                "name": r["name"],
                "type": "income" if r["is_income"] else "expense",
            }
            for r in rows
        ]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_finance/test_actual_import.py::TestActualParserAccounts tests/test_finance/test_actual_import.py::TestActualParserCategories -v
```
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/finance/actual_parser.py backend/tests/test_finance/test_actual_import.py
git commit -m "feat: ActualParser — read accounts and categories from Actual SQLite"
```

---

### Task 2: Transaction reconstruction — simple transactions

**Files:**
- Modify: `backend/app/finance/actual_parser.py`
- Modify: `backend/tests/test_finance/test_actual_import.py`

- [ ] **Step 1: Add failing test for simple transactions**

Append to `test_actual_import.py`:

```python
class TestActualParserTransactions:
    def test_reads_simple_expense(self):
        schema = """
        CREATE TABLE accounts (id TEXT, name TEXT, offbudget INTEGER, closed INTEGER, tombstone INTEGER);
        CREATE TABLE categories (id TEXT, name TEXT, is_income INTEGER, cat_group TEXT, tombstone INTEGER);
        CREATE TABLE transactions (
            id TEXT, isParent INTEGER, isChild INTEGER, parent_id TEXT,
            acct TEXT, category TEXT, amount INTEGER, description TEXT,
            notes TEXT, date INTEGER, transferred_id TEXT, tombstone INTEGER
        );
        CREATE TABLE payees (id TEXT, name TEXT);
        CREATE TABLE payee_mapping (id TEXT, targetId TEXT, payeeId TEXT);
        """
        inserts = [
            "INSERT INTO accounts VALUES ('acc1', 'ING', 0, 0, 0)",
            "INSERT INTO accounts VALUES ('acc2', 'Gotowka', 0, 0, 0)",
            "INSERT INTO categories VALUES ('cat1', 'Jedzenie', 0, 'g1', 0)",
            "INSERT INTO payees VALUES ('pay1', 'Biedronka')",
            "INSERT INTO payee_mapping VALUES ('pm1', 'tx1', 'pay1')",
            # Expense: -5000 groszy, ING, Jedzenie, 2026-07-15
            "INSERT INTO transactions VALUES ('tx1', 0, 0, NULL, 'acc1', 'cat1', -5000, 'pm1', 'notatka', 20260715, NULL, 0)",
        ]
        db_path = _make_actual_db(schema, inserts)
        parser = ActualParser(db_path)

        result = parser.get_transactions()
        assert len(result) == 1
        txn = result[0]
        assert txn["type"] == "expense"
        assert txn["date"] == date(2026, 7, 15)
        assert "Biedronka" in txn["description"]
        assert txn["postings"][0]["account_actual_id"] == "acc1"
        assert txn["postings"][0]["direction"] == "credit"
        assert txn["postings"][0]["source_amount"] == 5000
        assert txn["postings"][1]["account_actual_id"] == "acc1"
        assert txn["postings"][1]["category_actual_id"] == "cat1"
        assert txn["postings"][1]["direction"] == "debit"
        assert txn["postings"][1]["source_amount"] == 5000

    def test_reads_simple_income(self):
        schema = """
        CREATE TABLE accounts (id TEXT, name TEXT, offbudget INTEGER, closed INTEGER, tombstone INTEGER);
        CREATE TABLE categories (id TEXT, name TEXT, is_income INTEGER, cat_group TEXT, tombstone INTEGER);
        CREATE TABLE transactions (
            id TEXT, isParent INTEGER, isChild INTEGER, parent_id TEXT,
            acct TEXT, category TEXT, amount INTEGER, description TEXT,
            notes TEXT, date INTEGER, transferred_id TEXT, tombstone INTEGER
        );
        CREATE TABLE payees (id TEXT, name TEXT);
        CREATE TABLE payee_mapping (id TEXT, targetId TEXT, payeeId TEXT);
        """
        inserts = [
            "INSERT INTO accounts VALUES ('acc1', 'ING', 0, 0, 0)",
            "INSERT INTO categories VALUES ('cat1', 'Pensja', 1, 'g2', 0)",
            "INSERT INTO payees VALUES ('pay1', 'Pracodawca')",
            "INSERT INTO payee_mapping VALUES ('pm1', 'tx1', 'pay1')",
            # Income: +500000, ING, Pensja
            "INSERT INTO transactions VALUES ('tx1', 0, 0, NULL, 'acc1', 'cat1', 500000, 'pm1', NULL, 20260715, NULL, 0)",
        ]
        db_path = _make_actual_db(schema, inserts)
        parser = ActualParser(db_path)

        result = parser.get_transactions()
        assert len(result) == 1
        txn = result[0]
        assert txn["type"] == "income"
        assert txn["postings"][0]["direction"] == "debit"    # income: account gets debited (money arrives)
        assert txn["postings"][1]["direction"] == "credit"   # income category gets credited
        assert txn["postings"][0]["source_amount"] == 500000
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_finance/test_actual_import.py::TestActualParserTransactions -v
```
Expected: `AttributeError: 'ActualParser' object has no attribute 'get_transactions'`

- [ ] **Step 3: Implement get_transactions**

Append to `actual_parser.py`:

```python
from typing import TypedDict as _TypedDict


class PostingDict(_TypedDict):
    account_actual_id: str
    category_actual_id: str | None
    source_amount: int
    source_currency: str
    direction: str


class TransactionDict(_TypedDict):
    actual_id: str
    type: str
    date: date
    description: str
    postings: list[PostingDict]


def _parse_date(actual_date: int) -> date:
    """Convert YYYYMMDD integer to date."""
    s = str(actual_date)
    return date(int(s[:4]), int(s[4:6]), int(s[6:8]))


class ActualParser:
    # ... (existing methods remain)

    def get_transactions(self) -> list[TransactionDict]:
        """Return simple (non-parent, non-child, non-transfer) transactions."""
        # Load payee mapping
        payee_rows = self._conn.execute(
            "SELECT pm.targetId, p.name FROM payee_mapping pm "
            "JOIN payees p ON p.id = pm.payeeId"
        ).fetchall()
        payee_map = {r["targetId"]: r["name"] for r in payee_rows}

        rows = self._conn.execute(
            "SELECT id, acct, category, amount, description, notes, date "
            "FROM transactions "
            "WHERE tombstone=0 AND isParent=0 AND isChild=0 AND transferred_id IS NULL"
        ).fetchall()

        result = []
        for r in rows:
            amount = r["amount"]
            abs_amount = abs(amount)

            if amount < 0:
                txn_type = "expense"
                posting1_direction = "credit"   # money leaves account
                posting2_direction = "debit"    # expense category
            else:
                txn_type = "income"
                posting1_direction = "debit"    # money enters account
                posting2_direction = "credit"   # income category

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
```

- [ ] **Step 4: Run tests**

```bash
cd backend && python -m pytest tests/test_finance/test_actual_import.py::TestActualParserTransactions -v
```
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/finance/actual_parser.py backend/tests/test_finance/test_actual_import.py
git commit -m "feat: reconstruct simple expense/income transactions from Actual"
```

---

### Task 3: Transaction reconstruction — transfers

**Files:**
- Modify: `backend/app/finance/actual_parser.py`
- Modify: `backend/tests/test_finance/test_actual_import.py`

- [ ] **Step 1: Add failing test for transfers**

Append to `TestActualParserTransactions`:

```python
    def test_reconstructs_transfer(self):
        schema = """
        CREATE TABLE accounts (id TEXT, name TEXT, offbudget INTEGER, closed INTEGER, tombstone INTEGER);
        CREATE TABLE categories (id TEXT, name TEXT, is_income INTEGER, cat_group TEXT, tombstone INTEGER);
        CREATE TABLE transactions (
            id TEXT, isParent INTEGER, isChild INTEGER, parent_id TEXT,
            acct TEXT, category TEXT, amount INTEGER, description TEXT,
            notes TEXT, date INTEGER, transferred_id TEXT, tombstone INTEGER
        );
        CREATE TABLE payees (id TEXT, name TEXT);
        CREATE TABLE payee_mapping (id TEXT, targetId TEXT, payeeId TEXT);
        """
        inserts = [
            "INSERT INTO accounts VALUES ('acc_ing', 'ING', 0, 0, 0)",
            "INSERT INTO accounts VALUES ('acc_cash', 'Gotowka', 0, 0, 0)",
            # Transfer: ING -> Gotowka, 10000 groszy (100 PLN)
            "INSERT INTO transactions VALUES ('tx_a', 0, 0, NULL, 'acc_ing', NULL, -10000, NULL, NULL, 20260701, 'link_1', 0)",
            "INSERT INTO transactions VALUES ('tx_b', 0, 0, NULL, 'acc_cash', NULL, 10000, NULL, NULL, 20260701, 'link_1', 0)",
        ]
        db_path = _make_actual_db(schema, inserts)
        parser = ActualParser(db_path)

        result = parser.get_transfers()
        assert len(result) == 1
        txn = result[0]
        assert txn["type"] == "transfer"
        assert txn["description"] == "Transfer: ING → Gotowka"
        assert len(txn["postings"]) == 2
        assert txn["postings"][0]["account_actual_id"] == "acc_ing"
        assert txn["postings"][0]["direction"] == "credit"
        assert txn["postings"][0]["source_amount"] == 10000
        assert txn["postings"][1]["account_actual_id"] == "acc_cash"
        assert txn["postings"][1]["direction"] == "debit"
        assert txn["postings"][1]["source_amount"] == 10000
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_finance/test_actual_import.py::TestActualParserTransactions::test_reconstructs_transfer -v
```
Expected: `AttributeError: 'ActualParser' object has no attribute 'get_transfers'`

- [ ] **Step 3: Implement get_transfers**

Append to `ActualParser`:

```python
    def get_transfers(self) -> list[TransactionDict]:
        """Reconstruct transfer transactions from paired transferred_id rows."""
        # Get accounts for name lookup
        acct_rows = self._conn.execute(
            "SELECT id, name FROM accounts"
        ).fetchall()
        acct_names = {r["id"]: r["name"] for r in acct_rows}

        rows = self._conn.execute(
            "SELECT id, acct, amount, date, transferred_id "
            "FROM transactions "
            "WHERE tombstone=0 AND isParent=0 AND isChild=0 AND transferred_id IS NOT NULL "
            "ORDER BY transferred_id, amount"
        ).fetchall()

        # Group by transferred_id
        pairs: dict[str, list] = {}
        for r in rows:
            tid = r["transferred_id"]
            if tid not in pairs:
                pairs[tid] = []
            pairs[tid].append(r)

        result = []
        for tid, pair in pairs.items():
            if len(pair) != 2:
                continue  # skip incomplete pairs

            # Negative = source, positive = destination
            source_row = pair[0] if pair[0]["amount"] < 0 else pair[1]
            dest_row = pair[1] if pair[1]["amount"] > 0 else pair[0]

            if source_row["amount"] >= 0 or dest_row["amount"] <= 0:
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
                "actual_id": tid,  # transferred_id as the reference
                "type": "transfer",
                "date": _parse_date(source_row["date"]),
                "description": f"Transfer: {source_name} → {dest_name}",
                "postings": postings,
            })

        return result
```

- [ ] **Step 4: Run test**

```bash
cd backend && python -m pytest tests/test_finance/test_actual_import.py::TestActualParserTransactions::test_reconstructs_transfer -v
```
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/finance/actual_parser.py backend/tests/test_finance/test_actual_import.py
git commit -m "feat: reconstruct transfer transactions from Actual paired rows"
```

---

### Task 4: Transaction reconstruction — split transactions

**Files:**
- Modify: `backend/app/finance/actual_parser.py`
- Modify: `backend/tests/test_finance/test_actual_import.py`

- [ ] **Step 1: Add failing test for splits**

Append to `TestActualParserTransactions`:

```python
    def test_reconstructs_split_transaction(self):
        schema = """
        CREATE TABLE accounts (id TEXT, name TEXT, offbudget INTEGER, closed INTEGER, tombstone INTEGER);
        CREATE TABLE categories (id TEXT, name TEXT, is_income INTEGER, cat_group TEXT, tombstone INTEGER);
        CREATE TABLE transactions (
            id TEXT, isParent INTEGER, isChild INTEGER, parent_id TEXT,
            acct TEXT, category TEXT, amount INTEGER, description TEXT,
            notes TEXT, date INTEGER, transferred_id TEXT, tombstone INTEGER
        );
        CREATE TABLE payees (id TEXT, name TEXT);
        CREATE TABLE payee_mapping (id TEXT, targetId TEXT, payeeId TEXT);
        """
        inserts = [
            "INSERT INTO accounts VALUES ('acc1', 'ING', 0, 0, 0)",
            "INSERT INTO categories VALUES ('cat1', 'Jedzenie', 0, 'g1', 0)",
            "INSERT INTO categories VALUES ('cat2', 'Chemia', 0, 'g1', 0)",
            # Parent: Biedronka, suma
            "INSERT INTO transactions VALUES ('parent1', 1, 0, NULL, 'acc1', NULL, -8000, NULL, NULL, 20260715, NULL, 0)",
            # Child 1: -5000, Jedzenie
            "INSERT INTO transactions VALUES ('child1', 0, 1, 'parent1', 'acc1', 'cat1', -5000, NULL, NULL, 20260715, NULL, 0)",
            # Child 2: -3000, Chemia
            "INSERT INTO transactions VALUES ('child2', 0, 1, 'parent1', 'acc1', 'cat2', -3000, NULL, NULL, 20260715, NULL, 0)",
        ]
        db_path = _make_actual_db(schema, inserts)
        parser = ActualParser(db_path)

        result = parser.get_splits()
        assert len(result) == 1
        txn = result[0]
        assert txn["type"] == "expense"
        assert len(txn["postings"]) == 3  # 1 credit + 2 debits
        # First posting: credit on account for total
        assert txn["postings"][0]["account_actual_id"] == "acc1"
        assert txn["postings"][0]["direction"] == "credit"
        assert txn["postings"][0]["source_amount"] == 8000
        # Second: debit for Jedzenie
        assert txn["postings"][1]["account_actual_id"] == "acc1"
        assert txn["postings"][1]["category_actual_id"] == "cat1"
        assert txn["postings"][1]["direction"] == "debit"
        assert txn["postings"][1]["source_amount"] == 5000
        # Third: debit for Chemia
        assert txn["postings"][2]["account_actual_id"] == "acc1"
        assert txn["postings"][2]["category_actual_id"] == "cat2"
        assert txn["postings"][2]["direction"] == "debit"
        assert txn["postings"][2]["source_amount"] == 3000
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_finance/test_actual_import.py::TestActualParserTransactions::test_reconstructs_split_transaction -v
```
Expected: `AttributeError: 'ActualParser' object has no attribute 'get_splits'`

- [ ] **Step 3: Implement get_splits**

Append to `ActualParser`:

```python
    def get_splits(self) -> list[TransactionDict]:
        """Reconstruct split transactions from parent/child pattern."""
        # Get parent transactions
        parents = self._conn.execute(
            "SELECT id, acct, amount, date FROM transactions "
            "WHERE tombstone=0 AND isParent=1 AND isChild=0"
        ).fetchall()

        if not parents:
            return []

        # Get all children for these parents
        parent_ids = [p["id"] for p in parents]
        placeholders = ",".join("?" for _ in parent_ids)
        children = self._conn.execute(
            f"SELECT id, parent_id, acct, category, amount "
            f"FROM transactions "
            f"WHERE tombstone=0 AND isChild=1 AND parent_id IN ({placeholders}) "
            f"ORDER BY parent_id, amount",
            parent_ids,
        ).fetchall()

        # Group children by parent_id
        children_by_parent: dict[str, list] = {}
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
                "type": "expense",  # splits in Actual are always expenses
                "date": _parse_date(p["date"]),
                "description": f"Split transaction ({len(child_list)} parts)",
                "postings": postings,
            })

        return result
```

- [ ] **Step 4: Run test**

```bash
cd backend && python -m pytest tests/test_finance/test_actual_import.py::TestActualParserTransactions::test_reconstructs_split_transaction -v
```
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/finance/actual_parser.py backend/tests/test_finance/test_actual_import.py
git commit -m "feat: reconstruct split transactions from Actual parent/child pattern"
```

---

### Task 5: NBP FX rates provider

**Files:**
- Create: `backend/app/finance/nbp_rates.py`
- Modify: `backend/tests/test_finance/test_actual_import.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to test_actual_import.py
import pytest
from unittest.mock import AsyncMock, patch
from datetime import date
from app.finance.nbp_rates import NbpRateProvider


class TestNbpRates:
    @pytest.mark.asyncio
    async def test_fetches_eur_rate(self):
        provider = NbpRateProvider()

        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "code": "EUR",
            "rates": [{"mid": 4.30, "effectiveDate": "2026-07-15"}]
        }
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.get", return_value=mock_response):
            rate = await provider.get_rate("EUR", date(2026, 7, 15))
            assert rate == 4.30

    @pytest.mark.asyncio
    async def test_caches_same_day(self):
        provider = NbpRateProvider()

        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "code": "EUR",
            "rates": [{"mid": 4.30, "effectiveDate": "2026-07-15"}]
        }
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.get", return_value=mock_response) as mock_get:
            rate1 = await provider.get_rate("EUR", date(2026, 7, 15))
            rate2 = await provider.get_rate("EUR", date(2026, 7, 15))
            assert rate1 == rate2 == 4.30
            assert mock_get.call_count == 1  # cached

    @pytest.mark.asyncio
    async def test_pln_always_one(self):
        provider = NbpRateProvider()
        rate = await provider.get_rate("PLN", date(2026, 7, 15))
        assert rate == 1.0

    def test_calculate_base_amount(self):
        provider = NbpRateProvider()
        assert provider.calculate_base_amount(100, 4.30) == 430
        assert provider.calculate_base_amount(50, 4.2678) == 213  # round to int
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_finance/test_actual_import.py::TestNbpRates -v
```
Expected: `ModuleNotFoundError: No module named 'app.finance.nbp_rates'`

- [ ] **Step 3: Write NbpRateProvider implementation**

```python
# backend/app/finance/nbp_rates.py
from datetime import date

import httpx


NBP_API_BASE = "https://api.nbp.pl/api/exchangerates/rates/A"


class NbpRateProvider:
    def __init__(self):
        self._cache: dict[tuple[str, date], float] = {}
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def get_rate(self, currency: str, rate_date: date) -> float:
        """Get NBP mid-rate for currency on date. Returns 1.0 for PLN."""
        if currency.upper() == "PLN":
            return 1.0

        cache_key = (currency.upper(), rate_date)
        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            date_str = rate_date.strftime("%Y-%m-%d")
            url = f"{NBP_API_BASE}/{currency.upper()}/{date_str}/"
            client = await self._get_client()
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            rate = float(data["rates"][0]["mid"])
            self._cache[cache_key] = rate
            return rate
        except Exception:
            self._cache[cache_key] = 0.0  # cache failures too
            return 0.0

    def calculate_base_amount(self, source_amount: int, fx_rate: float) -> int:
        """Convert source_amount in foreign currency minor units to PLN minor units."""
        if fx_rate <= 0:
            return source_amount
        return round(source_amount * fx_rate)

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
```

- [ ] **Step 4: Run tests**

```bash
cd backend && python -m pytest tests/test_finance/test_actual_import.py::TestNbpRates -v
```
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/finance/nbp_rates.py backend/tests/test_finance/test_actual_import.py
git commit -m "feat: NBP FX rate provider with caching for Actual import"
```

---

### Task 6: Enrich transactions with currency and FX rates

**Files:**
- Modify: `backend/app/finance/actual_parser.py`
- Modify: `backend/tests/test_finance/test_actual_import.py`

- [ ] **Step 1: Add test for multi-currency account**

Append to `TestActualParserTransactions`:

```python
    def test_detects_currency_from_account_name(self):
        schema = """
        CREATE TABLE accounts (id TEXT, name TEXT, offbudget INTEGER, closed INTEGER, tombstone INTEGER);
        CREATE TABLE transactions (
            id TEXT, isParent INTEGER, isChild INTEGER, parent_id TEXT,
            acct TEXT, category TEXT, amount INTEGER, description TEXT,
            notes TEXT, date INTEGER, transferred_id TEXT, tombstone INTEGER
        );
        CREATE TABLE categories (id TEXT, name TEXT, is_income INTEGER, cat_group TEXT, tombstone INTEGER);
        """
        inserts = [
            "INSERT INTO accounts VALUES ('rev_eu', 'Revolut EU', 0, 0, 0)",
            "INSERT INTO accounts VALUES ('rev_pln', 'Revolut PLN', 0, 0, 0)",
            "INSERT INTO categories VALUES ('cat1', 'Zakupy', 0, 'g1', 0)",
            "INSERT INTO transactions VALUES ('tx1', 0, 0, NULL, 'rev_eu', 'cat1', -500, NULL, NULL, 20260715, NULL, 0)",
            "INSERT INTO transactions VALUES ('tx2', 0, 0, NULL, 'rev_pln', 'cat1', -10000, NULL, NULL, 20260715, NULL, 0)",
        ]
        db_path = _make_actual_db(schema, inserts)
        parser = ActualParser(db_path)
        accounts = parser.get_accounts()

        eu_acc = next(a for a in accounts if a["name"] == "Revolut EU")
        pln_acc = next(a for a in accounts if a["name"] == "Revolut PLN")
        assert eu_acc["currency"] == "EUR"
        assert pln_acc["currency"] == "PLN"

        txns = parser.get_transactions()
        eu_txn = next(t for t in txns if t["actual_id"] == "tx1")
        pln_txn = next(t for t in txns if t["actual_id"] == "tx2")
        assert eu_txn["postings"][0]["source_currency"] == "EUR"
        assert pln_txn["postings"][0]["source_currency"] == "PLN"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_finance/test_actual_import.py::TestActualParserTransactions::test_detects_currency_from_account_name -v
```
Expected: `AssertionError: assert 'PLN' == 'EUR'` (currency not yet propagated to postings)

- [ ] **Step 3: Update get_transactions to use account currency**

In `actual_parser.py`, the `get_transactions` method currently hardcodes `source_currency: "PLN"`. We need to build a currency lookup first.

Modify `get_transactions` — before the main query, add:

```python
    def get_transactions(self) -> list[TransactionDict]:
        # Build currency lookup from accounts
        acct_currency = {
            a["actual_id"]: a["currency"]
            for a in self.get_accounts()
        }
        # ... rest of existing method, replace "PLN" with acct_currency.get(r["acct"], "PLN")
```

Replace the two `"source_currency": "PLN"` lines inside postings with:
```python
                "source_currency": acct_currency.get(r["acct"], "PLN"),
```

- [ ] **Step 4: Run test**

```bash
cd backend && python -m pytest tests/test_finance/test_actual_import.py::TestActualParserTransactions::test_detects_currency_from_account_name -v
```
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/finance/actual_parser.py backend/tests/test_finance/test_actual_import.py
git commit -m "feat: propagate account currency to transaction postings"
```

---

### Task 7: FX rate enrichment during migration

**Files:**
- Create: `backend/scripts/migrate_actual.py`
- Create: `backend/tests/test_finance/test_actual_import.py` (add test)

- [ ] **Step 1: Add integration test for FX enrichment**

Append to `test_actual_import.py`:

```python
class TestFxEnrichment:
    @pytest.mark.asyncio
    async def test_enriches_eur_postings_with_nbp_rate(self):
        from app.finance.nbp_rates import NbpRateProvider

        provider = NbpRateProvider()
        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "code": "EUR",
            "rates": [{"mid": 4.2856, "effectiveDate": "2026-07-15"}]
        }
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.get", return_value=mock_response):
            # EUR posting: 500 euro cents (5.00 EUR)
            base_amount = provider.calculate_base_amount(500, await provider.get_rate("EUR", date(2026, 7, 15)))
            assert base_amount == 2143  # 5.00 * 4.2856 = 21.428 -> round to 2143 groszy

    @pytest.mark.asyncio
    async def test_pln_postings_unchanged(self):
        from app.finance.nbp_rates import NbpRateProvider

        provider = NbpRateProvider()
        rate = await provider.get_rate("PLN", date(2026, 7, 15))
        base_amount = provider.calculate_base_amount(10000, rate)
        assert rate == 1.0
        assert base_amount == 10000
```

- [ ] **Step 2: Run tests**

```bash
cd backend && python -m pytest tests/test_finance/test_actual_import.py::TestFxEnrichment -v
```
Expected: 2 passed

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_finance/test_actual_import.py
git commit -m "test: add FX enrichment integration tests"
```

---

### Task 8: Main migration CLI script

**Files:**
- Create: `backend/scripts/migrate_actual.py`
- Create: `backend/tests/test_finance/test_actual_import.py` (add test)

- [ ] **Step 1: Write test for migration pipeline (dry-run)**

Append to `test_actual_import.py`:

```python
class TestMigrationPipeline:
    @pytest.mark.asyncio
    async def test_dry_run_produces_report(self, db_session):
        """Full pipeline dry-run with synthetic data."""
        import json
        import sys
        from pathlib import Path
        from app.finance.actual_parser import ActualParser
        from app.finance.nbp_rates import NbpRateProvider
        from app.finance.service import create_account, create_category

        # Build synthetic Actual SQLite
        schema = """
        CREATE TABLE accounts (id TEXT, name TEXT, offbudget INTEGER, closed INTEGER, tombstone INTEGER);
        CREATE TABLE categories (id TEXT, name TEXT, is_income INTEGER, cat_group TEXT, tombstone INTEGER);
        CREATE TABLE transactions (
            id TEXT, isParent INTEGER, isChild INTEGER, parent_id TEXT,
            acct TEXT, category TEXT, amount INTEGER, description TEXT,
            notes TEXT, date INTEGER, transferred_id TEXT, tombstone INTEGER
        );
        """
        inserts = [
            "INSERT INTO accounts VALUES ('acc1', 'ING', 0, 0, 0)",
            "INSERT INTO accounts VALUES ('acc2', 'Gotowka', 0, 0, 0)",
            "INSERT INTO categories VALUES ('cat1', 'Jedzenie', 0, 'g1', 0)",
            "INSERT INTO categories VALUES ('cat2', 'Pensja', 1, 'g2', 0)",
            # Simple expense
            "INSERT INTO transactions VALUES ('tx1', 0, 0, NULL, 'acc1', 'cat1', -5000, NULL, 'Biedronka', 20260701, NULL, 0)",
            # Simple income
            "INSERT INTO transactions VALUES ('tx2', 0, 0, NULL, 'acc1', 'cat2', 500000, NULL, 'Wyplata', 20260701, NULL, 0)",
            # Transfer
            "INSERT INTO transactions VALUES ('tx_a', 0, 0, NULL, 'acc1', NULL, -20000, NULL, NULL, 20260701, 'link1', 0)",
            "INSERT INTO transactions VALUES ('tx_b', 0, 0, NULL, 'acc2', NULL, 20000, NULL, NULL, 20260701, 'link1', 0)",
            # Split
            "INSERT INTO transactions VALUES ('parent1', 1, 0, NULL, 'acc1', NULL, -10000, NULL, NULL, 20260701, NULL, 0)",
            "INSERT INTO transactions VALUES ('child1', 0, 1, 'parent1', 'acc1', 'cat1', -6000, NULL, NULL, 20260701, NULL, 0)",
            "INSERT INTO transactions VALUES ('child2', 0, 1, 'parent1', 'acc1', 'cat1', -4000, NULL, NULL, 20260701, NULL, 0)",
        ]
        db_path = _make_actual_db(schema, inserts)

        # Parse
        parser = ActualParser(db_path)
        accounts = parser.get_accounts()
        categories = parser.get_categories()
        transactions = parser.get_transactions()
        transfers = parser.get_transfers()
        splits = parser.get_splits()

        # Verify counts
        assert len(accounts) == 2
        assert len(categories) == 2
        assert len(transactions) == 2   # 1 expense + 1 income
        assert len(transfers) == 1
        assert len(splits) == 1

        # Verify all transactions have balanced postings
        all_txns = transactions + transfers + splits
        for txn in all_txns:
            total = 0
            for p in txn["postings"]:
                signed = p["source_amount"] if p["direction"] == "debit" else -p["source_amount"]
                total += signed
            assert total == 0, f"Transaction {txn['actual_id']} not balanced: {total}"

        # Create accounts and categories in DB (for dry-run we write to test DB)
        acct_map = {}
        user_id = uuid.uuid4()
        for a in accounts:
            pa_account = await create_account(db_session, user_id, AccountCreate(
                name=a["name"], type=a["type"], currency=a["currency"],
            ))
            acct_map[a["actual_id"]] = pa_account.id

        cat_map = {}
        for c in categories:
            pa_cat = await create_category(db_session, user_id, CategoryCreate(
                name=c["name"], type=c["type"],
            ))
            cat_map[c["actual_id"]] = pa_cat.id

        # Build final PA transactions with resolved IDs (all PLN, no FX needed)
        resolved = []
        for txn in all_txns:
            postings = []
            for p in txn["postings"]:
                postings.append(PostingCreate(
                    account_id=acct_map[p["account_actual_id"]],
                    category_id=cat_map.get(p["category_actual_id"]) if p.get("category_actual_id") else None,
                    source_amount=p["source_amount"],
                    source_currency=p["source_currency"],
                    base_amount_pln=p["source_amount"],  # all PLN in test
                    fx_rate=1.0,
                    fx_rate_source="manual",
                    direction=p["direction"],
                ))
            resolved.append({
                "actual_id": txn["actual_id"],
                "type": txn["type"],
                "date": txn["date"],
                "description": txn["description"],
                "postings": postings,
            })

        # Write each transaction to DB via service
        for txn in resolved:
            await create_transaction(db_session, user_id, TransactionCreate(
                transaction_date=txn["date"],
                description=f"[actual:{txn['actual_id']}] {txn['description']}",
                type=txn["type"],
                source="actual",
                postings=txn["postings"],
            ))

        # Verify data in DB
        from app.finance.service import get_transactions
        db_txns = await get_transactions(db_session, user_id, limit=100)
        assert len(db_txns) == 5  # 2 simple + 1 transfer + 1 split
```

Note: this test requires imports at the top of the file:
```python
import uuid
from app.finance.schemas import AccountCreate, CategoryCreate, PostingCreate, TransactionCreate
from app.finance.service import create_account, create_category, create_transaction
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_finance/test_actual_import.py::TestMigrationPipeline -v
```
Expected: Test passes (this test uses existing services and parser that should already work by now). If it fails on foreign key or other issues, debug and fix.

- [ ] **Step 3: Write the CLI script**

```python
# backend/scripts/migrate_actual.py
"""
Migrate data from Actual Budget SQLite to Personal Advisor PostgreSQL.

Usage:
    python scripts/migrate_actual.py --blob-path /path/to/file-xxx.blob --dry-run
    python scripts/migrate_actual.py --blob-path /path/to/file-xxx.blob --execute

Requirements: Run inside backend container (has access to DB + models).
"""

import argparse
import asyncio
import json
import sys
import uuid
import zipfile
from datetime import date
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import async_session_factory
from app.finance.actual_parser import ActualParser
from app.finance.nbp_rates import NbpRateProvider
from app.finance.schemas import AccountCreate, CategoryCreate, PostingCreate, TransactionCreate
from app.finance.service import create_account, create_category, create_transaction, get_transactions


async def extract_sqlite(blob_path: Path) -> Path:
    """Extract db.sqlite from Actual encrypted ZIP blob."""
    extract_dir = blob_path.parent / "extracted"
    extract_dir.mkdir(exist_ok=True)
    with zipfile.ZipFile(blob_path, "r") as zf:
        zf.extractall(extract_dir)
    sqlite_path = extract_dir / "db.sqlite"
    if not sqlite_path.exists():
        raise FileNotFoundError(f"db.sqlite not found in {blob_path}")
    return sqlite_path


async def resolve_ids(
    db: AsyncSession,
    user_id: uuid.UUID,
    parser: ActualParser,
) -> tuple[dict[str, uuid.UUID], dict[str, uuid.UUID], dict[str, str]]:
    """Create accounts and categories, return Actual ID -> PA ID mappings."""
    acct_map = {}
    cat_map = {}
    acct_currency = {}

    for a in parser.get_accounts():
        pa_acct = await create_account(db, user_id, AccountCreate(
            name=a["name"], type=a["type"], currency=a["currency"],
        ))
        acct_map[a["actual_id"]] = pa_acct.id
        acct_currency[a["actual_id"]] = a["currency"]

    for c in parser.get_categories():
        pa_cat = await create_category(db, user_id, CategoryCreate(
            name=c["name"], type=c["type"],
        ))
        cat_map[c["actual_id"]] = pa_cat.id

    return acct_map, cat_map, acct_currency


def build_pa_postings(
    txn: dict,
    acct_map: dict[str, uuid.UUID],
    cat_map: dict[str, uuid.UUID],
    acct_currency: dict[str, str],
    fx_rates: dict[tuple[str, date], float],
) -> list[PostingCreate]:
    """Convert parser postings to PA PostingCreate with resolved IDs and FX."""
    postings = []
    for p in txn["postings"]:
        actual_acct_id = p["account_actual_id"]
        currency = acct_currency.get(actual_acct_id, "PLN")
        fx_rate = fx_rates.get((currency, txn["date"]), 1.0)
        if fx_rate == 0.0:
            base_amount = p["source_amount"]
            fx_source = "nbp_error"
        elif currency == "PLN":
            base_amount = p["source_amount"]
            fx_source = "manual"
        else:
            base_amount = round(p["source_amount"] * fx_rate)
            fx_source = "nbp"

        postings.append(PostingCreate(
            account_id=acct_map[actual_acct_id],
            category_id=cat_map.get(p.get("category_actual_id")) if p.get("category_actual_id") else None,
            source_amount=p["source_amount"],
            source_currency=currency,
            base_amount_pln=base_amount,
            fx_rate=fx_rate,
            fx_rate_source=fx_source,
            direction=p["direction"],
        ))
    return postings


def make_description(actual_id: str, description: str) -> str:
    """Prefix description with Actual UUID for idempotency."""
    return f"[actual:{actual_id}] {description}"


async def check_idempotent(db: AsyncSession, user_id: uuid.UUID, actual_id: str) -> bool:
    """Check if transaction with this Actual ID already exists."""
    from sqlalchemy import select, text
    from app.finance.models import FinancialTransaction

    result = await db.execute(
        select(FinancialTransaction.id).where(
            FinancialTransaction.user_id == user_id,
            FinancialTransaction.source == "actual",
            FinancialTransaction.description.like(f"[actual:{actual_id}]%"),
        )
    )
    return result.first() is not None


def generate_report(
    stats: dict,
    errors: list[str],
    warnings: list[str],
    mapping: dict,
) -> str:
    """Generate human-readable report."""
    lines = [
        "=" * 60,
        "Actual Budget → Personal Advisor — Migration Report",
        "=" * 60,
        "",
        f"Accounts imported:    {stats.get('accounts', 0)}",
        f"Categories imported:  {stats.get('categories', 0)}",
        f"Transactions:         {stats.get('transactions', 0)} (simple)",
        f"Transfers:            {stats.get('transfers', 0)}",
        f"Splits:               {stats.get('splits', 0)}",
        f"Total written:        {stats.get('written', 0)}",
        f"Skipped (duplicate):  {stats.get('skipped', 0)}",
        f"Errors:               {stats.get('errors', 0)}",
        "",
    ]
    if warnings:
        lines.append("Warnings:")
        for w in warnings:
            lines.append(f"  ⚠ {w}")
    if errors:
        lines.append("Errors:")
        for e in errors:
            lines.append(f"  ✗ {e}")
    lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)


async def migrate(
    blob_path: Path,
    user_id: uuid.UUID,
    dry_run: bool = False,
) -> None:
    """Main migration pipeline."""
    sqlite_path = await extract_sqlite(blob_path)
    parser = ActualParser(sqlite_path)
    nbp = NbpRateProvider()

    errors: list[str] = []
    warnings: list[str] = []
    stats = {
        "accounts": 0, "categories": 0,
        "transactions": 0, "transfers": 0, "splits": 0,
        "written": 0, "skipped": 0, "errors": 0,
    }
    mapping = {"accounts": {}, "categories": {}}

    # Phase 1: Parse
    print("Phase 1: Reading Actual data...")
    accounts = parser.get_accounts()
    categories = parser.get_categories()
    simple_txns = parser.get_transactions()
    transfers = parser.get_transfers()
    splits = parser.get_splits()
    print(f"  Accounts: {len(accounts)}, Categories: {len(categories)}")
    print(f"  Simple: {len(simple_txns)}, Transfers: {len(transfers)}, Splits: {len(splits)}")

    if dry_run:
        # Validate all postings
        all_txns = simple_txns + transfers + splits
        for txn in all_txns:
            total = 0
            for p in txn["postings"]:
                signed = p["source_amount"] if p["direction"] == "debit" else -p["source_amount"]
                total += signed
            if total != 0:
                errors.append(f"Posting sum not zero for {txn['actual_id']}: {total}")

        # Fetch FX rates for non-PLN accounts (only to validate availability)
        fx_dates = set()
        for txn in all_txns:
            for p in txn["postings"]:
                acct = next((a for a in accounts if a["actual_id"] == p["account_actual_id"]), None)
                if acct and acct["currency"] != "PLN":
                    fx_dates.add((acct["currency"], txn["date"]))

        for currency, dt in fx_dates:
            rate = await nbp.get_rate(currency, dt)
            if rate == 0.0:
                warnings.append(f"NBP rate unavailable: {currency} on {dt}")

        # Generate dry-run report
        report = generate_report(
            {"accounts": len(accounts), "categories": len(categories),
             "transactions": len(simple_txns), "transfers": len(transfers),
             "splits": len(splits), "written": 0, "skipped": 0, "errors": len(errors)},
            errors, warnings, mapping,
        )
        print(report)

        output_dir = Path("scripts/output")
        output_dir.mkdir(exist_ok=True)
        (output_dir / "migration_report.txt").write_text(report)
        (output_dir / "migration_log.json").write_text(json.dumps({
            "stats": stats, "errors": errors, "warnings": warnings,
        }, indent=2, default=str))
        print("Report saved to scripts/output/")
        return

    # Phase 2: Write to DB
    async with async_session_factory() as db:
        print("Phase 2: Creating accounts and categories...")
        acct_map, cat_map, acct_currency = await resolve_ids(db, user_id, parser)
        stats["accounts"] = len(acct_map)
        stats["categories"] = len(cat_map)
        for actual_id, pa_id in acct_map.items():
            mapping["accounts"][actual_id] = str(pa_id)
        for actual_id, pa_id in cat_map.items():
            mapping["categories"][actual_id] = str(pa_id)

        # Fetch FX rates for non-PLN accounts
        print("Phase 3: Fetching FX rates...")
        fx_rates: dict[tuple[str, date], float] = {}
        all_txns = simple_txns + transfers + splits
        for txn in all_txns:
            for p in txn["postings"]:
                actual_acct_id = p["account_actual_id"]
                currency = acct_currency.get(actual_acct_id, "PLN")
                if currency != "PLN":
                    rate = await nbp.get_rate(currency, txn["date"])
                    fx_rates[(currency, txn["date"])] = rate
                    if rate == 0.0:
                        warnings.append(f"NBP rate unavailable: {currency} on {txn['date']}")

        # Phase 4: Write transactions
        print("Phase 4: Writing transactions...")
        stats["transactions"] = len(simple_txns)
        stats["transfers"] = len(transfers)
        stats["splits"] = len(splits)

        for txn in all_txns:
            if await check_idempotent(db, user_id, txn["actual_id"]):
                stats["skipped"] += 1
                continue

            postings = build_pa_postings(txn, acct_map, cat_map, acct_currency, fx_rates)

            # Validate before writing
            total = 0
            for p in postings:
                signed = p.base_amount_pln if p.direction == "debit" else -p.base_amount_pln
                total += signed
            if total != 0:
                errors.append(f"Posting sum not zero for {txn['actual_id']}: {total} after FX")
                stats["errors"] += 1
                continue

            try:
                await create_transaction(db, user_id, TransactionCreate(
                    transaction_date=txn["date"],
                    description=make_description(txn["actual_id"], txn["description"]),
                    type=txn["type"],
                    source="actual",
                    postings=postings,
                ))
                stats["written"] += 1
            except Exception as e:
                errors.append(f"Failed to write {txn['actual_id']}: {e}")
                stats["errors"] += 1

        # Generate report
        report = generate_report(stats, errors, warnings, mapping)
        print(report)

        output_dir = Path("scripts/output")
        output_dir.mkdir(exist_ok=True)
        (output_dir / "migration_report.txt").write_text(report)
        (output_dir / "migration_log.json").write_text(json.dumps({
            "stats": stats, "errors": errors, "warnings": warnings,
            "mapping": mapping,
        }, indent=2, default=str))
        print("Report saved to scripts/output/")

        if not dry_run:
            await db.commit()

    await nbp.close()


async def main():
    parser = argparse.ArgumentParser(description="Migrate Actual Budget to Personal Advisor")
    parser.add_argument("--blob-path", required=True, help="Path to Actual blob file (file-*.blob)")
    parser.add_argument("--user-id", required=True, help="PA user UUID to assign imported data to")
    parser.add_argument("--dry-run", action="store_true", help="Validate and report only, no writes")
    parser.add_argument("--execute", action="store_true", help="Actually write to database")
    args = parser.parse_args()

    if args.execute and args.dry_run:
        print("Error: cannot use both --dry-run and --execute")
        sys.exit(1)
    if not args.dry_run and not args.execute:
        print("Error: must specify --dry-run or --execute")
        sys.exit(1)

    blob_path = Path(args.blob_path)
    if not blob_path.exists():
        print(f"Error: blob file not found: {args.blob_path}")
        sys.exit(1)

    user_id = uuid.UUID(args.user_id)
    await migrate(blob_path, user_id, dry_run=args.dry_run)


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Commit**

```bash
git add backend/scripts/migrate_actual.py backend/tests/test_finance/test_actual_import.py
git commit -m "feat: migration CLI script with dry-run and execute modes"
```

---

### Task 9: Run all tests and verify

**Files:**
- None (verification only)

- [ ] **Step 1: Run all import-related tests**

```bash
cd backend && python -m pytest tests/test_finance/test_actual_import.py -v
```
Expected: All tests pass (12+ tests)

- [ ] **Step 2: Run existing tests to verify no regressions**

```bash
cd backend && python -m pytest tests/ -v --ignore=tests/test_finance/test_actual_import.py
```
Expected: All existing tests pass (11 unit + 4 integration)

---

### Task 10: Execute migration on actual data

**Files:**
- Modify: `docker/finanse/compose.yaml` (add Actual data volume mount)

- [ ] **Step 1: Add Actual data volume to backend service in compose**

```yaml
# docker/finanse/compose.yaml — add to finanse-backend volumes:
    volumes:
      - ../../opt/finanse/backend:/app
      - /docker/actualbudget/data/user-files:/actual_data:ro
```

- [ ] **Step 2: Restart backend**

```bash
docker compose restart finanse-backend
```

- [ ] **Step 3: Run dry-run**

```bash
docker exec -it finanse-backend python scripts/migrate_actual.py \
  --blob-path /actual_data/file-1bdc93e7-2c30-473e-b538-740a6b6021dc.blob \
  --user-id <USER_UUID> \
  --dry-run
```

- [ ] **Step 4: Review dry-run report, then execute**

```bash
docker exec -it finanse-backend python scripts/migrate_actual.py \
  --blob-path /actual_data/file-1bdc93e7-2c30-473e-b538-740a6b6021dc.blob \
  --user-id <USER_UUID> \
  --execute
```

- [ ] **Step 5: Verify data in PA**

```bash
# Check counts
docker exec -it finanse-postgres psql -U finanse -d finanse -c "
  SELECT 'accounts' as entity, count(*) from accounts
  UNION ALL SELECT 'categories', count(*) from categories
  UNION ALL SELECT 'transactions', count(*) from financial_transactions where source='actual'
  UNION ALL SELECT 'postings', count(*) from postings;
"
```

- [ ] **Step 6: Revert compose volume mount (production cleanup)**

```yaml
# Remove the /actual_data volume mount from compose
```

- [ ] **Step 7: Final commit with migration log**

```bash
git add backend/scripts/output/migration_report.txt backend/scripts/output/migration_log.json
git commit -m "docs: add Actual migration report and log"
```
