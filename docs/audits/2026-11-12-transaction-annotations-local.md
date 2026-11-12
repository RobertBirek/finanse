# Oznaczenia opisowe transakcji — odbiór lokalny

## Zakres i zgoda

Użytkownik zatwierdził własny opis bez nadpisania źródłowego, notatkę, tworzone
podczas edycji i ponownie używane tagi oraz opcjonalny istniejący projekt.
Następnie zaakceptował plan i wykonanie natywne z jednym końcowym review.
Spec: `docs/superpowers/specs/2026-11-12-transaction-annotations-design.md`;
plan: `docs/superpowers/plans/2026-11-12-transaction-annotations.md`.
Bez zgody na merge/push/deploy lub produkcyjne zmiany danych.

## Postęp i dowody

- BASE8c6e79d w istniejącym linkedworktree. Poprzedni kod niezmieniony od pełnego
  odbioru2398backend/656frontend/8E2E. Unrelateddirtydocs/audity zachowane.
- Task1:951a981. Modele PostgreSQL annotation/tag/link, constraints owner i FK,
  canonicalproject_id zSETNULL, dynamiclimity i strictschematy. Migracja
  3254a4781542←84fdbd10aa18 wygenerowana przez Alembic; preflight invalidprojects
  odmawia zamiast poprawiać dane. Żadnego backfill źródłowych opisów.
- Task1RED: missingmodels; migrationRED3 pokazał nieprawidłową kolejność autogen
  (FK przed parentunique). Uporządkowano i usunięto unrelatedscheduledindexdrift.
  GREEN8 i powtórzone8PASS, Ruff/mypy195PASS. Testy rzeczywistego Alembic upgrade
  chronią źródło i jawnie odrzucają missing/foreignprojectref bez czyszczenia.
- Task2:c094fdc. RED18: nieistniejący GET404 i legacyimportPATCH200. Dedykowany GET/PUTannotations
  i GETtags, owner/snapshot/version/receipt/audit, sources bez uprawnień finansowych.
  FirstGREEN17PASS/2fixtureFAIL przez odczyt ORM ID po rollback (MissingGreenlet).
  Naprawiono tylko helper testowy przez inspect.identity; końcowy gate32PASS obejmuje
  rzeczywisty bankcommit/evidence/replay i regresje kategorii/dat/paragonów/pożyczek.
- Task3:846962b. RED4→GREEN4, gate28PASS (również oryginalnysearch/ruleexact/Actualpin).
  Batched projekcja list/account/detail/search i mutationresponses; EXISTS dla q
  nie mnoży wierszy. Sourceopis nadal zasila reguły i importer, bez nowego discovery.
  Rozwiązano importcycle entities→queries→reads→annotations→ledger przez localbuilderimport.
- Backend pełny:2426PASS/3FAIL/0error/skip. Trzy przypadki starego testu bankowego
  nadal zakładały edycję sourceopisu, sprzecznie z zatwierdzonym nowym kontraktem.
  Zmieniono tylko tę funkcję, wymagając denial legacyPATCH i nowej nakładki.
  Cały plik10PASS po ponownej normalnej kolekcji. Końcowa unia2429PASS/0fail/error/skip,
  exactJUnit,444hash; AST potwierdza niezmienione inne testy/fixtures oraz cały produkt.
- Frontend nowehook/dialog/oznaczenia; legacydataeditor osobno, bez nadpisania source.
  RED2missingmodule/legacyRED4→GREEN17. PendingbackdropRED1→Dialogbusy. Walidacja
  FastAPI422arrayRED1+Reacterror→bezpiecznytekst, focused18PASS. Pierwszy pełny666PASS;
  końcowy667PASS/109plików po ostatnim teście i poprawkach, ESLint/tsc/buildPASS.
- Pierwszy E2E4PASS/2FAIL: exactlabelProjekt liczył także tekst options w zagnieżdżonym
  label. Dodano explicituseId/htmlFor. Kolejny test kwoty uwzględnia sąsiadujące
  textnodes bez whitespace (sprawdzone w traceDOM, nie zgadywane). Final6E2EPASS:
  annotations+importedcategory+splitcategory na375/1440, zero realAPI.
  Screeny obejrzane, bez poziomego overflow; wysoki formularz na telefonie przewijany.
