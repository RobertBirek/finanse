# Wsparcie decyzji i porównanie OpenAI — plan implementacji

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Dodać cztery osobno testowane funkcje Personal Advisor w kolejności 1 → 2 → 3 → 5.

**Architecture:** Doradca komponuje typowane wyniki domenowe i wystawia je niezależnie od OpenAI. Wyjaśnienie jest drugą, jawną akcją; backend ponownie wyznacza fakty z ograniczonych parametrów zamiast ufać danym z klienta.

**Tech Stack:** Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy async/PostgreSQL; React, TypeScript, TanStack Query, pytest/Vitest.

**Spec:** `docs/superpowers/specs/2026-11-21-ai-decision-support-design.md`

## Global Constraints

- Tylko OpenAI, bez migracji, nowych zależności, modyfikacji domenowych przez funkcje i bez wdrożenia; telemetryka tylko istniejącą ścieżką.
- Kwoty w groszach. Odczyty uwierzytelnione i ograniczone do właściciela. POST ma istniejącą ochronę CSRF; akcje z OpenAI obejmuje ogranicznik.
- Fakty, kolejność i linki pozostają niezależne od odpowiedzi modelu. Użyj odpowiedzi strukturalnych, zwróć tekst i status, nie generuj HTML ani linków modelem.
- Każdy etap kończy się testem backendu i UI, `/lint`, `/typecheck`, `/test` zgodnie z projektem oraz selektywnym commitem. Testy wymagające PG uruchamiaj wyłącznie na zatwierdzonej izolowanej bazie lub CI.
- Uruchom implementację z czystej gałęzi na aktualnym `origin/main`; nie włączaj lokalnych notatek z checkoutu hosta.

## Review Focus

- Zadanie zamknięte, dokument zarchiwizowany lub płatność rozliczona nie powinny zajmować miejsca w rankingu (etap 1).
- Ostatni dzień horyzontu jest uwzględniony; termin poza horyzontem nie daje prognozy (etap 2).
- Już ujemne saldo lub pominięte zobowiązanie nie mogą dać komunikatu „bezpieczne” (etap 2).
- Zwrot, dzień graniczny i wielokrotne postings nie mogą zniekształcić porównania (etap 3).
- Jednostronny timeout lub brak tokenów nie unieważnia drugiego wariantu i nie staje się zerem (etap 5).

### Task 1: Priorytety Doradcy i wspólne objaśnienie

**Pliki:** nowe `backend/app/advisor/decision_support.py`, `decision_schemas.py`, `decision_explanation.py`; zmiany `backend/app/advisor/router.py`, `backend/app/work/service.py`; nowe `frontend/src/api/advisorDecisions.ts`, `frontend/src/components/advisor/AdvisorDecisions.tsx`; montaż w `frontend/src/pages/Advisor.tsx`. Testy w `backend/tests/test_advisor/test_decision_support.py` i `frontend/src/components/advisor/AdvisorDecisions.test.tsx`.

**Kontrakt:** `get_attention(db: AsyncSession, user_id: UUID, *, today: date | None = None) -> AttentionResult`; `GET /api/advisor/decisions/attention`. `AttentionResult` zawiera `as_of` i `items`; wpis ma `kind` (`payment`, `document`, `task`), `source_id`, `title`, `reason`, `due_date`, `href`. `POST /api/advisor/decisions/attention/explain` zwraca `status` (`ok`, `unavailable`, `no_facts`) i `text: str | None`. `explain_facts(db: AsyncSession, user_id: UUID, facts: dict[str, object]) -> DecisionExplanation` korzysta z zapisanej konfiguracji Doradcy.

