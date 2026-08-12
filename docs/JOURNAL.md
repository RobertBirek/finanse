# Journal

Techniczny dziennik sesji. Kontekst dla agentów w nowych sesjach.

---
## 2026-08-12 — Sesja 9: Końcowa jakość projektu

### Cel sesji
Zamknąć dokumentację po implementacji poprawek jakościowych Advisora, testów oraz konfiguracji frontendu. Nie zmieniać kodu i nie deklarować deployu produkcyjnego.

### Co zrobiono
- Zweryfikowano 27 commitów `f90a4d6..HEAD`; wcześniejsza dokumentacja podawała nieaktualną liczbę 17 commitów.
- Potwierdzono atomiczność potwierdzania mutacji Advisora: blokada wiersza chroni przed równoległym wykonaniem, savepoint wycofuje częściowe zapisy executora, a błąd audit logu nie zostawia mutacji.
- Potwierdzono bezpieczną walidację `create_transaction`: jawne `account_name`, dodatnia kwota całkowita, zgodna waluta konta oraz odrzucenie niezweryfikowanego FX.
- Dodano i uruchomiono testy tool-calling loop, błędnych argumentów, nieznanych narzędzi, błędów executorów, limitu iteracji, potwierdzeń Level 2 i rollbacku.
- Zweryfikowano izolowaną bazę PostgreSQL na `127.0.0.1:55432`; fixture ogranicza operacje schematu do lokalnej bazy `finanse_test`, a `make test-integration` usuwa kontener i sieć po zakończeniu.
- Potwierdzono polling Advisora co 2 sekundy tylko dla `pending_confirmation` oraz poprawkę lokalnego harmonogramu uwzględniającą granice dnia i DST.
- Udokumentowano poprawkę `7cc1973`, która przywróciła lokalną semantykę daty transakcji: brak jawnej daty używa bieżącego dnia użytkownika zamiast daty UTC.
- Dodano konfigurację ESLint 8 i usunięto 7 błędów lintowania frontendu.

### Weryfikacja
- `/opt/finanse/backend/.venv/bin/ruff check app/ tests/` — PASS: bez błędów.
- `/opt/finanse/backend/.venv/bin/mypy app/` — PASS: 46 plików źródłowych, bez błędów; narzędzie wypisało 2 noty o niejawnie typowanych funkcjach.
- `/opt/finanse/backend/.venv/bin/pytest -v` — PASS: `87 passed, 16 skipped, 6 warnings`; testy wymagające niedostępnej bazy zostały pominięte.
- `make VENV=/opt/finanse/backend/.venv/bin test-integration` — PASS: `16 passed, 87 deselected, 12 warnings`; kontener i sieć zostały usunięte przez trap Makefile.
- `npm run lint` — PASS.
- `npm run typecheck` — PASS.
- `npm run test` — PASS: 1 plik, 4 testy.
- `npm run build` — PASS: Vite wygenerował production build.

### Decyzje techniczne
1. Dokumentacja rozróżnia świeży wynik `16 passed` od wcześniejszego, wymaganego do zachowania w historii wyniku `15 passed`; dodatkowy test zwiększył aktualny zestaw integracyjny.
2. Niedostępna baza w zwykłym pytest pozostaje ostrzeżeniem środowiskowym, nie powodem do użycia produkcyjnego DSN. Pełny zakres integracyjny uruchomiono wyłącznie na izolowanym PostgreSQL.

### Znane problemy
- Testy emitują ostrzeżenia o domyślnym scope event loop w `pytest-asyncio`, deprecacjach `crypt`/Argon2 i `datetime.utcnow` w zależnościach oraz `RuntimeWarning` w mocku NBP.
- Trzy daty USD bez kursu NBP (`2026-05-30`, `2026-06-14`, `2026-06-21`) nadal wymagają ręcznej korekty.
- Parser split transactions nie został sprawdzony na rzeczywistych danych użytkownika.
- Polling obsługuje oczekujące potwierdzenia; aplikacja nie ma SSE/streamingu dla pozostałych zmian.
- Nie wykonano migracji ani deployu produkcyjnego.

### Następna sesja
1. Osobno uporządkować ostrzeżenia testowe i zależności.
2. Zweryfikować split transactions na reprezentatywnych danych.
3. Zaplanować SSE, jeśli aplikacja będzie wymagać aktualizacji bez pollingu.

---
## 2026-08-12 — Sesja 8: Konfiguracja ESLint frontendu

### Cel sesji
Uzupełnić brakującą konfigurację ESLint i domknąć frontendowy quality gate w worktree `quality-advisor`.

