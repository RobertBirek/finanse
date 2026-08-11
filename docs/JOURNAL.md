# Journal

Techniczny dziennik sesji. Kontekst dla agentów w nowych sesjach.

---

## 2026-08-12 — Sesja 3: Doradca z narzędziami

### Cel sesji
Podłączyć istniejące narzędzia (finanse, work) do Doradcy przez OpenAI function calling.

### Co zrobiono

**Tool Registry (`advisor/tools/registry.py`):**
- 6 narzędzi tylko-do-odczytu (autonomy level 0)
- Każde z OpenAI function schema + async executor
- Narzędzia: get_accounts, get_financial_summary, get_transactions, get_today_schedule, get_tasks, get_projects

**Tool Calling Loop (`advisor/service.py`):**
- Przepisane `send_message` — pętla tool calling (max 3 iteracje)
- LLM → tool_call → execute → result → LLM → odpowiedź
- Tool executions zapisywane w DB (model ToolExecution)
- System prompt zawiera opisy narzędzi

**Frontend (`Advisor.tsx`):**
- ToolCallBanner — expandable bannery między wiadomościami
- Pokazuje nazwę narzędzia, status (✓/✗), wynik (JSON)

### Decyzje techniczne

1. **Tylko poziom 0** — narzędzia obserwacyjne. Mutacje (create_transaction, create_task) na później.
2. **Tool registry jako osobny moduł** — czyste oddzielenie definicji narzędzi od pętli wywołań.
3. **Eager loading tool_executions** — selectinload w obu endpointach (send_message + list_messages) dla poprawnego zwracania relacji.

### Znane problemy

- ~~Frontend nie ładuje danych z API~~ — NAPRAWIONE. Wszystkie strony (Today, Inbox, Projects, Calendar, Finances, Advisor, Documents, Settings) używają TanStack Query i ładują dane poprawnie.
- Brak testów jednostkowych dla tool calling loop (trudne do mockowania DeepSeek API)
- Tool call bannery nie aktualizują się w czasie rzeczywistym — widoczne dopiero po przeładowaniu konwersacji

---

## 2026-08-11 — Sesja 2: Import z Actual + Stirling OCR

### Cel sesji
Zaimplementować skrypt migracyjny Actual Budget → Personal Advisor i wykonać migrację produkcyjną.

### Co zrobiono

**ActualParser (`backend/app/finance/actual_parser.py`, 321 linii):**
- Odczyt kont (z filtrem tombstone/closed, detekcja waluty po nazwie)
- Odczyt kategorii (is_income → income/expense)
- Rekonstrukcja transakcji: simple (expense/income), transfery (self-join po transfer_id), splity (parent/child)
- Adaptacja do rzeczywistego schematu Actual: `v_transactions` (widok) vs `transactions` (tabela)
- Transfery: Actual używa wzajemnych referencji (A.transfer_id → B.id, B.transfer_id → A.id), nie wspólnego link ID

**NbpRateProvider (`backend/app/finance/nbp_rates.py`, 52 linie):**
- Async HTTP do NBP API (tabela A: EUR, USD)
- Cache per (waluta, data)
- Błędy NIE cache'owane (retry przy ponownej próbie)
- `calculate_base_amount()`: source_amount × fx_rate → zaokrąglone do groszy

**Skrypt CLI (`backend/scripts/migrate_actual.py`, 325 linii):**
- 4 fazy: extract SQLite → parse → resolve IDs → write
- Idempotentność: `description LIKE '[actual:{uuid}]%'`
- `--dry-run` / `--execute`
- Raport + log JSON

**Migracja produkcyjna:**
- 15 kont, 46 kategorii, 800 transakcji (734 simple + 66 transferów)
- 0 błędów, 1600 postingów (2 na transakcję, double-entry invariant zachowany)
- 8 ostrzeżeń NBP: USD w weekendy (niedziele: 2026-05-30, 2026-06-14, 2026-06-21)
- 0 split transactions w danych Actual

### Decyzje techniczne

1. **v_transactions zamiast transactions** — Actual używa widoku który już rozwiązuje payee i używa innych nazw kolumn (`account`, `transfer_id`). Parser wykrywa dostępność widoku i adaptuje zapytania.

