# AGENTS.md — Personal Advisor

Konstytucja projektu. Wszyscy agenci (OpenCode, dev) przestrzegają tych zasad.

## Produkt

**Personal Advisor** — osobisty system operacyjny do zarządzania czasem, pieniędzmi, projektami i decyzjami.

Domena produkcyjna: `https://finanse.birek.online`
Środowisko: VPS Ubuntu, Docker Compose, npmplus reverse proxy.

## Zasady nadrzędne

1. **Jedna informacja, wiele kontekstów.** Nie duplikuj danych między domenami.
2. **Oddzielne cykle życia = oddzielne modele.** `task != calendar_event != time_block != transaction`.
3. **PostgreSQL jest źródłem prawdy.** Nie Supabase, nie pliki JSON.
4. **LLM nie jest źródłem prawdy.** LLM interpretuje, klasyfikuje, podsumowuje — nie oblicza sald, nie wykonuje SQL, nie modyfikuje danych z pominięciem serwisów domenowych.
5. **Modularny monolit.** Nie mikroserwisy. Oddzielne pakiety per domena w backendzie.

## Stack

| Warstwa | Technologia |
|---------|------------|
| Frontend | React, Vite, TypeScript, Tailwind CSS, TanStack Query, React Router, Zustand |
| Backend | Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2.x (async), Alembic |
| Baza | PostgreSQL 16 |
| Cache/Kolejki | Redis |
| Reverse proxy | npmplus (Nginx Proxy Manager fork) |
| Dokumenty | Stirling PDF (wewnętrzny kontener) |
| AI | OpenAI API przez backend, Structured Outputs, Tool Calling |

## Docker — pattern

```
/docker/finanse/          ← infrastruktura (poza repo)
/opt/finanse/             ← kod (git repo)
```

Usługi na sieci `proxy` (external) dostępne przez npmplus. Postgres, Redis, Stirling PDF na sieci `internal`, nie wystawione.

## Finanse — zasady nienaruszalne

- **Uproszczona księga podwójnego zapisu** — każda transakcja ma min. 2 postings, suma = 0.
- Kwoty: `BIGINT` w najmniejszej jednostce waluty (grosze, centy).
- Waluta bazowa: PLN. Obsługiwane: PLN, EUR, USD.
- Każdy posting: source_amount, source_currency, base_amount_pln, fx_rate, fx_rate_source.
- Transfer wewnętrzny != przychód/wydatek.
- Przewalutowanie zapisuje obie rzeczywiste kwoty + rzeczywisty kurs.
- Prowizja = osobny koszt.

## AI — narzędzia Doradcy

- Tylko kontrolowane, małe narzędzia aplikacyjne (np. `get_financial_summary`, `get_today_schedule`).
- Nigdy dowolny SQL. Nigdy bezpośredni dostęp do bazy.
- Operacje mutujące: autoryzacja → walidacja domenowa → policy engine → audit log → opcjonalne zatwierdzenie.
- Poziomy autonomii: 0-obserwacja, 1-sugestie, 2-zatwierdzenie, 3-ograniczona, 4-agent.

## Konwencje kodu

### Backend
- Python 3.12+, type hints wszędzie.
- FastAPI routery per domena w `backend/app/<domena>/router.py`.
- Serwisy domenowe w `backend/app/<domena>/service.py`.
- Modele SQLAlchemy w `backend/app/<domena>/models.py`.
- Schematy Pydantic w `backend/app/<domena>/schemas.py`.
- Testy w `backend/tests/test_<domena>/`.
- Alembic migracje w `backend/migrations/versions/`.

### Frontend
- Komponenty per strona w `frontend/src/pages/`.
- Współdzielone komponenty w `frontend/src/components/`.
- API hooki TanStack Query w `frontend/src/api/`.
- Stan globalny Zustand w `frontend/src/stores/`.
- Tailwind CSS, PWA-ready.

## Testy

- Unit testy + integracyjne dla każdej domeny.
- Finanse: property-based testing invariantów (suma postings = 0, transfer != income/expense).
- `pytest` dla backendu. `vitest` dla frontendu.
- Przed każdym commitem: lint + typecheck + testy.

## Bezpieczeństwo

- Argon2id dla haseł.
- HttpOnly, Secure, SameSite cookies dla sesji.
- CSRF protection.
- Rate limiting na auth endpointach.
- Nigdy sekretów w repozytorium ani frontendzie.
- Wszystkie treści użytkownika traktowane jako niezaufane.

## Zakazy

- Nie używaj Supabase.
- Nie wystawiaj PostgreSQL, Redis, Stirling PDF do Internetu.
- Nie wykonuj DROP TABLE, TRUNCATE, ani masowego DELETE bez zgody.
- Nie nadpisuj oryginalnych dokumentów.
- Nie hardkoduj stawek podatkowych, modeli AI, limitów.
- Nie twórz ogromnego MVP — iteracyjnie, pionowe slice'y.
