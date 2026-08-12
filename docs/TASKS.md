# Tasks

Backlog zadań ze statusami.

Statusy: `[ ]` pending, `[~]` in progress, `[x]` done, `[-]` cancelled

---

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

### Import z Actual
- [x] Skrypt migracyjny Actual → Personal Advisor
- [x] Mapowanie kont, kategorii, transakcji
- [x] Zachowanie double-entry invariant (0 błędów na 800 transakcji)
- [x] Transfery wewnętrzne (66 par)
- [x] Kursy walut NBP (EUR/USD)
- [x] Migracja produkcyjna wykonana (2026-08-11)

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

### Dokumenty — ekstrakcja danych
- [x] OpenAI extraction z OCR text (structured JSON: type, amount, currency, category)
- [x] Inbox item z sugerowaną transakcją po ekstrakcji

### Kalendarz i Finanse
- [x] Kalendarz: widok miesiąca, taski z due dates, filtrowanie zakresem, kolorowane bloki
- [x] Finanse: endpoint transakcji per konto, opening balances w migracji
- [x] Finanse: redesign strony (salde, wybór konta, transakcje per konto)
- [x] Payee resolution z fallbackiem na kategorię

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
- [x] Testy: 15 testów (11 unit, 4 integracyjne)
- [x] Agent OpenCode: .opencode/agent/personal-advisor.md
- [x] CHANGELOG.md, JOURNAL.md, TASKS.md