### Co zrobiono
- Potwierdzono ESLint `8.57.1`, `@typescript-eslint` `7.18.0`, `eslint-plugin-react-hooks` `4.6.2` oraz `eslint-plugin-react-refresh` `0.4.x`.
- Dodano `frontend/.eslintrc.cjs` w formacie legacy z parserem TypeScript, regułami React Hooks/Refresh oraz env browser/ES2022.
- Usunięto 7 błędów lintowych ujawnionych przez konfigurację: nieużywane deklaracje/importy oraz dwa niejawne `any`, bez szerokich wyłączeń reguł.
- Nie zmieniono zachowania aplikacji ani nie dodano testów, ponieważ zadanie dotyczyło wyłącznie konfiguracji jakościowej.

### Weryfikacja
- `cd frontend && npm run lint` — PASS.
- `cd frontend && npm run typecheck` — PASS.
- `cd frontend && npm run test` — PASS: 1 plik, 4 testy.
- `cd frontend && npm run build` — PASS: Vite production build.

### Decyzje techniczne
- Wybrano `.eslintrc.cjs`, ponieważ projekt używa ESLint 8 i nie wymaga migracji do flat config.
- Pozostawiono `--report-unused-disable-directives` i `--max-warnings 0` ze skryptu npm; nie dodano globalnych disable.

### Znane problemy
- Backendowy dług Ruff/mypy z poprzedniej sesji został spłacony; pozostały ostrzeżenia testowe i zależności opisane w Sesji 9.

---
## 2026-08-12 — Sesja 7: Task 6 — weryfikacja jakościowa

### Cel sesji
Przejrzeć historię Task 1-5, wykonać pełną dostępną weryfikację i udokumentować rzeczywisty stan bez zmian w kodzie, deployu ani migracji produkcyjnej.

### Co zrobiono
- Przejrzano 17 commitów `origin/main..HEAD` w worktree `quality-advisor` oraz aktualne dokumenty projektu. Liczba była poprawna dla tego wcześniejszego punktu historii; końcowy zakres sesji wyniósł 27 commitów od `f90a4d6` do `ab344ad`.
- Uruchomiono izolowany PostgreSQL z `/docker/finanse/compose.test.yaml` na `127.0.0.1:55432`; testowy kontener został posprzątany przez `make test-integration`.
- Pełny backend pytest: `81 passed, 15 warnings`.
- Backend testy integracyjne: `15 passed, 66 deselected, 12 warnings` w ówczesnym uruchomieniu; późniejszy test zwiększył świeży wynik do 16.
- Frontend Vitest: `1 test file passed, 4 tests passed`; `npm run typecheck` zakończył się kodem 0; `npm run build` zakończył się kodem 0.
- Nie zmieniono kodu, nie uruchomiono migracji ani deployu produkcyjnego.

### Komendy i wyniki
- `make lint` — FAIL, kod 127: brak `backend/.venv/bin/ruff`.
- `make typecheck` — FAIL, kod 127: brak `backend/.venv/bin/mypy`.
- `make test` — FAIL, kod 127: brak `backend/.venv/bin/pytest`.
- `make test-integration` — FAIL, kod 127 bez override `VENV`; baza wystartowała, ale brak lokalnego pytest.
- `TEST_DATABASE_URL=postgresql+asyncpg://finanse:finanse@127.0.0.1:55432/finanse_test /opt/finanse/backend/.venv/bin/pytest -v` (w `backend`) — PASS: `81 passed, 15 warnings`.
- `make VENV=/opt/finanse/backend/.venv/bin test` — PASS: backend `66 passed, 15 skipped`; frontend `4 passed` (uruchomienie równoległe z integracją zatrzymało bazę po zakończeniu integracji).
- `make VENV=/opt/finanse/backend/.venv/bin test-integration` — PASS: `15 passed, 66 deselected`.
- `make VENV=/opt/finanse/backend/.venv/bin lint` — FAIL w ówczesnym uruchomieniu: ruff zgłaszał 20 błędów; późniejsze commity spłaciły ten dług.
- `make VENV=/opt/finanse/backend/.venv/bin typecheck` — FAIL w ówczesnym uruchomieniu: mypy zgłaszał 9 błędów; późniejsze commity spłaciły ten dług.
- `npm run test` (w `frontend`) — PASS: `1 test file passed, 4 tests passed`.
- `npm run lint` (w `frontend`) — FAIL w ówczesnym uruchomieniu: brak konfiguracji ESLint, mimo zainstalowanych zależności; konfigurację dodano w Sesji 8.
- `npm run typecheck` (w `frontend`) — PASS.
- `npm run build` (w `frontend`) — PASS: Vite wygenerował `dist`.

### Decyzje techniczne
1. Nie kopiowano ani nie tworzono `backend/.venv` w worktree; użyto istniejącego venv poza repo wyłącznie do weryfikacji, aby nie modyfikować kodu i zachować reprodukowalność znanego ograniczenia.
2. Nie naprawiano lint/typecheck: nie było jasnej regresji z Task 1-5 blokującej testy, a polecenie sesji wymagało pozostawienia kodu bez zmian.

