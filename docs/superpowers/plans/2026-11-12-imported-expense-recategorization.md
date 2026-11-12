# Imported Expense Recategorization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement task-by-task. Steps use checkbox syntax.

**Goal:** Odblokować jawną ręczną zmianę kategorii importowanych wydatków bez zmiany ich strony kontowej, kwot, dat i pochodzenia.

**Architecture:** Użyć istniejącego get-context → preview → confirm/apply i audytu kategoryzacji. Poszerzyć uprawnienie wyłącznie dla świadomej komendy użytkownika, nie wspólnej domyślnej kwalifikacji reguł/AI/paragonów. Nie usuwać ogólnego guarda źródła bez rozdzielenia tych ścieżek.

**Tech Stack:** FastAPI/Pydantic/SQLAlchemy/PostgreSQL; React18/TanStackQuery/TypeScript; pytest/vitest/Playwright.

**Spec:** Zatwierdzony opis w czacie (2026-11-12): ręczna zmiana kategorii importowanych wydatków; kwota, konto, daty i powiązania importu pozostają; audit i przeliczenie raportów kategorii, bez zmiany salda. Płatności pożyczek nadal chronione. To nie pełna edycja wszystkich pól. Implementacja lokalna; brak zgody na deploy tego zadania.

## Global Constraints

- Pracować w istniejącym linkedworktree; obecny HEAD a145088. Zachować unrelateddirtydocs/audity. main76fbebf ma dodatkowe wcześniejsze deploymentdocs.
- PLN, zaksięgowany dodatni wydatek, jedna strona kontowa, istniejąca zbilansowana księga; FX, przychody, transfery, zwroty i pożyczki poza tym slice.
- Własne aktywne docelowe kategorie expense; nie rozszerzać automatyzacji lub AI na historię.
- Strona kontowa w całości byte-equivalent/column-equivalent po operacji, także ID, kwoty, kierunek, currency/rate/budget/timestamps. Konto może być archiwalne historycznie, bez przywracania aktywności.
- Transaction ID/source/date/purchase-booking metadata i import mappings/evidence/receipts pozostają; updated_at i provenance/audit zmieniają się wyłącznie jako ślad ręcznej decyzji.
- Nie zmieniać źródłowych wyciągów, archiwów Actual, przypiętych historycznych manifestów lub istniejących receiptów. Replay importu nie nadpisuje ręcznej kategorii; ewentualny konflikt uzgodnienia ma być jawny, fail-closed.
- Preview/snapshot/version/owner/idempotency i loan/ledger-shape guards nadal obowiązują. Bez masowych aktualizacji, migracji lub produkcyjnych mutacji.

## Review Focus

1. Shared eligibility: przyznanie ręcznej edycji nie może pozwolić regułom/AI/paragonom zmieniać importów.
2. Imported/mapped historical accounts: account posting i saldo oraz import/evidence IDs nie zmieniają się, także archiwalne konto i wcześniejszy split.
3. Stale context: zmiana linku importu/pożyczki albo kategorii między preview/apply nie może ominąć blokady.
4. Replay importu: ręczna kategoria nie jest nadpisana ani duplikowana; uzgodnienie z archiwum może jawnie wykazać różnicę kategorii.
5. UI: stare allowed=false zamienia się na pełen preview/confirmation dla wspieranego importu; pożyczka/FX/refund nadal podają konkretną przyczynę zamiast obiecywać pełną edycję.

---

### Task 1: Ręczne uprawnienie i ochrona księgi/importów

**Files:**
- Modify `backend/app/finance/categorization_context.py`, `backend/app/finance/categorization.py`.
- Conditional modify `backend/app/finance/imports/provenance.py` lub `commit.py` wyłącznie jeśli istniejący replay modyfikuje poprawioną kategorię; nie przebudowywać importera.
- Tests `backend/tests/test_finance/test_imported_categorization.py`, istniejące `test_categorization.py`, `test_categorization_races.py`, `test_rule_events.py`, `test_proposals.py`, `test_receipt_payment.py`, `test_actual_incremental.py` i `test_bank_imports/`.

