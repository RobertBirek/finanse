# Tasks

Backlog zadań ze statusami.

Statusy: `[ ]` pending, `[~]` in progress, `[x]` done, `[-]` cancelled

---

## Task 5 — Security Baseline: limity i audyt za reverse proxy (2026-08-20)

- [x] npmplus przekazuje łańcuch wyłącznie do Nginx frontendu, który normalizuje
  go do jednego adresu; backend przyjmuje tylko ścisły literal IP od zaufanego
  kontenera frontend, a łańcuch/spoof wraca do peera.
- [x] Limity loginu, Advisora i uploadu są zależnościami FastAPI; odrzucenia 429
  zapisują niezależny, zredagowany event audytu.
- [x] Backend jest wyłącznie na `internal`; frontend jest jedynym serwisem na
  dedykowanych `finanse_ingress` i `internal`; npmplus ma tam stałe `172.24.0.2`.
  Zweryfikowano konfigurację Compose bez deployu; runtime czeka na Task 7.

---

## Task 1 -- Security Baseline: backup i weryfikacja odtworzenia (2026-08-19)

- [x] Wersjonowane skrypty Restic wykonują prywatny snapshot PostgreSQL i uploads
  z manifestem SHA-256, tagami oraz retencją 7/4/6.
- [x] Izolowana weryfikacja odtworzenia wymaga loopbackowego DSN do bazy
  `_restore`/`_test`, weryfikuje checksumy przed ekstrakcją lub `pg_restore`,
  uruchamia migracje i kontrolę invariantów księgi.
- [x] Dokumentacja operacyjna, targety Makefile oraz statyczne testy zostały
  dodane; nie skonfigurowano credentiali i nie uruchomiono backupu produkcyjnego.

---

## Task 17 — Ukrywanie nieaktywnych kont i kategorii (2026-08-19)

- [x] Formularze transakcji, schedulera i budżetów pokazują wyłącznie aktywne
  encje, zachowując filtrowanie typu i ograniczenie kont schedulera do PLN.
- [x] Dashboard finansów i nawigacja transakcji ukrywają nieaktywne konta;
  wybrane wcześniej konto nie jest usuwane z istniejącego widoku.
- [x] `FinanceAccounts` i API pozostawiono bez zmian.
- [x] Quality gate: frontend `106 passed`, lint/typecheck/build PASS.

## Task 16 — Usuwanie i dezaktywacja kont i kategorii (2026-08-17)

- [x] Model: `categories.is_active` (Boolean NOT NULL, default true) + migracja `1dbfe88dfb1b` (upgrade/downgrade zweryfikowane na izolowanej bazie).
- [x] Serwis: `delete_account`/`delete_category` (blokada przy powiązanych rekordach, ValueError z sugestią dezaktywacji), odrzucanie nieaktywnych kont/kategorii w transakcjach, budżetach i schedulerze.
- [x] API: `DELETE /accounts/{id}` i `DELETE /categories/{id}` (204/404/409) oraz `is_active` w `PATCH /categories/{id}`.
- [x] Frontend: hooki tworzenia/edycji/usuwania, strona `/finances/accounts` i
  link „Konta” w sidebarze; nieaktywne encje są wygaszone, a pełna lista
  pozostaje dostępna tylko na stronie zarządzania.
- [x] Quality gate: `make test` — backend `126 passed, 109 skipped`, frontend
  `106 passed`; `make test-integration` — `109 passed`; lint/typecheck/build PASS.
- [x] Produkcja: migracja `1dbfe88dfb1b`, deploy backendu/frontendu/workera i
  smoke test `GET /api/health` (HTTP 200).

## Task 15 — Budżety w prognozie płynności (2026-08-15)

- [x] Backend: `CashflowBudgetSummary` + pole `budgets` w prognozie (z `get_budget_status`).
- [x] Frontend: karta „Budżety w tym miesiącu" + ostrzeżenie o przekroczeniu płynności.
- [x] Quality gate: backend `91 integracyjnych`, frontend `80 passed`, lint/typecheck/build PASS.

## Task 14 — Przewalutowanie PLN↔EUR/USD (2026-08-15)

- [x] Backend: `create_exchange_transaction` (walidacja kont/walut, kurs NBP lub ręczny, suma zero) + `POST /transactions/exchange`.
- [x] Frontend: hook `useCreateExchange` i typ „Przewalutowanie" w formularzu (dwa konta, opcjonalny kurs).
- [x] Quality gate: backend `89 integracyjnych`, frontend `76 passed`, lint/typecheck/build PASS.

## Task 13 — Edycja i usuwanie transakcji (2026-08-15)

