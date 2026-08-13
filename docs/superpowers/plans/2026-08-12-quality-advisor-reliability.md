# Jakość i niezawodność Doradcy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Usunąć bieżący dług Ruff/mypy, przetestować krytyczną pętlę tool-calling, uruchamiać integracyjne testy z izolowanym PostgreSQL i odświeżać statusy mutacji Doradcy bez ręcznego przeładowania.

**Architecture:** Zachowujemy istniejący modularny monolit, registry narzędzi i API. Logikę statusów egzekucji uszczelniamy w routerze/serwisie, konfigurację testowej bazy trzymamy w fixture, a polling realizujemy przez `refetchInterval` TanStack Query. Nie dodajemy SSE/WebSocketów ani nowych funkcji biznesowych.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, pytest/pytest-asyncio, PostgreSQL 16 Docker, React 18, TypeScript, TanStack Query v5, Vitest.

---

## Mapa zmian

- Modify: `backend/app/advisor/service.py` — stabilna obsługa pętli tool-calling i typów.
- Modify: `backend/app/advisor/router.py` — autoryzacja właściciela, status guard i 409 dla powtórnej decyzji.
- Modify: `backend/app/advisor/tools/registry.py` — jawne typy executorów i bezpieczne ograniczenia argumentów, wyłącznie jeśli wymagane przez mypy/testy.
- Create: `backend/tests/test_advisor/__init__.py` — pakiet testów Doradcy.
- Create: `backend/tests/test_advisor/test_service.py` — testy pętli LLM i registry.
- Create: `backend/tests/test_advisor/test_router.py` — testy confirm/deny i izolacji użytkowników.
- Modify: `backend/tests/conftest.py` — `TEST_DATABASE_URL`, czytelne pomijanie przy niedostępnej bazie i bezpieczne sprzątanie.
- Modify: `backend/pyproject.toml` — wyłącznie ustawienia wymagane przez naprawione typy/lint.
- Modify: `Makefile` — jawny target uruchomienia testowej bazy i testów integracyjnych.
- Create: `/docker/finanse/compose.test.yaml` — izolowany PostgreSQL testowy z portem loopback; plik infrastruktury pozostaje poza repozytorium kodu.
- Modify: `frontend/src/api/advisor.ts` — polling wiadomości i precyzyjne invalidation cache.
- Modify: `frontend/src/pages/Advisor.tsx` — status polling, blokady i komunikaty błędów mutacji.
- Create: `frontend/src/api/advisor.test.ts` — testy helpera/pollingu i invalidation hooków.
- Modify: `docs/CHANGELOG.md`, `docs/TASKS.md`, `docs/JOURNAL.md` — dokumentacja końcowa po weryfikacji.

## Task 1: Baseline i bezpieczny cleanup Ruff

**Files:**
- Modify: pliki wskazane przez Ruff w `backend/app/` i `backend/tests/`.
- Test: istniejące testy backendu.

- [ ] **Step 1: Uruchomić baseline i zapisać listę błędów**

Run:

```bash
cd /opt/finanse/backend && .venv/bin/ruff check app/ tests/
```

Expected: aktualny raport błędów Ruff; nie zmieniać konfiguracji ani nie wyłączać reguł na tym etapie.

- [ ] **Step 2: Wykonać wyłącznie bezpieczne automatyczne poprawki**

Run:

```bash
cd /opt/finanse/backend && .venv/bin/ruff check app/ tests/ --fix
```

Następnie przejrzeć każdy zmieniony plik przez `git diff`; odrzucić poprawki zmieniające zachowanie domenowe, zwłaszcza w ledgerze i auth.

- [ ] **Step 3: Naprawić pozostałe błędy ręcznie**

Utrzymać istniejące zasady: importy na początku pliku, maksymalna długość linii 100, brak `print`/debuggerów i brak sekretów. Dla wyjątków w kodzie aplikacji zachować kontrolowany wynik API zamiast tracebacka.

- [ ] **Step 4: Potwierdzić czysty Ruff**

Run:

```bash
cd /opt/finanse/backend && .venv/bin/ruff check app/ tests/
```

