# Tasks

Backlog zadań ze statusami.

Statusy: `[ ]` pending, `[~]` in progress, `[x]` done, `[-]` cancelled

---

## Iteracja 1 — Pierwszy Vertical Slice (MVP)

### Inbox → Task
- [ ] Backend: endpoint `POST /api/inbox/{id}/classify` do klasyfikacji inbox_item w task
- [ ] Frontend: Inbox page ładuje listę inbox_items z API
- [ ] Frontend: przycisk "Utwórz zadanie" tworzy task i oznacza inbox_item jako processed
- [ ] Frontend: pokaż historię (processed items)

### Dzisiaj z live danymi
- [ ] Frontend: Today ładuje taski z API (due_date=today lub status=in_progress)
- [ ] Frontend: Today ładuje time_blocki z API
- [ ] Frontend: Today ładuje financial_summary z API
- [ ] Backend: endpoint `GET /api/work/tasks?due_date=today` 
- [ ] Backend: endpoint `GET /api/finance/summary`

### Finanse CRUD
- [ ] Frontend: Finances page ładuje listę kont z API
- [ ] Frontend: formularz tworzenia konta (nazwa, typ, waluta)
- [ ] Frontend: lista transakcji z API
- [ ] Frontend: formularz uproszczony transakcji (backend pilnuje double-entry)

### Doradca
- [ ] Backend: integracja OpenAI API
- [ ] Backend: implementacja `get_financial_summary` tool
- [ ] Frontend: chat UI (wysyłanie wiadomości, wyświetlanie odpowiedzi)

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
