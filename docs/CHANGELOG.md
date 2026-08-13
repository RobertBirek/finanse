# Changelog

Wszystkie istotne zmiany w projekcie.

Format oparty na [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Wersjonowanie: [Semantic Versioning](https://semver.org/).

## [Unreleased] — 2026-08-13

### Fixed
- Domknięto historię tool calls Advisora dla kolejnych tur, walidację własności i walut transakcji w serwisie domenowym oraz oznaczenie sald `balance_pln` jako PLN.
- Fixture testowej bazy wiąże aplikacyjny session factory z izolowanym silnikiem per test.

### Changed
- `DB_SCHEMA.md` opisuje rzeczywiste statusy `ToolExecution`.

### Added
- Testy pętli tool-calling Advisora: odpowiedź Level 0 po wykonaniu narzędzia, błędny JSON, nieznane narzędzie, błędy executora, limit iteracji oraz oczekiwanie na potwierdzenie Level 2.
- Testy potwierdzania mutacji: blokada ponownego confirm/deny, izolacja użytkownika, odrzucenie błędnego wyniku oraz rollback częściowej mutacji, gdy executor lub audit log zakończy się błędem.
- Izolowana baza PostgreSQL do testów integracyjnych na `127.0.0.1:55432`; fixture tworzy i usuwa schemat, a `make test-integration` sprząta kontener i sieć po zakończeniu.

### Changed
- **Doradca — bezpieczne mutacje finansowe**: `create_transaction` wymaga jawnego `account_name`, akceptuje wyłącznie dodatnie kwoty całkowite i odrzuca niezgodność waluty konta oraz walutę bez zweryfikowanego kursu FX.
- **Doradca — atomiczność potwierdzeń**: blokada wiersza chroni przed równoległym potwierdzeniem, a savepoint wycofuje częściowe zapisy executora i audit logu.
- **Frontend Advisora**: polling aktywnej rozmowy co 2 sekundy działa wyłącznie przy `pending_confirmation`; po rozstrzygnięciu polling się zatrzymuje.
- Poprawiono lokalne granice dnia i obsługę zmian czasu w harmonogramie, w tym offset DST zależny od konkretnej daty.
- Przywrócono lokalną semantykę daty transakcji (`7cc1973`): brak jawnej daty używa bieżącego dnia użytkownika zamiast daty UTC.
- Dodano konfigurację ESLint 8 z parserem TypeScript, regułami React Hooks/Refresh oraz środowiskiem browser/ES2022.

### Fixed
- Usunięto 7 błędów frontendowego lintowania.
- Spłacono backendowy dług Ruff i mypy: `ruff check app/ tests/` oraz `mypy app/` przechodzą.
- Poprawiono ochronę fixture testowej bazy: schemat można tworzyć i usuwać tylko w lokalnej bazie `finanse_test` na zatwierdzonym porcie; niedostępna baza powoduje pominięcie testów integracyjnych zamiast ingerencji w inną bazę.

### Verified
- Historia sesji `f90a4d6..ab344ad` obejmuje 27 commitów; wcześniejszy zapis o 17 commitach był nieaktualny. Bieżący corrective docs commit nie należy do tego zakresu.
- Backend Ruff: PASS, bez błędów.
- Backend mypy: PASS, `46 source files`, bez błędów.
- Backend pytest: PASS, `89 passed, 23 skipped, 5 warnings`; testy zależne od niedostępnej lokalnie bazy zostały pominięte.
- Testy integracyjne z izolowanym PostgreSQL: PASS, `23 passed, 89 deselected, 11 warnings` w świeżonym uruchomieniu.
- Frontend: `npm run lint`, `npm run typecheck`, `npm run test` (`1 test file, 4 tests`) oraz `npm run build` przeszły.
- Zmiany wyłącznie porządkowe w `backend/migrations/` przywrócono do `f90a4d6`; nie zmieniono schematu.
- Weryfikacja nie uruchamiała migracji ani deployu produkcyjnego.

### Known Limitations
- Backend i frontend korzystają w tym worktree z zależności poza repozytorium: backend z `/opt/finanse/backend/.venv`, frontend z lokalnego `node_modules`.
- Testy zgłaszają ostrzeżenia dotyczące domyślnego scope event loop w `pytest-asyncio`, deprecacji `crypt`/Argon2 i `datetime.utcnow` w zależnościach oraz `RuntimeWarning` w mocku NBP.
- Trzy historyczne daty USD bez kursu NBP pozostają do ręcznej korekty: 2026-05-30, 2026-06-14 i 2026-06-21.
- Parser split transactions nie został zweryfikowany na rzeczywistych danych użytkownika.
- Brak SSE/streamingu dla zmian innych niż polling oczekujących potwierdzeń.

## [0.3.0] — 2026-08-12

### Added
- **Doradca Level 2 — narzędzia mutujące z potwierdzeniem użytkownika**
  - `create_task`, `create_time_block`, `create_transaction` w tool registry
  - Endpointy `POST /api/advisor/tool-executions/{id}/confirm` / `/deny`
  - Status `pending_confirmation` → `completed` / `denied` + audit log
  - Frontend: przyciski potwierdzenia/odrzucenia mutacji w czacie
- **Ekstrakcja danych finansowych z dokumentów (OpenAI/DeepSeek)**
  - `documents/extractor.py`: OCR text → structured JSON (type, amount w groszach, currency, category_suggestion)
  - Tworzy inbox item z sugerowaną transakcją → zatwierdzenie przez użytkownika w Inbox
- **Stirling PDF + OCR pipeline (dokończenie Iteracji 2)**
  - Worker async (Redis + ARQ), pipeline: upload → SHA-256 → Stirling → OCR → tekst
  - Frontend Dokumenty: upload, lista, podgląd plików
- **Rozbudowany kalendarz**: widok miesiąca, taski z due dates, filtrowanie po zakresie dat, kolorowane bloki czasowe
- **Finanse**: endpoint transakcji per konto, opening balances w migracji z Actual
- **Konfiguracja opencode pod projekt**
  - LSP: pyright (Python) + typescript-language-server (TS) — `lsp: true` + jawny override TS
  - MCP EXA: remote `https://mcp.exa.ai/mcp`, klucz przez `{env:EXA_API_KEY}` (bez sekretu w repo)
  - 7 komend: `/test`, `/lint`, `/typecheck`, `/migrate`, `/migration "opis"`, `/deploy`, `/docs`
  - Formatter: ruff (Python) + prettier (TS/JS/CSS/HTML/JSON) po zapisie
  - References (docs, infra), watcher ignore, permissions (lsp/webfetch/websearch/gh)
  - Skill `session-workflow` (inicjalizacja sesji + aktualizacja docs)
- **Narzędzia dev**: ruff 0.16.2 + mypy 2.3.0 w `backend/.venv`; config w `pyproject.toml`
  (ruff line-length 100, mypy `explicit_package_bases`, pytest `pythonpath`); Makefile naprawiony (jawne ścieżki `.venv/bin/`)

### Changed
- **Finanse — redesign strony**: uproszczona z 470 → 86 linii (widok sald, wybór konta, transakcje per konto)
- **Stirling OCR**: pipeline dwustopniowy — najpierw OCR dokumentu, potem ekstrakcja tekstu
- Frontend: lista kont z saldami, sekcja przychodów/wydatków

### Fixed
- **Statusy narzędzi Doradcy**: polling aktywnej rozmowy co 2 s tylko dla `pending_confirmation`, precyzyjne invalidacje po confirm/deny i obsługa błędów w bannerze
- **Payee resolution** w imporcie z Actual (fallback na kategorię)
- **Opening balances** poprawnie zapisywane przy migracji
- **Frontend nie ładował danych z API** — ostatecznie naprawione (wszystkie strony na TanStack Query)
- **Eager-loading tool_executions** w `get_conversation_messages` (ToolCallBanner po przeładowaniu)

## [0.2.0] — 2026-08-11

### Added
- **Import z Actual Budget**: skrypt CLI `scripts/migrate_actual.py`
  - Parser Actual SQLite (konta, kategorie, transakcje, transfery, splity)
  - Provider kursów NBP z cache (EUR, USD)
  - Double-entry invariant zachowany — 800 transakcji zaimportowanych (0 błędów)
  - Idempotentność przez `[actual:{uuid}]` prefix w description
  - Tryb `--dry-run` do walidacji przed zapisem
  - Raporty `migration_report.txt` + `migration_log.json`
- **22 testy** dla importu (unit + integracyjne)

### Changed
- Actual Budget dane zaimportowane do PA (15 kont, 46 kategorii, 800 transakcji)
- Backend ma dostępne narzędzia importu w `scripts/`

## [0.1.0] — 2026-08-10

### Added
- **Backend**: FastAPI + SQLAlchemy 2.x async + Alembic
  - 7 domen: identity, finance, work, inbox, advisor, documents, audit
  - Double-entry ledger: konta, kategorie, transakcje, postings (BIGINT)
  - Auth: Argon2id, JWT w HttpOnly Secure SameSite=Strict cookies
  - Policy engine dla Advisor (poziomy autonomii 0-4)
  - Audit log dla operacji mutujących
- **Frontend**: React 18 + Vite + TypeScript + Tailwind CSS
  - TanStack Query + React Router v6 + Zustand
  - 9 stron: Login, Today, Inbox, Projects, ProjectDetail, Calendar, Finances, Advisor, Settings
  - Dark theme (gray-950), responsive layout
  - PWA-ready (manifest, theme-color)
- **Docker**: postgres:16, redis:7, backend, frontend (nginx+SPA), stirling-pdf
  - Wzorzec: kod w `/opt/finanse/`, infrastruktura w `/docker/finanse/`
  - Reverse proxy: npmplus (Nginx Proxy Manager fork)
- **Dokumentacja**: AGENTS.md, PRD.md, DB_SCHEMA.md, 9 ADR-ów
  - CHANGELOG.md, JOURNAL.md, TASKS.md
  - Agent OpenCode: `.opencode/agent/personal-advisor.md`
- **Testy**: 15 testów (11 unit + 4 integracyjne wymagające DB)
  - Double-entry invarianty, hashowanie haseł, tokeny, auth middleware

### Changed
- Actual przeniesiony z `finanse.birek.online` na `finanse.vps.birek.online`

### Verified
- E2E: rejestracja → logowanie → redirect /today → sesja cookie
- E2E: tworzenie konta → tworzenie transakcji (double-entry, suma=0)
- Frontend: wszystkie assety ładują się (302 KB JS + 21 KB CSS)
- Backend: health check, wszystkie endpointy auth i finance