- [ ] RED: dla zaległej płatności, dokumentu do decyzji, zadania po terminie i płatności jutro oczekuj kolejności typów `payment, document, task` i odrzucenia czwartej pozycji. Nie zwracaj rekordów obcego właściciela ani źródeł rozliczonych, zamkniętych lub zarchiwizowanych. Sprawdź pusty wynik oraz 401. W UI kliknięcie nie zapisuje danych, a błąd objaśnienia nie usuwa trzech pozycji.
- [ ] Uruchom testy i potwierdź, że brak endpointu lub widoku powoduje oczekiwaną porażkę.
- [ ] Zastosuj 7-dniowe okno prognozy, listę dokumentów do decyzji i właścicielskie zapytanie z filtrem terminu przed `LIMIT`. Ranking: zaległa płatność → płatność dziś → dokument do decyzji → zadanie po terminie → płatność w oknie, następnie termin, typ i identyfikator. Deduplikuj identyfikator zdarzenia, nie całą serię płatności. Linki aplikacyjne buduje kod; jeśli widok nie ma linku do rekordu, dodaj ograniczone przejście przez zweryfikowane ID lub użyj istniejącej listy z jasną etykietą. Do objaśnienia nie przekazuj tytułów użytkownika.
- [x] GREEN lokalnie; wspólny commit etapów 1–3.

### Task 2: Symulacja wydatku

**Pliki:** nowe `backend/app/finance/cashflow_scenario.py`; rozszerz kontrakty i router Doradcy z etapu 1 oraz `AdvisorDecisions.tsx`. Testy `backend/tests/test_finance/test_cashflow_scenario.py` i test UI etapu 1.

**Kontrakt:** `simulate_expense(forecast: CashflowForecastResponse, *, expense_date: date, amount_pln_minor: int) -> CashflowScenarioResult`; `POST /api/advisor/decisions/cashflow-scenario` i analogiczne `/explain`. Body: `expense_date` oraz dodatnie całkowite `amount_pln_minor` w obsługiwanym zakresie księgi. Odpowiedź: `baseline_minimum`, `scenario_minimum`, `first_negative_date`, `opening_balance_negative`, `next_payday`, `excluded_obligation_reasons`, `covers_day_before_payday`.

- [ ] RED: saldo otwarcia `25000`, salda 2 i 3 dnia miesiąca `20000` i `12000`; dla wydatku `15000` dnia 2 minimum wariantu to `-3000` dnia 3, baza zachowuje `12000`. Sprawdź koniec horyzontu, datę poza nim (422), dotychczas ujemne saldo, niepełne pokrycie i brak zawołań zapisu. W UI brak sugestii „bezpieczne” dla niepełnych danych.
- [ ] Uruchom testy i potwierdź oczekiwaną porażkę.
- [ ] Odejmij wydatek jedynie od sald zamknięcia w dniu wydatku i później; uwzględnij saldo otwarcia w minimum. Dla remisu wybierz najwcześniejszą datę. Nie powielaj wyliczania zdarzeń prognozy. Wywoławca pobiera istniejący `get_cashflow_forecast` i mapuje zmianę na DTO bez zapisu.
- [x] GREEN lokalnie; wspólny commit etapów 1–3.

### Task 3: Zmiany wydatków

**Pliki:** `backend/app/finance/reporting.py` (wspólna projekcja wydatków bez zmiany istniejących raportów), nowe `backend/app/finance/spending_comparison.py`; rozszerz router, schemat, hook i widok z etapu 1. Testy `backend/tests/test_finance/test_spending_comparison.py` i test UI etapu 1.

**Kontrakt:** `get_spending_comparison(db: AsyncSession, user_id: UUID, *, days: Literal[14, 30, 90], today: date | None = None) -> SpendingComparisonResult`; `GET /api/advisor/decisions/spending-comparison?days=30`. Rozdział przedziałów: `[today-2*days, today-days)` i `[today-days, today)`. Wynik: granice, `previous_total_pln`, `current_total_pln`, `delta_pln`, do pięciu zmian kategorii i do pięciu transakcji ze znakiem wpływu na różnicę, wskaźnik ucięcia. `/explain` przyjmuje wyłącznie `days`.

- [ ] RED: poprzednio wydatek `10000`; teraz zakup `18000`, zwrot `-2000` i transfer `50000`; oczekuj `16000`, delta `6000`. Uwzględnij datę zakupu różną od księgowania, równą granicy, wiele postings kont oraz rekord obcego właściciela. Przy pustej bazie nie pokazuj procentu jako zero.
- [ ] Uruchom testy porównania i istniejących raportów przed zmianą; tylko przypadki nowej funkcji mają być czerwone.
- [ ] Użyj daty zakupu z fallbackiem i warunku istnienia właścicielskiego konta budżetowego zamiast mnożącego JOIN. Sumuj podpisane postings wydatków przed limitem. Dla poprzedniego okresu odwróć znak przy liczeniu wkładu w różnicę; kolejność według wartości bezwzględnej i stabilnego ID. Ewentualne powtarzanie pokaż tylko jako etykietę sugestii na podstawie oddzielnych dat, bez przewidywania przyszłości.
- [x] GREEN lokalnie bez bazy; test PostgreSQL i regresje raportów wymagające bazy do CI. Wspólny commit etapów 1–3.

