# Uzgodniona migracja Actual Budget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Poprawnie importować pełną historię Actual z saldami kont, kontami pozabudżetowymi i hierarchią kategorii oraz blokować korektę produkcji, dopóki raport uzgodnieniowy nie potwierdzi zgodności.

**Architecture:** Ledger rozdzieli posting kontowy od postingu kategorii: `Posting.account_id` stanie się opcjonalny, a zwykły przychód/wydatek otrzyma konto finansowe po jednej stronie i kategorię po stronie przeciwstawnej. `Account.is_budget_account` oraz `Posting.is_budget_impact` utrzymają semantykę Actual `offbudget`, także dla agregacji kategorii. Parser Actual zwróci grupy kategorii i flagę konta, importer utworzy rodziców przed dziećmi, a oddzielny moduł reconciliacji porówna źródłowe salda Actual z saldami PA po imporcie testowym.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 async, Alembic, PostgreSQL 16, SQLite Actual, pytest/pytest-asyncio, React 18, TypeScript, TanStack Query, Vitest.

---

## Granice bezpieczeństwa

- Etapy 1–6 pracują wyłącznie na kodzie i izolowanym `finanse_test` na `127.0.0.1:55432`.
- Nie wolno uruchamiać `DELETE`, `TRUNCATE`, `DROP`, migracji produkcyjnej ani importu `--execute` przeciwko bazie `finanse`.
- Produkcyjna korekta będzie oddzielnym, ręcznie zatwierdzonym planem po przedstawieniu raportu z Task 6.
- Aktualny import produkcyjny pozostaje nienaruszony jako materiał audytowy do czasu zatwierdzonej korekty.

## Mapa plików

- Modify: `backend/app/finance/models.py` — `Account.is_budget_account`, nullable `Posting.account_id`, `Posting.is_budget_impact`.
- Modify: `backend/app/finance/schemas.py` — opcjonalne `account_id` i nowe pola odpowiedzi konta/postingu/kategorii podsumowania.
- Create: `backend/migrations/versions/d5f9a1c2b3e4_actual_reconciliation_ledger.py` — rozszerzenie schematu z bezpiecznymi wartościami domyślnymi.
- Modify: `backend/app/finance/service.py` — walidacja postingów konto/kategoria, salda, podsumowania wyłącznie kont budżetowych i agregaty kategorii.
- Modify: `backend/app/finance/router.py` — endpoint agregatów kategorii.
- Modify: `backend/app/finance/actual_parser.py` — `offbudget`, grupy kategorii, konta i kwoty transferów w rzeczywistych walutach.
- Modify: `backend/scripts/migrate_actual.py` — mapowanie rodzic-dziecko, poprawne postingi, FX i uruchamialny import testowy.
- Create: `backend/app/finance/reconciliation.py` — czysty model raportu i porównanie per konto/kategoria.
- Modify: `backend/tests/test_finance/test_actual_import.py` — parser, postingi i end-to-end import do testowej bazy.
- Modify: `backend/tests/test_finance/test_ledger.py` — invariant postingów kontowych/kategoryjnych oraz wykluczenie offbudget.
- Create: `backend/tests/test_finance/test_reconciliation.py` — różnice sald, FK kategorii i blokada importu z nierozliczonym kontem.
- Modify: `frontend/src/api/finance.ts` — typy `is_budget_account`, hierarchia kategorii i hook podsumowania kategorii.
- Modify: `frontend/src/pages/Finances.tsx` — osobna sekcja kont pozabudżetowych i wydatki wg grup/kategorii.
- Create: `frontend/src/api/finance.test.ts` — test transformacji drzewa kategorii i rozdziału kont.
- Modify: `docs/CHANGELOG.md`, `docs/TASKS.md`, `docs/JOURNAL.md` — tylko po zweryfikowanym dry-run.

## Task 1: Rozszerzyć model ledgeru bez zmiany istniejących danych

**Files:**
- Modify: `backend/app/finance/models.py:21-85`.
- Modify: `backend/app/finance/schemas.py:7-86`.
- Create: `backend/migrations/versions/d5f9a1c2b3e4_actual_reconciliation_ledger.py`.
- Test: `backend/tests/test_finance/test_ledger.py`.