Expected: `All checks passed!`.

- [ ] **Step 5: Zrobić mały commit cleanupu**

```bash
git add backend/app backend/tests
git commit -m "chore: spłać dług lintowy backendu"
```

## Task 2: Ustabilizować typy backendu i statusy egzekucji

**Files:**
- Modify: `backend/app/advisor/service.py:91-233`.
- Modify: `backend/app/advisor/router.py:83-153`.
- Modify: `backend/app/advisor/tools/registry.py:1-23`.
- Test: `backend/tests/test_advisor/test_router.py`.

- [ ] **Step 1: Dodać failing test dla ponownego confirm/deny**

W `test_router.py` utworzyć testy API, które przygotowują `ToolExecution` o statusie `completed` albo `denied`, a następnie sprawdzają `409` i brak drugiego wywołania executora. Dodać także test deny z cudzym użytkownikiem i oczekiwać `404`.

Minimalny wzorzec asercji:

```python
response = await async_client.post(f"/api/advisor/tool-executions/{execution.id}/confirm")
assert response.status_code == 409
executor.assert_not_awaited()
```

- [ ] **Step 2: Uruchomić nowe testy i potwierdzić porażkę**

```bash
cd /opt/finanse/backend && .venv/bin/pytest tests/test_advisor/test_router.py -q
```

Expected: FAIL, ponieważ obecny router wykonuje confirm bez sprawdzenia statusu, a deny nie sprawdza właściciela.

- [ ] **Step 3: Dodać wspólną kontrolę właściciela i statusu**

W obu endpointach pobierać egzekucję razem z `ToolExecution.message` oraz `Message.conversation`:

```python
result = await db.execute(
    sa_select(ToolExecution)
    .options(selectinload(ToolExecution.message).selectinload(Message.conversation))
    .where(ToolExecution.id == execution_id)
)
te = result.scalar_one_or_none()
if te is None or te.message.conversation.user_id != current_user.id:
    raise HTTPException(status_code=404, detail="Tool execution not found")
if te.status != "pending_confirmation":
    raise HTTPException(status_code=409, detail="Tool execution already resolved")
```

Nie używać lazy loadingu na obiektach SQLAlchemy async.

- [ ] **Step 4: Zabezpieczyć wynik confirm przed częściowym błędem**

Po sukcesie ustawić `result`, `completed` i `policy_check_passed=True`, a audit log wykonać przez istniejące `log_event`. Przy wyjątku ustawić `status="error"` i wynik `{"error": "Nie udało się wykonać operacji."}`; nie wykonać audit logu jako udanego confirm.

- [ ] **Step 5: Naprawić wykrywanie pending w pętli**

W `send_message` użyć lokalnej flagi ustawianej podczas tworzenia `ToolExecution`, zamiast polegać na tym, że świeżo dodany obiekt jest już obecny w `assistant_msg.tool_executions`:

```python
has_pending_confirmation = False
...
if tool is not None and tool.autonomy_level >= 2:
    has_pending_confirmation = True
...
if has_pending_confirmation:
    return assistant_msg
```

Zachować `MAX_TOOL_ITERATIONS = 3` i istniejący przepływ Level 0.

- [ ] **Step 6: Uporządkować typy registry i service**

Zastąpić nieparametryzowane `dict`/`list` tam, gdzie mypy zgłasza błąd, typami `dict[str, Any]`, `list[dict[str, Any]]` i jawnie opisać `ToolExecutor` jako callable przyjmujący `AsyncSession`, `str` oraz keyword arguments. Nie zmieniać publicznych nazw narzędzi.

- [ ] **Step 7: Uruchomić testy routera i mypy**

```bash
cd /opt/finanse/backend && .venv/bin/pytest tests/test_advisor/test_router.py -q
cd /opt/finanse/backend && .venv/bin/mypy app/
```

Expected: testy routera PASS; liczba błędów mypy nie może wzrosnąć względem baseline, a po zakończeniu Task 2 ma wynosić zero dla zmienionych plików.

- [ ] **Step 8: Zrobić commit bezpieczeństwa statusów**