- [x] Backend: `delete_transaction` (kaskada postingów) + `DELETE /transactions/{id}` (204/404).
- [x] Frontend: hooki `useUpdateTransaction`/`useDeleteTransaction` + `invalidateFinanceLedger`.
- [x] Frontend: edycja inline opisu/daty i usuwanie z potwierdzeniem w liście transakcji.
- [x] Quality gate: backend `128 unit + 81 integracyjnych`, frontend `70 passed`, lint/typecheck/build PASS.

## Task 12 — Ręczne księgowanie transakcji (2026-08-15)

- [x] Frontend: helper `buildTransactionPostings` (konwencja `balance = credit − debit` dla przychodu/wydatku/transferu).
- [x] Frontend: formularz `TransactionForm` (typ, konto PLN, kategoria filtrowana, kwota, data, opis; walidacja i błąd inline).
- [x] Frontend: integracja na `/finances/transactions` + naprawa `transaction_date` w `useCreateTransaction`.
- [x] Quality gate: frontend `63 passed`, backend bez zmian (`125 unit + 79 integracyjnych`), lint/typecheck/build PASS.

## Task 11 — Miesięczne budżety z limitami (2026-08-15)

- [x] Backend: model `CategoryBudget` (limit > 0, unikalny per użytkownik+kategoria) + migracja `4340d1460982`.
- [x] Backend: serwis CRUD z walidacją własności i typu `expense`; `get_budget_status` z roll-upem potomków i zerowymi wydatkami.
- [x] Backend: endpointy `GET/POST /budgets`, `PATCH/DELETE /budgets/{id}`, `GET /budget-status`; duplikat → 422.
- [x] Frontend: hooki budżetów + `budgetProgress`; strona `/finances/budgets` z listą, edycją inline, dodawaniem, usuwaniem i sekcją bez budżetu.
- [x] Quality gate: backend `125 unit + 79 integracyjnych`, frontend `55 passed`, lint/typecheck/build PASS.

## Task 10 — Podstrony finansowe i zarządzanie płynnością (2026-08-15)

- [x] Backend: parametryzowane okresowo raporty `summary` i `category-summary` (`month`/`year`).
- [x] Backend: `DELETE /cashflow/items/{id}` oraz `POST /cashflow/items/{id}/confirm` — potwierdzenie tworzy zbilansowaną transakcję tylko dla `due`/`overdue`, odrzuca non-PLN/przyszłe/niepewne/zdublowane, blokada wiersza chroni przed podwójnym księgowaniem.
- [x] Frontend: typowane hooki ustawień, mutacji schedulera, potwierdzenia i parametrowanych raportów; centralna invalidacja cache.
- [x] Frontend: trasy `/finances`, `/finances/transactions`, `/finances/cashflow`, `/finances/budgets`, `/finances/reports` + realne linki sidebara.
- [x] Frontend: strona cashflow z formularzami ustawień/schedulera, prognozą, listą pozycji i dialogiem potwierdzenia sugestii.
- [x] Quality gate: backend `123 unit + 61 integracyjnych`, frontend `41 passed`, lint/typecheck/build PASS.

## Task 9 — Finalny przegląd: znak, invalidacja, non-PLN (2026-08-15)

- [x] Poprawiono znak transakcji per konto: income → posting `credit` (zielony „+"), expense → `debit` (czerwony „−").
- [x] Zweryfikowano i udokumentowano testem zakres invalidacji cashflow: prefiks `["finance","accounts"]` obejmuje transakcje per-konto (TanStack Query v5, prefix-match).
- [x] Ograniczono selektor konta schedulera do aktywnych kont budżetowych w PLN i zablokowano walutę na „PLN".
- [x] Quality gate frontendu: Vitest `41 passed`, ESLint, TypeScript typecheck i Vite production build.

---

## Task 6 — Spłata długu jakościowego (2026-08-12)

- [x] Przejrzano 27 commitów z zakresu `f90a4d6..ab344ad` oraz aktualną dokumentację; wcześniejszy zapis o 17 commitach był nieaktualny.
- [x] Uruchomiono izolowaną testową bazę PostgreSQL bez dotykania produkcji.
- [x] Backend: Ruff `app/ tests/` i mypy `app/` przechodzą; pytest `89 passed, 23 skipped, 5 warnings` przy niedostępnej bazie lokalnej.
- [x] Testy integracyjne: świeże uruchomienie `23 passed, 89 deselected, 11 warnings` na izolowanym PostgreSQL.
- [x] Frontend: ESLint, Vitest `4 passed`, TypeScript typecheck i Vite production build.
- [x] Dodano testy pętli tool-calling, atomiczności/rollbacku potwierdzeń oraz bezpiecznej walidacji mutacji finansowych.
- [x] Doradca odświeża oczekujące potwierdzenia pollingiem co 2 sekundy; harmonogram używa lokalnych granic dnia i offsetu DST dla konkretnej daty.
- [x] Przywrócono lokalną datę transakcji (`7cc1973`): brak jawnej daty używa bieżącego dnia użytkownika, nie dnia UTC.
- [x] Zapisano dokładne wyniki i ograniczenia w CHANGELOG/JOURNAL; porządkowe zmiany `backend/migrations/` przywrócono do `f90a4d6` bez zmiany schematu.
- [x] Frontend lint: dodano konfigurację ESLint i usunięto 7 błędów wykrytych w kodzie.
- [x] Frontend auth: rozróżniono sesję uwierzytelnioną, nieuwierzytelnioną i niedostępny backend; błędy 5xx/sieci nie czyszczą znanego użytkownika, a widok awarii udostępnia ponowienie.
- [x] Frontend auth: 401 zachowuje wyłącznie lokalny `returnTo`; logowanie waliduje powrót i odrzuca adresy zewnętrzne. Vitest `122 passed`, ESLint, TypeScript i Vite build przeszły; bez deployu.