- [ ] **Step 1: Napisać failing test dla postingu wyłącznie kategorii**

W `test_ledger.py` dodać test, który tworzy wydatek z jednym postingiem kontowym i jednym kategoriowym:

```python
postings = [
    PostingCreate(
        account_id=account.id,
        category_id=None,
        source_amount=5000,
        source_currency="PLN",
        base_amount_pln=5000,
        fx_rate=1.0,
        fx_rate_source="manual",
        direction="credit",
        is_budget_impact=True,
    ),
    PostingCreate(
        account_id=None,
        category_id=category.id,
        source_amount=5000,
        source_currency="PLN",
        base_amount_pln=5000,
        fx_rate=1.0,
        fx_rate_source="manual",
        direction="debit",
        is_budget_impact=True,
    ),
]
transaction = await create_transaction(db_session, user_id, TransactionCreate(
    description="Paliwo", type="expense", postings=postings
))
assert transaction.postings[0].account_id == account.id
assert transaction.postings[1].account_id is None
```

- [ ] **Step 2: Uruchomić test i potwierdzić RED**

Run:

```bash
cd backend && TEST_DATABASE_URL=postgresql+asyncpg://finanse:finanse@127.0.0.1:55432/finanse_test /opt/finanse/backend/.venv/bin/pytest tests/test_finance/test_ledger.py::test_category_only_posting_is_persisted -v
```

Expected: FAIL, ponieważ `PostingCreate.account_id` i kolumna `postings.account_id` są obecnie wymagane.

- [ ] **Step 3: Dodać pola modelu i schematów**

W `Account` dodać:

```python
is_budget_account: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
```

W `Posting` zmienić kolumnę na nullable i dodać:

```python
account_id: Mapped[uuid.UUID | None] = mapped_column(
    UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=True, index=True
)
is_budget_impact: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
```

W Pydantic użyć `account_id: uuid.UUID | None = None`, `is_budget_impact: bool = True` w `PostingCreate`; dodać `is_budget_account` do request/response konta i `is_budget_impact` do odpowiedzi postingu.

- [ ] **Step 4: Utworzyć migrację Alembic ręcznie**

Migracja ma dokładnie:

```python
op.add_column("accounts", sa.Column("is_budget_account", sa.Boolean(), server_default=sa.true(), nullable=False))
op.add_column("postings", sa.Column("is_budget_impact", sa.Boolean(), server_default=sa.true(), nullable=False))
op.alter_column("postings", "account_id", existing_type=sa.UUID(), nullable=True)
op.alter_column("accounts", "is_budget_account", server_default=None)
op.alter_column("postings", "is_budget_impact", server_default=None)
```

Downgrade przywraca `account_id` do NOT NULL wyłącznie po walidacji, że nie istnieją postingi bez konta; w przeciwnym razie podnosi czytelny `RuntimeError` i nie usuwa danych.

- [ ] **Step 5: Zaimplementować minimalną walidację domain service**

W `_validate_transaction_postings` wymagać, aby każdy posting miał co najmniej `account_id` albo `category_id`; konto walidować tylko, gdy `account_id is not None`, kategorię tylko gdy `category_id is not None`. Zachować wymaganie co najmniej dwóch postingów i sumy signed `base_amount_pln == 0`.

Nie zabraniać historycznych postingów z jednoczesnym `account_id` i `category_id`, ponieważ obecne dane oraz manualny klient API mogą je posiadać; poprawiony importer nie może jednak tworzyć takiego postingu.

- [ ] **Step 6: Uruchomić GREEN i migrację na testowej bazie**

```bash
docker compose -f /docker/finanse/compose.test.yaml up -d --wait postgres-test
cd backend && DATABASE_URL=postgresql+asyncpg://finanse:finanse@127.0.0.1:55432/finanse_test /opt/finanse/backend/.venv/bin/alembic upgrade head
TEST_DATABASE_URL=postgresql+asyncpg://finanse:finanse@127.0.0.1:55432/finanse_test /opt/finanse/backend/.venv/bin/pytest tests/test_finance/test_ledger.py -v
docker compose -f /docker/finanse/compose.test.yaml down
```

Expected: test PASS; testowa migracja kończy się bez zmiany produkcyjnej bazy.