```bash
git add backend/app/advisor backend/tests/test_advisor/test_router.py
git commit -m "fix: uszczelnij potwierdzanie narzędzi Doradcy"
```

## Task 3: Testy pętli tool-calling i executorów

**Files:**
- Create: `backend/tests/test_advisor/__init__.py`.
- Create: `backend/tests/test_advisor/test_service.py`.
- Modify: `backend/app/advisor/service.py` tylko, gdy failing tests ujawnią błąd.

- [ ] **Step 1: Przygotować fabryki mockowanych odpowiedzi OpenAI**

W teście użyć prostych obiektów `SimpleNamespace` z polami `choices[0].message`, `content` i `tool_calls`, aby nie wykonywać połączeń sieciowych:

```python
def llm_text(content: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=None))]
    )

def llm_tool_call(name: str, arguments: str, call_id: str = "call-1"):
    call = SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=[call]))]
    )
```

- [ ] **Step 2: Napisać test odpowiedzi bez narzędzia**

Mockować `app.advisor.service._get_llm_client`, zwrócić `llm_text("Dzień dobry")`, wywołać `send_message` i sprawdzić rolę, treść oraz brak `ToolExecution`.

- [ ] **Step 3: Napisać test Level 0 z drugą odpowiedzią LLM**

Zamockować `get_tool_by_name`/executor narzędzia odczytowego oraz `client.chat.completions.create` z sekwencją: `llm_tool_call("get_projects", "{}")`, następnie `llm_text("Masz jeden projekt.")`. Sprawdzić, że executor wywołano z `str(user_id)`, do drugiego requestu trafiła wiadomość `role="tool"`, a wynik końcowy jest zapisany.

- [ ] **Step 4: Napisać test błędów narzędzia**

Osobnymi przypadkami pokryć:

```python
pytest.mark.parametrize("arguments", ["{", "not-json"])
```

oraz nieznaną nazwę i executor rzucający `RuntimeError`. Oczekiwany jest kontrolowany `ToolExecution.status == "error"` albo wynik z kluczem `error`, bez wyjątku wydostającego się z `send_message`.

- [ ] **Step 5: Napisać test Level 2 bez wykonania**

Zamockować narzędzie z `autonomy_level=2` i executorem `AsyncMock`, wywołać `send_message`, sprawdzić `pending_confirmation`, brak `await` executora i zachowanie argumentów w `ToolExecution`.

- [ ] **Step 6: Napisać test limitu iteracji**

Zwracać tool call w każdej odpowiedzi LLM, uruchomić `send_message` i sprawdzić, że `create` wywołano dokładnie trzy razy, a końcowa wiadomość ma tekst `Przetworzyłem dane. Czy potrzebujesz dodatkowych informacji?`.

- [ ] **Step 7: Uruchomić testy i poprawić minimalną implementację**

```bash
cd /opt/finanse/backend && .venv/bin/pytest tests/test_advisor/test_service.py -q
```

Expected: wszystkie testy PASS; jeśli test ujawni błąd, zmienić wyłącznie `service.py`/registry w zakresie opisanym w specyfikacji.

- [ ] **Step 8: Zrobić commit testów Doradcy**

```bash
git add backend/tests/test_advisor/test_service.py backend/tests/test_advisor/__init__.py backend/app/advisor/service.py backend/app/advisor/tools/registry.py
git commit -m "test: dodaj testy pętli tool-calling"
```

## Task 4: Izolowany PostgreSQL dla testów integracyjnych

**Files:**
- Modify: `backend/tests/conftest.py:1-39`.
- Modify: `Makefile:1-26`.
- Create outside repository: `/docker/finanse/compose.test.yaml`.
- Modify: `docs/JOURNAL.md` only at final documentation step.

- [ ] **Step 1: Dodać testowy compose poza repozytorium kodu**

Utworzyć `/docker/finanse/compose.test.yaml` z izolowanym serwisem:

```yaml
services:
  postgres-test:
    image: postgres:16-alpine
    container_name: finanse-postgres-test
    environment:
      POSTGRES_USER: finanse
      POSTGRES_PASSWORD: finanse
      POSTGRES_DB: finanse_test
    ports:
      - "127.0.0.1:55432:5432"
    tmpfs:
      - /var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U finanse -d finanse_test"]
      interval: 2s
      timeout: 5s
      retries: 15
```

