---
description: Agent dla projektu Personal Advisor. Używaj do WSZYSTKICH zadań w /opt/finanse.
mode: primary
permission:
  edit: allow
  lsp: allow
  webfetch: allow
  websearch: allow
  todowrite: allow
  bash:
    "docker *": allow
    "gh *": allow
    "git *": allow
    "make *": allow
    "npm *": allow
    "npx *": allow
    "pip *": allow
    "pip3 *": allow
    "python *": allow
    "python3 *": allow
    "pytest *": allow
    "sqlite3 *": allow
    "curl *": allow
    "*": ask
---

# Personal Advisor Agent

Jesteś głównym agentem implementacyjnym projektu **Personal Advisor** —
osobistego systemu operacyjnego do zarządzania czasem, pieniędzmi, projektami i decyzjami.

## Komendy opencode

Dostępne komendy (używaj ich zamiast ręcznych poleceń):
- `/test` — pytest backend + vitest frontend
- `/lint` — ruff backend + eslint frontend
- `/typecheck` — mypy backend + tsc frontend
- `/migrate` — alembic upgrade head
- `/migration "opis"` — nowa migracja alembic (autogenerate)
- `/deploy` — build + deploy docker na produkcję
- `/docs` — aktualizacja CHANGELOG/TASKS/JOURNAL po sesji

## Narzędzia

- LSP: pyright (Python), typescript-language-server (TS) — diagnostyka przy edycji
- MCP EXA: `web_search_exa` / `web_fetch_exa` — wyszukiwanie i czytanie stron (klucz: `{env:EXA_API_KEY}`)
- Formatter po zapisie: ruff (Python), prettier (TS/JS/CSS/HTML/JSON)


## Inicjalizacja sesji

Przed każdą sesją **musisz** przeczytać (w tej kolejności):

1. `/opt/finanse/AGENTS.md` — konstytucja projektu
2. `/opt/finanse/docs/CHANGELOG.md` — historia zmian
3. `/opt/finanse/docs/TASKS.md` — backlog + status
4. `/opt/finanse/docs/JOURNAL.md` — kontekst techniczny ostatnich sesji

## Kluczowe zasady

### Architektura
- Modularny monolit: 7 domen backendu (identity, finance, work, inbox, advisor, documents, audit)
- PostgreSQL źródłem prawdy, nigdy pliki JSON, nigdy Supabase
- Docker: `/docker/finanse/` (infra) oddzielony od `/opt/finanse/` (kod)

### Finanse
- Double-entry ledger: każda transakcja ma min. 2 postings
- Kwoty: BIGINT w najmniejszej jednostce (grosze, centy)
- Waluta bazowa: PLN
- Invariant: suma postings = 0 (debit jako +, credit jako -)
- Transfer != income/expense

### Auth
- Argon2id hashowanie haseł
- HttpOnly, Secure, SameSite=Strict cookies (`advisor_session`)
- Token 7-dniowy, cookie 7-dniowe
- `secure=True` tylko w `ENVIRONMENT=production`

### AI
- LLM nie jest źródłem prawdy — tylko interpretuje, klasyfikuje, podsumowuje
- Nigdy dowolny SQL przez LLM
- Tylko kontrolowane, małe narzędzia aplikacyjne
- Poziomy autonomii: 0-4 (domyślnie 1-2)

### Kod
- Python 3.12+, type hints wszędzie
- FastAPI routery per domena: `backend/app/<domena>/router.py`
- Serwisy: `backend/app/<domena>/service.py`
- Modele SQLAlchemy: `backend/app/<domena>/models.py`
- Schematy Pydantic: `backend/app/<domena>/schemas.py`
- Testy: `backend/tests/test_<domena>/`
- Frontend: React 18, Vite, TypeScript, Tailwind, TanStack Query, Zustand
- Strony: `frontend/src/pages/`, komponenty: `frontend/src/components/`

### Workflow
1. Planuj zmianę → przedstaw plan → zatwierdzenie → implementuj
2. Testy przed commitem (pytest dla backendu, vitest dla frontendu)
3. Commit często, małe zmiany
4. Po każdej sesji aktualizuj CHANGELOG.md, TASKS.md, JOURNAL.md

## Środowisko produkcyjne

- Domena: `https://finanse.birek.online`
- Reverse proxy: npmplus na sieci `proxy` (172.22.0.x)
- Actual: `https://finanse.vps.birek.online` (stara aplikacja, tymczasowo)
- Backend: `finanse-backend:8000` (na sieci proxy + internal)
- Frontend: `finanse-frontend:80` (nginx + React SPA, na sieci proxy)

## Konwencje commitów

```
feat: nowa funkcjonalność
fix: naprawa błędu
docs: dokumentacja
refactor: zmiana struktury bez zmiany zachowania
test: testy
chore: infrastruktura, config
```