### Znane problemy
- Ruff: 20 błędów w ówczesnym punkcie historii, później usuniętych.
- Mypy: 9 błędów w ówczesnym punkcie historii, później usuniętych.
- Frontend ESLint: brak pliku konfiguracyjnego w ówczesnym punkcie historii; konfigurację dodano w Sesji 8.
- Pytest: ostrzeżenia dotyczą m.in. scope fixture `pytest-asyncio`, `passlib`/`argon2`, `python-jose`, a także nieoczekiwanego `RuntimeWarning` w teście NBP.

### Następna sesja
1. Uzupełnić konfigurację ESLint i zależności/typy wymagane przez mypy.
2. Usunąć 20 błędów ruff po osobnym przeglądzie semantycznym.
3. Uporządkować ostrzeżenia testowe, zwłaszcza konfigurację event loop i mock NBP.

---
## 2026-08-12 — Sesja 6: Odświeżanie statusów narzędzi Doradcy

### Cel sesji
Zrealizować Task 5: odświeżać statusy narzędzi oczekujących na potwierdzenie bez SSE.

### Co zrobiono
- Dodano polling wiadomości aktywnej rozmowy co 2 sekundy wyłącznie dla `pending_confirmation`.
- Zatrzymano polling dla statusów rozstrzygniętych i braku aktywnej rozmowy; odświeżanie w tle jest wyłączone.
- Confirm/deny mają typowane wyniki i unieważniają tylko aktywną rozmowę oraz listę rozmów.
- Banner przekazuje `conversationId`, blokuje oba przyciski podczas mutacji i pokazuje zwięzły błąd bez usuwania bannera.
- Dodano testy helpera `hasPendingConfirmation` i decyzji o interwale.

### Decyzje techniczne
1. Użyto `refetchInterval` callbacku TanStack Query v5 oraz `refetchIntervalInBackground: false`; opcja v5 nie nazywa się `refetchInBackground`.

### Znane problemy
- `npm run lint` nie uruchamia się, ponieważ frontend nie ma konfiguracji ESLint.

---

## 2026-08-12 — Sesja 5: Konfiguracja opencode pod projekt

### Cel sesji
Doposażyć opencode w narzędzia pracy: LSP, MCP EXA, komendy, formatter, skill — oraz naprawić narzędzia dev (lint/typecheck/testy).

### Co zrobiono

**LSP:**
- `lsp: true` w opencode.json (w opencode 1.18.16 LSP jest domyślnie wyłączony!)
- Zainstalowano `pyright` 1.1.411 + `typescript-language-server` 5.3.0 (npm global)
- TypeScript LSP nie startował automatycznie — brak `package.json` w root `/opt/finanse` (built-in wymaga "typescript dependency in project"). Rozwiązanie: jawny override `lsp.typescript.command` — wymaga restartu

**MCP EXA:**
- Remote endpoint `https://mcp.exa.ai/mcp`, `oauth: false`, header `x-api-key: {env:EXA_API_KEY}` (interpolacja z env, sekret NIE w repo)
- `EXA_API_KEY` w `~/.bashrc`; zweryfikowano `web_search_exa` end-to-end

**7 komend opencode (`.opencode/command/`):**
- `/test` (pytest+vitet), `/lint` (ruff+eslint), `/typecheck` (mypy+tsc)
- `/migrate`, `/migration "opis"` (alembic), `/deploy` (docker), `/docs` (aktualizacja docs)

**Narzędzia dev (naprawa):**
- `ruff` 0.16.2 + `mypy` 2.3.0 w `backend/.venv` (Makefile lint/typecheck nie działały — narzędzi brakowało)
- `pyproject.toml`: `[tool.ruff]` (line-length 100), `[tool.mypy]` (explicit_package_bases — błąd "source file found twice"), `[tool.pytest.ini_options]` (pythonpath — `ModuleNotFoundError: app`)
- Makefile: jawne ścieżki `.venv/bin/` (wcześniej wymagał aktywowanego venv)

**Formatter:** custom ruff (`$FILE`) + prettier (extensions ograniczone do kodu, `.md` wyłączone — chroni docs przed churnem)

**Inne:** references (docs, infra), watcher ignore, permissions (lsp/webfetch/websearch/gh), skill `session-workflow`, agent file zsynchronizowany

### Decyzje techniczne