Pozostały ostrzeżenia zależności/testów, ograniczenie streamingu bez SSE, trzy daty USD bez kursu NBP oraz brak rzeczywistych danych split transactions w testach. Nie wykonano deployu ani migracji produkcyjnej.

## Iteracja 1 — Pierwszy Vertical Slice (MVP)

### Inbox → Task
- [x] Backend: endpoint `POST /api/inbox/{id}/process` — tworzy task z inbox_item
- [x] Frontend: Inbox page ładuje listę inbox_items z API
- [x] Frontend: przycisk "Utwórz zadanie" tworzy task i oznacza inbox_item jako processed
- [x] Frontend: pokaż historię (processed items)
- [x] E2E: Playwright test — wpisz w Inbox → utwórz zadanie → task w API

### Dzisiaj z live danymi
- [x] Frontend: Today ładuje taski z API (status=todo,in_progress)
- [x] Frontend: Today ładuje time_blocki z API (start_time/end_time)
- [x] Frontend: Today ładuje financial_summary z API
- [x] Backend: comma-separated status filter (status=todo,in_progress)
- [x] E2E: tasks from Inbox visible on Today with 'Inbox' badge

### Finanse CRUD
- [x] Frontend: Finances page ładuje listę kont z saldami z API
- [x] Frontend: formularz tworzenia konta (nazwa, typ, waluta)
- [x] Frontend: lista transakcji z API
- [x] Frontend: formularz transakcji
- [x] Backend: balance_pln computed from postings per account

### Doradca
- [x] Backend: integracja DeepSeek API (v4-pro)
- [x] Backend: chat endpoint POST /api/advisor/messages
- [x] Backend: conversation listing + message history
- [x] Frontend: chat UI z live odpowiedziami DeepSeek
- [x] Frontend: tworzenie nowej konwersacji + pamięć kontekstu
- [x] System prompt: polski doradca (czas, pieniądze, projekty)
- [x] E2E: DeepSeek odpowiada po polsku, pamięta kontekst rozmowy

---

## Iteracja 2 — Dokumenty i Import

### Jakość, bezpieczeństwo i deploy (2026-08-13)
- [x] Scalono gałąź `quality-advisor` do `main`.
- [x] Wdrożono backend i frontend na produkcję.
- [x] Smoke test produkcji: `/api/health` i frontend odpowiadają HTTP 200.
- [ ] Obserwacja produkcji po wdrożeniu i zebranie realnych problemów.

### Import z Actual
- [x] Skrypt migracyjny Actual → Personal Advisor
- [x] Mapowanie kont, kategorii, transakcji
- [x] Zachowanie double-entry invariant (0 błędów na 800 transakcji)
- [x] Transfery wewnętrzne (66 par)
- [x] Kursy walut NBP (EUR/USD)
- [x] Migracja produkcyjna wykonana (2026-08-11)
- [x] Uzgodnienie kategorii/grup niezależne od księgowania importu i trwałe provenance kont/kategorii.
- [~] Kontrolowana korekta produkcyjna legacy Actual: kod i quality gates gotowe; polecenie produkcyjne nie zostało uruchomione.
- [x] Preflight korekty rozpoznaje wyłącznie historyczne, syntetyczne bilanse otwarcia Actual; lookalike, rekord ręczny i niezbilansowany BO są odrzucane.

### Task 7 — Próbne uzgodnienie Actual (2026-08-14)
- [x] Uruchomiono pełny quality gate w worktree `actual-reconciliation`: lint, typecheck, backend pytest, frontend Vitest i production build.
- [x] Zastosowano migracje i utworzono wyłącznie testowego użytkownika w izolowanej bazie `finanse_test` na `127.0.0.1:55432`.
- [x] Dodano testowany fallback NBP Table A dla soboty/niedzieli: poprzedni opublikowany kurs zachowuje datę efektywną w cache i źródło `nbp_previous_business_day` w postingach; brak kursu nadal odrzuca transakcję.
- [x] Import DOM blobu z `--execute --require-reconciled` zakończył się kodem 0: 800 transakcji, 0 błędów, `is_reconciled=true`, 15 kont i 46 kategorii bez różnic. Nie wykonano operacji na produkcyjnym PA ani Actual.

