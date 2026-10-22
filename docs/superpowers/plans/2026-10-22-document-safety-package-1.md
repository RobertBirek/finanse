# Bezpieczne dokumenty i retry OCR — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ograniczyć zużycie zasobów przy obsłudze dokumentów, naprawić limit uploadu i automatycznie ponawiać wyłącznie przejściowe błędy OCR.

**Architecture:** Modularny monolit pozostaje bez zmian. Walidacja plików przechodzi z wątku API do osobnego, ograniczonego procesu; PostgreSQL przechowuje harmonogram retry, Redis pozostaje mechanizmem dostarczania zadań. Dotychczasowe blokady i przekazywanie zweryfikowanych bajtów zostają zachowane.

**Tech Stack:** Python 3.12/Linux, FastAPI, SQLAlchemy/PostgreSQL, Alembic, ARQ/httpx, Pillow/pypdf, React/TypeScript, Nginx/Docker.

**Spec:** `docs/audits/2026-10-22-audit.md`, pakiet 1 (R01 + A01/A02), zatwierdzony kierunkowo przez użytkownika. Konkretne wartości poniżej są propozycją implementacyjną, nie wcześniejszą decyzją użytkownika.

## Global Constraints

- Bez deployu, migracji produkcyjnej, zmian `/docker/finanse/`, poświadczeń i `webapp/`.
- Nie nadpisujemy i nie usuwamy istniejących oryginałów. GC i retencja poza pakietem.
- Zachowujemy SHA-256 przed OCR oraz użycie tych samych zweryfikowanych bajtów.
- API i frontend zachowują statusy pending/processing/done/error; retry oczekuje jako pending z terminem kolejnej próby.
- Każdy limit aplikacyjny konfigurowalny przez Settings; brak cichego wyłączenia limitów w produkcji.
- Proponowane defaults: plik 20 MiB, całe żądanie uploadu 21 MiB, parser 512 MiB przestrzeni adresowej, 10 s CPU, 15 s wall-clock, 2 procesy parsera jednocześnie na proces API, najwyżej 2 s oczekiwania na slot.
- Proponowane defaults dokumentu: 100 stron PDF, 25 mln pikseli obrazu, 1 klatka; odpowiedź binarna OCR/konwersji 64 MiB, tekst OCR 2 MiB (UTF-8).
- Proponowane defaults retry: 3 próby kończące się kontrolowanym wynikiem, opóźnienia 30 s i 120 s. Crash/cancel workera pozostaje obsługiwany istniejącym recovery; nie deklarować trwałego licznika wszystkich uruchomień procesu.
- Proponowane defaults storage: 1 GiB logicznych dokumentów/użytkownika, 10 GiB łącznie i 1 GiB rezerwy wolnego miejsca. Istniejące nadlimitowe dokumenty pozostają dostępne; blokujemy tylko nowe unikalne pliki. To kontrola przyjęcia, nie systemowa quota filesystemu.
- API nie zwraca stack trace, ścieżek ani treści dokumentu w komunikacie błędu.
- Migrację tworzymy i testujemy wyłącznie w izolowanym środowisku. Wdrożenie nowego kodu z polami retry będzie wymagało osobnej zgody na migrację.

## Review Focus

1. Zabity/timed-out parser nie pozostawia procesu zombie ani zajętego slotu — Task 1.
2. Retry nie obchodzi mismatch SHA-256, limitu wyniku ani budżetu prób — Task 3.
3. Dwa uploady/worker deliveries nie obchodzą quota ani nie tworzą dwóch wyników — Task 2/3.
4. Limit OCR obowiązuje także bez Content-Length i dla odpowiedzi skompresowanej — Task 3.
5. Użytkownik widzi oczekiwanie na retry; 413/503 nie wygląda jak udany upload — Task 2/4.

## Task 1: Ograniczony proces walidacji