- [ ] **Step 7: Commit**

```bash
git add backend/app/finance/models.py backend/app/finance/schemas.py backend/migrations/versions backend/app/finance/service.py backend/tests/test_finance/test_ledger.py
git commit -m "feat: rozdziel postingi kontowe i kategoryjne"
```

## Task 2: Semantyka kont pozabudżetowych i analizy kategorii

**Files:**
- Modify: `backend/app/finance/service.py:37-66,272-342`.
- Modify: `backend/app/finance/schemas.py:123-129`.
- Modify: `backend/app/finance/router.py:198-203`.
- Test: `backend/tests/test_finance/test_ledger.py`.

- [ ] **Step 1: Napisać failing test dla podsumowania z offbudget**

Utworzyć konto budżetowe `ING` i pozabudżetowe `Pożyczka`, następnie dwie transakcje wydatkowe o kwocie `10000`. Posting kategorii transakcji drugiego konta ma `is_budget_impact=False`. Sprawdzić:

```python
summary = await get_financial_summary(db_session, user_id)
assert summary.expense_total_pln == 10000
assert [account["name"] for account in summary.accounts] == ["ING"]
```

- [ ] **Step 2: Uruchomić RED**

```bash
cd backend && TEST_DATABASE_URL=postgresql+asyncpg://finanse:finanse@127.0.0.1:55432/finanse_test /opt/finanse/backend/.venv/bin/pytest tests/test_finance/test_ledger.py::test_summary_excludes_offbudget_account_and_category_impact -v
```

Expected: FAIL, ponieważ obecne summary wybiera wszystkie aktywne konta i liczy postingi bez flagi budżetowej.

- [ ] **Step 3: Wykluczyć konta informacyjne z analiz**

W `get_financial_summary` ograniczyć konta do:

```python
select(Account).where(
    Account.user_id == user_id,
    Account.is_active.is_(True),
    Account.is_budget_account.is_(True),
)
```

Przychody i wydatki liczyć z postingów kategorii (`Posting.category_id.is_not(None)`) z `Posting.is_budget_impact.is_(True)`, właściwym kierunkiem i zakresem dat. Nie opierać analizy kategorii na `Posting.account_id`, bo poprawione postingi kategorii nie mają konta.

- [ ] **Step 4: Dodać odpowiedź agregatów kategorii**

W schematach zdefiniować:

```python
class CategorySpendResponse(BaseModel):
    category_id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None
    total_pln: int

class CategorySummaryResponse(BaseModel):
    month: int
    year: int
    groups: list[CategorySpendResponse]
    categories: list[CategorySpendResponse]
```

`get_category_summary` pobiera category-only/budget-impact expense postings miesiąca, sumuje dzieci, a następnie dopisuje do rodzica sumę wszystkich bezpośrednich dzieci. Endpoint `GET /api/finance/category-summary` zwraca tę odpowiedź dla zalogowanego użytkownika.

- [ ] **Step 5: Napisać test agregacji „Transport → Paliwo”**

Utworzyć kategorię `Transport`, dziecko `Paliwo`, transakcję `5000`; sprawdzić `categories == [{"name": "Paliwo", "total_pln": 5000, ...}]` i `groups == [{"name": "Transport", "total_pln": 5000, ...}]`. Dodać offbudgetową transakcję `3000`, która nie zmienia obu wyników.

- [ ] **Step 6: Uruchomić GREEN**

```bash
cd backend && TEST_DATABASE_URL=postgresql+asyncpg://finanse:finanse@127.0.0.1:55432/finanse_test /opt/finanse/backend/.venv/bin/pytest tests/test_finance/test_ledger.py -v
```