2. **Transfery przez self-join** — W `v_transactions`, `transfer_id` wskazuje na ID drugiej transakcji (mutual reference), nie wspólny identyfikator. Rozwiązanie: `JOIN v_transactions t2 ON t1.transfer_id = t2.id WHERE t1.id < t2.id`.

3. **Ekstrakcja ZIP do /tmp** — Wolumen Actual montowany jako read-only, więc ekstrakcja ZIP musi iść do tymczasowego katalogu (`tempfile.mkdtemp`).

4. **NBP błędy niecache'owane** — Przy 404 (weekend/holiday) rate = 0.0 ale nie zapisujemy w cache, więc ponowna próba może zadziałać.

### Znane problemy

- **3 daty USD bez kursu NBP**: 2026-05-30, 2026-06-14, 2026-06-21 (niedziele). Transakcje z Revolut USD w te dni mają `base_amount_pln = source_amount`, `fx_rate_source = 'nbp_error'`. Do ręcznej korekty po migracji.

- **Split transactions nie występują** w danych Actual użytkownika. Kod parsera jest gotowy ale nieprzetestowany na rzeczywistych danych.

### Następna sesja
1. Stirling PDF + OCR pipeline (Iteracja 2)
2. Worker async (Redis + ARQ)

---

## 2026-08-10 — Sesja 1: Fundament + Deployment

### Cel sesji
Zbudować fundament Personal Advisor i wdrożyć na produkcję.

### Co zrobiono

**Architektura i projekt:**
- Wybrano podejście C: Hybrid (minimalny fundament + szybki vertical slice)
- Zatwierdzono strukturę: modularny monolit, 7 domen, double-entry ledger
- Utworzono 9 ADR-ów dokumentujących kluczowe decyzje

**Backend (FastAPI + SQLAlchemy):**
- 7 domen: identity, finance, work, inbox, advisor, documents, audit
- 16 tabel PostgreSQL przez Alembic auto-generate
- Auth: Argon2id + JWT HttpOnly cookies, Secure=True w produkcji
- Double-entry: transakcje + postings, invariant suma=0

**Frontend (React + Vite + Tailwind):**
- 9 stron z nawigacją, dark theme
- Auth flow: login → cookie → redirect /today
- TanStack Query hooks dla wszystkich domen API

**Infrastruktura:**
- `/docker/finanse/compose.yaml` — 5 serwisów
- npmplus: Actual → finanse.vps.birek.online, PA → finanse.birek.online
- SSL: Let's Encrypt (ważny do 2026-11-08)

**Workflow:**
- Dedykowany agent OpenCode: `.opencode/agent/personal-advisor.md`
- CHANGELOG.md, JOURNAL.md, TASKS.md

### Decyzje techniczne

1. **CORS_ORIGINS jako string zamiast List[str]** — pydantic-settings próbuje parsować JSON z env vars przed walidatorem. Rozwiązanie: pole jako `str` + property `cors_origins_list` z parsowaniem JSON/comma-separated.

2. **Cookie 7-dniowe, token 7-dniowy** — dla personal app (single user, nie bank), wygoda > restrykcyjne bezpieczeństwo. `ACCESS_TOKEN_EXPIRE_MINUTES=10080`.

3. **Frontend proxy /api/* przez nginx** — architektura: npmplus → frontend:80 (nginx) → /api/* → backend:8000. Frontend i backend na tej samej domenie, brak CORS w produkcji.

4. **Volume mount `/opt/finanse/backend:/app` w compose** — kod backendu montowany jako volume do kontenera. Pozwala na hot-reload (`--reload`). Do usunięcia w produkcji.

### Znane problemy

- ~~Frontend nie ładuje danych z API~~ — NAPRAWIONE w iteracjach 1-2.

- **Brak importu danych z Actual**: Actual działa na finanse.vps.birek.online ale nie ma jeszcze skryptu migracyjnego. Zaplanowane na Iterację 2.

- **Stirling PDF nie skonfigurowany**: kontener istnieje ale nie ma workflow OCR. Zaplanowane na Iterację 2.

- **`expose` zamiast `ports` w compose**: backend dostępny tylko przez sieć Docker. Dobrze dla bezpieczeństwa, utrudnia lokalny dev bez Dockera.

### Następna sesja
1. Dokumentacja sesji (CHANGELOG, JOURNAL, TASKS)
2. Inbox → Task end-to-end (pierwszy vertical slice)
3. Ekran Today z live danymi z API