### Task 5: Porównanie modeli i promptów OpenAI

**Pliki:** nowe `backend/app/advisor/ai_benchmark.py` i `frontend/src/components/advisor/AIBenchmark.tsx`; zmiany `backend/app/advisor/ai_settings_router.py`, `backend/app/security/rate_limit.py`, `frontend/src/api/aiSettings.ts`, `frontend/src/pages/AISettings.tsx`; testy `backend/tests/test_advisor/test_ai_benchmark.py` i `frontend/src/components/advisor/AIBenchmark.test.tsx`.

**Kontrakt:** `POST /api/advisor/settings/benchmark`; `variants` zawiera dokładnie dwa wpisy (`model`, `instructions`), ograniczenia modeli według istniejącego `resolve_credentials` i instrukcji według limitu `PromptChange`. Przed pierwszym żądaniem uwierzytelniony router rozwiązuje oba warianty bez mutowania profilu. `compare_configs(owner_id: UUID, variants: tuple[BenchmarkVariant, BenchmarkVariant], *, credentials: tuple[AdvisorCredentials, AdvisorCredentials]) -> BenchmarkResult`. Wynik: `suite_version`, per-wariant i per-przypadek `status`, `matches_expected: bool | None`, `duration_ms`, nullable `input_tokens` i `output_tokens`. Pierwsza wersja porównuje ustawienia Doradcy; sześć pojedynczych wywołań na uruchomienie, bez ponowień, z istniejącym ograniczeniem czasu. Limit uruchomień skonfiguruj po stronie serwera.

- [ ] RED: dla tej samej pary wariantów atrapa widzi te same trzy przykłady, `store=False`, bez danych domenowych. Poprawne/niepoprawne odpowiedzi punktuj deterministycznie. Timeout jednego wariantu zachowuje drugi; brak tokenów to `null`. Niedozwolony model i przekroczenie limitu nie wywołują dostawcy. Nie zmienia się profil ani wersja promptu.
- [ ] Uruchom testy i potwierdź oczekiwaną porażkę.
- [ ] Użyj wersjonowanej biblioteki syntetycznej z trzema przypadkami o jednoznacznych wynikach: klasyfikacja zadania `task`, odmowa braku danych `insufficient_data`, wybór istniejącej referencji `A2`. Klient OpenAI jest przypięty do zatwierdzonego hosta i klucza skonfigurowanego dla Doradcy. Zapisz jedynie istniejące metryki `kind=test`, bez treści porównania; wynik UI jest przejściowy. Nie traktuj score jako dowodu jakości w produkcji.
- [x] GREEN i osobny commit `feat: porównuj konfiguracje OpenAI na syntetycznych przypadkach`.

## Odbiór całości

Etapy 1–3 sprawdzono łącznie, ponieważ wspólnie zmieniają router i widok
Doradcy; trafiają do jednego commitu. Benchmark pozostaje osobnym przyrostem.
Scenariusze RED → GREEN oraz próby UI ukończono lokalnie. Przypadki
zależne od bazy przeszły w zatwierdzonym CI na tymczasowym PostgreSQL.

- [x] Niezależny przegląd granicy kont, operacji tylko do odczytu, pieniądza w groszach, kosztów wywołań i informacji wysyłanych do OpenAI.
- [x] Dwa przebiegi UI na desktop/mobile; przetestuj działanie faktów bez OpenAI, błędy, klawiaturę i linki źródłowe.
- [x] Zaktualizuj `CHANGELOG.md`, `TASKS.md`, `JOURNAL.md`. Bez deployu; nie dołączaj prywatnych zmian hosta.
- [x] Potwierdzono testy PostgreSQL w [CI #44886741957](https://github.com/RobertBirek/finanse/actions/runs/44886741957)
  na `8b75579`: 11/11 zadań i 3136 testów backendu bez pominięć w JUnit.