**Files:**
- Create: `backend/app/documents/validation.py` — interfejs rodzica, limity, spawn/timeout/cleanup.
- Create: `backend/app/documents/validation_process.py` — wejście procesu potomnego, rlimits, parsowanie.
- Modify: `backend/app/documents/service.py`, `backend/app/config.py`.
- Test: `backend/tests/test_documents/test_validation.py`, `backend/tests/test_documents/test_service.py`.

**Interfaces:**
- `async validate_document_content(content: bytes, declared_mime: str) -> str`: zwraca zweryfikowany MIME; błędny format/limit dokumentu → `UnsupportedDocumentFormatError`; brak slotu/niedostępny proces → `DocumentValidationUnavailableError`.
- Parser przekazuje przez stdin bajty pliku, przez stdout tylko mały wynik JSON (maks. 4096 bajtów). Żaden oryginał nie trafia do trwałego katalogu przed akceptacją.

- [ ] Napisać failing tests: poprawny PDF/PNG/JPEG, mismatch, ucięcia, encrypted/zero-page PDF, 101 stron, nadlimitowy obraz/animacja; zachować istniejący corpus.
- [ ] Napisać failing tests kontrolowanego procesu testowego: timeout/exit/error output, anulowanie rodzica i brak slotu; po każdym przypadku slot odzyskany, proces zakończony i odebrany przez wait.
- [ ] Uruchomić testy, potwierdzić RED z powodu brakującej izolacji/limitów.
- [ ] Przenieść parser do subprocess bez shell/preexec_fn, z minimalnym środowiskiem (bez kluczy i DSN); ustawić resource limits przed importem parserów, ograniczyć stdout/stderr i concurrency. Timeout rodzica zabija i reapuje dziecko także przy cancellation.
- [ ] Zastąpić `asyncio.to_thread(detect_document_mime_type, ...)` interfejsem async. Walidacja nadal należy do store_document, również dla wywołań spoza routera.
- [ ] Sprawdzić GREEN i pełne testy domeny; lint/typecheck; review i mały commit.

**Granica bezpieczeństwa:** subprocess + rlimits izoluje awarię i ogranicza zasoby,
ale nie daje samodzielnie izolacji dostępu do filesystemu/sieci przy przejęciu
parsera. Nie nazywać tego pełnym sandboxem. Utwardzenie kontenera w Task 5 jest
drugą warstwą; pełny osobny worker bez sekretów może być kolejną iteracją.

## Task 2: Limit transportu, przyjmowania i miejsca

**Files:**
- Create: `backend/app/documents/upload_limits.py` — ograniczenie request body przed multipart.
- Modify: `backend/app/main.py`, `backend/app/documents/service.py`, `backend/app/documents/router.py`, `backend/app/config.py`, `frontend/nginx.conf`.
- Test: `backend/tests/test_documents/test_upload_limits.py`, `backend/tests/test_documents/test_service.py`, `backend/tests/test_documents/test_proxy_upload.py`.

**Interfaces:**
- `DocumentUploadBodyLimitMiddleware`: tylko ścieżka uploadu, licznik otrzymanych bajtów, 413 również dla streamu bez Content-Length; nie buforuje drugiej pełnej kopii całego body.
- `async enforce_storage_admission(db: AsyncSession, user_id: UUID, content_size: int) -> None`: po deduplikacji, przed zapisem bloba; 507 dla rezerwy dysku, 413 dla quota z bezpiecznym komunikatem.