Expected: wszystkie testy ledgeru PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/finance/service.py backend/app/finance/schemas.py backend/app/finance/router.py backend/tests/test_finance/test_ledger.py
git commit -m "feat: wyklucz konta pozabudżetowe z analiz"
```

## Task 3: Odtworzyć `offbudget` i grupy kategorii w parserze Actual

**Files:**
- Modify: `backend/app/finance/actual_parser.py:7-125,127-306`.
- Modify: `backend/tests/test_finance/test_actual_import.py:24-138,139-306`.

- [ ] **Step 1: Napisać failing test parsera konta informacyjnego**

Rozszerzyć istniejący fixture i oczekiwać:

```python
assert by_id["a1"]["is_budget_account"] is True
assert by_id["a2"]["is_budget_account"] is False
```

- [ ] **Step 2: Napisać failing test grup kategorii**

Na fixture `category_groups(g1, "Transport")` i `categories(c1, "Paliwo", 0, "g1", 0)` oczekiwać:

```python
groups = parser.get_category_groups()
categories = parser.get_categories()
assert groups == [{"actual_id": "g1", "name": "Transport", "type": "expense"}]
assert categories[0]["group_actual_id"] == "g1"
```

Typ grupy określić na podstawie dzieci: wyłącznie przychodowe → `income`, w pozostałych przypadkach → `expense`. Grupa bez aktywnych dzieci nie jest importowana.

- [ ] **Step 3: Uruchomić RED**

```bash
cd backend && /opt/finanse/backend/.venv/bin/pytest tests/test_finance/test_actual_import.py::TestActualParserAccounts tests/test_finance/test_actual_import.py::TestActualParserCategories -v
```

Expected: FAIL, ponieważ parser nie zwraca wymienionych pól ani grup.

- [ ] **Step 4: Rozszerzyć TypedDict i parser**

Zdefiniować `CategoryGroupDict`; `AccountDict` dostaje `is_budget_account: bool`, a `CategoryDict` dostaje `group_actual_id: str | None`. `get_accounts` mapuje `offbudget=0` na `True`, a `offbudget=1` na `False`. `get_category_groups` pobiera `category_groups` i wyłącznie aktywne dzieci, bez zależności od kolejności rekordów.

- [ ] **Step 5: Zachować rzeczywiste waluty transferów**

W `get_transfers` użyć `_get_account_currency_map()`. Pierwszy posting ma `source_amount=abs(amount źródłowy)` i walutę konta źródłowego; drugi `source_amount=abs(amount docelowy)` i walutę konta docelowego. Nie kopiować kwoty strony źródłowej na stronę docelową.

Test transferu PLN→USD ma sprawdzić obie kwoty i obie waluty.

- [ ] **Step 6: Uruchomić GREEN**

```bash
cd backend && /opt/finanse/backend/.venv/bin/pytest tests/test_finance/test_actual_import.py -v
```

Expected: parser tests PASS bez ruchu do PostgreSQL.

- [ ] **Step 7: Commit**

```bash
git add backend/app/finance/actual_parser.py backend/tests/test_finance/test_actual_import.py
git commit -m "feat: odtwórz konta i grupy kategorii Actual"
```

## Task 4: Poprawić importer oraz obsługę FX bez fałszowania sald

**Files:**
- Modify: `backend/scripts/migrate_actual.py:48-122,172-275,358-444`.
- Modify: `backend/app/finance/nbp_rates.py` only if a verified rate fallback helper is required; otherwise do not change it.
- Modify: `backend/tests/test_finance/test_actual_import.py`.

- [ ] **Step 1: Napisać failing test `build_pa_postings` dla wydatku**

Dla wydatku `Paliwo 5000 PLN` sprawdzić:

```python
assert postings[0].account_id == account_map["acc1"]
assert postings[0].category_id is None
assert postings[0].direction == "credit"
assert postings[1].account_id is None
assert postings[1].category_id == category_map["fuel"]
assert postings[1].direction == "debit"
assert sum(p.base_amount_pln if p.direction == "debit" else -p.base_amount_pln for p in postings) == 0
```

- [ ] **Step 2: Uruchomić RED**

```bash
cd backend && /opt/finanse/backend/.venv/bin/pytest tests/test_finance/test_actual_import.py::TestMigrationPostings::test_expense_uses_account_and_category_sides -v
```

Expected: FAIL, ponieważ aktualna implementacja przypisuje oba postingi do `acc1`.

- [ ] **Step 3: Zmienić `resolve_ids` na trzy mapowania**

Najpierw utworzyć `CategoryCreate` dla grup i zapisać `group_map`. Następnie tworzyć kategorie transakcyjne z:

```python
CategoryCreate(
    name=category["name"],
    type=category["type"],
    parent_id=group_map.get(category["group_actual_id"]),
)
```

Konta tworzyć z `is_budget_account=account["is_budget_account"]`.

- [ ] **Step 4: Utworzyć poprawne postingi zwykłej transakcji**

`build_pa_postings` ma tworzyć:

```python
PostingCreate(account_id=account_id, category_id=None, ..., direction=account_direction,
              is_budget_impact=is_budget_account)