1. **`lsp: true` w opencode.json** — w 1.18.16 LSP wyłączony domyślnie; `true` włącza wszystkie built-iny, object override dla konkretnych serwerów.
2. **MCP EXA remote zamiast local npx** — oficjalne zalecenie Exa dla OpenCode; `{env:EXA_API_KEY}` w headers = brak sekretu w repo; `oauth: false` zapobiega auto-detekcji OAuth.
3. **Custom formatter z jawnymi ścieżkami** — PEP 668 blokuje globalny pip; ścieżki do venv/node_modules zamiast `--break-system-packages`.
4. **TypeScript LSP wymaga root package.json** — opencode sprawdza zależności w root projektu, nie w podkatalogach; jawny command omija to sprawdzenie.

### Znane problemy

- **TypeScript LSP**: config dodany, wymaga restartu opencode, żeby wystartował.
- **Dług lintowy**: 210 błędów ruff (projekt nigdy nie był lintowany; 87 auto-fixowalnych).
- **Błędy typów**: 25 w mypy (7 plików), m.in. "Too few arguments" w `advisor/router.py:106` i `advisor/service.py:197` — możliwe realne bugi.
- **Testy integracyjne**: wymagają PostgreSQL na `localhost:5432`, a postgres jest tylko na wewnętrznej sieci Docker (port niezpublished) — 10 testów pada, 35 przechodzi.

### Następna sesja
1. Spłata długu lintowego (ruff --fix) + błędy mypy
2. Testy tool calling loop (Level 0 + Level 2 z potwierdzeniem)
3. Dokumentacja testów integracyjnych (DB w Docker)

---

## 2026-08-11/12 — Sesja 4: Dokumenty, ekstrakcja, Level 2, kalendarz, finanse

### Cel sesji
Dokończyć Iterację 2 (Stirling OCR + ekstrakcja danych), rozszerzyć Doradcę o narzędzia mutujące (Level 2), ulepszyć kalendarz i finanse.

### Co zrobiono

**Stirling PDF + OCR pipeline:**
- Worker async (Redis + ARQ): upload → SHA-256 → Stirling → OCR → tekst
- Pipeline dwustopniowy: najpierw OCR dokumentu (poprawka po tym, że jednorazowe OCR nie działało), potem ekstrakcja tekstu
- `documents/` — service, router, ARQ worker; frontend Dokumenty (upload, lista, podgląd)

**Ekstrakcja danych finansowych (`documents/extractor.py`, 94 linie):**
- OCR text → LLM (DeepSeek/OpenAI) → structured JSON: `type` (expense/income), `amount` w groszach, `currency`, `description`, `date`, `category_suggestion`
- `detected=false` gdy dokument nie zawiera danych finansowych; tekst ucinany do 8000 znaków
- Wynik → inbox item z sugerowaną transakcją → zatwierdzenie w Inbox

**Doradca Level 2 — mutacje z potwierdzeniem:**
- `registry.py`: `_execute_create_task`, `_execute_create_time_block`, `_execute_create_transaction` (167 linii)
- Endpointy `POST /tool-executions/{id}/confirm` i `/deny`: status `pending_confirmation` → `completed`/`denied`, `policy_check_passed=true`, audit log (`performed_by=human`)
- Frontend: przyciski potwierdzenia/odrzucenia w czacie

**Kalendarz (`Calendar.tsx`, +263/-74):**
- Widok miesiąca, taski z due dates, filtrowanie po zakresie dat, kolorowane bloki czasowe

**Finanse:**
- `actual_parser.py`: payee resolution z fallbackiem na kategorię
- `migrate_actual.py` (+76): opening balances
- Endpoint transakcji per konto (`/api/finance/accounts/{id}/transactions`)
- Redesign `Finances.tsx`: 470 → 86 linii (salde, wybór konta, transakcje)

### Decyzje techniczne

1. **Level 2 = poziom autonomii 2** (zatwierdzenie) — mutacje NIE wykonują się bez potwierdzenia człowieka; spełnia policy engine z AGENTS.md.
2. **Ekstrakcja przez LLM to sugestia, nie źródło prawdy** — LLM zwraca JSON, użytkownik zatwierdza w Inbox; kwoty w groszach (BIGINT).
3. **Two-step OCR** — oddzielny krok OCR + ekstrakcja tekstu (jedno przejście Stirling zwracało binarny PDF bez tekstu).

### Znane problemy

- Tool call bannery nie mają streamingu SSE; oczekujące potwierdzenia odświeża polling.
- Testy tool-calling loop dodano w późniejszej części sesji jakościowych.
- 3 daty USD bez kursu NBP (niedziele: 2026-05-30, 2026-06-14, 2026-06-21) — `base_amount_pln = source_amount`, do ręcznej korekty.

### Następna sesja
1. Konfiguracja opencode (LSP, MCP EXA, komendy) — patrz Sesja 5
2. Spłata długu: lint, typecheck, testy integracyjne

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
- Tool call bannery nie miały wówczas odświeżania w czasie rzeczywistym; późniejszy polling obejmuje oczekujące potwierdzenia.

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
