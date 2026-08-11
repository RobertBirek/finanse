# Changelog

Wszystkie istotne zmiany w projekcie.

Format oparty na [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Wersjonowanie: [Semantic Versioning](https://semver.org/).

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