**Interfaces:**
- `LedgerContext.eligibility(*, allow_imported: bool = False) -> CategorizationEligibility`.
- `LedgerContext.response(*, allow_imported: bool = False) -> CategorizationContext`.
- `build_preview(ctx: LedgerContext, parts: list[CategorizationPart], *, allow_imported: bool = False) -> CategorizationPreview`.
- Tylko publiczne ręczne `get_categorization_context`, `preview_categorization`, `apply_categorization` wywołują je z True. Inni konsumenci pozostają na False. Kształt HTTP bez zmian.
- Allowlista źródeł manual/document_payment/actual/bank_import, własne mappings; loans nadal denied niezależnie od opcji. Nieznane źródło lub obcy mapping nigdy nie daje uprawnienia.

- [ ] **RED:** integration parametrized Actual+mapping i bank_import: contextallowed, preview/apply jednej nowej kategorii, audit/provenance manual, saldo takie samo, raport kategorii przeniesiony, accountposting exactcolumns i cały graph importów bez zmian. Expected: obecny protected denial.
- [ ] **RED:** pożyczka/nieznanysource/obcymapping/refund/FX pozostają denied; eligibility/defaultpreview przy allow_imported=False nadal denied na tym samym imporcie. Expected: nowe testy odblokowania FAIL, guardy bazowe PASS.
- [ ] **GREEN:** małe rozdzielenie ręcznej kwalifikacji przez keyword-only flag, bez zmiany default. Publiczna ręczna ścieżka używa flagi w każdym response/preview/apply; snapshot wiąże istniejące powiązania.
- [ ] **RED/GREEN:** stale link/version/category, równoległy preview/apply, idempotent retry, archived account i istniejący split; pożyczka dopięta po preview blokuje zapis. Oczekiwane409/deny bez częściowych zmian.
- [ ] **Replay test:** reimport/dedup/replay nie nadpisuje poprawionej kategorii i nie tworzy drugiej transakcji. Manifesty Actual i import receipts nie zmieniają się; jeśli pełne źródłowe uzgodnienie rozbieżne, błąd jawny bez zapisu. Expected: zachowana manualdecision lub jawny reconciliationconflict.
- [ ] Focused pytest, Ruff i mypy w zgodnym runnerze, pełny backend na własnych no-portPG z poprawną kolekcją conftest. Expected:0fail/error/skip, exactJUnitcaseunion i sourcehash. Nie używać istniejących testDB/prod.

### Task 2: Kontrakt UI, testy end-to-end i odbiór

**Files:**
- Tests `frontend/src/components/finance/TransactionCategorization.test.tsx`, `frontend/e2e/imported-categorization.spec.ts` (new).
- Conditional modify `frontend/src/components/finance/TransactionCategorizationDialog.tsx` wyłącznie dla jasnych komunikatów; nie przebudowywać formularza.
- Docs CHANGELOG/TASKS/JOURNAL plus własny raport audytu.

**Interfaces:** Istniejący endpoint kategoryzacji, `eligibility.allowed`, previewtoken i manualconfirm. Bez nowych pól do edycji kwoty/konta/dat, bez nowych permissionflag po stronie klienta.

- [ ] **RED/GREEN:** syntetyczny import z allowed=true otwiera obecne kategorie, wybór nowej pełnej ścieżki, preview/confirm; błędy409 zachowują formularz, disabledloan nadal czytelny. Jeśli UI już działa, zapisać to jako regressiontestexistingbehavior, nie twierdzić fałszywegoRED.
- [ ] Vitest całego frontendu, ESLint/tsc/build. Expected:PASS, istniejący bundlewarning odnotować.
- [ ] Playwright375/1440 z syntetycznym importem: zmiana kategorii, podgląd, świadomezatwierdzenie, refreshraportu; request nie zawiera kwoty konta/dat; loan nadal blocked. Expected:PASS/zero realAPI.
- [ ] Jeden niezależny review całości, ważne uwagi jednym TDDfixpass, dokumentacja i jawny localcommit po wszystkich bramkach. Expected:0Critical/Important; bez merge/push/deploy.

## Self-review

Cały zatwierdzony zakres pokryty Tasks1–2; identyczny kontrakt HTTP, zachowane granice automatyzacji i pożyczek. Trzy flagowane funkcje są wspólne dla kilku funkcji finansowych, dlatego default pozostaje restrykcyjny. Replay i immutableimportgraph są obowiązkowymi testami, a nie przypuszczeniem wynikającym ze zmiany jednego ifa. Brak zgody na pełną edycję lub automatyczne poprawianie istniejących danych.
