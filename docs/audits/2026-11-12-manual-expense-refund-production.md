# Wdrożenie ręcznych zwrotów wydatków

## Zgoda i zakres

Użytkownik: „scal, wypchnij do main i wdróż”. Rewizja aplikacji `94211b2`:
backend, worker i frontend razem, ponieważ formularz korzysta z nowego endpointu.
Schema `84fdbd10aa18` bez migracji. Bez testowych zwrotów, importów i korekt danych.

## Integracja i przygotowanie

- main `0a3cb5b→a4d4228` przez merge, zwykły push i remoteSHA potwierdzone.
  Trzy konflikty dokumentacji rozwiązano zachowując oba wpisy historyczne.
  Kod backend/frontend/ops w main jest dokładnie zgodny z zatwierdzonym94211b2.
- Pełne dowody implementacji2375backend/655frontend/10E2E i hashe źródeł sprawdzone.
  Świeżyfrontend655/static/build/2targetedE2EPASS. Backend nie powtarzany bez driftu;
  uwzględniono jawny wcześniejszy101fixture-error→101PASS oraz finalfocused24PASS.
- Zależności, nginx, migracje i narzędzia wdrożeniowe bez zmian. Trzy obrazy
  zbudowane offline z rzeczywistych dotychczasowych runtime69ee8b7/d09ee8a.
  Pełny Compose zgodny poza3image/build, bez zmian env/user/mountów/sieci/hardeningu.
- Mandatoryverify_release: nonroot10001:10001, read/importPASS dla dokładnych
  gotowychimageIDs backend/workera.6rzeczywistych packagingproxyPASS/11deselected.
- Syntetyczne testy rollbacku2PASS: mieszane poprzednie rewizje i wymuszone odtworzenie
  frontendu usuwające maintenance; błędny obraz zatrzymuje potwierdzenie rollbacku.

## Status

Pakiet przygotowany. One safetyreview:3Important — gotowość workera rollbacku,
drift konfiguracji, współbieżne metadane. Jedna poprawka operatora: RED6→GREEN7;
workercheck, hash+fullrendergate, runtimeconfigcompare i deployment-wideflock/CAS.
Przy błędzie preflight bez rozpoczętej maintenance nie ma composeapply/rollback.
Bez zmian kodu produktu. Produkcyjna podmiana **zakończona i verified-live**.
Odczyt nowej definicji API używa backendowego loopback GET `/openapi.json`, ponieważ
nginx SPA przekazuje tylko `/api/*`, a publiczne `/openapi.json` zwracałoby index.html.
Publiczne HTTPS/auth/assets nadal sprawdzane przez właściwą domenę. Bez POSTrefund.
503/drain/stopPASS. Freshencryptedbackup bez retencji:
`9fd14fcbf0214e2f103cdfb9d42fdd921e48097533f22b8f46d432724f688827`.
Restorechecksum i własny no-port/no-network klon:76tabel/alltablehash/schema84/ledger0,
uploadshash i nowyORMreadonlyPASS. Podmieniono3apps, potwierdzono dokładneimageIDs,
env/user/mounty/sieci i pełną retencję danych przedotwarciem ingress.

Publiczne HTTPS/health200, protectedAPI401, distbyte-match oraz GET-onlybrowser375/1440PASS.
Screeny obejrzane, bez błędówJS lub overflow.29kontroli przez302.82s:0ERROR/restartów,
ledger0 i workerready. PostgreSQL/Redis/Stirling: identyczneID/starttime/restartcounts,
bez odtwarzania lub restartowania. Atomicactive94211b2/schema84 **verified-live**.
Własny klon idle/stopExit0/rm/absence i plaintextrestorecleanupPASS, bezforce/prune.
Backup i wszystkie obrazy rollbacku zachowane. Bez realnych zwrotów testowych.

Rollback: pełna lista base/prod + poprzedni
`category-selects-d09ee8a/compose.active.yaml`: backend/worker69ee8b7 i frontendd09ee8a,
bez DOWN lub DBrestore. Metadane przełączane dopiero po weryfikacji runtime.
Prywatne dowody: `/opt/finanse/webapp/releases/manual-refund-94211b2/evidence`.
