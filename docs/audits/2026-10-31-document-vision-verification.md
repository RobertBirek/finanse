# Weryfikacja odczytu dokumentów — 2026-11-01

## Zakres

Task 8 dodaje testy akceptacyjne dla syntetycznego obrazu, trwałego zadania
vision, ręcznego review oraz zbudowanego frontendowego dist z lokalnym fake API.
Żaden test nie używa prywatnego dokumentu, klucza ani sieci dostawcy.

## Dowody (2026-11-01)

- Backend: `test_vision_invariants.py` używa prawdziwego serwisu uploadu,
  worker'a oraz `httpx.MockTransport`; transport jest jedyną atrapą zewnętrznego
  dostawcy. Niepusty legacy ledger, konto/balance i inbox są serializowane przed
  uploadem, wykonaniem vision i ręcznym approval; named test starego obrazu
  sprawdza GET list/detail/review/original/preview i duplikat bez jobu/revizji/
  wywołania providera, a jawny POST vision jako jedyny tworzy job i call.
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

Końcowy niezależny review całej gałęzi: **PENDING (controller)**.
