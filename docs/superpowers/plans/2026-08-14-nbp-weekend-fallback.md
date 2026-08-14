# NBP Weekend FX Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Import weekend Actual foreign-currency transactions with the preceding published NBP Table A rate and explicit provenance.

**Architecture:** Replace the provider's float-only cache with an immutable quote containing the rate, NBP effective date, and source. The importer passes these quotes to posting construction so its persisted provenance labels an exact rate as `nbp` and a weekend fallback as `nbp_previous_business_day`.

**Tech Stack:** Python 3.12, httpx, pytest, SQLAlchemy/Pydantic importer schemas.

---

### Task 1: Specify Weekend Lookup Behavior

**Files:**
- Modify: `backend/tests/test_finance/test_actual_import.py:615-684`

- [ ] **Step 1: Write failing provider tests**

```python
@pytest.mark.asyncio
@pytest.mark.parametrize("weekend_date, effective_date", [
    (date(2026, 5, 30), date(2026, 5, 29)),
    (date(2026, 6, 14), date(2026, 6, 12)),
])
async def test_uses_previous_published_rate_for_weekend_404(weekend_date, effective_date):
    quote = await provider.get_rate("USD", weekend_date)
    assert quote.rate == 3.6395
    assert quote.effective_date == effective_date
    assert quote.source == "nbp_previous_business_day"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `/opt/finanse/backend/.venv/bin/pytest tests/test_finance/test_actual_import.py::TestNbpRates -v`

Expected: FAIL because the provider returns a float and does not request a fallback range.

### Task 2: Preserve Quote Metadata in the Provider

**Files:**
- Modify: `backend/app/finance/nbp_rates.py:1-52`
- Test: `backend/tests/test_finance/test_actual_import.py:615-684`

- [ ] **Step 1: Introduce immutable rate quote and cache it by requested date**

```python
@dataclass(frozen=True)
class NbpRate:
    rate: float
    effective_date: date
    source: str
```

- [ ] **Step 2: Keep exact lookups primary and fallback only after weekend 404**

```python
if response.status_code == 404 and rate_date.weekday() in (5, 6):
    response = await client.get(f"{url_start}/{url_end}/")
```

Select the newest returned `effectiveDate` earlier than the requested date. Cache only a valid quote; do not cache failed lookups.

- [ ] **Step 3: Run provider tests to verify they pass**

Run: `/opt/finanse/backend/.venv/bin/pytest tests/test_finance/test_actual_import.py::TestNbpRates -v`

Expected: PASS, including cache and unavailable-range cases.

### Task 3: Propagate Provenance to Imported Postings

**Files:**
- Modify: `backend/scripts/migrate_actual.py:319-443,704-715,848-856`
- Modify: `backend/tests/test_finance/test_actual_import.py:769-840`
- Modify: `backend/tests/test_finance/test_reconciliation.py:320-356`

- [ ] **Step 1: Write failing posting provenance test**

```python
postings = build_pa_postings(..., {("USD", saturday): weekend_quote})
assert all(posting.fx_rate_source == "nbp_previous_business_day" for posting in postings)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `/opt/finanse/backend/.venv/bin/pytest tests/test_finance/test_actual_import.py::TestMigrationPostings -v`

Expected: FAIL because the importer only accepts numeric rates and unconditionally emits `nbp`.

- [ ] **Step 3: Change the FX map to retain quotes**

Use the quote value for `base_amount_pln`, quote source for `fx_rate_source`, and continue raising `ImportValidationError` for an unavailable quote.

Update the existing unavailable-FX reconciliation fixture to return `None`, which is the provider's explicit unavailable value.

- [ ] **Step 4: Run focused tests to verify they pass**

Run: `/opt/finanse/backend/.venv/bin/pytest tests/test_finance/test_actual_import.py -v`

Expected: PASS.

### Task 4: Verify The Isolated Reconciliation

**Files:**
- Modify: `docs/CHANGELOG.md`
- Modify: `docs/TASKS.md`
- Modify: `docs/JOURNAL.md`

- [ ] **Step 1: Run focused backend quality checks**

Run: `/opt/finanse/backend/.venv/bin/ruff check app/ tests/ && /opt/finanse/backend/.venv/bin/mypy app/ && /opt/finanse/backend/.venv/bin/pytest tests/test_finance/test_actual_import.py -v`

Expected: exit code 0.

- [ ] **Step 2: Execute the DOM import only against `finanse_test`**

Run the established `DATABASE_URL` for `127.0.0.1:55432/finanse_test`, use the test user and DOM blob, and pass `--execute --require-reconciled`.

Expected: exit code 0 and `is_reconciled=true` in `/tmp/actual_migration/reconciliation.json`.

- [ ] **Step 3: Record verified results and commit**

```bash
git add backend/app/finance/nbp_rates.py backend/scripts/migrate_actual.py backend/tests/test_finance/test_actual_import.py docs/
git commit -m "fix: obsłuż weekendowe kursy NBP w imporcie Actual"
```
