# Wdrożenie pełnych ścieżek kategorii

## Zgoda i zakres

Użytkownik: „scal, wypchnij do main i wdróż”, następnie „dokończ”.
Rewizja `d09ee8a`; wyłącznie frontend. Backend i worker pozostają na `69ee8b7`,
schema `84fdbd10aa18`. Bez migracji, zmian danych, importów i restartów tych usług.

## Integracja i przygotowanie

- Fast-forward main `493bf48→d09ee8a`, zwykły push i dokładne remoteSHA potwierdzone.
- Świeży frontend648PASS, ESLint/tsc/buildPASS,6docelowych testów Playwright
  desktop/mobilePASS. Wcześniejsze80E2E mają dokładnie zgodne hashe źródeł.
  Backend/API/runtime dependencies/nginx bez zmian; nie powtarzano backendu.
- Niezmienny obraz przygotowany przez `ops/prepare_release.py`, build offline
  z kontrolą odczytu plików przez nginx. Pełny render Compose różni się wyłącznie
  image/build frontendu. Nie budowano i nie podmieniano backendu/workera.
- Backup szyfrowany `9eaf1fccfa346902dfd7d243b965840cac09e01c84581dbe0418c611bf210d47`,
  bez retencji/prune. Restore checksumPASS. Pierwszy odczyt przerwał limit narzędzia120s;
  wznowiono ten sam snapshot, bez powielania backupu i bez zmian produkcji.
- Własny klon PostgreSQL bez sieci/portów: restore76tabel/schema/upload archive,
  ledger0. Nie wykonywano restore na produkcji ani zatrzymywania backendu/workera.
- Safetyreview:2Important — atomowe końcowe metadane mieszanych rewizji oraz
  weryfikacja rollbacku. Naprawy skryptu operatora RED3KeyError→GREEN3PASS.
  Finalizacja wymaga browser/observation/live/backup/clonePASS, rollback potwierdza
  poprzedni obraz/HTTPS/auth i brak zmian pozostałych5kontenerów.

## Status wykonania

Frontend podmieniony. Publiczne HTTPS/health200, protectedAPI401,15plików dist
byte-match. GET-onlybrowser375/1440PASS, brak błędów JS, mutacji i overflow;
screeny obejrzane. Backend/worker/PostgreSQL/Redis/Stirling zachowują ID, obrazy,
mounty, starttime i liczniki restartów. Końcowa obserwacja minimum300sPASS:
brak błędów/restartów, ledger0 i workerready.

Atomowe active metadata z frontendd09ee8a/backend-worker69ee8b7 zapisano dopiero po
tych dowodach: **verified-live**. Własny klon idle/stopExit0/rm/absencePASS,
plaintext restore usunięty bezforce/prune. Backup i obrazy rollbacku pozostają.
Rollback: pełna lista base/prod + poprzedni `bill-declaration-69ee8b7/compose.active.yaml`,
`up -d --no-deps --no-build frontend`; bez restartu usług danych lub DBrestore.
Prywatne dowody: `/opt/finanse/webapp/releases/category-selects-d09ee8a/evidence`.