Nie dodawać tego serwisu do produkcyjnego `compose.yaml` i nie używać wolumenu produkcyjnego.

- [ ] **Step 2: Uczytelnić fixture bazy**

W `conftest.py` ustawić:

```python
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://finanse:finanse@localhost:5432/finanse_test",
)
```

W fixture utworzyć `engine`, spróbować `create_all`, a `sqlalchemy.exc.OperationalError` zamienić na `pytest.skip(f"Test PostgreSQL unavailable at {TEST_DATABASE_URL}: ...")`. Flaga `schema_created` ma sprawić, że `drop_all` wykona się wyłącznie po udanym `create_all`; zawsze wywołać `engine.dispose()` w `finally`.

- [ ] **Step 3: Dodać targety Makefile**

Rozszerzyć `.PHONY` i dodać:

```make
test-db-up:

	docker compose -f /docker/finanse/compose.test.yaml up -d --wait postgres-test

test-integration: test-db-up

	cd backend && TEST_DATABASE_URL=postgresql+asyncpg://finanse:finanse@localhost:55432/finanse_test $(VENV)/pytest -v -m integration
```

Istniejący `make test` nadal uruchamia cały test suite; testy integracyjne oznaczyć markerem `integration`, a domyślny fallback 5432 zachować dla lokalnego środowiska.

- [ ] **Step 4: Oznaczyć testy wymagające PostgreSQL**

W testach korzystających z `db_session` dodać `@pytest.mark.integration`; w `[tool.pytest.ini_options]` dodać `markers = ["integration: requires PostgreSQL test database"]`.

- [ ] **Step 5: Sprawdzić ścieżkę Docker**

```bash
make test-db-up
TEST_DATABASE_URL=postgresql+asyncpg://finanse:finanse@localhost:55432/finanse_test make test-integration
docker compose -f /docker/finanse/compose.test.yaml down
```

Expected: testy integracyjne PASS, a po `down` nie zostają dane testowe ani kontener `finanse-postgres-test`.

- [ ] **Step 6: Zrobić commit fixture i targetów**

```bash
git add backend/tests/conftest.py backend/pyproject.toml Makefile
git commit -m "test: dodaj izolowaną bazę PostgreSQL dla integracji"
```

Plik `/docker/finanse/compose.test.yaml` nie jest commitowany, ponieważ infrastruktura Docker znajduje się poza repozytorium.

## Task 5: Polling statusów mutacji w frontendzie

**Files:**
- Modify: `frontend/src/api/advisor.ts:44-105`.
- Modify: `frontend/src/pages/Advisor.tsx:11-71,79-110`.
- Create: `frontend/src/api/advisor.test.ts`.

- [ ] **Step 1: Dodać czysty helper do decyzji o pollingu**

W `advisor.ts` dodać:

```typescript
export function hasPendingConfirmation(messages: Message[] | undefined): boolean {
  return messages?.some((message) =>
    message.tool_executions?.some((execution) => execution.status === "pending_confirmation")
  ) ?? false;
}
```

- [ ] **Step 2: Napisać testy helpera przed podłączeniem hooka**

W Vitest sprawdzić `false` dla `undefined`/pustej listy, `true` dla jednego pending execution oraz `false` dla `completed` i `denied`.

- [ ] **Step 3: Podłączyć polling do `useMessages`**

Ustawić w query:

```typescript
refetchInterval: (query) =>
  hasPendingConfirmation(query.state.data) ? 2000 : false,
refetchIntervalInBackground: false,
```

Pozostawić `enabled: !!conversationId`; dzięki temu polling zatrzyma się dla nieaktywnej rozmowy i po rozstrzygnięciu ostatniej egzekucji.

- [ ] **Step 4: Uściślić invalidation mutacji**

W `useConfirmToolExecution` i `useDenyToolExecution` przyjmować opcjonalny `conversationId` albo invalidować istniejące klucze dokładnie tak, aby aktywna rozmowa została natychmiast odświeżona. Zachować invalidation `advisor/conversations`. Typować wynik confirm jako `Message` i deny jako `{ status: string }`.

