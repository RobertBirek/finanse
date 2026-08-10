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
- [ ] Skrypt migracyjny Actual → Personal Advisor
- [ ] Mapowanie kont, kategorii, transakcji
- [ ] Zachowanie double-entry invariant

### Stirling PDF + OCR
- [ ] Worker async (Redis + ARQ)
- [ ] Pipeline: upload → SHA-256 → Stirling → OCR → tekst
- [ ] Ekstrakcja danych przez OpenAI
- [ ] Zatwierdzenie przez użytkownika

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