- Ruff/mypy198PASS. Jeden końcowy review ses_e2e7ef90dffeu351PXrWjRvqAt:
  0Critical/1Important/0Minor/Declinednone. Jedna uwaga rozstrzygnięta poniżej na
  podstawie jawnej zgodności legacyAPI w zatwierdzonej specyfikacji; bez zmiany
  produktu po pełnej weryfikacji. Dodatkowe10regresji zgodnościPASS, frontend667PASS
  ponowiony przed commitem. Końcowyproof444backend/299frontendhash zgodny ztestami.
  Cleanup18własnychidlecontainersPASS. Warningbundle>500kB,
  passlibcrypt/argon2version i Starlette422aliasdeprecation jawne, nie nowe błędy.

## Rozstrzygnięcia autora

- Niedostępne slashcommands zastępują równoważne komendy we własnym no-portPG/runner.
  Koszt: konfigurację bezpieczeństwa runnera trzeba sprawdzać ręcznie.
- Nie powtarzano poprzedniego pełnego baseline bez zmiany kodu; nowy pełny suite
  jest obowiązkowy na końcu. Koszt: baseline opiera się na sprawdzonym sourceidentity.
- ORM relacje nakładek mają lazyraise, explicitbatchloading w publicznych odczytach,
  nie globaleagerselectin — stare migracje i ich narzędzia pracują przed nowymi
  tabelami. Koszt: wszystkie readpaths muszą jawnie załączyć projekcję, co testujemy.
- Odpowiedź zawiera także original_description/project_name dla formularza znającego
  tylko transactionID, bez dodatkowego magazynu danych. Koszt: większy response.
- Projekt blokowany przed transakcją, zgodnie z kolejnością PostgreSQL FKSETNULL przy
  DELETE projektu. Koszt: projektrowlock utrzymywany dłużej, bez odwróconego deadlocka.
- Stary kontrakt źródłowego opisu celowo zmieniony na osobną nakładkę: legacyklienci
  muszą korzystać z annotationsPUT. To zatwierdzona ochrona importu, nie osłabienie
  testu w celu ukrycia błędu.
- Zachowano wynik pełnego suite przez podmianę wyników tylko jednego ponowionego
  pliku testowego. AST dowodzi identyczności pozostałych funkcji/fixtures, hashe
  całego produktu bez zmian; exact2429JUnitunion. Koszt: mniejsza kontrola wpływu
  kolejności między plikami niż w jednym serialrun.
- Review wskazało, że legacyPATCH nadal pozwala właścicielowi zmieniać ręcznie
  napisany opis transakcji FX lub wpisu powiązanego z pożyczką. Specyfikacja jawnie
  pozostawia legacyAPI wpisów ręcznych (wiersz43), a chroni oryginalne opisy importów.
  Regresja `test_linked_loan_date_change_rejected_and_description_remains_editable`
  wymaga właśnie tego zachowania. Nakładka nie zmienia istniejących uprawnień
  kategorii/księgi, nie otwiera legacyPATCH i nie nadpisuje źródła. Rozstrzygnięcie:
  zachować zatwierdzoną kompatybilność, bez nowego globalnego zakazu ręcznych opisów.
  Koszt jeśli oczekiwano szerszej ochrony: stary klient API nadal może zmienić własny
  ręcznie napisany opis FX/pożyczki; globalne zamrożenie to osobna decyzja zgodności.
  Po ponownej ocenie nie jest nowym defektem tej funkcji. Nie odłożono drobnych uwag.

## Środowisko

Tylko własny disposablePostgreSQL bez sieci/portów i runner we wspólnej przestrzeni
sieciowej tego PG. Migrationfixture wymaga hexrole: początkowy roleann zastąpiono
własnym bank_import_task_aee20261112 i idle runner wymieniono bezforce/prune.
Produkcyjna baza i kontenery nie były używane. Cleanup18kontenerów po exactID/label/
noports/zeroactiveDBclients; stop/rm bezforce/prune, runnerexit143normalSIGTERM/PGexit0.
Zachowano branch/worktree i unrelateddirtydocs/audity. Lokalne commity tylko z tej
funkcji, bez merge/push/deploy. Wdrożenie wymaga oddzielnej zgody, migracji i jej
produkcyjnego preflight referencji projektów.
