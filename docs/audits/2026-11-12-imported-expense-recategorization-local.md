# Ręczna korekta kategorii importowanego wydatku — odbiór lokalny

## Zatwierdzony zakres

Użytkownik zgłosił blokadę „Historia importu lub płatność pożyczki jest chroniona”
przy zmianie kategorii starszej transakcji. Przyczyna była zależna od źródła,
nie wieku. Zatwierdzono odblokowanie ręcznej korekty kategorii importowanego
zaksięgowanego dodatniego wydatku PLN, bez pełnej edycji kwot/kont/dat. Płatności
pożyczek, FX, zwroty, przychody, transfery i nieznane źródła pozostają chronione.
Plan: `docs/superpowers/plans/2026-11-12-imported-expense-recategorization.md`.

## Rozwiązanie i granice

- Istniejący workflow kontekst → podgląd → świadome zatwierdzenie i idempotentny
  receipt, bez zmiany HTTPschema lub nowej permissionflag w przeglądarce.
- `allow_imported=False` jest nadal domyślne w eligibility/response/build_preview.
  Wyłącznie ręczne get/preview/apply używająTrue. Reguły, AI i płatności paragonów
  nie uzyskują uprawnienia do automatycznej zmiany historii.
- Manual/document_payment zachowują obecne zachowanie, explicitmanual może edytować
  actual/bank_import oraz własne Actualmapping. Obcy mapping lub bank evidence,
  loanlink lub nieprawidłowy kształt księgi nie daje uprawnienia.
- Bankowe dowody są odczytywane/lockowane i wiążą snapshot podglądu. Ich zmiana
  między podglądem/zapisem wymaga nowej decyzji. Dotychczasowe snapshoty bez dowodów
  zachowują ten sam kształt. Strona kontowa, jejID/timestamps/waluta/kurs/kwoty/
  kierunek/budgetflag i saldo pozostają dokładnie bez zmian.
- TransactionID/source/daty i referencje importu pozostają; `updated_at`, ręczna
  proweniencja oraz audit dokumentują korektę. Zmienia się raport kategorii/budżetów,
  nie suma kosztu. Historyczne konto może pozostać archiwalne.
- Replay bankowego commitu zachowuje poprawioną kategorię, accountposting/evidence
  i pierwotny receipt. SourcearchiveActual/pinnedmanifest nie są przepisywane.
  Reimport wymagający ścisłego uzgodnienia z oryginalną taksonomią może jawnie
  odmówić uzgodnienia — nie odtwarza starej kategorii ani nie zgaduje mapowania.

## Dowody i stan

- Baselinefrontend655PASS. BackendRED:7brakcapabilityFAIL/8guardPASS plus2błędy
  syntetycznego loanfixture (wymaga oddzielnych kont, poprawione tylko dane testowe).
- Pierwszy focusedgreen:51PASS/3testfixtureFAIL przez odczyt wygaszonego updated_at;
  dodano jawny async refresh przed snapshotem testowym. Nie poprawiano produktu
  obchodzeniem asyncguard. Końcowy focused:57PASS.
- Bank evidence drift RED1FAIL: apply zwracał200 zamiast409. Dodano wiązanie dowodów
  do snapshotu; test przeszedł w końcowym focused.
- Frontend656PASS/107plików, ESLint/tsc/buildPASS. UIprodukcja nie wymagała zmian:
  regresja allowedimport działa istniejącym edytorem.8E2EPASS375/1440: importedchange,
  protectedloan i dotychczasowe category/rulesworkflow. Screeny obejrzane, bez overflow.
- Jeden świeży review:0Critical/1Important/0Minor. Potwierdzono wyścig mapowań
  Actual: brakFK polymorphicentityID oznaczał, że blokada transakcji nie blokowała
  inserta mapowania. RED3 (insert/update/delete na drugiej sesji) → GREEN3:
  odczyt mapowań `FOR UPDATE`, importer `_store_mapping` blokuje transakcję przed
  insertem mapowania transakcji. Po zakończeniu review legalny insert znów działa.
  Bez drugiego review; pełny backend po poprawce2398PASS/0fail/error/skip,
  8izolowanychPG i pełna kolekcja katalogu przed rozłączną selekcją plików.
  ExactJUnitcaseunion2398 i zgodne425sourcehash+osobnyhashimportera79afcb47…;
  frontend294hash zgodne z656vitest/8E2E. Standardowyproxyinfra poza kolekcją
  backendu, bez zmianyinfra w tym zadaniu.
- Ruff/mypyPASS193sourcefiles; istniejące ostrzeżenia: passlibcryptdeprecation,
  frontend chunk >500kB. Bez migracji, zmian zależności lub produkcyjnych zapisów.
- Cleanup20ownidlecontainers po ownership/exactID/noports/zeroactiveDBsessions,
  bezforce/prune. Operatorcleanup: docker top wymagaPID, użyto pid,args;
  runnerSIGTERMexit143 iPGexit0 prawidłowe. Nie pozostały żadne taskcontainers.

### Rozstrzygnięcia wykonawcze

- Minimalna poprawka obejmuje `_store_mapping` w skrypcie Actual, choć plan
  dopuszczał zmiany importera warunkowo przy replay. Bez wspólnej blokady nie da
  się zamknąć phantominsert; koszt ewentualnej nadmiarowości: oczekiwanie importera.
- FX/refund/full-edit pozostają poza zakresem, zgodnie z akceptacją; nowe przypadki
  wymagają osobnej funkcji. Review nie oceniało pełnego suite — bramka należy
  do wykonawcy i wymaga dowodu przed commitem.
- Slashcommands nie są dostępne przez narzędzia tej sesji. Użyto równoważnych
  komend pytest/vitest/lint/types/build wyłącznie w odseparowanych środowiskach.
- Pełny backend rozdzielono na8rozłącznych grup plików po normalnej kolekcji
  conftest; dokładneJUnitcases i hashe dowodzą kompletności. Koszt wobec serialrun:
  mniejsze pokrycie zależności od kolejności między plikami.

## Integracja

Lokalna implementacja w linkedworktree od a145088. Unrelateddirtydocs/audity
pozostają poza zmianą. Nie scalano, nie wypychano i nie wdrażano. Usługi testowe
mają wyłącznie własne disposablePG/runner bez portów; żadnego użycia produkcyjnejDB.