PostingCreate(account_id=None, category_id=category_id, ..., direction=category_direction,
              is_budget_impact=is_budget_account)
```

Wymagać kategorii dla income/expense. Jeśli Actual rekord jej nie ma, dodać błąd do raportu i nie zapisywać transakcji; nie podstawiać pierwszej kategorii.

- [ ] **Step 5: Usunąć błędne opening balances z pełnego importu**

Usunąć wywołanie `create_opening_balances` z przepływu pełnej historii. Pozostawić osobną funkcję tylko dla przyszłego importu od daty granicznej, ale zmienić jej podpis na wymagający dedykowanego konta otwarcia i nie wywoływać jej w tym planie.

- [ ] **Step 6: Obsłużyć kursy i transfer międzywalutowy**

`build_pa_postings` ma przyjmować rzeczywistą kwotę i walutę każdego parser posting. Dla EUR/USD brak kursu `0.0` dodaje błąd `Missing FX rate: <currency> on <date>` i pomija całą transakcję; nie zapisuje `fx_rate=0`, `base_amount=source_amount` ani `nbp_error` jako akceptowanego wyniku.

Po obliczeniu bazowych kwot transferu:

```python
delta = debit_base_total - credit_base_total
```

gdy `delta != 0`, dodać category-only posting do kategorii `Różnice kursowe — strata` (debit dla ujemnego salda) albo `Różnice kursowe — zysk` (credit dla dodatniego salda), aby zachować zero. Utworzyć te dwie kategorie tylko, jeśli rzeczywiście wystąpią różnice. Ich `is_budget_impact` jest `False`, aby techniczna różnica kursowa nie zniekształcała budżetu transakcyjnego Actual.

- [ ] **Step 7: Dodać testy walutowe**

Pokryć:

1. EUR posting z NBP `4.2856` → właściwe `base_amount_pln`;
2. brak kursu USD → transakcja jest zgłoszona jako błąd i nie jest zapisana;
3. transfer USD→PLN z różnymi `source_amount` tworzy trzeci posting różnicy kursowej i signed PLN sumuje się do zero.

- [ ] **Step 8: Uruchomić GREEN**

```bash
cd backend && /opt/finanse/backend/.venv/bin/pytest tests/test_finance/test_actual_import.py tests/test_finance/test_ledger.py -v
```

Expected: wszystkie testy importu i ledgeru PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/scripts/migrate_actual.py backend/tests/test_finance/test_actual_import.py
git commit -m "fix: popraw księgowanie importu Actual"
```

## Task 5: Raport uzgodnieniowy i blokada importu nierozliczonych danych

**Files:**
- Create: `backend/app/finance/reconciliation.py`.
- Modify: `backend/scripts/migrate_actual.py`.
- Create: `backend/tests/test_finance/test_reconciliation.py`.

- [x] **Step 1: Napisać failing test różnicy salda**

W `test_reconciliation.py` utworzyć oczekiwane salda Actual:

```python
expected = {
    "actual-account-1": SourceBalance(
        actual_id="actual-account-1", name="ING", currency="PLN",
        is_budget_account=True, amount=109805,
    )
}
```

oraz rekord PA `109800`; sprawdzić `difference == 5` i `report.is_reconciled is False`.

- [x] **Step 2: Uruchomić RED**

```bash
cd backend && /opt/finanse/backend/.venv/bin/pytest tests/test_finance/test_reconciliation.py -v
```

Expected: FAIL, moduł nie istnieje.

- [x] **Step 3: Zaimplementować czysty model raportu**

Zdefiniować dataclasses `SourceBalance`, `AccountReconciliation`, `ReconciliationReport`. `reconcile_account_balances(expected, actual)` zwraca stabilnie posortowane wiersze i `is_reconciled=True` tylko, gdy dla każdego mapowanego konta różnica wynosi zero, waluta jest zgodna, a nie ma kont niezamapowanych.