- [ ] Testy RED dla requestu >21 MiB z/bez Content-Length i niezgodnym nagłówkiem; żadnego store/parse/OCR po odrzuceniu.
- [ ] Testy RED granic 20 MiB pliku, quota użytkownika/globalnej i wolnego miejsca. Małe konfigurowalne limity w testach, bez zapełniania dysku.
- [ ] Test dwóch konkurencyjnych uploadów na izolowanej DB: wspólna quota nieprzekroczona, duplikat nie nalicza ponownie zajętości.
- [ ] Implementować middleware i konfigurację; zachować kontrolę rozmiaru również wewnątrz store_document. Deduplikacja i quota w spójnej kolejności blokad (globalny advisory lock dla admission), przed zapisem nowych danych.
- [ ] Ustawić jawne `client_max_body_size 21m` wyłącznie dla uploadu; backendowy limit pozostaje obowiązkowy. Dokumentować zgodność override Settings z konfiguracją proxy.
- [ ] Izolowany Nginx + testowy upstream: 2 MiB dociera do upstream, >21 MiB daje 413. Bez requestów uploadu do produkcji.
- [ ] GREEN, pełne testy domeny, lint/typecheck, review i commit. Nie wdrażać zwiększonego limitu proxy oddzielnie od zabezpieczeń.

## Task 3: Bounded OCR i trwałe retry

**Files:**
- Create: `backend/app/documents/ocr_client.py` — bounded HTTP streaming.
- Create: `backend/app/documents/retry.py` — klasyfikacja i harmonogram.
- Modify: `backend/app/worker.py`, `backend/app/documents/models.py`, `backend/app/documents/service.py`, `backend/app/documents/router.py`, `backend/app/config.py`.
- Create: `backend/migrations/versions/<generated_revision>_document_retry_metadata.py` przez `/migration "document retry metadata"`; review autogenerate przed użyciem.
- Test: `backend/tests/test_documents/test_ocr_client.py`, `backend/tests/test_documents/test_retry.py`, `backend/tests/test_worker.py`, `backend/tests/test_documents/test_retry_migration.py`.

**Interfaces:**
- `async read_bounded_response(response: httpx.Response, max_bytes: int) -> bytes`: działa wewnątrz `client.stream`, limit liczony po dekodowaniu transferu/kompresji, przekroczenie → `OCRResponseTooLargeError`, zamknięcie streamu.
- `is_retryable_ocr_error(error: Exception) -> bool`: transport timeout/connect/read i HTTP 408/429/500/502/503/504 → true; integrity, malformed, output limit i pozostałe 4xx → false.
- `retry_delay_seconds(attempt_count: int) -> int`: bierze konfigurowaną sekwencję; walidacja konfiguracji spójna z max attempts.
- Nowe pola Document: `attempt_count` NOT NULL default 0, `next_attempt_at` nullable timestamptz, `last_error_code` nullable ograniczony string; indeks terminu/statusu. Brak zapisanych tekstów wyjątków.

- [ ] RED: duża odpowiedź z i bez nagłówka, skompresowany stream, 2 MiB tekstu (limit bajtów UTF-8), zamknięcie streamu po błędzie. Testy korzystają z mockowanych strumieni, bez Stirling/LLM.
- [ ] RED: 503 → pending/termin → dispatcher po terminie → success; przed terminem brak enqueue; po 3 kontrolowanych porażkach error. SHA mismatch i output limit od razu error, bez retry.
- [ ] RED: duplicate delivery, DB error, restart dispatchera, brak Redis i re-upload dokumentu w terminalnym error. Re-upload nie resetuje budżetu automatycznie; brak ukrytej nieskończonej pętli.
- [ ] Zaimplementować bounded streaming; przekazywać dalej wyłącznie zweryfikowane oryginały lub ograniczony wynik konwersji. Oddzielić błąd odczytu integralności od ogólnego OSError.
- [ ] Dodać metadata retry/migrację. Zachować zewnętrzny lock dokumentu; operacje mogące uszkodzić sesję wykonać w savepoint. Błąd kontrolowany nie może zwolnić locku przez globalny rollback przed zapisaniem stanu retry. Dispatcher wybiera wyłącznie pending z pustym lub minionym next_attempt_at oraz dotychczasowe stale processing.
- [ ] Test upgrade na istniejącym dokumencie i downgrade wyłącznie w nowej izolowanej bazie; żadnego resetu wspólnego/produkcyjnego schematu.
- [ ] GREEN, pełne testy backendu, lint/typecheck, review i commit. Crash recovery bez nowego durable lease nadal ma dotychczasową semantykę — nie rozszerzać pakietu po cichu.

