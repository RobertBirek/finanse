# Kategorie importów i oznaczenia transakcji — odbiór produkcyjny

## Zgoda i zakres

Użytkownik: „scal, wypchnij do main i wdróż”. Zatwierdzony appcommitdb3a4b3:
ręczna kategoryzacja importowanych wydatków oraz opis/notatka/tagi/projekt.
Spójny backend/worker/frontend i addytywna migracja3254a4781542←84fdbd10aa18.
Bez importowania wyciągów, przepisywania historii, zmiany polityk AI lub testowych
mutacji danych finansowych użytkownika.

## Integracja i bramki

- Main76fbebf→9e17435 merge/push, remoteexactSHA. Trzy konflikty wyłącznie docs,
  zachowano oba wpisy. Kod backend/frontend/ops dokładnie zgodny zdb3a4b3.
- Świeży frontend667PASS/109plików,6E2EPASS375/1440, ESLint/tsc/buildPASS.
  Backend2429caseunion/444hash z implementacji tej samej sesji, brak zmian produktu
  po weryfikacji. Nowa migracja i readpaths dodatkowo sprawdzane na odtworzonejDB.
- Prywatny operator i dowody: `/tmp/opencode/annotations-deploy-db3a4b3`;
  docelowy release `/opt/finanse/webapp/releases/annotations-db3a4b3`.
- Poprzedni aktywny94211b2/schema84 verified-live, jego obrazy i override pozostają.
  Forward/rollback obejmuje pełną listę bazowy+prod+releaseCompose, bez zmian
  użytkownika/env/mountów/sieci lub usług danych.
- Wszystkie3obrazy gotowe, mandatorynonroot10001read/importgate exactimageIDsPASS;
  packagingproxy6PASS/11deselected. Existingprojectrefspreflight0invalid, configfreezePASS.
- Safetyreview1Critical/1Important rozwiązane jednym fixpass: brakowało artifactold
  rollbackCompose — przechwycony i porównany z pierwotnym render/config; migracja
  po timeoutcie musi zatrzymać demonowy kontener — ownedname/create/start/stop/wait/rm
  i blokada rollbacku przy niepewnym zatrzymaniu. RED2→GREEN5+REALsynthetictimeoutPASS.
  Docker zwraca lowercase„no such object”; false-negative po usunięciu syntheticID
  wyjaśniony i porównanie uniezależnione od wielkości liter, próba powtórzonaPASS.
  Minorprivacy już spełnione0700/0600, bez rozszerzania uprawnień. Bez drugiego review.
- GitHubCI main9e17435: run43306569775 był w toku przy odczycie; starsze76fbebf/a4d4228
  miały statusfailure. Lokalnych bramek nie utożsamia się z zielonym GitHubCI.

## Wynik wykonania

- WrapperEXIT0. Świeży szyfrowanybackup100dc2a9fcda32e144ab130230bd162c8fc127e3f3632ae9a40fc65487db6556,
  bez retencji; restorechecksumsPASS. Własny no-portclone: wszystkie76tablehash i uploads
  zgodne, ledger0. Migracja325 na kopii oraz nowyreadonlyannotations/search/category
  i stary942readonlyORM na325PASS. Rollbackaplikacyjny certyfikowany przed produkcją.
- Produkcyjna migracja84→325 zatwierdzona,3nowetabelepuste, wszystkie starewiersze
  w76tabelach bez zmian, ledger0. Namedmigrator zakończony/removed/absencechecked,
  prywatnyenvfile usunięty. Bez produkcyjnego importu/testowejtransakcji/oznaczenia.
-3apps exactimageIDs/db3, env/user/mounty/sieci i usługi danych bez zmian. HTTPS200,
  auth401, wszystkie assets byte-match, OpenAPIannotationsPUT i browserGET-only
 375/1440PASS. Screeny obejrzane bez overflow.29kontroli/303.60s:0ERROR/restartów,
  ledger0/workerready. Freshvalidate_final.pyPASS już po zakończeniu.
- Metadaneactive atomowodb3a4b3/schema325verified-live. Ownclone i plaintextrestore
  usunięte po ownership/idle/exactID, bezforce/prune. Backup/rollback zachowane.
- Dowody: `/opt/finanse/webapp/releases/annotations-db3a4b3/evidence/`.

## Certyfikacja i osobna uwaga CI

Runtime: PASS — sourceidentity/localquality, dokładneimageIDs, migracja/retention,
liveness/readiness, read-onlycriticalroutes oraz obserwacja.

GitHubCI: NIEPASS. Konkretny main9e job43306569775 zakończył frontend na
`npm audit --audit-level=low`:7podatności(6moderate/1high). Follow-redirects
GHSA-mrwp-f3q8-3g9p oraz minimatchGHSA-g3hv-75wg-m249 i zależny devtoolchain.
Backendjob był nadal w toku w chwili sprawdzenia. Lokalny dodatkowy odczyt npmaudit
timeout, więc nie jest dowodem stanu; dane pochodzą z pobranego GitHubjoblog.

Dependencylock/packagejson/backendrequirements nie zmieniały się względem94211b2.
To nie zmiana zależności tego release'u, ale nadal pilne ryzyko do odrębnego usunięcia.
Nie użyto `npm audit fix --force`, nie cofano aplikacji do identycznego zależnościowo
poprzednika jako pozornego rozwiązania. Zadanie zapisane w TASKS. Nie przedstawiać
lokalnych testów lub zdrowego runtime jako zielonego całego GitHubCI.

## Plan wykonawczy

1. Wersjonowane immutableobrazy/offlinebuild i obowiązkowy nonrootread/importgate.
2. Niezależny safetyreview operatora przed mutacją runtime.
3. Deployment-wideflock; ingress503, drain, stopbackend/worker, table/uploadhashes.
4. Świeży szyfrowany backup bez retencji i odtworzenie na własnym no-portclone.
5. Exactretention starego schematu, migracja klonu, wszystkie stare wiersze bez
   zmian/newtablesempty/ledger0. Readonly old942ORM na325 i noweAPI/projekcje.
6. Produkcyjna migracja nowym obrazem z dotychczasowym backendenv, po weryfikacji
   backup/clone/maintenance/stoppedwriters. Bez DOWN lub DBrestore.
7. Podmiana3apps, workerready i retention przed otwarciem ingress; readonlyHTTPS/
   auth/assets/OpenAPI/browser375/1440, minimum300s obserwacji/logs/ledger.
8. Atomowe active metadata, cleanup wyłącznie ownedidleclone i plaintextrestore;
   szyfrowany backup i rollback zostają. Wszystkie powyższe kroki zaliczone.

Rollback aplikacyjny do94211b2 z pozostawieniem addytywnego325 wymaga wcześniejszego
potwierdzenia kompatybilności na klonie. Nie ma zgody na downgrade lub odtwarzanie
produkcji z backupu. Awaria backup/migracji kończy się sprawdzonym rollbackapps,
nie niekontrolowaną naprawą bazy.
