# Weryfikacja odczytu dokumentów — odbiór 2026-11-02

## Zakres

Task 8 dodaje testy akceptacyjne dla syntetycznego obrazu, trwałego zadania
vision, ręcznego review oraz zbudowanego frontendowego dist z lokalnym fake API.
Żaden test nie używa prywatnego dokumentu, klucza ani sieci dostawcy.

## Odbiór końcowy — 2026-11-02

Kod odebrany lokalnie w `feat/financial-document-workflow`, ostatnia poprawka
`85e086c`. Osiem etapów oraz końcowy review i scoped odbiór poprawek zakończone;
nie pozostały otwarte Important/Critical w odebranym zakresie. Nie jest to zgoda
na merge, push, wdrożenie lub aktywację dostawcy.

- Najnowszy pełny gate: **1017 backend PASS, 8 proxy deselected, 10 znanych
  ostrzeżeń bibliotek; 308 frontend PASS**. Ruff/mypy/ESLint/tsc PASS.
- Build PASS; koordynator ponownie wykonał wszystkie projekty Playwright na
  końcowym kodzie `85e086c`: **93 PASS, 1 celowy desktop skip**. Wcześniejsza
  kontrola obu wersji vision desktop/mobile po dopisaniu kodów błędów: **18 PASS**.
  Artefakty ostatniego przebiegu: `/tmp/opencode/vision-controller-final-e2e/`.
- Końcowy review wykrył wyścig expected_epoch w CLI i niepełne zakończenie błędów
  vision. W `e815ba7` kontrola epoki i przejście są atomowe pod tą samą blokadą,
  terminalne zadania kończą dokument, polling śledzi tylko aktywną pracę, a cel CLI
  jest parsowany i porównywany z konfiguracją środowiska. Regresje obejmują dwie
  sesje CLI, quota/provider/config/paused/exhaustion oraz historyczny pending.
- `85e086c` domyka cztery rzeczywiste terminalne kody dostawcy jako „AI niedostępne”
  i awaryjny przypadek brakującej rewizji. Ostatni scoped review: Approved.
- Migracja schematu nie zmieniła się podczas końcowych poprawek; opisany niżej
  rzeczywisty dump/restore 29 tabel pozostaje właściwym dowodem.

Prywatne dowody wykonania i raporty przeglądów zachowane poza Git:
`/tmp/opencode/document-vision-20261102-evidence-85e086c/`.

### Rozstrzygnięcia koordynatora i koszt pomyłki

1. Zmiana modelu/celu unieważnia epokę i wymaga jawnego ponownego włączenia;
   koszt: dodatkowy krok operatora przy zamierzonej zmianie.
2. Publikacja przyjmuje opcjonalny zegar UTC, domyślnie rzeczywisty czas;
   koszt: niewielkie rozszerzenie interfejsu serwisu.
3. Jeden datowany test konfliktów używa stałego zegara swojego scenariusza;
   koszt: nie testuje w tym przypadku wszystkich dat bieżących.
4. Read-only review zapisanego zakresu uruchomiono równolegle z ostatnim testem;
   koszt: późniejszy delta-test wymagał osobnego scoped odbioru (wykonany).
5. CLI pozwala na cel zgodny z konfiguracją środowiska, nie na dopasowanie substringu;
   koszt: operator musi skorygować niespójny cel, nie ma cross-environment override.
6. Pozostałą lukę tego samego punktu terminalnego domknięto wąską kontynuacją;
   koszt: dodatkowy cykl regresji/gate, bez poszerzania funkcji.

## Dowody (2026-11-01)

- Backend: `test_vision_invariants.py` używa prawdziwego serwisu uploadu,
  worker'a oraz `httpx.MockTransport`; transport jest jedyną atrapą zewnętrznego
  dostawcy. Niepusty legacy ledger, konto/balance i inbox są serializowane przed
  uploadem, wykonaniem vision i ręcznym approval; named test starego obrazu
  sprawdza GET list/detail/review/original/preview i duplikat bez jobu/revizji/
  wywołania providera, a jawny POST vision jako jedyny tworzy job i call.