## Task 4: Czytelne stany i regresje UI

**Files:**
- Modify: `backend/app/documents/schemas.py`, `frontend/src/api/documents.ts`, `frontend/src/components/DocumentList.tsx`, `frontend/src/components/DocumentUpload.tsx`.
- Test: `frontend/src/api/documents.test.ts`, `frontend/src/pages/Documents.test.tsx`.

**Interfaces:** DocumentResponse dodaje `attempt_count`, `next_attempt_at`,
`last_error_code`; nie dodaje nowego statusu ani ścieżek do wyjątków.

- [ ] RED: pending z next_attempt_at pokazuje „Ponowna próba”, terminal error nie obiecuje retry, 413/503 są ogłaszane jako alert i nie dopisują dokumentu do listy.
- [ ] Dodać pola i komunikaty, zachować polling oczekujących dokumentów; bez nowego przycisku manualnego resetu budżetu prób w tej iteracji.
- [ ] GREEN: Vitest, ESLint, TypeScript, build i regresja przeglądarkowa bez produkcyjnego backendu; review i commit.

## Task 5: Profil wdrożeniowy, gate i dokumentacja

**Files:**
- Create: `ops/document-hardening.compose.yaml` — wersjonowany, niewłączony automatycznie profil.
- Modify: `docs/operations/backup-restore.md`, `docs/CHANGELOG.md`, `docs/TASKS.md`, `docs/JOURNAL.md`.
- Test: `backend/tests/test_document_hardening.py` — test kontraktu profilu.

- [ ] RED test profilu: limity pamięci/CPU/PID backendu/workera/Stirling, no-new-privileges, cap_drop, jawny UID/GID aplikacji, brak opublikowanych portów parsera, brak Docker socket.
- [ ] Przygotować profil dla zatwierdzanego później deployu: backend 2 GiB/1 CPU/128 PID (dwa procesy parsera plus rodzic), worker 1 GiB/1 CPU/128 PID, Stirling 2 GiB/2 CPU/256 PID jako wartości startowe do testu staging. Sprawdzić budżet łączny hosta przed wdrożeniem; nie uznawać defaults za sizing produkcji.
- [ ] Udokumentować test zgodności UID i uprawnień uploads, read-only rootfs/tmpfs oraz wybór zweryfikowanego digestu Stirling. Nie zmieniać uprawnień istniejących plików ani nie wymyślać digestu; brak zgodności blokuje deploy, nie prowadzi do cichego cofnięcia hardeningu.
- [ ] Uruchomić `/test`, `/lint`, `/typecheck` i build; pełne integracyjne na izolowanej DB, Nginx smoke i kontenerowy test limitów bez produkcji. Użyć definicji komend opencode, gdy interfejs nie udostępnia bezpośredniego wywołania slash command.
- [ ] Niezależny review całej gałęzi: limity, semantyka retry, bezpieczeństwo migracji i zachowanie dotychczasowych testów SHA/deduplikacji.
- [ ] Uaktualnić dokumentację wynikami rzeczywiście wykonanych testów; osobno oznaczyć niewykonane kontrole runtime.
- [ ] Przedstawić diff, testy i plan wdrożenia do osobnej zgody. W tej sesji nie uruchamiać `/deploy` ani `/migrate` na produkcji.

## Poza zakresem

Policy engine AI, inne błędy finansów/projektów, dokument → transakcja, GC,
pełne przeniesienie pracy sieciowej poza transakcję DB, globalny lockfile,
automatyczne wdrożenie i zmiany danych historycznych. Readiness/alerty ogólne
pozostają osobną iteracją operacyjną, nie warunkiem potwierdzającym sukces tego kodu.