### Task 8 — Kontekstowy sidebar (2026-08-14)
- [x] Zastąpiono płaski sidebar układem `IconRail + ContextualSidebar` opartym
  o jedną, typowaną konfigurację nawigacji.
- [x] Kontekst wynika z najdłuższego pasującego prefiksu URL; istniejące
  `/finances` i pozostałe route'y, auth, topbar, treść stron oraz paleta pozostały bez zmian.
- [x] Dodano tooltipy raila, dolny UserPanel i ten sam model danych dla desktopu
  oraz mobilnego drawera; przyszłe pozycje są nieklikalne i oznaczone „Wkrótce”.
- [x] Frontend quality gate: Vitest `12 passed`, ESLint, TypeScript i Vite build.

### Stirling PDF + OCR
- [x] Worker async (Redis + ARQ)
- [x] Pipeline: upload → SHA-256 → Stirling → OCR → tekst
- [x] Ekstrakcja danych przez OpenAI → inbox item
- [x] Zatwierdzenie przez użytkownika (Inbox → Utwórz transakcję)

### Doradca Level 2 — narzędzia mutujące
- [x] Tool registry: create_task, create_time_block, create_transaction
- [x] Endpointy confirm/deny tool-execution z potwierdzeniem użytkownika
- [x] Audit log dla mutacji (performed_by=human)
- [x] Frontend: przyciski potwierdzenia/odrzucenia w czacie
- [x] Frontend: polling statusu narzędzi tylko dla oczekujących potwierdzenia

### Dokumenty — ekstrakcja danych
- [x] OpenAI extraction z OCR text (structured JSON: type, amount, currency, category)
- [x] Inbox item z sugerowaną transakcją po ekstrakcji

### Kalendarz i Finanse
- [x] Kalendarz: widok miesiąca, taski z due dates, filtrowanie zakresem, kolorowane bloki
- [x] Finanse: endpoint transakcji per konto, opening balances w migracji
- [x] Finanse: redesign strony (salde, wybór konta, transakcje per konto)
- [x] Payee resolution z fallbackiem na kategorię
- [x] Finanse: pierwszy slice prognozy płynności cyklu wypłaty — ustawienia,
  miesięczne pozycje, forecast do wypłaty, trzydniowa niepewność i UI tylko do odczytu.

---

## Konfiguracja opencode (2026-08-12)

### LSP i MCP
- [x] LSP włączony (`lsp: true`) + pyright + typescript-language-server
- [x] MCP EXA (remote, klucz przez `{env:EXA_API_KEY}`)

### Komendy
- [x] `/test`, `/lint`, `/typecheck` — pytest/vitest, ruff/eslint, mypy/tsc
- [x] `/migrate`, `/migration "opis"` — alembic upgrade/autogenerate
- [x] `/deploy` — docker compose build+up na produkcję
- [x] `/docs` — aktualizacja CHANGELOG/TASKS/JOURNAL po sesji

### Narzędzia i konfiguracja
- [x] ruff + mypy w backend/.venv (Makefile lint/typecheck działają)
- [x] pyproject.toml: ruff, mypy, pytest config
- [x] Formatter po zapisie: ruff (Python), prettier (TS/JS/CSS/HTML/JSON)
- [x] References: docs + infra; watcher ignore; permissions (lsp/webfetch/websearch/gh)
- [x] Skill `session-workflow`

---

## Done

- [x] Domknięcie przeglądu jakości: historia tool calls, walidacja mutacji finansowych, oznaczenie sald PLN, aktualizacja schematu DB

- [x] Fundament backendu (7 domen, 16 tabel)
- [x] Fundament frontendu (9 stron, routing, Tailwind)
- [x] Docker: postgres, redis, backend, frontend, stirling-pdf
- [x] Auth flow (rejestracja, logowanie, cookies, redirect)
- [x] Double-entry ledger (konta, transakcje, postings, invariant)
- [x] npmplus: Actual → finanse.vps.birek.online
- [x] npmplus: PA → finanse.birek.online (HTTPS + SSL)
- [x] Docker Compose + .env + Makefile
- [x] Repo: github.com/RobertBirek/finanse
- [x] Dokumentacja: AGENTS.md, PRD.md, DB_SCHEMA.md, 9 ADR-ów
- [x] Testy początkowego vertical slice'a: 15 testów (11 unit, 4 integracyjne)
- [x] Agent OpenCode: .opencode/agent/personal-advisor.md
- [x] CHANGELOG.md, JOURNAL.md, TASKS.md