- Fix round 2 rozszerza tę samą niepustą macierz o ukończone operacje: po
  `prepare_vision_review(...successful-vision-retry)` snapshot legacy rows,
  wyliczonych balances i inbox jest identyczny zarówno po utworzeniu intentu,
  jak i po publikacji workera (revision 2 `ready`, drugi i ostatni provider
  call). Po `request_ocr_retry(...successful-local-ocr)` realny wrapper
  `worker.process_document_job` kończy job `local_ocr`, zapisuje `DocumentText`
  przez upsert, ale zachowuje SHA oryginału, metodę `vision`, ostatnią image
  revision/data/status i ten sam snapshot księgi/inbox/balances. Mockowane są
  tylko granice Stirling; text LLM i provider vision po local OCR mają zero
  dodatkowych wywołań.
- Fix round 3 zapisuje przed `successful-vision-retry` rzeczywiste
  `Document.sha256_hash`, `processing_method` i SHA-256 bajtów wskazanego pliku
  oryginału. Po publikacji retry worker test porównuje wszystkie trzy wartości
  z tym snapshotem, zanim rozpocznie local OCR.
- Frontend: `document-vision.spec.ts` uruchamia oba projekty Playwright na
  zbudowanym dist i stateful fake API: syntetyczny JPEG przechodzi przez
  `setInputFiles` i multipart POST do pending→ready; binarne private
  preview/original mają response/request assertions oraz link download; faktyczne
  HTTP 429 po POST AI pokazuje feedback i zachowuje ręczne pole. Pokryte także
  375/1440, jasny/ciemny motyw, pola dirty, pusta waluta, Escape z powrotem
  focusu do opener'a, overflow i kontrakt legacy PDF.
- Gate `task-8-completion-gate`, przez `finanse-refactor-testdb` na loopback
  `55432`: backend **1008 PASS, 8 deselected, 10 warnings**; frontend
  **302 PASS**.
- Gate `task-8-fix2-gate` na tym samym izolowanym `55432`: backend **1008 PASS,
  8 deselected, 10 warnings**; frontend **302 PASS**.
- Gate `task-8-fix3-gate` na tym samym izolowanym `55432`: backend **1008 PASS,
  8 deselected, 10 warnings**; frontend **302 PASS**.
  Ostrzeżenia są deprecations passlib/FastAPI, bez nowych failures.
- `npm run build`: PASS. Pełne Playwright Chrome (`/usr/bin/google-chrome`):
  **93 PASS, 1 expected desktop skip** w obu projektach; artefakty
  `/tmp/opencode/task8-all-e2e-completion`.
- Parser HEIF i disposable proxy upload: **3 PASS**. Oddzielny verifier migracji
  wykonał `7f8ce92bda94 → 92eef8e8086c` na testowym kontenerze: **29 legacy
  tables**, wszystkie kolumny/wiersze i hash originalu zachowane;
  `pg_dump -Fc`/`pg_restore --exit-on-error` oraz drugi dump/restore po upgrade
  PASS. Trzy własne bazy rehearsal usunięto; komendy/DSN są zredagowane.
  Dowód: `task-8-migration-verification.md` i machine evidence JSON.

## Ograniczenia i aktywacja

Atrapa providera: pokryta. Rzeczywisty provider/model, egress, retencja i koszt:
**NOT RUN**. Viewporty przeglądarki: pokryte; Android/iPhone/aparat/HEIC:
**NOT CERTIFIED**. Proponowane (nieaktywowane) wartości pozostają w binding
context: edge 2048, 4 MiB, timeout 60 s, concurrency 2, dwa podejścia, limit
50/dzień i lease 120 s.

## Axe and review

Skan Axe jest wykonywany przed zamknięciem review, wyłącznie dla
`.include('[role=dialog]')`, bez wyłączania `tabindex` ani
`label-content-name-mismatch`. Wykryty kontrast linku pobrania poprawiono na
kontrastowy token; to nie jest certyfikacja całej powłoki.

Końcowy niezależny review przyrostu vision względem odebranego PR5 oraz scoped
review jego poprawek: **APPROVED**. Nie twierdzimy, że powtórzono przegląd każdej
niezmienionej linii PR5, wykonano realny provider call lub certyfikowano telefony.