- [ ] **Step 5: Przekazać kontekst rozmowy z bannera**

Zmienić `ToolCallBanner` na propsy `{ message }`, a hooki mutacji wywoływać z `message.conversation_id`, tak aby invalidation mogło wskazać konkretny query key. Nie usuwać bannera po błędzie.

- [ ] **Step 6: Dodać komunikaty błędów i blokadę przycisków**

W `ConfirmButton` i `DenyButton` użyć `isPending`, a po błędzie pokazać krótki komunikat (`Nie udało się zatwierdzić.` / `Nie udało się odrzucić.`). Po sukcesie status bannera zmieni się przez invalidation i polling; nie utrzymywać osobnego, rozjeżdżającego się stanu statusu.

- [ ] **Step 7: Przetestować helper i hooki**

```bash
cd /opt/finanse/frontend && npm run test -- src/api/advisor.test.ts
cd /opt/finanse/frontend && npm run typecheck
cd /opt/finanse/frontend && npm run lint
```

Expected: testy PASS, TypeScript i ESLint bez błędów.

- [ ] **Step 8: Zrobić commit frontendu**

```bash
git add frontend/src/api/advisor.ts frontend/src/api/advisor.test.ts frontend/src/pages/Advisor.tsx
git commit -m "fix: odświeżaj statusy narzędzi Doradcy"
```

## Task 6: Weryfikacja całości i dokumentacja sesji

**Files:**
- Modify: `docs/CHANGELOG.md` — wpis na górze dla zmian z 2026-08-12.
- Modify: `docs/TASKS.md` — oznaczyć spłatę długu jakościowego jako zakończoną.
- Modify: `docs/JOURNAL.md` — nowy wpis sesji na górze.

- [ ] **Step 1: Uruchomić pełny lint**

```bash
make lint
```

Expected: backend Ruff i frontend ESLint PASS.

- [ ] **Step 2: Uruchomić pełne typowanie**

```bash
make typecheck
```

Expected: backend mypy i frontend `tsc --noEmit` PASS.

- [ ] **Step 3: Uruchomić testy z testową bazą**

```bash
make test-db-up
TEST_DATABASE_URL=postgresql+asyncpg://finanse:finanse@localhost:55432/finanse_test make test
docker compose -f /docker/finanse/compose.test.yaml down
```

Expected: pytest i Vitest PASS; po teście testowy kontener jest zatrzymany.

- [ ] **Step 4: Sprawdzić brak zmian niezamierzonych**

```bash
git diff --check
git status --short
git diff --stat
```

Oczekiwane są wyłącznie zmiany w plikach wymienionych w mapie planu oraz dokumentacji. Nie uruchamiać migracji, deployu ani operacji na produkcyjnej bazie.

- [ ] **Step 5: Zaktualizować dokumentację**

W `CHANGELOG.md` dodać sekcje `Changed`/`Fixed` o spłacie lint/typecheck, testach Doradcy, izolowanym PostgreSQL i pollingu. W `TASKS.md` dodać zakończoną sekcję jakościową. W `JOURNAL.md` opisać: cel, wykonane zmiany, decyzję o pollingu, wyniki komend oraz ewentualne znane problemy.

- [ ] **Step 6: Wykonać końcowy commit dokumentacji**

```bash
git add docs/CHANGELOG.md docs/TASKS.md docs/JOURNAL.md
git commit -m "docs: udokumentuj spłatę długu jakościowego"
```

## Kryteria ukończenia

- `make lint` kończy się kodem 0.
- `make typecheck` kończy się kodem 0.
- `make test` kończy się kodem 0 po uruchomieniu testowego PostgreSQL.
- Testy potwierdzają brak wykonania Level 2 przed confirm, idempotentność decyzji i izolację użytkowników.
- Polling trwa wyłącznie dla aktywnej rozmowy z `pending_confirmation` i zatrzymuje się po `completed`/`denied`.
- Dokumentacja sesji jest aktualna.