- [x] **Step 4: Dodać ekstrakcję sald Actual i PA**

`ActualParser.get_account_balances()` sumuje aktywne nogi transakcji Actual per konto w walucie źródłowej. Funkcja importerowa `get_pa_source_balances(db, user_id, account_map)` sumuje `Posting.source_amount` ze znakiem direction wyłącznie dla postingów kontowych. Nie używać `base_amount_pln` do kryterium zgodności salda źródłowego.

- [x] **Step 5: Zapisać raport JSON i tekstowy**

`migrate_actual.py` po dry-run/import testowy zapisuje `reconciliation.json` i `reconciliation_report.txt` obok istniejącego raportu. Tekst zawiera wiersze:

```text
ING | PLN | budget | Actual 109805 | PA 109805 | diff 0 | OK
```

oraz listę braków kursowych, niezaimportowanych transakcji i różnic kategorii. Kod kończy się niezerowo w trybie `--require-reconciled`, jeśli `report.is_reconciled` jest fałszywe.

- [x] **Step 6: Dodać test blokady**

Sprawdzić, że raport z jedną różnicą powoduje wyjątek `ReconciliationError` przed wygenerowaniem komunikatu sukcesu; raport bez różnic przechodzi.

- [x] **Step 7: Uruchomić GREEN**

```bash
cd backend && /opt/finanse/backend/.venv/bin/pytest tests/test_finance/test_reconciliation.py -v
```

Expected: PASS dla zgodnego i rozbieżnego przypadku.

- [x] **Step 8: Commit**

```bash
git add backend/app/finance/reconciliation.py backend/scripts/migrate_actual.py backend/tests/test_finance/test_reconciliation.py
git commit -m "feat: dodaj raport uzgodnieniowy Actual"
```

## Task 6: Pokazać konta informacyjne i agregaty kategorii w UI

**Files:**
- Modify: `frontend/src/api/finance.ts`.
- Modify: `frontend/src/pages/Finances.tsx`.
- Create: `frontend/src/api/finance.test.ts`.

- [ ] **Step 1: Napisać failing test helperów widoku**

Wyeksportować z `api/finance.ts` czyste funkcje:

```typescript
export function splitAccounts(accounts: Account[]) {
  return {
    budget: accounts.filter((account) => account.is_budget_account),
    informational: accounts.filter((account) => !account.is_budget_account),
  };
}

export function buildCategoryTree(summary: CategorySummary): CategoryGroup[] { /* ... */ }
```

Test musi sprawdzić, że konto `false` nie trafia do `budget`, a `Transport` zawiera `Paliwo` z poprawną sumą.

- [ ] **Step 2: Uruchomić RED**

```bash
cd frontend && npm run test -- src/api/finance.test.ts
```

Expected: FAIL, helpery i typy nie istnieją.

- [ ] **Step 3: Dodać typy i hook**

`Account` dostaje `is_budget_account: boolean`; `CategorySummary` i `CategorySpend` odpowiadają backendowi. Dodać `useCategorySummary()` z kluczem `['finance', 'category-summary']` i endpointem `/finance/category-summary`.

- [ ] **Step 4: Renderować dwie sekcje kont**

`Finances.tsx` renderuje najpierw `Konta budżetowe`, potem — tylko gdy lista niepusta — `Pozabudżetowe / informacyjne` z etykietą „poza analizami”. Sekcja podsumowania używa wyłącznie backendowego summary; nie sumuje kont w frontendzie.

- [ ] **Step 5: Renderować wydatki według grup**

Pod kartami summary dodać listę grup: nazwa grupy i suma PLN, a pod nią dzieci z nazwą i sumą. Pusta odpowiedź pokazuje „Brak wydatków skategoryzowanych w tym miesiącu”. Nie wyświetlać danych offbudget, ponieważ backend już je filtruje.

- [ ] **Step 6: Uruchomić GREEN oraz build**

```bash
cd frontend && npm run test -- src/api/finance.test.ts
npm run lint
npm run typecheck
npm run build
```

