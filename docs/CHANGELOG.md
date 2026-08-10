# Changelog

Wszystkie istotne zmiany w projekcie.

Format oparty na [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Wersjonowanie: [Semantic Versioning](https://semver.org/).

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
