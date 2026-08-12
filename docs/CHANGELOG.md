# Changelog

Wszystkie istotne zmiany w projekcie.

Format oparty na [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Wersjonowanie: [Semantic Versioning](https://semver.org/).

## [Unreleased] — 2026-08-12

### Changed
- **Task 6 — weryfikacja jakościowa**: potwierdzono pełny zestaw testów backendu (`81 passed`) po uruchomieniu izolowanej bazy PostgreSQL oraz testy integracyjne (`15 passed`); frontend Vitest (`4 passed`), typecheck i build również przeszły.
- Udokumentowano wyniki weryfikacji wszystkich dostępnych ścieżek Makefile bez modyfikowania kodu ani wdrażania zmian.

### Known Limitations
- `make lint`, `make typecheck`, `make test` i `make test-integration` bez override `VENV` nie startują w tym worktree, ponieważ brakuje `backend/.venv`; uruchomienie z `/opt/finanse/backend/.venv/bin` pozwoliło wykonać testy oraz ujawniło problemy niżej.
- Backend `ruff` kończy się 20 błędami, a `mypy` 9 błędami.
- `frontend/npm run lint` kończy się błędem, bo projekt nie ma konfiguracji ESLint; zależności ESLint są zainstalowane.
- Testy backendu zgłaszają 15 ostrzeżeń deprecacyjnych/runtime; nie blokują testów, ale wymagają osobnego porządku jakościowego.

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
