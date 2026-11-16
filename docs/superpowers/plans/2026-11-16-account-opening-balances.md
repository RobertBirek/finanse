# Account Opening Balances Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** BO dla każdego konta, podpisana kwota przy tworzeniu, edycja tylko bez innych transakcji i zerowa inicjalizacja istniejących kont bez zmiany sald.

**Architecture:** Dedykowany rekord BO wskazuje opcjonalną dwustronną transakcję; księga pozostaje jedynym źródłem niezerowej kwoty. Komenda z blokadami, wersją, idempotencją i audytem nie rozszerza zwykłych uprawnień do transakcji. Addytywna migracja tworzy wyłącznie zerowe rekordy dla istniejących kont.

**Tech Stack:** FastAPI, SQLAlchemy async, PostgreSQL 16, Alembic, React, TypeScript, TanStack Query, pytest, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-11-16-account-opening-balances-design.md` — wymagania i decyzje wykonawcze zatwierdzone w czacie; wykonanie Native.

**Wynik:** lokalnie zweryfikowane. Backend2632PASS, frontend707PASS, E2E205PASS/1expectedskip.
Raport i odstępstwa: `docs/audits/2026-11-16-account-opening-balances-local.md`.
Bez merge/push/deploy i bez produkcyjnego backfillu.

## Global Constraints

- Kwoty: BIGINT w najmniejszej jednostce; API signed integer w zakresie ±9007199254740991, bool/float niedozwolone.
- Każda transakcja BO: dokładnie 2 postings, suma debit+ / credit− = 0.
- Nie resetować sald ani nie rozpoznawać dawnych BO po opisie. Istniejące postings pozostają identyczne.
- Zero nie tworzy transakcji; każde konto ma rekord BO. Data nowych: `_local_today()`, starych: `opened_at`.
- BO nie jest przychodem/wydatkiem; brak automatyzacji, AI i nowych zewnętrznych integracji.
- Bez nowych zależności, produkcyjnej migracji, wdrożenia, fetch/merge/push bez osobnej decyzji.
- Polecenia `/test`, `/lint`, `/typecheck`, `/migration` zgodnie z projektem; gdy interfejs ich nie udostępnia, odczytać `.opencode/command/` i użyć równoważnego izolowanego runnera, dokumentując odstępstwo. Nie używać produkcyjnej bazy.

## Review Focus

- Konto o zerowym saldzie po kompensujących się transakcjach nadal blokuje edycję BO — Task 2.
- Równoczesny zapis BO i pierwszej transakcji ma wynik odpowiadający kolejności blokad, nigdy ominięcie warunku — Task 2.
- Brak uprawnień przez zwykłe API, spoofing `source`, alokacje dokumentów i linki osób/kredytów — Task 2.
- Zerowy backfill nie zmienia żadnej starej kwoty/wiersza; obejmuje stare PLN/EUR/USD, karty, konta nieaktywne — Task 1.
- Utrata odpowiedzi, zmiana konta/sesji i HTTP409 nie mogą powtórnie naliczać BO — Tasks 2–3.

## Przygotowanie wykonania

- [x] Utworzyć osobny worktree przez `using-git-worktrees`, bez zmiany istniejących worktree/klonów.
  Odczyt 2026-11-16: lokalny `main=593a232`, lokalny `origin/main=c960d9c`
  (13 commitów nowszy; diff finansowych plików opisanych w planie pusty).
  Wybrać zatwierdzoną bazę, przeczytać jej AGENTS/CHANGELOG/TASKS/JOURNAL.
- [x] Potwierdzić działający bezpieczny runner oraz baseline. Nie aktualizować sharedvenv,
  nie używać zachowanego prywatnego klonu certyfikacyjnego. Jeśli brak własnej dopuszczonej
  testowej bazy, uzyskać zgodę na własny PostgreSQL bez portów zamiast omijać safety guard.

### Task 1: Rekord BO i retencyjna migracja

**Files:**
- Create: `backend/app/finance/opening_balance_models.py`
- Modify: `backend/app/finance/models.py` (rejestracja metadanych)
- Create: `backend/migrations/versions/<generated>_account_opening_balances.py`
- Test: `backend/tests/test_finance/test_opening_balance_models.py`, `test_opening_balance_migration.py`

**Interfaces:**
- Produces: `AccountOpeningBalance` z `user_id`, unikalnym `account_id`, `opening_date`,
  `version >= 1`, nullable unikalnym `transaction_id`, owner-safe złożonymi FK do konta/transakcji.
- Produces: częściowy unikalny indeks kategorii technicznej `(user_id) WHERE source='opening_balance'`.
  Kategoria tworzona leniwie przez Task 2, nie przez backfill.

- [x] **Step 1: Write failing model/migration tests.**
  `test_opening_balance_owner_and_uniqueness`: drugie BO konta i link do obcej transakcji
  odrzucone; rollback nie usuwa prawidłowego BO.
  `test_opening_backfill_preserves_history`: seed kont wszystkich typów/walut,
  aktywne/nieaktywne, historyczne postings i istniejące opisy `[BO]`; po realnym
  Alembic UP dokładnie jeden zerowy rekord na konto, data=`opened_at`,
  `transaction_id=None`, stare wiersze i oba salda identyczne.
- [x] **Step 2: Run targeted tests**, oczekiwany RED z braku modeli/migracji, nie z konfiguracji DB.
- [x] **Step 3: Implement models; generate `/migration "account opening balances"`** wyłącznie
  na własnej bazie. Migracja backfilluje rekordy BO przez INSERT SELECT, bez transakcji,
  kategorii technicznej lub modyfikacji starych tabel poza nowym indeksem.
  Downgrade odmawia usunięcia zapisanych niezerowych BO; żadnych destrukcyjnych prób
  na bazie użytkownika. Rejestracja modelu musi działać także w CLI Alembic.
- [x] **Step 4: Run tests to GREEN**; sprawdzić wygenerowany SQL, brak obcego driftu schematu.
- [x] **Step 5: Commit** `feat: dodaj model i zerową inicjalizację bilansów otwarcia`
  dopiero po lint/typecheck/test gate dotyczących zadania.

### Task 2: Księgowanie, odczyt, edycja i serwerowe blokady BO

**Files:**
- Create: `backend/app/finance/opening_balances.py`, `opening_balance_schemas.py`, `opening_balance_guards.py`
- Modify: `backend/app/finance/entities.py`, `queries.py`, `schemas.py`, `router.py`, `transactions.py`
- Modify: `backend/app/finance/ledger_validation.py`, `transaction_dates.py`, `categorization.py`,
  `bill_payments.py`, `people.py`, `loans.py` (tylko wejścia potrzebne do strażników)
- Test: `backend/tests/test_finance/test_opening_balances.py`,
  `test_opening_balance_api.py`, `test_opening_balance_races.py`, `test_opening_balance_guards.py`

**Interfaces:**
- Consumes: model z Task 1, `lock_document_mutations`, `lock_accounts(..., exclusive=True)`,
  `FinanceCommandReceipt`, `app.audit.service.log_event`, istniejące serwisy odczytu sald.
- Produces: `OpeningBalanceInput(amount_minor: int = 0, date: date | None = None,
  fx_rate: Decimal | None = None)` jako `AccountCreate.opening_balance`.
- Produces: `OpeningBalanceView(amount_minor: int, date: date, fx_rate: Decimal | None,
  version: int, can_edit: bool, blocked_reason: str | None)` jako `AccountResponse.opening_balance`.
- Produces: `OpeningBalanceUpdate(amount_minor: int, date: date, fx_rate: Decimal | None,
  expected_version: int)` i `PUT /accounts/{account_id}/opening-balance` z `Idempotency-Key`.
- Produces: `initialize_opening_balance(db: AsyncSession, owner: UUID, account: Account,
  data: OpeningBalanceInput) -> None`; `update_opening_balance(db: AsyncSession,
  owner: UUID, account_id: UUID, data: OpeningBalanceUpdate,
  idempotency_key: str) -> OpeningBalanceView`.
- Produces: `guard_opening_balance_transaction(db: AsyncSession, owner: UUID,
  transaction_id: UUID) -> None`; rozpoznaje rzeczywisty link BO, nie opis klienta.
- Wewnętrzna transakcja `type/source=opening_balance` nie jest dodawana do dozwolonych
  `TransactionCreate.type`; tylko serwis BO konstruuje dokładny kształt.

- [x] **Step 1: Write failing financial/API tests.**
  Parametry `125050`, `-125050`, `0`: saldo źródłowe równe BO, PLN zgodny z kursem,
  signed suma=0, dokładnie 2 postings dla nonzero / 0 dla zero, income/expense/budget
  bez zmian. Dla EUR/USD kurs `4.123456`, oba znaki i HALF_EVEN; brak kursu nonzero
  odrzucony, 0 bez kursu dozwolone; odrzucić nonfinite, >6 decimals i overflow wyceny.
  Tworzenie konta/karty i BO jest atomowe, zwraca od razu poprawne saldo.
  Wszystkie domenowe ścieżki tworzenia konta, także importer Actual, tworzą BO=0
  domyślnie bez nowej transakcji i bez ingerencji w importowaną historię.
- [x] **Step 2: Run targeted financial tests to confirmed RED.**
- [x] **Step 3: Implement initialization/reads/command.**
  Dodatnie BO: credit konta / debit kategorii; ujemne odwrotnie.
  Techniczna kategoria typu transfer `source=opening_balance`, bez wybieralności,
  zwykłej edycji/usunięcia i bez ręcznego użycia nawet przez znane ID.
  Publiczne `AccountUpdate` nie akceptuje BO (nie może milcząco zignorować tej próby).
  Komenda: owner lock → exclusive account lock → świeży warunek braku innych postings
  → version → atomowy ledger+rekord+audit+receipt. Identyczny retry odtwarza wynik,
  zmieniony payload z tym samym kluczem daje409; GET nie zapisuje niczego.
  Niezmienione BO również podlega blokadzie historii; stary version daje409.
  Wersjonowane zerowanie usuwa wyłącznie dedykowany własny BO po weryfikacji kształtu.
  Nie dodawać BO do publicznego `AccountUpdate`; dedykowany endpoint jest jedyną edycją.
- [x] **Step 4: Write failing guard/race tests.**
  `test_pending_and_net_zero_history_block_edit`: oczekująca albo kompensujące transakcje blokują.
  `test_only_linked_opening_is_excluded`: podobny opis/source/type nie omija warunku.
  `test_first_posting_races_opening_edit`: dwa rzeczywiste połączenia DB, oba porządki;
  po pierwszej transakcji BO409; gdy BO pierwsze, transakcja dopiero potem.
  `test_other_owner_cannot_read_or_mutate_opening`:404, zero zmian.
  `test_opening_cannot_use_other_mutation_paths`: PATCH/DELETE/date editor,
  kategoryzacja, dokument, darowizna, spłata i techniczna kategoria odrzucone bez zmian.
  `test_zero_opening_allows_empty_account_delete_and_currency_rules`: brak regresji;
  nonzero blokuje zmianę waluty; nowa waluta przy zerowym BO nie zostawia starej wyceny.
- [x] **Step 5: Confirm RED, add guards and run GREEN.**
  Zachować wspólny porządek blokad; nie wykonywać N+1 odczytów BO.
  Domyślny przepływ zwykłych/AI/importowanych transakcji nie dostaje uprawnień BO.
  Dodać regresje sald kart i prognozy, starych importów Actual i kont archiwalnych.
- [x] **Step 6: Run backend lint/types/tests**, commit
  `feat: księguj i chroń edycję bilansu otwarcia konta`.

### Task 3: Formularze, czytelny BO i odbiór całości

**Files:**
- Create: `frontend/src/components/finance/OpeningBalanceFields.tsx`,
  `frontend/src/api/openingBalances.ts`
- Modify: `frontend/src/api/finance.ts`, `frontend/src/pages/FinanceAccounts.tsx`,
  `frontend/src/components/finance/AccountSettingsRow.tsx`,
  `AccountTransactions.tsx`, `TransactionDetail.tsx`
- Test: `frontend/src/components/finance/OpeningBalanceFields.test.tsx`,
  `frontend/src/pages/FinanceAccounts.test.tsx`,
  `frontend/src/components/finance/AccountSettingsRow.test.tsx`,
  `frontend/e2e/opening-balances.spec.ts`
- Modify: `docs/CHANGELOG.md`, `docs/TASKS.md`, `docs/JOURNAL.md`

**Interfaces:**
- Consumes: DTO/API Task 2; frontend `Account.opening_balance`,
  `useUpdateOpeningBalance()` z kluczem cache uwzględniającym właściciela.
- Produces: signed kwota + data, warunkowy kurs EUR/USD nonzero; czyste pola tekstowe
  parsowane do groszy bez mnożenia IEEE754 i bez cichego zaokrąglania.

- [x] **Step 1: Write failing UI tests.**
  Kwoty `123,45`, `-123,45`, `0`, puste→0; data domyślna lokalna;
  `1,234` odrzucone, bezwzględne limity/APIprecision sprawdzone.
  Formularz tworzenia przesyła jeden request konto+BO.
  Istniejące konto pokazuje0 niezależnie od rzeczywistego salda.
  Edytor BO jest dostępny tylko dla `can_edit=true`; po transakcji pokazuje przyczynę.
  Zapis BO ma własną akcję, nie zapisuje niepowiązanych draftów danych konta/karty.
  W409 odświeżenie i ponowna zgoda; błąd sieci zachowuje key, zmiana sesji/konta
  blokuje starego handlera; sukces odświeża konta/salda/raporty/prognozę/karty.
- [x] **Step 2: Run relevant Vitest tests to confirmed RED.**
- [x] **Step 3: Implement fields, hook and editors** zgodnie z istniejącym Tailwind/UI.
  BO=0 jest trwałym stanem, nie brakiem danych. `opening_balance` w odczytanej
  transakcji jest wyświetlany jako „Bilans otwarcia”, nie „Transfer” lub „Przychód”;
  bez zwykłego przycisku usunięcia/edycji, z odnośnikiem do BO konta.
- [x] **Step 4: Run UI tests to GREEN; Playwright375/1440**:
  nowa karta z ujemnym BO, zwykłe konto z dodatnim, zero, edycja i409.
  Obejrzeć screenshoty, sprawdzić brak overflow i dostępność etykiet/klawiatury.
- [x] **Step 5: Full verification** `/lint`, `/typecheck`, `/test`, frontend build,
  dotknięte E2E i test realnej migracji/retencji; nie deklarować PASS ze starego zestawu.
  Jeden świeży niezależny review całości; uwagi odtwarzać testem przed poprawką.
  Zachować wyniki, source hashes i jawne ograniczenia środowiska.
- [x] **Step 6: Update docs and commit**
  `feat: dodaj formularze bilansu otwarcia i bezpieczną edycję`.
  Status „lokalnie zweryfikowane” dopiero po wynikach; osobna zgoda na merge/push/deploy
  i produkcyjny backfill. Sprzątać tylko własne zasoby testowe po kontroli tożsamości.

## Self-review planu

- Wymagania rozmowy mają pokrycie: znaki/zero/data/tworzenie Task2–3, edycja i blokady
  Task2–3, wszystkie istniejące konta bez zmiany sald Task1.
- Nie ma drugiej kopii kwoty BO ani zerowej transakcji obchodzącej walidację postings.
- Pięć Review Focus ma przypisane konkretne przypadki testowe.
- Decyzje wykonawcze (techniczna kategoria, ręczny FX, date starych BO, nullable link)
  są jawne i nie są przedstawiane jako wcześniejsze wypowiedzi użytkownika.
- Plan nie upoważnia do uruchomienia produkcyjnej migracji lub backfillu.