Expected: PASS dla testu, lint, TypeScript i production build.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/finance.ts frontend/src/api/finance.test.ts frontend/src/pages/Finances.tsx
git commit -m "feat: pokaż konta pozabudżetowe i grupy kategorii"
```

## Task 7: Pełny import próbny do izolowanej bazy i raport

**Files:**
- No production data changes.
- Output outside repository: `/tmp/actual_migration/reconciliation_report.txt`, `/tmp/actual_migration/reconciliation.json`.
- Modify: `docs/CHANGELOG.md`, `docs/TASKS.md`, `docs/JOURNAL.md` po rzeczywistym wyniku.

- [ ] **Step 1: Przygotować testową bazę i zastosować migrację**

```bash
docker compose -f /docker/finanse/compose.test.yaml up -d --wait postgres-test
cd backend
DATABASE_URL=postgresql+asyncpg://finanse:finanse@127.0.0.1:55432/finanse_test /opt/finanse/backend/.venv/bin/alembic upgrade head
```

- [ ] **Step 2: Utworzyć wyłącznie testowego użytkownika**

W testowej bazie utworzyć użytkownika przez istniejący endpoint/repozytorium i zapisać jego UUID w zmiennej powłoki `TEST_USER_ID`; nie używać UUID użytkownika produkcyjnego.

- [ ] **Step 3: Uruchomić importer przeciwko testowej bazie**

```bash
DATABASE_URL=postgresql+asyncpg://finanse:finanse@127.0.0.1:55432/finanse_test \
/opt/finanse/backend/.venv/bin/python scripts/migrate_actual.py \
  --blob-path /docker/actualbudget/data/user-files/file-1bdc93e7-2c30-473e-b538-740a6b6021dc.blob \
  --user-id "$TEST_USER_ID" --execute --require-reconciled
```

Expected: importer either returns 0 with every saldo source difference equal to zero, or returns nonzero with a report naming every unresolved account/FX exception. It must never contact the production PA database.

- [ ] **Step 4: Niezależnie porównać salda SQL**

Wykonać read-only query per PA account:

```sql
SELECT a.name, a.currency,
       SUM(CASE WHEN p.direction = 'debit' THEN p.source_amount ELSE -p.source_amount END) AS source_balance
FROM accounts a
JOIN postings p ON p.account_id = a.id
GROUP BY a.name, a.currency
ORDER BY a.name;
```

Porównać z `reconciliation.json`; różnica większa od zero jest blokadą dla dalszych działań.

- [ ] **Step 5: Uruchomić pełną weryfikację kodu**

```bash
cd /opt/finanse
make lint
make typecheck
TEST_DATABASE_URL=postgresql+asyncpg://finanse:finanse@127.0.0.1:55432/finanse_test make test
```

Expected: wszystkie komendy kończą się kodem 0. W razie niedostępnego lokalnego venv użyć jawnej ścieżki `/opt/finanse/backend/.venv/bin` i zapisać faktyczny wynik.

- [ ] **Step 6: Zaktualizować dokumentację wyłącznie faktami**

`CHANGELOG.md`: nowe pola ledgeru, importer, raport i wynik dry-run. `TASKS.md`: zaznaczyć implementację oraz pozostawić korektę produkcji jako pending. `JOURNAL.md`: cel, raport różnic, decyzje FX, brak zmian w produkcji i następny krok.

- [ ] **Step 7: Zrobić końcowy commit dokumentacji**

```bash
git add docs/CHANGELOG.md docs/TASKS.md docs/JOURNAL.md
git commit -m "docs: opisz próbne uzgodnienie Actual"
```

## Kryteria ukończenia przed decyzją produkcyjną

- Testowy import nie tworzy postingów z tym samym kontem po obu stronach zwykłej transakcji.
- Raport per konto wykazuje `difference = 0` dla wszystkich sald źródłowych Actual.
- Każdy posting i transakcja spełnia double-entry invariant w PLN.
- Konta `offbudget` mają `is_budget_account=False` i nie wpływają na summary/category summary/Doradcę.
- Grupy kategorii i dzieci są widoczne przez API oraz UI.
- Brak kursu FX blokuje import zamiast fałszować wartość przez kurs 1.0.
- Produkcyjna baza `finanse` nie zmienia się w żadnym etapie tego planu.
