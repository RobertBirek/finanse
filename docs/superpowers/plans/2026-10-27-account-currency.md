# Account Currency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bezpieczna widoczność/edycja PLN/EUR/USD kont bez historii.
**Architecture:** Capability odczytowa z księgi i powiązań, ponowny guard w serwisie
mutacji, współdzielone blokady account rows w ścieżkach walidacji transakcji i planów.
**Tech Stack:** FastAPI/Pydantic/SQLAlchemy/PostgreSQL, React/TypeScript/TanStack Query.
**Spec:** `docs/superpowers/specs/2026-10-27-account-currency-design.md`.

## Global Constraints

- Bez migracji schematu, deployu, importu, korekt księgi i zmian danych produkcji.
- Waluty PLN/EUR/USD; saldo zero nie dowodzi braku historii.
- Pełny gate przed commitem, niezależne review na końcu.

## Review Focus

- Pierwszy posting równolegle ze zmianą waluty: brak rozjazdu waluty konta/postingu.
- Pending/zerowe saldo/import/nieaktywny harmonogram nie obchodzą blokady.
- Brak capability na starym API nie odblokowuje edycji.
- Konflikt PATCH nie zmienia innych pól; ownership sprawdzony.
- Odczyt list/detail ma zgodne capability bez dodatkowego SELECT per konto.

### Task 1: Backend walidacja i capability

**Files:** `backend/app/finance/{schemas,entities,models,queries,router,ledger_validation,cashflow}.py`;
test `backend/tests/test_finance/test_account_currency.py`.
**Interfaces:** AccountResponse `can_change_currency: bool`; AccountUpdate `currency: str | None`
(omitted dozwolone, explicit null zabronione); istniejące service signatures bez zmian.

- [x] RED: testy PATCH pustego konta EUR, PLN/USD, lowercase, niepoprawne/null,
  owner404, history409 i atomic metadata, idempotentna waluta; capability list/detail.
- [x] RED: testy posting/pending/zero-balance, schedule inactive, Actual mapping/source.
- [x] GREEN: rozszerzyć schemas i computed property/query, guard przed przypisaniem pól,
  row-lock i poprawny router409. Współdzielone blokady walidacji uporządkowane po account.id.
- [x] Testy konkurencji w izolowanej bazie: zmiana waluty vs pierwszy posting/plan.
- [x] Weryfikacja targeted pytest (25 PASS) i Ruff (pełny gate w Task 3).

### Task 2: UI edycji kont

**Files:** `frontend/src/api/finance.ts`, `frontend/src/components/finance/AccountSettingsRow.tsx`
i jego `.test.tsx`, `frontend/src/pages/FinanceAccounts.test.tsx`.
**Interfaces:** optional capability dla zgodności starych fixtures, brak/false blokuje select;
AccountUpdateInput `currency?: string`.

- [x] RED: aktywny select ma EUR/USD/PLN i wysyła tylko zmienioną walutę.
- [x] RED: false/brak capability blokuje select, nazwa nadal edytowalna, komunikat błędu409.
- [x] GREEN: select z etykietą i opisem, draft inicjalizowany przy rozpoczęciu edycji.
- [x] Weryfikacja targeted Vitest (31 PASS) oraz pełny Vitest (235 PASS).

### Task 3: Gate, E2E i review

**Files:** `frontend/e2e/account-currency.spec.ts`, CHANGELOG/TASKS/JOURNAL.
**Interfaces:** exact-build fixtures, wyłącznie fikcyjne PATCH obsługiwane w teście.

- [x] E2E: edycja EUR→USD na pustym koncie, zablokowane historyczne konto,
  nazwa pozostaje edytowalna, błąd409 przy wyścigu nie zamyka edycji.
- [x] Pełne pytest812 PASS (lokalna finanse_test), Ruff/mypy, Vitest235/ESLint/tsc/build/E2E47+1skip.
- [x] Świeże read-only review całej gałęzi bez blokad; poprawiono setup testu
  inactive_schedule, aby naprawdę dezaktywował harmonogram przez serwis.
- [x] Aktualizacja trzech dokumentów i commit bez merge/push/deployu.

## Progress ledger

- Baseline: 21 backend account/query i 26 frontend account tests PASS.
- Pre-flight: Task2 konsumuje capability Task1; fail-closed przy braku pola.
- Wykonanie natywne w istniejącym worktree, gałąź `feat/account-currency` od11a625d.
- Slices Q7 i następne pozostają kolejnymi iteracjami, bez zmiany ich danych.
- E2E pierwszy run: 43 PASS / 4 FAIL — selektor `.last()` trafiał w formularz
  tworzenia zamiast edycji. Zastąpiono jednoznacznym ID kontrolki edycji; bez zmian produktu.
- Pierwszy pełny pytest przekroczył limit narzędzia240s bez zgłoszonych FAIL;
  powtórzono bez timeoutu. Pierwszy dodatkowy mypy uruchomiony z root zamiast backend
  nie rozwiązał importów app; gate ponawiany z właściwego katalogu, bez zmian konfiguracji.
- Mypy wskazał brak zadeklarowanego backing pola capability w konstruktorze;
  dodano typowany setter właściwości (bez mapowanej kolumny), odczyty i konstruktor
  używają tej właściwości. Mypy65/Ruff PASS; targeted backend do ponowienia po suite.
- Końcowe ponowienie targeted25 po setterze PASS; pełna suite812 PASS z2 znanymi
  warningami i8 proxy deselected. Review bez blokad; Q7 następny, bez zmiany historii.
