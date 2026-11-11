# Tasks

Backlog zadań ze statusami.

## Import harmonogramów — B odebrane lokalnie (2026-11-11)

- [x] B1: modele, strict DTO i migracja84fdbd10aa18 bez backfillu; backend2204PASS,
  JUnit0failure/error/runtime-skips, 14standardexcluded, 686hashzgodne; lint/typesPASS.
- [x] B2: parser VeloPDF;31testów/148parserregression/2235pełnybackendPASS, lint/types,
  JUnit0failure/error/runtime-skips i692hashPASS;2originals59+59rows sourcecomparePASS.
- [x] B3: diff/projekcja/ochrona historii — testy napisane przed implementacją;
  RED23FAIL/1PASS potwierdzony; implementacja diff/projekcji/409/ownerlock gotowa do
  GREEN, ruff/mypy187PASS. Focused24 i świeżyfrontend/static w toku, potemfullgate.
  UPDATEfocused24PASS143.66s (4realDBraces); uruchomiony affectedguards→static→pełny
  backend2259expected/JUnit/hashgate. BezB3commitu i bezstartuB4 przedwynikiem.
  FINAL2259PASS/14standardexcluded/0runtime-skips/696hashPASS; affected97/frontend596/
  ruff/mypy187/tsc/eslintPASS. B3 gotowe do lokalnego commitu/task-done.
- [x] B4: frozenpreview/aktywacja/history/receipts — testy napisane przed kodem.
  RED27FAIL/1PASS→GREEN28PASS320.70s, lint/typesPASS. Uruchomione finalneupdatedB4+
  sharedArequests/full2288expectedJUnit/hashgate i świeżyfrontend; bezB4commitu do wyników.
  BackendFINAL2288PASS/14standardexcluded/0runtime-skips/704hashPASS; focused45/staticPASS.
  Frontend595PASS/1DocumentArchive timeout; unchangedsource268hash iisolated4PASS;
  pełnyfrontendconfirmation/static po restarcie w toku, bez osłabiania testów.
  FINALfrontendconfirmation596PASS64.08s/eslint/tscPASS bez zmian kodu/asercji/timeoutów.
  B4 gotowe do lokalnego commitu/task-done, pierwotny timeout zachowany w dowodach.
- [x] B5: UI target/diff/confirmation/history, owner-scoped hooks i import z kredytu;
  REDfrontend/missingoriginalmetadata potwierdzone, focused/static w toku.
  UPDATEfrontend613PASS/eslint/tsc/buildPASS. Browser4FAIL(dotyczyłlocatoragetByLabel,
  DOMcomboboxpoprawny); zachowanaasercjawartości, rerunrolelocatorna tym samymdist.
  Backend2289expectedgate i browser/screenproof w toku, bezB5commitu.
  BackendFINAL2289PASS/437hash/JUnitPASS. Front613/static/build i4browserPASS, lecz
  visualreview wykazał mobileclipping; mocniejszytest2RED, gridminwidth/flexwrapfix,
  finalfreshfrontend/build/4browsergeometry w toku. B5nadalbezcommitu.
  FINAL2289backend/613frontend/static/build/4browser16.6sPASS;8screenów375/1440light/
  darkobejrzane,740sourcehash i15distproofPASS. B5gotowe do commitu/task-done.
- [x] B6: odbiór całości harmonogramów, E2E/retencja/runbook/finalreview.
  B5commita8fabf7/taskdone23PASS; realPDF→worker→activation→freshread RED1FAIL/2PASS
  wykrył brak statusu/licznika po aktywacji. Minimalnyfix→GREEN3PASS; pełnygate później.
  BaselineFINAL2292backend/613frontend/179E2E+1expectedskip/2Alembic/originalsreadonlyPASS.
  Jedenreview2Important: reopenreceipt i reparsecomparison. JednofixpassRED→GREEN,
  focused43backend/617frontend/12browser/static/buildPASS; nowyfullbackend2300expected
  iALL_E2E w toku. Nowe4screeny375/1440light/darkobejrzane,307fronthash i15distzgodne.
  FINALfrontendpo review617PASS/static/build/ALL_E2E183PASS+1expecteddesktopskip,
  source/distproofzgodne. Dozamknięcia pozostaje pełnybackend2300expected/JUnit/hash.
  ZAMKNIĘCIE:2300backendPASS/14standardexcluded/0runtime-skips;617frontend/183E2E+
  1expectedskip/static/buildPASS.747sourcehash/15dist/JUnitPASS,2Important naprawione
  jednymTDDpass,0Critical/Minor. A+B odebrane lokalnie; szczegóły i decyzje w raporcie
  docs/audits/2026-11-08-loan-schedule-import-local.md. Commit/task-done i cleanup własnych
  zasobów kończą sesję; gałąź/worktree pozostają, brak zgody na release produkcyjny.
  WYKONANE:commit8e77988/task-done11PASS112.81s, cleanup własnychPG/runner/wolumenuPASS,
  archiwum556plików bezprywatnychdanych + checksum. Brak pozostałych zadań etapu B;
  release/main/push/deploy/realnyimport wymagają osobnej decyzji użytkownika.
- Bez merge/push/deploy/migracji produkcyjnej i importu rzeczywistych harmonogramów.

## Import wyciągów i harmonogramów — projekt (2026-11-08)

- [x] Potwierdzić banki: Velo, ING, Revolut; Citi wyraźnie wykluczone.
- [x] Zatwierdzić formaty pierwszej wersji: tekstowe PDF Velo rachunku/karty,
  PDF ING Direct/oszczędnościowego, CSV Revolut PLN/EUR/USD, PDF harmonogramów.
- [x] Rozpoznać istniejący obieg dokumentów/księgi i prywatne próbki bez mutacji.
- [x] Spisać pełny projekt i przeprowadzić builder check; doprecyzować zachowanie
  historii Actual, kursów NBP, tożsamości preview i ochrony istniejących rat Q7.
- [x] Przedstawić i uzyskać akceptację całego opisu działania, nie tylko formatów;
  user „tak” po pełnym opisie, bez potrzeby makiet.
- [x] Przygotować i samodzielnie sprawdzić roadmapę oraz dwa plany implementacji,
  z kontraktami między etapami, TDD, pełną regresją i odrębnymi migracjami.
- [x] User zatwierdził plan i wykonanie w tej sesji (Native), z niezależnym końcowym review.
- [x] Po zajętym55432/5432 user wyraźnie zatwierdził własne kontenery PG+runner bez
  publikowania portów, z cleanup tylko własnych zasobów. Utworzono network-none PG16
  i runner we wspólnym namespace; safety gate testów nie zmieniony, produkcja nietknięta.
- [x] Etap A, zadanie1: kontrakty źródeł i komend, trwałe modele i owner-scoped staging.
  Kontrakty40PASS, staging+ownerFK51PASS, prawdziwy Alembic roundtrip+retencja1PASS;
  rozszerzony focused suite70PASS. Najnowszy lint/types PASS.
  Backend lint/types oraz frontend baseline568/lint/types PASS. Bazowy backend miał
  1861PASS/2błędy kontekstu Git w testach backupu; po environment-only poprawce cały
  backup module21PASS. Dodatkowe23testy runner-context/migration PASS; poprawiony pełny
  gate aktualnych źródeł zakończony1933PASS/zero runtime skips,14standard proxy deselected;
  JUnit i bieżący lint/types sprawdzone. Migracja6bd8758ebc7d tylko lokalnie,
  bez produkcyjnego upgrade. A1 zakończone, commit e4c6e20, final focused70PASS.
- [x] A2: prywatny upload PDF/CSV, hashe/ścieżki, ograniczony odczyt tekstu PDF,
  ochrona źródeł przed archive/delete/OCR/AI i frontend bez etykiety AI/OCR.
  Rozszerzone147backend, audyt i prywatny streaming HTTP2PASS; frontend569PASS,
  lint/types/build PASS. Pusty CSV wykryty testem RED i poprawiony. Końcowy focused150
  i pełny backend1971PASS (14standard proxy-deselected,0runtime-skips); JUnit i hashe
  wszystkich aktualnych źródeł zgodne ze zweryfikowanym snapshotem. Commit f58fdf1,
  finalny task-done150PASS510.88s.
- [x] A3: trwałe zadania/retry/lease fencing, worker bez transakcji DB podczas pypdf,
  zachowanie starej rewizji i dowodów przy ponownym odczycie rozliczonego źródła.
  Pierwsze21testów PASS; rozszerzone45 i pełne1992backend PASS, lint/types167filesPASS.
  JUnit/źródła potwierdzone; commit21ff9df i final task-done45PASS157.35s.
- [x] A4: parser Revolut CSV PLN/EUR/USD, dokładne kwoty/fee/stany i pełne surowe pola.
  Pierwsze92testy PASS; prywatne128wierszy/3waluty/all required checks PASS, mieszany
  CSV jawnie odrzucony. Focused124 i pełny2047backendPASS, lint/typesPASS, JUnit/hashe
  źródeł zgodne; commit00748c2 i final task-done99PASS7.48s.
- [x] A5: Velo rachunek PDF, pełna tabela/strony/daty/znaki/obroty/salda. Pierwsze30testów
  PASS; trzy dodatkowe regresje kompletności RED→fix. Prywatne3wyciągi/154wiersze
  i niezależne sumyDecimalPASS. Focused112 i pełne2064backendPASS, lint/types170PASS;
  commitc95cb14, final task-done33PASS3.31s; JUnit i hashe źródeł zweryfikowane.
- [x] A6: ING Direct; użytkownik jawnie odłożył oszczędnościowe (brak nieszyfrowanych
  próbek). 132parser testsPASS, lint/types171PASS; prywatne8Direct/292wiersze i sumy
  DecimalPASS. Pozostałe13DirectPDF szyfrowane są jawnie odrzucone. Pełne2081backendPASS,
  JUnit/hashe źródeł zgodne; commit524a237, final task-done61PASS0.97s.
- [ ] ING oszczędnościowe: osobne rozszerzenie po dostarczeniu nieszyfrowanej próbki;
  nie deklarować obsługi na podstawie hipotetycznego układu.
- [x] A7: Velo karta, jawne sekcje i niezależne metadane/minimum/termin.68testówPASS,
  lint/types173PASS;5prywatnych cykli/96wierszy zachowane,4zgodne/1jawnie blocked bez
  zgadywania deduplikacji. Pełny2105backendPASS/JUnit i hashe źródeł potwierdzone.
  Commit28403ec, final task-done43PASS206.45s; literówka ścieżki pierwszego task-done
  poprawiona bez powtarzania commitu. Nie ma jeszcze commitu finansowego/UI importera.
- [x] A8: owner-scoped decyzje/mapowania, kandydaci tylko sugestiami, zamrożone kursy
  i preview ze śladem źródeł/wersji/księgi. Kolejne23/33/38/43testyPASS. TDD napraw
  cache/membership races, metadanych karty, fee-only, powrotu do review i porównania
  candidate; końcowe288importer i pełne2151backendPASS, lint/types177PASS. JUnit i
  hashe źródeł zgodne. Commit6aa8f6d/task-done46PASS; zmienione wiersze po reparse blocked.
- [x] A9: atomowy commit/receipt/replay, zaufany adapter bankowy i dowody źródłowe.
  Testy RED przed kodem;16commit+3financialgroupsPASS,4races/linkPASS,5HTTPPASS;
  poprawki dodatkowychRED snapshotNumeric/datemetadata/bodylimit w finalgate.
  Focused+legacy429PASS/1FAIL(testCSRF nie włączał production); poprawiono tylko test.
  Pełny2188backendPASS(JUnit0fail/error/runtime-skips i zgodna kolekcja); źródła
  zgodne ze snapshotem. Frontend569/lint/typesPASS. Commita068a0c, finaltask-done45PASS.
- [x] A10: strony Import/review, per-file upload, mapowania/decyzje, readonly źródła,
  frozenpreview/confirm/receipt i linki z kont/kart/dokumentów.596frontend/lint/types/
  buildPASS,4UI375/1440light/darkPASS19s incl editor+keyboard, screenyobejrzane.
  Źródła245zgodne z manifestem, backendniezmieniony. Commitb3aa562/task-done67PASS.
- [x] A11: końcowe bramki PASS — backend2197/0runtime-skips/14standardproxy,
  frontend596/171E2E+1expectedskip/4themes, lint/types/build, Alembic-retencja.
  JUnit i manifest677plików zgodne;44prywatnepliki parser-only/hashbez zmian,
  niejednoznaczny cykl karty jawnieblocked. Runbook i raport lokalny gotowe.
  Jedenreview:2ImportantfixedRED→GREEN fd0e6a4,0Critical/Minor; affected49PASS.
  Commitad1b53f/task-done6PASS86.67s, dowody zarchiwizowane, cleanupwyłącznie
  własnych2kontenerów/1wolumenuPASS; obrazcache/worktree/niepowiązanezmiany zachowane.
- [~] Etap B: użytkownik „ok, działaj”; nowa osobna zgoda na własny PG+runner/wolumen
  bez portów i cleanup tylko tych zasobów. B1 w toku: testy modeli/migracji napisane
  przed implementacją, legacy paid/partial/past-unpaid i dane etapu A muszą pozostać.
  Świeży frontend596/lint/typesPASS; baseline backend i RED B1 w toku, bez zmian produkcji.
  UPDATEbaselinebackend36PASS; B1modele/realroundtrip7PASS, naprawiony wyłącznie seed
  testustarejmigracjiA (futureORMvsoldcolumns). Expanded44focused/static i pełnygate
  przedB1commitem; migracja84fdbd10aa18 wygenerowana, źródła686zamrożone.
  Expanded38PASS/6fixtureerrors (cross-conftest import) poprawione wyłącznie wfixturesB.
  Trwa correctedfocused→static→pełnybackend/JUnit/hashgate, B1bezcommitu, B2niezaczęte.
  CORRECTIONfixturecause: importconftest nie był potwierdzoną przyczyną. Probe wykazał
  zależnośćod rozdzielonych selektorów CLI; sąsiadujące zachowują wszystkie44testy
  i poprawneownerdefs. Pełna kolekcja2204+14standardexcludedPASS; nowygate w toku.
  UPDATE44focused/staticPASS; pełny2202PASS/2FAIL(legacy bill/loan migrationtests),
  bezruntime-skips. Testy przeniesione na realne ownedscratchAlembic przy zachowanych
  asercjach, productbytesbez zmian. Trwa focusednapraw, potem ponownyfullgate.
  Legacyfix3PASS28.31s, importylint poprawione; świeży static→3legacy→fullJUnit/hashgate
  w toku, bez nowego commitu. Własny PG/runner nadal aktywne na potrzeby etapu B.
- [ ] Osobna zgoda na merge/push/deploy, produkcyjną migrację lub realny import.

Projekt `docs/superpowers/specs/2026-11-08-bank-statements-and-loan-schedule-import-design.md`.
Plany `docs/superpowers/plans/2026-11-08-bank-imports.md` i wskazane w nim etapy A/B.
Etap A **odebrany lokalnie, nie jest wdrożony**; etap B niezaimplementowany.
Nie mylić z zakończoną operatorską konfiguracją Q7.

## Konfiguracja istniejącego kredytu Velo Q7 (2026-11-08)

- [x] Po ponownym odczycie dokumentów Google Drive uzgodniono zakres; Plan→Build
  i zgoda „ok, działaj”. Właściciel przypięty do wcześniejszego wyboru „Robert”.
- [x] Odczyt bez zapisu: istniejące aktywne konta Q7/VELOBANK w PLN, brak umowy.
  Nowszy harmonogram: 59 rat; zgodne hashe źródeł, sumy rat i łańcuch kapitału.
- [x] Walidacja 59 wierszy przez schematy wdrożonego backendu i odrzucenie 8 błędnych
  payloadów; brak połączeń DB w tej kontroli. Świeży szyfrowany backup PASS.
- [x] Kontrola skryptu i atomowy zapis umowy/harmonogramu; tylko powiązanie jednej
  istniejącej raty, bez nowych kont, postings, transakcji i odtwarzania nadpłat.
- [x] Odczyt po commit, retencja wszystkich istniejących wierszy 62 tabel modelowych
  i sald, źródłowy audyt agenta, widoczność w liście kredytów i końcowa dokumentacja.
- [ ] Osobne uzgodnienie zadłużenia i historycznych podziałów spłat z bankiem,
  gdy pojawią się brakujące dowody. Konfiguracja nie zamyka wcześniejszego audytu Q7.

Raport: `docs/audits/2026-11-08-velo-q7-configuration.md`.

## Typ konta karty i przegląd wielu kart (2026-11-08)

- [x] Zatwierdzony podział i plan w rozmowie, po Build „ok, działaj”; osobna zgoda
  na własny efemeryczny PostgreSQL bez portów/produkcji i cleanup tylko własnych danych.
- [x] Nowy typcredit_card odrębny odcredit, konto+profil atomowo, mały edit response,
  zbiorczy owner-scoped/current-ledger summary, ochrona wersji/PLN/loanlinks.
- [x] Migracja739144d5eaef tylko klasyfikuje istniejące profile; prawdziwy Alembic
  upgrade/downgrade/reupgrade zachowuje dane62tabel i księgę, genericcredit bez zmian.
- [x] Warunki w create/edit konta, lista wielu kart i przyciski; osobne rozliczenia,
  linki/reload/back, brak drugiej konfiguracji; cache odświeżany po zmianach.
- [x] Focused54backend/12E2E, pełne568frontend, lint/types/build PASS;
  TDD regresji URL, cache, atomic save i migracji; screeny desktop/mobile obejrzane.
- [x] Pełne165E2EPASS+1expectedskip,5.8min; oba viewporty i dotychczasowe moduły.
- [x] Niezależny końcowy review całej zmiany: brak Critical/Important/Minor.
- [x] Pełny backend1863PASS/zero runtime-skips,14standardowo wyłączonych proxy;
  JUnit/kolekcja/manifest źródeł, dokumentacja i końcowy odbiór lokalny PASS.
- [x] Cleanup tylko własnego PG i jego wolumenu po kontroli ID/nazwy/etykiety/mountów;
  potwierdzony brak, bez force/prune i zmian innych środowisk.
- [x] User „scal, wypchnij do main i wdróż”; osobne zatwierdzenie rewizji7801ba5,
  migracji00a9→739, backup/restore/maintenance i klasyfikacyjnego rollbacku739→00a9.
  FF/pushmain i trzy aplikacje wdrożone; retencja62tabel/ledger/summary/HTTPS/auth PASS.
- [x] Końcowy browser375/1440 i obserwacja316s/31checks, health200/restarty0/błędy0/
  ledger0naruszeń/Redisready PASS; atomowe active metadata, trwałe dowody i cleanup
  wyłącznie dwóch własnych restoreDB po kontroli OID/braku połączeń, bez force.
- [x] Po odrębnej zgodzie „masz dane skonfiguruj od razu” i wyborze „Robert” zapisano
  zgodne warunki na istniejącym profilu Velo: due17→12/grace56→57/version1→2;
  limit33600/APR14.50/cykl17 bez zmian. Retencja/pozycja/odczyt po commit PASS.

Raport `docs/audits/2026-11-08-credit-card-accounts-local.md`;
produkcja `docs/audits/2026-11-08-credit-card-accounts-production.md`;
plan `docs/superpowers/plans/2026-11-08-credit-card-accounts.md`.

## Karty kredytowe i plany ratalne (2026-11-07)

- [x] Uzgodniony zakres dla istniejącej karty Velo: limit33600PLN, APR14.50%,
  max57dni warunkowo, cykl18–17, domyślnie12, pierwszeństwo dat wyciągu.
  Stare plany zamknięte; nowe mają własne stopy i bankowy/szacunkowy harmonogram.
- [x] Po Plan→Build zgoda „ok, działaj” i osobna zgoda na własny offlinePG bez
  publikacji portów, używania wcześniejszych baz lub produkcji.
- [x] Lokalna implementacja ledger-backed limitów, wyciągów, planów, kosztów/korekt,
  spłat i ochrony powiązań; istniejące konto bez tworzenia drugiego zadłużenia.
- [x] Addytywna migracja sześciu tabel z guardem retencji; próba na własnej bazie:
  56 starych tabel i dane/kolumny/indeksy zachowane, pusty downgrade/reupgrade PASS.
- [x] UI/API/TDD, baseline1805 i backend przed review1841, frontend555 PASS.
  Jeden niezależny review; naprawy Important: klasyfikacja zwrotów i rozdzielenie
  kont kart/kredytów,3RED→4PASS. Pełny final gate ponowiony po naprawach.
- [x] Końcowy pełny backend1847PASS/555frontend/159E2E+1expectedskip, lint/types/build,
  źródła zgodne z manifestem. Naprawione również zachowanie publicznego kontraktu,
  późny retry po odpięciu kosztu i prywatność cudzego identyfikatora wyciągu.
- [x] Dokumentacja/instrukcja/raport, backend09d1d79/frontend7aa1629 lokalnie;
  cleanup wyłącznie dwóch własnych efemerycznych kontenerów i ich wolumenów.
- [x] Osobna zgoda „scal do main i wdróż” oraz „Tak, migracja i wdrożenie”:
  FF/pushmain020c229, dwa backupy/restore/próby migracji, produkcyjny schemat00a9
  i trzy nowe usługi. Retencja danych, ledger, public/auth/assets/browser PASS.
- [x] Końcowa obserwacja312s/31kontroli, logi/restarty0/health/Redis/ledger PASS;
  atomowe active metadata, trwałe dowody i dokumentacja wdrożenia. Cleanup tylko
  dwóch własnych restoreDB z kontrolą OID i braku połączeń, bez force.
- [x] Świadoma konfiguracja istniejącej karty, odrębna zgoda i wybór właściciela:
  `docs/audits/2026-11-08-velo-card-configuration.md`; bez przepisywania sald/historii.
- [ ] Uzgodnienie aktualnego zadłużenia z najnowszym wyciągiem, jeśli wymagane;
  nie utożsamiać zapisu warunków z takim uzgodnieniem. Starych planów nie odtwarzano.

Raport `docs/audits/2026-11-07-credit-cards-local.md`,
wdrożenie `docs/audits/2026-11-08-credit-cards-production.md`,
instrukcja `docs/operations/credit-cards.md`.

## Bezpieczeństwo pakietów backend/worker (2026-11-07, implementacja lokalna)

- [x] Po „ok,działaj” przygotować krótki zakres, nie implementację ani deploy.
  Przeczytano wymagane docs, aktualny prepare_release i jego testy; RCA z poprzedniego
  wdrożenia: archive extraction przyumask077→copieddirs0700→UID10001 import failure.
- [x] Zatwierdzić małą zmianę: user „tak”; copiedbackend dirs0755/files0644, zachowane wykonywalne
 0755, bez zmian bajtów/źródeł/prywatnego release root0700. Bramka gotowych obrazów
  przed rollout: rzeczywisty docelowy non-root UID/GID, networknone, syntetyczne env,
  import app.main/app.worker + odczyt źródeł; błąd blokuje przełączenie, bez fallbackroot.
- [x] TDD: umask077, nestedsource, executable, niezmienione hashe;
  syntetyczny obraz goodPASS/tamperedpermissionsFAIL, istniejące frontendguards nadalPASS.
  Sam test build/import offline, bez DB/Composeup/secrets/mounts/API/providerów.
- [x] Lokalnie przygotowane prepare_release + verify_release i obowiązkowa bramka
  w /deploy/runbook.46opsunit i6DockerPASS; realne obrazy tylko jako nowe offlineprobes.
- [x] Końcowy unit/static gate:931backendunit/540frontend/6Docker i lint/types PASS;
  niezależny review bez uwag. Raport `docs/audits/2026-11-07-release-nonroot-local.md`.
  DBintegrations nieuruchamiane; wczesne próby wyboru bezDB zatrzymane guardami,
  końcowy wybór wyłącza również6starych nieoznaczonych testów DB po nazwach.
- [x] Osobna zgoda „scal i wdróż”: FF+push main e8f6714 i aktywacja narzędzi na
  serwerze;931backendunit/540frontend/6Docker/staticPASS po scaleniu. Weryfikator
  sprawdzony z finalComposeusers/exactimages. Bez odtwarzania aplikacji lub migracji.
  Raport `docs/audits/2026-11-07-release-nonroot-integration.md`.

## Dokumenty ↔ płatności, etap 5A (2026-11-07, wdrożone)

- [x] Zgoda na przygotowanie najmniejszego zakresu po przeglądzie: user „ok, działaj”.
- [x] Read-only backend/frontend recon: obecne kwalifikacje, alokacje i replay,
  daty/ranking, kontrakty/UI, testy i luki; bez nowych uruchomień/testów produktu.
- [x] Projekt `docs/superpowers/specs/2026-11-07-document-payment-matching-design.md`
  po rozpoznaniu kodu; niezależny read-only builder check „nothing important left”.
- [x] Akceptacja pełnego zakresu: user „tak” 2026-11-07.
- [x] Szczegółowy plan `docs/superpowers/plans/2026-11-07-document-payment-matching.md`:
  cztery zadania TDD, dokładne interfejsy, scenariusze regresji i self-review pokrycia spec.
- [x] Akceptacja planu i wykonanie natywne: user „tak, natywnie”.
- [x] Zgoda na własny efemeryczny PostgreSQL bez publikacji portów: user „ok”.
- [x] Lokalny kod: addytywne evidence, daty/proweniencja, ostrożna nazwa-w-opisie,
  ranking i okno zakupu bez zawężania legacy, stany UI i ochrona aktualności wyboru.
- [x] TDD/regresje: 27 unit dowodów, 49 backend focused i 35 UI/API/detail focused;
  pełne1788backend/540frontend oraz lint/types PASS; build i focused24E2E PASS.
- [x] Całościowe153E2E PASS+1expectedskip i niezależny końcowy review bez uwag.
  Pierwszą próbę przerwał limit; wznowiony reviewer ukończył pełny scope bez zmian kodu.
- [x] Ostateczny lokalny odbiór i raport z decyzjami/ograniczeniami; commity lokalne.
  Dodatkowy stary DocumentList.test flake:539PASS/1FAIL→1isolatedPASS→540fullPASS,
  bez napraw niezwiązanego zakresu. Własny kontener testowy usunięty i brak potwierdzony.
  Na tym etapie bez produkcji; następnie osobna zgoda na merge/push/deploy poniżej.
- [x] User „scal, push do main i wdróż”: FF+pushmaina68d9e4 i wdrożenie trzech usług;
  freshbackup/restore, no-migration, HTTP/auth/assets/browser/logi/schema/ledger PASS.
  Raport `docs/audits/2026-11-07-document-payment-matching-production.md`.
- [x] Lokalna regresyjna poprawka prepare_release: normalizacja uprawnień skopiowanych
  katalogów backendu po gitarchive przyumask077 + bramka nonroot import przed rollout.
  Odebrana i następnie zintegrowana/aktywowana jako narzędzia e8f6714 bez restartu
  aplikacji. W wydaniu a68d9e4 naprawiono gotowy pakiet; próbę wycofano bez zmian danych.

## Edycja kodu koloru HEX (2026-11-07)

- [x] Zdiagnozować zgłoszenie: kod jest renderowany jako `span` we wspólnym pickerze;
  natywny wybór koloru/paleta działają, ale nie istnieje tekstowe pole HEX.
- [x] Zatwierdzić krótki plan: user „tak”; własny `#RRGGBB` (w tym czarny), wpisywanie/wklejanie,
  walidacja i synchronizacja palety/resetu w kontach/kategoriach; bez zmian danych.
- [x] Implementacja TDD:12RED/29oldPASS→41focusedPASS; tekstowy HEX i walidacja
  czterech ścieżek tworzenia/edycji, minimalny uppercasePATCH. Jeden review2Minor
  poprawione (16pxmobile/clipboardtest), końcowy518unit/145E2E+1expectedskip/
  lint/types/build/sourceSHA PASS. Dziedziczenie/reset/reload/black/paste sprawdzone.
- [x] Osobna zgoda użytkownika i wdrożenie dokładnego `ebe441e`: sam frontend,
  bez migracji. Backup/restore/schema/ledger/actualnginxreadgate/assets/browser/
  public200/health200/auth401/logi PASS. Backend/worker95f8380 i usługi danych bez
  zmian; active metadata wskazuje per-service rewizje i inheritedfullCompose.

## Kolory kont i kategorii (2026-11-06, wdrożone95f8380)

- [x] Po „działaj”: wybór palety/dowolnego HEX, automatyczny kolor konta,
  dziedziczenie najbliższego rodzica z nadpisaniem/resetem podkategorii; PostgreSQL,
  owner-scoped API, walidacjaHEX i addytywna migracja bez zmiany dawnych danych.
- [x] Spójne akcenty dashboardu, wykresy/słupki kategorii i budżetów, legendy;
  zachowane kwoty i semantyczne ostrzeżenia o przekroczeniu limitu. Frontend507testów/
  145browser+1expectedskip/lint/types/freshbuildPASS; źródła i testowanydist zahashowane.
  BackendownerAPI i addytywna migracja gotowe;1Importantreview downgraderetention
  poprawiony2RED→guard, bezdrugiegoreview. Końcowy pełny1734backendPASS/sourcefreeze,
  56starychtabelretain/newcolorsnull/downgraderetentionPASS. Poniżej osobny odbiór produkcji.
- [x] Końcowy lokalny odbiór testów/migracji/review:
  `docs/audits/2026-11-06-finance-colors-local.md`,1734/507/145+1skip/static/buildPASS.
- [x] Osobna zgoda użytkownika na dokładną rewizję `95f8380`, migrację
  `7b57 → f3a9`, maintenance i zweryfikowany backup. Bez kolejnego tree APPLY.
- [x] Wydanie produkcyjne95f8380/f3a9: trzy zgodne obrazy, jedna migracja, świeży
  fenced backup/restore, retencja56 tabel, ledger/uploads/polityki PASS. Maintenance
  zdjęty, publiczne200/health200/auth401/assets/browser375/1440/logi/dataIDs PASS.
  Prywatne pliki dist poprawiono na publicznie czytelne wyłącznie w obrazie; te same
  zaakceptowane bajty. Raport `docs/audits/2026-11-06-finance-colors-production.md`.
- [x] Osobne usprawnienie narzędzia release: normalizacja trybów publicznych plików
  dist po kopiowaniu prywatnego archiwum oraz gate odczytu jako użytkownik nginx.
  Po „tak, działaj”: copieddist755/644, source bez zmian, release root700; buildgate
  jako nginx dla index i wszystkich nestedassets.3unit/2Docker RED→GREEN,29ops/2Docker/
  Ruff/mypy147 PASS. Pełny1737backend/507frontend/static PASS, jeden read-only
  review bez blokad; źródła/hash active i siedem kontenerów/obrazów bez zmian.
  Obecny obraz naprawiony i odebrany; nie zmieniać ponownie działającej aplikacji.

## Drzewo kategorii (2026-11-06)

- [x] Przygotować pełny projekt/mapowanie do zatwierdzenia: wszystkie65kategorii i14nowych
  węzłów, dwa poziomy, zachowane ID/type/source i niejasne gałęzie historyczne HOLD.
  Spec `docs/superpowers/specs/2026-11-06-category-tree-design.md`; szczegóły prywatne
  w `/opt/finanse/webapp/category-designs/2026-11-06/`, nie publikować imion/ID w Git.
  Buildercheck: nothing important left; generator i niezależna rekonstrukcja parentIDPASS.
- [x] Uzyskać akceptację pełnego projektu. User „tak” na całość jako podstawę planu.
  Potwierdził też zakończenie migracji Actual; guard/mappings nie są zmieniane.
- [x] Przygotować odrębny plan operacyjny: `docs/superpowers/plans/2026-11-06-category-tree.md`.
  4zadania, testyTDD, źródłowe65→79, faktycznie30aktualizacji+14nowych, read-onlypreflight,
  atomowyreceipt/audit i próba na kopii. Self-review względem spec zakończony.
- [x] Uzyskać akceptację planu9f51686 i metody Native — user „tak”; osobny prywatny
  execution-approval, bez zmiany dawnego design-approval lub zgody produkcyjnej.
- [x] Wykonać plan: kompilator/guard/atomowyAPPLY/CLI i94operatorPASS; świeży encrypted
  backup/restore do własnej loopbackDB, realnemapowanie30updates+14creates/verify/replayPASS;
  produkcyjny READONLYpreflight65/no blockersPASS. Runbook gotowy. Whole-review1Important
  naprawiony7RED→GREEN (engine dopiero po walidacji); bez drugiego review. Pełny końcowy
  **1722backend/493frontend/lint/types PASS** (8proxy wyłączonych projektowym markerem).
  Powtórna próba zmienionego digestu i świeży READONLYprodpreflightPASS; sourcefreeze
  i wszystkie referencje zgodne z kopią. Operator odebrany lokalnie, nie wykonany na produkcji.
- [x] Osobna zgoda na dokładne produkcyjne APPLY po testach/próbie/backupie/preflight:
  user „tak” na30updates+14creates zmaintenance/finalbackuprestore. JedenAPPLY/receipt,
  79total/65oldIDs/35untouched/45audits, frozenref/ledger/HOLD/KEEP/global/filesPASS.
  Backup0c121fec+isolatedrestorePASS; samecontainers/images/config/active8121512,
  originalnginx/public200/health200/anonymous401/readonlyverifyapplied/jobs0/errors0PASS.
  Raport `2026-11-06-category-tree-production.md`. Marker/reguły/zgodyAI/konta/historia
  pozostają osobnymi decyzjami, nie skutkiem porządkowania drzewa.
- [ ] Osobno rozstrzygnąć historyczne FX, odsetki, bilans otwarcia/lokaty, niejasne Inne
  i duplikat podatku; nie naprawiać ich pod pozorem porządkowania drzewa.

## Powdrożeniowy przegląd finansów (2026-11-05)

- [x] Po zgodzie użytkownika i potwierdzeniu konta wykonać właścicielskie agregaty
  READ ONLY/rollback + publiczny browser375/1440 + przegląd kodu UI. Bez zmian danych,
  sesji, AI, grantów lub wdrożenia. Raport `2026-11-05-finance-readonly-review.md`.
- [ ] Osobno uzgodnić drobne poprawki UI: jednostka PLN w walidacji podziału, komunikat
  braku obrazu paragonu, ewentualnie zachowanie wyboru historycznej próby przy paginacji.
- [ ] Zalogowany test użytkowy na wskazanym koncie: wymaga legalnej sesji użytkownika;
  nie zastępować go przeglądem źródeł lub publicznego logowania. Kategoria techniczna,
  zgoda AI i reguły pozostają decyzjami użytkownika, nie skutkiem samego wdrożenia.

## Inteligentna kategoryzacja i daty zakupów (2026-11-03; wydanie 2026-11-05)

- [x] Wdrożenie i serwerowa aktywacja gotowych etapów1–4B po jawnym „tak” na exact8121512.
  Spójne3serwisy, sześćmigracji/schema7b57, backup a4ca11f6 + installedrestore/ledgerPASS.
  Zachowane dane32tabel/originalfiles/dataserviceIDs; aktywneAI3B/4Bepoch1, headersepoch4
  bez zmian, wymagane opt-in i ręczne zatwierdzenia nadal obowiązują. Brak historii/importu/
  mutacji finansowej w smoke. HTTPS/assets/auth/browser375/1440/logs/publicobservationPASS.
  Raport `2026-11-05-finance-production-release.md`; metadaneverified-active8121512.

- [x] Wykonać4A po akceptacji planu3be47c9: ręczne produkty, udziały rabatów,
  własne sklepy, bounded historia exact/prefix, wyszukiwarka wszystkich kategorii,
  immutable zatwierdzenia i osobny podział jednej pełnej istniejącej płatnościPLN.
  Odebrane lokalnie: backend09a624d/UI5ea6454; jeden whole-review, poprawka statusu
  aktualności dowodu4RED→5GREEN;1506backend/476frontend/static/freshbuild/131E2E+1skipPASS,
  exactsource/dist/migrationproofPASS. Raport `2026-11-04-receipt-items-local.md`.
- [x] Odrębne4B: user „tak” na przygotowanie projektu po rekomendacji następnego kroku.
  `2026-11-04-receipt-item-extraction-design.md`: odczyt wybranego obrazu na żądanie,
  jednorazowy dispatch/zgoda/limity, immutablepropozycja i jawny import do szkicu4A.
  Buildercheck zakończony: jawne anulowanie tylko przeddispatch i osobna zgoda nowejgeneracji
  pounknown. Po przekazaniu c147b85 user zatwierdził CAŁY projekt kolejnym„tak”.
  Plan `2026-11-04-receipt-item-extraction.md` gotowy:7zadań native/TDD, osobnyreadpurpose,
  contentkey/dispatchmarker/usage/cancel/worker/importlineage/UI, jeden końcowy review.
   User zatwierdził plan4a41000 kolejnym „tak”; nativeinline/TDD, implementacja1–6 lokalnie.
   Osobny cel defaultOFF, siedem tabel/migracja7b57f2f0bde6 tylko ownedtestschema,
   bounded adapter, durable start/cancel/quota/worker/recovery, immutable wynik/import/lineage,
   warning review i UI. Jeden whole-review1Important→2RED/GREEN: zachowanie niepewnej
   intencji po reload. Pełny1628backend/493frontend/lint/types/freshbuild/141E2E+1expectedskip
   PASS; exactsource/dist/migrationproof oraz commitybackendf9fe4c8/UI527e92a zgodne zgate.
   Raport `2026-11-04-receipt-read-local.md`. LOCAL/OFF; branch/worktree i Velo/Q7 zachowane.
- [x] Jedna syntetyczna próba rzeczywistego API4B: gpt-6.1-terra/HTTP200/1request,
   input2075/output221, net7200/1800,total9000,difference0,strictpayload i warnings0.
   Raport `2026-11-05-receipt-read-api-result.md`. Najpierw scopec6d687d i preflightSTOP
   przy braku reguły imagebilling; później user jawnie uchylił próg kosztu dla1call.
   10offlineguardtests/readonlyreviewPASS; aplikacja pozostajeOFF. Nie ponawiać tej próby.
- [ ] Prywatny pilot4B na właściwym zdjęciu paragonu (wydanie/serwerowa aktywacja już wykonane).
   To nie zostało wykonane w syntetycznej próbie. PDF/multipage/batch i etap5 dopasowania
   płatności nadal poza zakresem. Bez zmian produkcji, merge lub push.
   User dopuścił wcześniejsze zdjęcia; odnaleziony JPEG to faktura, a readonly query
   istniejących aktywnych źródeł receipt/imagePLN zwróciło0. Nie wysłano niczego doAI;
   prywatny test produktów pozostaje niewykonany, nie zastępować go eksportem faktury.
- [x] User2026-11-05 polecił wdrożyć i włączyć wszystkie gotowe funkcje. Preflight exact8121512
   obejmuje etapy1–4B,3serwisy/6migracji, serverAI z zachowaniem indywidualnych zgód.
   Snapshot7e2c0b91backupsuccess; restoredrillBLOCKED: host1865d90 nie zawiera produkcyjnej
   migracji2f. Potrzebna akceptacja exact8121512/scope/hostFF, naprawa checkoutdrift i PASS
   restore przed migracją/apply. Produkcja nadal8106532, AI nowych etapów nieaktywowane.
   Raport `2026-11-05-finance-all-production-preflight.md`; nie deklarować udanego deployu.
   Powyższy STOP historyczny: user zatwierdził exactSHA/scope/hostFF; restore naprawiony,
   wydanie8121512/schema7b57 wdrożone i odebrane. Aktualny raport produkcyjny wskazany wyżej.

- [x] Uzgodnić zakres w rozmowie: dokumenty/wyciągi, nowe kategorie do zatwierdzenia,
  split pozycji zawsze zatwierdzany, historia tylko nieskategoryzowana partiami,
  budżety według zakupu, uzgodnienie banku według księgowania. User po zmianie
  agenta z Plan na wykonawczego: „ok, działaj dalej”.
- [x] Etap1 lokalnie: daty/proweniencja, bezpieczna ręczna korekta, raporty/budżety
  i jawny fallback dla starych danych; backend+UI+review. Końcowe1205backend/
  420frontend/lint/types/build/105E2E+1expectedskipPASS; migracja84f28fe23ab8 tylko
  w izolowanymfinanse_test, bez backfillu/zmianyActualfingerprint/kwot/postings.
  Oba findingsreview (cacheowner/session i same-sessionrefresh) poprawione3RED→GREEN.
- [x] Etap2 lokalnie: zatwierdzane zmiany/splity kategorii,
  zachowanie strony kontowej i alokacji. Pełny plan656e9e6 zatwierdzony „tak”; lokalna
  implementacja native/TDD zakończona w9fef438. User po odbiorze63e2b9c: „ok, działaj dalej”.
  Buildercheck zakończony; spec/plan `2026-11-03-approved-category-splits*` zapisane.
  Kontekst→preview→apply, ręczna ponowna korekta/scalenie, receipt replay, ochrona
  Actual/loan/FX/pending; wspólny lock delete_category ma zamknąć wyścigSETNULL.
  Backendcontext/preview/apply/state/audit/receipt i UI są lokalnie; focused140backend
  oraz429frontend/lint/typesPASS, freshbuild/107E2E+1expectedskipPASS. Migracja2268
  tylko ownedtestschema/retentionPASS. Important whole-review: accountTOCTOU2RED→GREEN/
  focused28PASS. Końcowy pełny6gate1250backend/429frontend/lint/typesPASS i exactsource/
  dist/migrationproofPASS. Raport: `docs/audits/2026-11-04-approved-category-splits-local.md`.
- [~] Etap3: projekt trwałych propozycji, reguł, kontrolowanego LLM i zgód. User
  2026-11-04 zatwierdził wariant hybrydowy: automatyczne przypisanie tylko przez wcześniej
  zatwierdzone reguły dla nowych nieskategoryzowanych transakcji; LLM proponuje z
  uzasadnieniem, człowiek może zatwierdzić wybrane propozycje zbiorczo po przeglądzie.
  Pewność modelu nie daje prawa zapisu; manualne kategorie chronione. Nowe kategorie/
  podkategorie i splity zawsze wymagają akceptacji, historia tylko osobnym poleceniem.
  Pełny plan5e679b5 zatwierdzony kolejnym „tak”; lokalna implementacja3A i finalgate zakończone.
  Spec `2026-11-04-hybrid-categorization-design.md`; pierwszy plan3A
  `2026-11-04-approved-categorization-rules.md`: explicitmarker, exact reguły,
  osobnyorigin i outbox nowych wydatków.3B z propozycjami/LLM jest osobnym następnym
  krokiem, nie gotową częścią3A. Ustawienia/grant/origin/outbox/worker/UI są lokalnie,
  86focused +32worker/security/races/439frontend/lint/types/build/111E2E+1skip oraz2browser
  origin→manualPASS. Jedno whole-reviewImportant: account-history originRED→GREEN.
  Obowiązkowy fullgate po poprawce:1303backend/439frontend/lint/typesPASS, exactsource/
  dist/migrationhashPASS.3A gotowy lokalnie, nie całość etapu3. Raport
  `docs/audits/2026-11-04-approved-categorization-rules-local.md`.
- [x] Etap3A lokalnie: zatwierdzane reguły dla nowych ręcznych wydatkówPLN,
  technicalmarker/off, immutablegrant/origin/outbox/worker/UI i bezpieczne retry.
- [x] Etap3B lokalnie: trwałe propozycjeAI, limity/joby i ludzki
  przeglądu wybranej partii. User po odbiorze3A: „ok, działaj dalej”. Spec
  `2026-11-04-reviewed-ai-categorization-design.md` gotowy po read-only buildercheck
  („nothing important left”), zatwierdzony słowem „tak” po2dc69c4. Plan
  `docs/superpowers/plans/2026-11-04-reviewed-ai-categorization.md` zapisany i sprawdzony
  względem spec:5zadań, native/TDD i jeden końcowy review. Zatwierdzony kolejnym „tak”.
  Implementacja odebrana lokalnie: zgody/storage, creation-only job/dispatch/
  usage, kontrolowane peritem preview/apply/reject i UI zamrożonego przeglądu. Task1
  75focusedPASS, Task2 125focusedPASS, końcowy Task3 74focusedPASS; frontend456/lint/types
  i16nowych browsercasesPASS. Jedna migracja243aa1d9461c tylko w nowym ownedfinanse_test,
  bez backfillu. Jeden whole-review Critical0/Important0/Minor0. Pełny finalgate
  1406backend/456frontend/lint/types/freshbuild/127E2E+1expectedskip PASS; exactsource/
  dist/migrationproofPASS. Backend8a9560f/UI0347e58; raport
  `docs/audits/2026-11-04-reviewed-ai-categorization-local.md`.
  Realne providery/AI/historia i produkcja nadal wymagają osobnej zgody.
- [~] Etap4: projekt pozycji paragonów/rabatów/kontroli sum i zatwierdzania podziału.
  User po odbiorze3B: „ok, działaj dalej”; najtrudniejsze dopasowanie produktów do
  kategorii. Wskazówka z historii zakupów tego sklepu; bez niej pełna lista z wyszukiwarką
  filtrującą nazwy podczas pisania. Makieta odrzucona jako zbędna. Spec
  `2026-11-04-receipt-item-categorization-design.md` po buildercheck; rekomendacja autora:
  najpierw4A ręczne pozycje/historyhint/discounts/humanapply, potem4B odczyt pozycji.
  Obecny OCR nie ma produktów. Po buildercheck i commicieb972368 user zatwierdził
  dokument i5wyborów „tak”. Plan `2026-11-04-receipt-item-categorization.md` zapisany,
   sprawdzony względemspec:6zadań/native/TDD/jedno końcowe review, zatwierdzony kolejnym„tak”.
   4A zrealizowane i odebrane lokalnie w09a624d/5ea6454:1506backend/476frontend/131E2E+1skip,
   static/build/exactsource/dist/migrationproofPASS. Cały etap4 nadal wymaga osobnego4B;
   bez providerów/historybatch/produkcji. Raport `2026-11-04-receipt-items-local.md`.
- [ ] Etap5: lepsze dopasowanie dokument↔płatność mimo różnicy dat, bez dublowania.
- [ ] Etap6: jawne partie wcześniejszych nieskategoryzowanych transakcji, przegląd i odbiór.
- [ ] Osobna zgoda i procedura przed produkcyjną migracją/wdrożeniem, realnymi AI/OCR
  lub uruchomieniem historii. Obecna zgoda obejmuje lokalną implementację iteracyjną.

Spec: `docs/superpowers/specs/2026-11-03-smart-categorization-design.md`.
Odbiór etapu1: `docs/audits/2026-11-03-transaction-dates-local.md`.

## Usuwanie dokumentów — diagnoza (2026-11-03)

- [x] Po odbiorze8106532 użytkownik „zatwierdzam” na kierunek migracji/wdrożenia,
  następnie „akceptuję” na okno serwisowe i recovery zachowujące archiwum.
  Plan wydania: `docs/superpowers/plans/2026-11-03-document-archive-deployment.md`.
  Backup4e7b441f/installedrestore/izolowanyrehearsal92→2f/exactimages/12guardów/opsreview PASS.
  Jednorazowy apply810/schema2f, browser375/1440,11próbek/343s/logi/workerreadiness,
  finalsource/runtime/data/originalsproof PASS. Finalizacja13:53:23UTC; bez AI/OCR.
  Nie powtarzać apply/migracji ani nie uruchamiać starego rollbacku.
  Raport `docs/audits/2026-11-03-document-archive-deployment.md`. Bez hostmainmerge/push.
- [ ] OpsReviewMinor: w osobnym hardeningu zabezpieczyć manualny downgrade2f przed
  wyścigiem check→DDLlock z równoległą archiwizacją. Kontroler nigdy nie downgraduje,
  ogólny rollback odmawia; produkcyjny downgrade pozostaje niedozwolony.

- [x] Sprawdzić UI/API/FK i odtworzyć na syntetykach:13przypadków +2SQLSTATE23503
  probes. Ostatni produkcyjny409 ma approved/active powiązanie finansowe; bez DELETE
  na produkcji, treści dokumentu lub nowych AI/OCR.
- [x] Uzgodnić naprawę: czytelne blokady finansowe/aktywnej pracy, bez500 przy historii
  AI/OCR, spójny lifecycle z legacyOCR/review. Nie usuwać źródeł zatwierdzonych finansów,
  historii/audytu/usage lub oryginałów przez automatyczny CASCADE. Implementacja lokalna
  zatwierdzona jako archiwizacja; bez zgody na wdrożenie. Raport: `docs/audits/2026-11-03-document-delete-diagnosis.md`.
- [x] Bezpieczny wariant uzgodniony i zatwierdzony lokalnie: archiwizacja zamiast
  harddelete (także źródeł approved finansów, ale bez ruszania finansów/linków/plików),
  przywracanie, blokada aktywnej pracy, bez powtórnego AI/OCR. Spec i plan zapisane:
  `docs/superpowers/plans/2026-11-03-document-archive.md`. User„tak” na lokalną
  implementację/testy/review; jedna addytywna migracja tylko wfinanse_test. Stary backend nie
  rozumie archiwum — produkcyjny rollout/rollback wymaga osobnej procedury/zgody.
- [x] Lokalna implementacja archiwizacji: backendcommit8c96be6/417regresji/lint/typesPASS,
  UIarchiwum/restore/duplikaty, financeoriginalretainedE2E6PASS; po review2Important
  naprawione running-worker409 i prywatne cacheowner/session, frontend410PASS.
  Końcowy pełny gate: 1183backend/410frontend/lint/types/build PASS, E2E103PASS+1skip;
  zgodność źródeł/distu potwierdzona. Test starego headu migracji zaktualizowany,
  powtórny pełny gate PASS. Nie wdrażać ani nie uruchamiać migracji produkcyjnej.
- [ ] ReviewMinor: pominąć zbędne enqueue istniejącego terminalvisionjobu przy duplikacie
  starego archivedvisiondoc/statuspending. Claim już odrzuca archiwum/terminaljob,
  więc bez AI/OCR/usage lub zmiany widoczności; do poprawy wyłącznie efektywność kolejki.
- [ ] VisualMinor: na375px długi badge OCR zwęża widoczny fragment nazwy pliku;
  dać nazwie pełną pierwszą linię w wierszu. Pełna nazwa jest dostępna w podglądzie
  i etykiecie dostępności, brak overflow; nie blokuje bezpiecznej archiwizacji.

## Widoczność pracy AI/OCR i wynik odczytu (2026-11-03)

- [x] Potwierdzić brak payee_iban/sale_date w zapisanej revision5/ready (vision succeeded/1),
  bez eksportowania wartości lub nowego AI. Formularz obu pól nie gubi.
- [x] Uzgodnić lokalny zakres znacznika pracy AI/OCR i globalnego toastu; użytkownik
  zatwierdził implementację bez nowych wywołań AI lub wdrożenia.
- [x] Implementacja statusAPI, monitora Layout, wskaźnika i globalnych toastów: realny
  jobstate/identity, paginacja pracy poza50dokumentami, nawigacja/deep-link, dedup i
  izolacja sesji/użytkownika. ReviewImportant podglądu poprawiony4RED→GREEN;
  pełny1151backend/388frontend/lint/types/build i mockedE2E4desktop/mobile PASS.
  Po naprawie atrap akceptacji/statusu pełne E2E97PASS+1celowy skip; manifest źródeł
  i build PASS. Gotowe lokalnie, bez AI/OCR/push/merge/deployu.
- [x] Po zgodzie „tak, wdrażaj na produkcję”: wdrożyć dokładny69b6f3d, spójny
  backend/worker/frontend, po świeżym backup/restore i operations review. Zachować
  schemat, policyepoch4, prompt/schema2, dane i oryginały; bez AI/OCR/retry/migracji.
  Raport: `docs/audits/2026-11-03-document-processing-deployment.md`.
  Backup e0963350/installedrestore, opsreview/15guardów/exactimage203files+API,
  apply/HTTPS/assets/auth/browser375/1440/10próbek i finalreadonlyproof PASS.
  Metadane09:09:22UTC; rollbackd7a2432 zachowany, zeroAI/OCR/migracji/policychange.
- [ ] Osobno wyjaśnić, czy IBAN i data sprzedaży są czytelne w źródle; nie zgadywać
  brakujących wartości, nie zmieniać semantyki dat i nie ponawiać AI bez zgody.

## Migracja AI do OpenAI i wydanie produkcyjne (2026-11-02)

- [x] Po osobnej zgodzie na jedną dodatkową próbę AI: diagnostyka wskazała etap
  `amount`, pole `total`, typ `invalid_amount`; dokładnie 1 żądanie, bez ponowienia.
  Bez wartości faktury/odpowiedzi w raporcie. Oryginał, metadane dokumentu, rewizje
  i zadania bez zmian; usage +1, jednorazowy receipt +1, audit rezerwacji/zakończenia.
- [x] Użytkownik zatwierdził lokalną poprawkę kontraktu kwoty model → adapter → review:
  wzorzec dodatniej kanonicznej kwoty i instrukcja, bez zmiany walidacji finansowej,
  zgadywania lub zaokrąglania. RED27 → GREEN94; pierwszy pełny gate1146backend/
  335frontend/lint/types PASS. Scoped review zamknięty: opcjonalna kropka i `null`
  dla niejednoznacznych separatorów, 2RED → 95focusedPASS; końcowy gate1147backend/
  335frontend/lint/types PASS, dokładny manifest źródeł niezmieniony.
  Bez AI/OCR/deployu; konkretna postać błędnej wartości
  z diagnozy nieznana. Plan: `docs/superpowers/plans/2026-11-02-vision-amount-contract.md`.
- [x] Przygotowanie wydania d7a2432 zatwierdzone osobno, bez deployu/AI: źródła i gate
  sprawdzone, świeży build/E2E93PASS+1skip oraz backup9832d2c6/installed restore PASS.
  Pakiet zbudowany/digest-pinned,202backendfilesEachImage zgodneGit; exact image
  smoke21casesEachBackendWorker PASS/networknone/zeroAI/DB. Render bazowy zgodny,
  nowe etykiety prompt/schema i CAS policy wyłącznie nieaktywna propozycja. Stan
  produkcji bez zmian; operations review PASS. Raport:
  `docs/audits/2026-11-02-vision-amount-release.md`.
- [x] Użytkownik zatwierdził rollout d7a2432 + etykiety prompt/schema2 + audytowane
  policyCASoff/on bez AI/replay. Kontroler23offlinePASS, applyreviewPASS i hashbinding;
  jednorazowy apply PASS/exit0, policyenabled/epoch4 i data/originals/schemaPASS.
  Browser375/1440 i ponad5min/9próbek PASS; active-release atomowo06:10:33UTC,
  świeżeHTTPS/liveimageIDs/contractpolicyepoch4 PASS. Bez agentAI/retry. Raport:
  `docs/audits/2026-11-03-vision-amount-deployment.md`.
- [x] Użytkownik potwierdził lepszy odczyt po d7a2432; read-only revision5/ready,
  succeeded/1attempt. Brakuje IBAN i daty sprzedaży, nie deklarować kompletnego wyniku.
  Agent nie wykonywał kolejnej wysyłki ani reuploadu; dalsze braki badane osobno.
- [x] Późniejsza jawna próba lokalnegoOCR succeeded/1; odnotowany wyłącznie status,
  bez czytania tekstu/faktury lub twierdzenia o poprawności odczytu.
- [x] Lokalnyqualityprobe bezAI: potwierdzone ucięcie przez async images.normalize_image:
  pełny JPEG644947B vs65536Bprefix, missingEOI/OSError, hashprefixZGODNY zrewizjąAI.
  Rozdzielczość2048 sama nie jest wskazaną przyczyną; małe testy i wcześniejszy
  subprocess-onlysmoke nie ćwiczyły aplikacyjnej granicy odczytu strumienia.
- [x] Po zgodzie: naprawić boundedread-doEOF stdout konwertera, zachować limit+1/
  timeout/reap; regresje dużego syntetycznegoJPEG i chunkedpipe, realasyncAPIprobe
  bezAI/DB. Bez zmiany2048px/quality90 i bez automatycznego retry dokumentu.
  Userzatwierdził fullstream+PonówAI. Focused61backend33frontend/lint/typesPASS,
  trueasynccandidate/fullJPEG644947BdecodePASS, noAI/OCR. UIImportantreview4RED→GREEN,
  38frontendPASS; opswarunkowoApproved, finalny1080backend/335frontend/lint/types/
  build/93E2E+1skipPASS. Kod d9a5797 i dokładny pakiet/trueasyncstream/date/400smokePASS.
  Exactd9a5797 zatwierdzony przez user„tak”; runtimewdrożony, browser375/1440,
  10próbek/HTTPS/finalmetadata20:08:59Z PASS; usuwanie/history lifecycle poza tą poprawką.
- [x] Po retry5d5b82f: job succeeded/1, wynik incomplete/unreadable+missing_required_fields,
  errornull; UI nie daje PonówAI dla tego stanu. Po zgodzie uzupełnić jawnyretry i powód,
  bez automatycznegoAI/reuploadu lub fałszywej obietnicy odczytu. Zaimplementowane d9a5797.
- [x] Potwierdzić wynik jawnego PonówAI po d9a5797: `invalid_model_output`, a nie
  poprawny odczyt. Osobna zatwierdzona diagnostyka wskazała `total/invalid_amount`.
- [ ] ReviewMinor: wzmocnić test overlapstdin/stdout wymuszeniem wyjścia większego
  od typowej pojemnościOSpipe; istniejące dużeJPEG/chunk/pidreap regresjePASS.
- [ ] Zdiagnozowany DELETE500/ForeignKeyViolation po dodaniu trwałychjobów/rewizji:
  zaprojektować bezpieczny lifecycle usunięcia/archiwizacji zhistorią i blokadą źródeł
  finansowych/activejob; nie kasować zależności/audytu ręcznie w produkcji.
- [x] Diagnoza „AI niedostępne” po uploadzie: JPEG zapisany; odpowiedź dociera do
  ReviewFields, sale_date/value_error wywołuje nieobsłużony ValidationError poza
  bezpieczną granicą vision_client, recovery kończy attempts_exhausted po2próbach.
  Logi czytane tylko jako kody/pola/klasy, lokalna syntetyczna reprodukcja bezAI.
- [x] Po zgodzie: kontrakt datISO/null i bezpieczna obsługa całej konwersji odpowiedzi,
  bez rawValidationError/inputs wlogu oraz mylącego komunikatu braku dostępnościAI;
  testy syntetyczne regresji bez ponownej wysyłki prywatnej faktury doAI.
  Zatwierdzone; focused36backend51frontend/lint/typesPASS, niezależnyreviewPASS,
  16guardów+backup8d9d72db/restorePASS. Domknięty jawnyretry historycznej failedrewizji,
  bez replaynawejściu. Końcowy1070backend/325frontend/lint/types/build/93E2E+1skipPASS,
  source5d5b82f zapisany. Dokładny pakiet/8syntheticdatecases/4HTTPcodesPASS;
  userpotwierdził exactSHA5d5b82f. Runtimewdrożony, browser375/1440/10próbek/
  active-release18:34:03Z PASS; żadnego automatycznego odczytu starej faktury.
- [x] Po wydaniu5d5b82f użytkownik jawnie uruchomił PonówAI: model zwrócił incomplete/
  unreadable, co doprowadziło do diagnozy uciętej pochodnej; naprawione d9a5797.
- [x] Odtworzyć błąd na nowym JPEG udostępnionym przez użytkownika:3809248B,
  PillowMPO/2frames/4032x3024,primaryload+verifyPASS, dokładny produkcyjny parser
  odrzuca fmtMPO/n_frames2. Dowód offline bez AI/DB i zmiany oryginału.
- [x] Po zgodzie: obsługa rozpoznanego wariantu JPEG/MPO iPhone z głównym obrazem
  do pochodnych, zachowaniem oryginału i limitów; nie dopuszczać globalnie dowolnych
  multi-image. TDD na syntetykach, lokalna weryfikacja udostępnionego pliku, review,
  pełny gate i osobne bezpieczne wydanie. Userzatwierdził; rolaHDRgainmap potwierdzona.
  Kod/regresje lokalnie91PASS, dwa Importantreview zamknięte RED/GREEN, dostarczonyJPEG
  boundedparser/normalizerPASS. Pełny1057backend/316frontend/lint/typesPASS,
  kod45c8c2d zapisany; dokładny pakiet/privateJPEG i4kodysmokePASS. Pytanie o zgodę
  exactSHA zatwierdzone poleceniem „scal na main i wdróż”; hostmain FF8c2fa67,
  źródła identyczne zgate/świeże21testów/lint/typesPASS. Runtime45c8c2d wdrożony,
  browser375/1440 i10próbek obserwacji/metadanePASS; bez migracji/policychange.
- [x] Potwierdzić jedną rzeczywistą próbę uploadu z iPhone po wydaniu45c8c2d:
  JPEG zapisany/done; późniejszy odczyt AI ma osobny błąd daty opisany wyżej.
- [ ] ReviewMinor: uzupełnić bezpośrednie syntetyczne regresje brakujących/powtórzonych
  pól MPF; obecne testy obejmują korupcję zakresów/offsetów/typów/dependencies/EOI.
- [x] Zdiagnozować400 przy uploadzie faktury z biblioteki iPhone: błąd przedAI,
  genericUIerror; JPEG12MP na rzeczywistym parserze syntetyczniePASS. Ustalić format/
  wielkość i odtworzyć przyczynę przed poprawką; bez ponawiania prywatnej faktury doAI.
  Użytkownik: HEIF3024x4032/3,7MB — limity nieprzekroczone; białyHEIC12MP takżePASS,
  bardziej złożony syntetyczny HEIF3024x4032/3,6MB w izolowanym runtimePASS1,71s.
  Nadal potrzeba dokładnego powodu400; nie twierdzić, że konkretny upload został naprawiony.
  Oryginał udostępniony i zbadany lokalnie:3675697B/HEIF/3024x4032, decode i bounded
  validation takżeUID10001 PASS; zeroAI/DB/storage. Potrzebny bezpieczny powód400
  rzeczywistego żądania Safari, bo MIME/ewentualna konwersja w drodze nie są wlogach.
  Diagnostyka400 wdrożona w9369b5d po TDD/fullgate/review/backup/restore.
  Pozostaje jedna próba użytkownika i odczyt nowego komunikatu; nie ponawiać apply.
  Wynik próby: validation_failed; log dwóch odrzuceń pokazuje image/jpeg/3809248B,
  detectedunknown, a nie sprawdzony lokalnie HEIF3675697B. Następnie porównać ścieżkę
  wyboru oryginału przez Pliki; nie zakładać jeszcze uszkodzenia lub konkretnej konwersji.
  Próba przez Pliki też failed:12:50:25UTC,ponownieJPEG/3809248B. Pozyskać dokładny
  wybrany plik do lokalnej reprodukcji (bez AI/uploadu aplikacyjnego), nie ponawiać w ciemno.
- [x] Wdrożyć diagnostykę400:1036backend/316frontend/93E2E+1skip, lint/types/build,
  dokładne obrazy i źródło UI, HTTPS/assets/auth/browser375/1440 oraz10próbek PASS.
  Bez migracji, zmiany walidacji/polityki vision lub wywołania AI w diagnozie.

- [x] Użytkownik wybiera produkcję zamiast pilotażu oraz całe AI aplikacji na OpenAI.
- [x] Inwentaryzacja: doradca/tool calling, tekst/OCR i vision. Produkcyjna konfiguracja
  początkowo nie zawierała klucza OpenAI; sprawdzano obecność, bez wypisywania sekretów.
- [x] Użytkownik zatwierdził Sol dla doradcy i Terra dla ekstrakcji; klucz projektu
  OpenAI dodany poza czatem. Oba modele dostępne dla klucza (GET model200, bez generacji).
  Osobne ustawienia vision pozostają wymagane.
- [x] Dostosować klientów do wybranych modeli, w tym Responses dla narzędzi GPT6;
  zachować policy/audit/ręczny review, brak DeepSeek fallbacku i brak backfillu.
- [x] Odebrać84c9c27:1031backend/308frontend/lint/types/build/93E2E+1skip PASS;
  scopedreviewApproved, live syntetyczny Soltool i Terra tekst/review/image na obrazie PASS.
- [x] Regresje/mock transport oraz mały test syntetyczny rzeczywistego API, pełny gate,
  świeży backup/restore, rehearsal migracji i spójne wydanie backend/worker/frontend.
  Kod84c9c27 wdrożony, vision włączone (epoch2); browser/10próbek obserwacji/metadata
  i dodatkowybackup e037d2e8 zrestore PASS. Wydanie zakończone; nie ponawiać apply.
- [ ] Follow-up CLI: rejestracja wszystkich modeli SQLAlchemy przy bezpośrednim
  standalone uruchomieniu scripts.document_vision_policy. Wydanie używa jawnego
  operator bootstrap importapp.main przed CLI.run, również w trwałym rollbacku;
  odrębne uruchomienie bez rejestracji users ujawnia NoReferencedTableError audytu.

Statusy: `[ ]` pending, `[~]` in progress, `[x]` done, `[-]` cancelled

## Waluty i zobowiązania (2026-10-27)

- [x] Diagnoza dwóch zdjęć telefonu w podglądzie: upload poprawny, zapisany OCR
  nieczytelny przy tekście bokiem; review incomplete/llm_unavailable. Bezpośredni
  odczyt obrazów porównany po zgodzie, bez zapisów dokumentów lub płatności.
- [x] Uzgodnić i zaimplementować odczyt obrazów przez model wizyjny, normalizację JPEG przed
  OCR i rozdzielenie statusu zadania od jakości/gotowości review. Użytkownik wybrał
  automatyczne wysyłanie nowych zdjęć. Projekt automatic-document-vision2026-10-30
  po builder check zatwierdzony w całości; plan8 zadań i realizacja podagentami
  zatwierdzone31.10. Task1–8 i końcowe poprawki odebrane02.11; epoch CAS, terminalne
  statusy/polling i wszystkie findings zamknięte. Gate1017backend/308frontend PASS.
  Vision zamiast równoległego OCR, fallback lokalny tylko jawny. Następnie wdrożone
  na produkcję w84c9c27 po zgodzie użytkownika; preview bez zmian (AI nadal wyłączone).
- [-] Aktywacja vision w preview zastąpiona decyzją użytkownika o bezpośredniej
  produkcji i OpenAI. Prawdziwe Android/iPhone nadal do sprawdzenia; nie wysyłać
  ponownie dawnych prywatnych zdjęć bez osobnej zgody.
- [x] Zmiana decyzji02.11: bezpośrednia produkcja z całym AI OpenAI; dobór modeli,
  nowy runtime, backup/restore, rehearsal i jawna polityka włączona po odbiorze.
  Finalny kod84c9c27, bez push; obserwacja i atomowa aktualizacja metadanych PASS.

- [x] Zaprojektować wspólny obieg dokumentów finansowych przed rozszerzeniem Q7:
  użytkownik wybrał wyłącznie upload w aplikacji (bez Google/integracji), także zdjęcia
  faktur i paragonów aparatem telefonu. Ustalić rejestr faktur, termin/pozostałą kwotę,
  powiązanie opłaconych z księgą i nieopłaconych z Nadchodzącymi, bez podwójnego kosztu.
  Obecne Dokumenty/OCR/Inbox nie stanowią rejestru zobowiązań; projekt zaakceptowany.
  Użytkownik zatwierdził zmianę priorytetu: faktury/paragony przed Q7. Projekt
  `docs/superpowers/specs/2026-10-28-financial-document-workflow-design.md` gotowy,
  builder check po3 doprecyzowaniach bez istotnych pytań. Użytkownik zaakceptował zakres
  i obsługę HEIC/HEIF z lokalną konwersją do JPEG zamiast ręcznej zmiany formatu.
- [x] Przygotować plan implementacji dokumentów:10 zadań TDD, HEIC w ograniczonym
  procesie, rejestr/alokacje/cashflow, stare uploady, retry/IDOR/konkurencja i test aparatu.
  `docs/superpowers/plans/2026-10-28-financial-document-workflow.md`.
- [x] Użytkownik wybrał subagent-driven: niezależne wykonanie i review każdego taska.
- [x] Implementacja oprogramowania planu w linked worktree, gałąź `feat/financial-document-workflow`.
  Bazowy frontend243 PASS; backend858 PASS/8 proxy deselected na zgodnych zależnościach.
  Zadanie1 (HEIC/prywatny podgląd) zamknięte po poprawkach i ponownym review;
  backend867/frontend243 PASS, lint/types PASS. Zadanie2 zamknięte po rzeczywistym
  teście migracji i scoped review (backend874/frontend243). Zadanie3: odczyt/propozycje
  i obsługa istniejących uploadów zamknięte po poprawkach/review; backend886/frontend243
  i lint/types PASS. Zadanie4 rejestr/approve/duplikaty zamknięte po review, backend900/
  frontend243 PASS. Zadanie5 zakończone po review, backend915/frontend243 PASS.
  Zadanie6 ochrona księgi i operatorowego Actual zamknięte po review;
  backend924/frontend243/lint/types PASS. Zadanie7 coverage/Nadchodzące zakończone
  po poprawkach/review, backend933/frontend243/lint/types PASS. Zadanie8 zamknięte po
  poprawkach/review, backend934/frontend251/lint/types/build/browser PASS.
  Zadanie9 rejestr/rozliczenia/cashflow UI zamknięte po3rundachpoprawek/review;
  frontend278/lint/types/build, backend936 (bez późniejszych zmian backendu) PASS.
  Zadanie10 workflow/E2E/migracja/parser po poprawkach i review;
  końcowy gate941backend/278frontend/75E2E+1celowyskip, lint/types/build PASS.
  Bez zgody na deploy/import/korekty danych.
- [x] Całościowy przegląd bezpieczeństwa/zgodności gałęzi i zamknięcie raportu;
  4Important poprawione w0524cb9, scopedreview bez nowych findings,
  full949backend/279frontend/75E2E+1skip, lint/types/build i freshsyntheticrestore PASS.
- [ ] BLOCKED: rzeczywisty Android/iPhone aparat/galeria/dużeHEIC — brak urządzeń;
  viewport i syntetyczny parser nie zastępują certyfikacji telefonu.
- [x] Po zgodzie uruchomiono izolowany podgląd `https://finanse-test.birek.online`
  z osobnymi bazą/uploadami/OCR, fikcyjnymi danymi i bez LLM; HTTPS/API/browser/security
  PASS. Login przekazany poza repo. To nie zastępuje testu powyżej na prawdziwym telefonie.
- [x] Po osobnej zgodzie: push gałęzi i draft PR [#5](https://github.com/RobertBirek/finanse/pull/5)
  do `main`, bez merge/deploy. Przed push świeże949backend/279frontend/lint/types/build PASS.
- [x] Osobna zgoda na deploy/migrację produkcji02.11; lokalny main FF84c9c27 i spójne
  wydanie z aktywnym OpenAI. Bez przygotowania starych PDF/backfillu lub importów.

- [x] Nowe wyciągi28.10: inwentaryzacja46 plików, odczyt zakresów Velo/ING/Citi/
  Revolut, kontrola sald i nakładania źródeł, raport bez zmian produkcji.
- [x] Uzupełnione źródła Velo: sierpniowy rachunek i poprzednia karta do17.09.
  Q7: dokumenty pokazują rozdział wypłaty na Velo/ING; wrześniowa rata/nadpłata
  potwierdzone. Istniejące wpłaty i wrześniowe odsetki w snapshot — nie dublować.
- [ ] Nadal uzyskać historię RACHUNKU Velo01–28.10 (minimum01–06.10 dla spornych
  operacji, przez15.10 dla Q7); uzgodnić mapowania, podział rat i wypłatę kredytu.
  Powtórzenia wydruku karty rozstrzygać osobno; NO IMPORT / NO AUTO CORRECTIONS.

- [x] Osobna korekta waluty istniejącego konta po prośbie o EUR: potwierdzone kwoty
  źródłowe i zatwierdzona wycena PLN wg NBP; konto i obie strony6 operacji poprawione.
  Backend858/frontend243, lint/types, backup1732c2cc/restore/kopia/guard/audit i świeży
  odczyt PASS. Bez osłabiania globalnej blokady walut, importu lub deployu aplikacji.

- [x] Użytkownik zaakceptował kolejność: waluty, Q7, karta/Allegro Pay z odsetkami,
  pożyczki rodzinne, Goodie i darowizny. Nie zmieniać przy okazji historii Velo.
- [x] Slice walut: bezpieczny PATCH, capability, UI i testy konkurencji;
  backend812/frontend235/E2E47+1skip, lint/types/build PASS i review bez blokad
  w gałęzi `feat/account-currency`. Bez zmian produkcji.
- [x] Integracja/wdrożenie walut po potwierdzonym gate — razem z Q7 w9db255b (28.10).
- [x] Q7 jako pierwszy pionowy slice zobowiązań: plan kapitału, odsetek/opłat,
  harmonogram jako plan i przypisywanie rzeczywistych płatności bez duplikatów.
  Potwierdzono przypisanie dostarczonego harmonogramu do Q7. Projekt pierwszej
  iteracji (plan + link istniejących transferów, bez księgowania) przygotowany
  w `docs/superpowers/specs/2026-10-27-loan-schedule-design.md`; builder check zakończony,
  implementacja backend/frontend i targeted gate32 PASS; frontend243/E2E59+1skip PASS.
- [x] Po jawnej zgodzie28.10: pełny gate, integracja/main/push i wdrożenie obu slice'ów
  (waluta + Q7) z backup/restore i addytywną migracją. Bez importu i korekt historii.
- [x] Końcowa obserwacja wydania9db255b:10/10 PASS, brak restartów/błędów i zmian
  starych danych; atomowa aktualizacja metadanych runtime, rollback zachowany.
- [ ] Kolejny slice Q7: rzeczywiste księgowanie nowych spłat kapitału/odsetek/opłat,
  uzgodnienie historycznych transferów i niedublowana integracja z prognozą.
- [x] Podgląd59 rat Q7 z oryginalnego PDF, walidacja arytmetyki i kandydat pierwszej
  płatności; źródła i właścicielska księga/audyt bez zmian (wyłącznie READ ONLY).
- [x] Porównanie obu PDF Q7 z folderu użytkownika: kontrola118 wierszy, zgodności
  umowy/rachunku i terminów. Spadek kapitału zgodny z nadpłatą, obniżona rata bez
  skrócenia okresu; sam plan nie dowodzi daty i kwoty rzeczywistego przelewu.
- [x] Po uzupełnieniu przez użytkownika: odtworzono ciąg kapitału od kwoty początkowej
  przez ratę wrześniową, dwie nadpłaty i ratę październikową; oba PDF zgodne.
  Podział wrześniowej raty jest wyliczony, daty z OCR interpretowane — nie bankowe
  potwierdzenie rozksięgowania. Nadal trzeba odszukać istniejące operacje bez duplikacji.
- [ ] Po osobnej zgodzie: zapisać umowę,59 rat i jawny link pierwszej płatności;
  bez duplikowania przelewu, korekty starych odsetek lub automatycznego cashflow.
  Zgoda użytkownika jest warunkowa: uwzględnić zmiany harmonogramu i nadpłatę.
  Oba dokumenty już porównane; przed zapisem zaprojektować wersje harmonogramu
  oraz odrębną spłatę kapitału. Potwierdzić rzeczywisty transfer nadpłaty bez duplikacji.
- [ ] Rozszerzenie na kartę Velo i Allegro Pay (również oprocentowane raty).
- [ ] Pożyczki rodzinne: umowy i spłaty, bez zamiany na darowiznę automatycznie.
- [ ] Goodie: oczekujący/zatwierdzony/wypłacony, brak podwójnego przychodu;
  darowizny otrzymane/przekazane i jawne umorzenie zobowiązania.

## Poprawki po przeglądzie UI (2026-10-27)

- [x] Zgoda użytkownika na trzy poprawki wykryte podczas przeglądu.
- [x] Okres w URL, odświeżenie, Wstecz, zakładki i linki przeglądu; granice lat.
- [x] Kontrast archiwalnych kont bez opacity na całym wierszu.
- [x] Kopiowanie IBAN-u: sukces, odmowa, brak API, ręczne kopiowanie i Ukryj.
- [x] Końcowy frontend gate: 230 unit, 43 E2E + 1 celowy skip,
  lint/typecheck/build PASS; ponowne niezależne review bez blokad.
- [x] Po osobnej zgodzie scalono/push main i wdrożono frontend e5ce5f5;
  backend/worker nadal 1b42e34. Backup/restore, CI i smoke PASS.
- [x] Końcowa obserwacja 11/11 PASS, bez restartów/błędów i zmian danych;
  atomowo zaktualizowano metadane wydania, rollback zachowany.
- [ ] Ocena zalogowanej produkcji — testy fixtures jej nie zastępują.

## Przeprojektowanie UI/UX finansów (2026-10-26)

- [x] Porównanie oficjalnych wzorców Revolut, Monzo, Monarch, Actual i YNAB;
  propozycja oddzielenia codziennej pracy od konfiguracji w ustawieniach.
- [x] Zatwierdzona klikalna makieta pod `https://finanse.birek.online/makieta/`:
  fikcyjne dane, przegląd/transakcje/budżet/nadchodzące/raporty, ustawienia kont
  i danych bankowych, wielopoziomowe drzewo kategorii, desktop/mobile i dwa motywy.
  HTTPS/60 kombinacji/interakcje/axe PASS; istniejący frontend/API/dane bez zmian.
- [x] Użytkownik zaakceptował wygląd makiety, pełny plan i zasadę podlimitów kategorii;
  zatwierdził implementację w osobnym worktree, bez publikacji produkcyjnej.
- [x] Implementacja nowego UI i kontraktów backendu w gałęzi `feat/finance-ui-redesign`:
  ustawienia, drzewo, metadane kont, waluty, raporty i agregacja budżetów gotowe;
  testy backend790/frontend220/E2E31+1skip, lint/types/build i review zakończone.
- [-] Osobny podgląd przed wdrożeniem: użytkownik wybrał bezpośrednio main i produkcję.
- [x] Po jawnej zgodzie main/push + wdrożenie1b42e34 i addytywna migracja b8:
  backupc5520a46/restore/próba na kopii, backend790/frontend220/E2E31+1skip/CI PASS;
  HTTPS/assets/auth/browser i niezmienność historycznych danych/original uploads PASS.
- [x] `/public/makieta` zawarte w nowym obrazie i zweryfikowane przez HTTPS.
- [ ] Zebrać uwagi użytkownika do działającego UI na produkcji; poprawki małymi zmianami.
- [x] Przegląd40 wariantów dokładnego frontendowego wydania z fixtures (27.10):
  raport `docs/audits/2026-10-27-finance-ui-review.md`, bez mutacji produkcyjnych.
- [x] Po akceptacji poprawiono zachowanie miesiąca w URL/powrocie/zakładkach.
- [x] Po akceptacji poprawiono kontrast nieaktywnych kont w obu motywach.
- [x] Po akceptacji obsłużono sukces/odmowę/niedostępność kopiowania IBAN-u.
- [ ] Ocena zalogowanej produkcji: potrzebny uzgodniony dostęp; fixtures jej nie zastępują.

---

## Audyt przekrojowy (2026-10-22)

- [x] Po zgodzie użytkownika scalono/push main i wdrożono aplikacjęd3c2c68:
  backend778/frontend194/E2E29+1skip,lint/types/build/CI PASS,backupfa1551c7+restore PASS.
  HTTPS/health/assets/auth/browser PASS,hashe księgi/uploads i data container IDs bez zmian.
  Bez importu Actual/bankowego/migracji. Raport release-d3c2c68 opisuje także rollbacki.
- [ ] Uodpornić ops/prepare_release.py na restrictive umask; test source directories
  i obrazu jako produkcyjny UID10001. Obecny pakiet poprawiony/zweryfikowany,
  ale ogólny generator wymaga osobnego follow-up z regresją.
- [ ] Przenieść zweryfikowany kontrakt stanu deployu do narzędzi operacyjnych:
  dokładne hashe tabel/plików, odrębna kontrola dozwolonego cron i realnych jobs,
  zapis mismatch oraz logów przed rollbackiem. Prywatny helper ma9 testów PASS.

- [x] Przed importem bankowym odświeżyć dane z Actual: preflight źródła i backup/
  restore12055508 PASS. Następnie dostarczono aktualny eksport; backup/restore
  bc2a3f05 i odtworzenie izolowanej kopii PA PASS. Po poprawkach mapowania/zamkniętych
  kont i jawnego manifestu próba na kopii PASS:286 nowych, powtórzenie0 nowych,
  augmented16/54/9 zgodne; backend778/frontend194 i lint/types PASS.
  Kod wdrożonyd3c2c68;po osobnej zgodzie wykonano produkcyjnie286new/799skip/0errors,
  stan i salda zweryfikowane niezależnym odczytem.1601 wcześniejszych zapisów bez zmian.
  Backupbd201f28 przed i c69299d0 po +restore PASS. Brak importu danych bankowych.
- [x] Świeża kontrola aktualności po deployu,wyłącznie odczyt:Actual watermark zgodny,
  0 późniejszych komunikatów;produkcyjne1601 zapisy/33kont/102kategorii/869mapowań i pin
  identyczne z próbą. Zakres286 nowych/1 zachowana,0 konfliktów wspólnych operacji.
  Raport actual-current-preflight2026-10-24; bez zapisu do księgi.
- [x] Osobno zatwierdzony produkcyjny import286 nowych operacji ze wskazaną zachowaną
  historią. Backupbd201f28/restore PASS, ponowny guard źródła/pinu/baseline wykonany;
  pojedyncza komenda zakończona0:286new/799skip/0errors,1601 wcześniejszych zapisów
  zachowane,augmented16/54/9 zgodne. Niezależny odczyt po commicie PASS,backup po
  imporciec69299d0+restore PASS. Bez importu bankowego.
- [x] Zatwierdzono i wykonano podgląd CSV Revolut i tekstowych PDF VeloBank,
  deduplikacja względem odświeżonej PA i uzgodnienie sald;bez automatycznego zapisu.
  95 wierszy:73 pojedyncze kandydatury,17 niejednoznacznych,5 bez zgodnej kwoty
  (4 korekty odsetek i1 konflikt). Rozbieżności otwarcia/zdarzeń blokują import.
  Harmonogram kredytu nie tworzy wykonanych transakcji. Raport bank-preview2026-10-24.
- [ ] Wyjaśnić rozbieżności Velo przed jakimkolwiek zapisem:poprzedni wyciąg karty
  do17.09,rachunek za sierpień i księgowania początku października;potwierdzić mapowanie
  kont. Nie usuwać2 zapisów PA bez odpowiednika w wrześniowym PDF,nie dodawać4 korekt
  ani nie zmieniać kwoty zakupu automatycznie. Zgodne saldo końcowe karty nie wystarcza.
- [x] Pogłębienie Velo 27.10 bez zapisu: świeży owner-scoped READ ONLY,
  dokładne mosty sald, dwie operacje rachunku i konflikt karty zachowane z Actual;
  rekordy i oryginały bez zmian. Raport `docs/audits/2026-10-27-velo-reconciliation.md`.
- [ ] Uzyskać brakujące wyciągi Velo: sierpień rachunku, księgowania 01–06.10,
  poprzedni cykl karty do 17.09 i potwierdzenie mapowania kont. Nadal NO IMPORT.
  Użytkownik obecnie ma wyłącznie dotychczasowe cztery źródła; folder Drive
  zweryfikowany SHA-256, bez nowych dowodów. Zadanie czeka na dokumenty.
- [x] Zatwierdzona ograniczona poprawka mapowania Actual: regresja RED → GREEN,
  74 testy importera i backend666 PASS (8 proxy deselected), review bez blokad. Próba z wymaganym uzgodnieniem
  sald na kopii wykonana i wycofana przy kolejnej blokadzie; historia zachowana.
- [x] Zatwierdzono zakres obsługi zamkniętych kont w parserze Actual i uzgadnianiu;
  parser/historia bez aktywacji kont zaimplementowane, 90 testów importera PASS;
  review i próba na kopii zakończone, backend682/frontend194 i lint/types PASS.
  Bez usuwania/nadpisywania historii i bez wdrożenia/importu produkcyjnego.
- [x] Zatwierdzono jawny sposób raportowania jednej zachowanej operacji Actual nieobecnej
  w eksporcie (kontrola ID/hasz zapisu/hasz źródła/użytkownik). Plan actual-preserved-history
  zatwierdzony i wykonywany natywnie: moduł pinów/blokad3266377,66 PASS/backend748;
  integracja30 nowych/łącznie206 PASS; finding review dot. wszystkich źródłowych ID
  naprawiony RED3 → GREEN. Próba na kopii286/0errors i ponowienie0new PASS,
  wszystkie1601 wcześniejszych zapisów bez zmian. Backend778/frontend194 i lint/types PASS.
  Nie omijać kontroli sald, nie tworzyć automatycznej korekty księgowej.
  Prywatny raport dokładnie wiąże różnicę z istniejącym zapisem; polityka zatwierdzona
  początkowo dla próby na kopii,następnie jawnie rozszerzona na wykonany import
  produkcyjny286 operacji z backup/restore i niezależnym post-checkiem.

- [x] Test aplikacji po wdrożeniu UI8a7cda5: read-only production smoke4 viewporty,
  E2E29+1skip na release assets i Vitest194 PASS; raport webapp-test2026-10-23.
- [ ] Autoryzowany test zalogowanego konta produkcyjnego i nowego dokumentu OCR:
  wymaga sesji/konta testowego oraz jawnego zakresu mutacji; fixtures nie zastępują
  weryfikacji integracji produkcyjnej.

- [x] UI/UX po audycie desktop/mobile: poprawiono mobilne konta/kategorie,
  touch targets, retry finansów/formularza, zwartą agendę i hierarchię Dzisiaj.
  Lokalna typografia/paleta, E2E29 PASS +1 mobile-only skip, backend642 i frontend194
  PASS; lint/types/build, screenshoty i review bez blokad. Bez deployu.
- [x] UI8a7cda5 na main; pakiet frontend-only, immutable image/rollback,
  backup/restore cfc7102f i ponowiony frontend gate (194 unit,29 E2E+1skip) PASS.
- [x] Zatwierdzono i wdrożono frontend-only UI8a7cda5; backend/worker pozostają6811809.
  HTTPS/health/assets/fonts/logowanie PASS; pozostałe kontenery bez zmian.
- [ ] Uzupełnić jednostkowe testy trzech akcji ponawiania w przeglądzie finansów;
  ścieżka retry danych formularza jest pokryta E2E.
- [ ] Zoptymalizować lokalne fonty do WOFF2 (obecnie ok. 756 KB TTF);
  zachować polskie znaki i licencje. Poza zakresem bieżącej poprawki UX.

- [x] Refaktor `finance.service` po audycie: wydzielono transactions/reporting/
  budgets/cashflow/dates, fasada 63 linie zamiast 983. Kontrakty GREEN,
  AST 27/28 funkcji identyczne (28. ma tylko wydzielone traversal kategorii);
  backend 642 PASS, frontend 194 PASS, lint/types PASS; review bez blokad.
  Bez zmian zachowania, migracji i deployu.
- [ ] Drobne follow-up refaktoru: rozszerzyć testy aliasów fasady o starsze
  query/entity exports; opisać brak gwarancji dla zewnętrznych prywatnych helperów.

- [x] Audyt `7cde5ac` i niezależna weryfikacja raportu:
  `docs/audits/2026-10-22-audit.md`.
- [x] Zatwierdzono kierunek pakietu 1; przygotowano szczegółowy plan
  `docs/superpowers/plans/2026-10-22-document-safety-package-1.md`.
- [x] Zatwierdzono szczegóły planu i wykonanie inline; pozostałe pakiety poza zakresem.
- [x] Pakiet 1: implementacja, niezależny review i lokalny gate zakończone;
  poprawiono P2 ścieżki uploadu z `/` z regresją RED → GREEN.
- [x] Profil runtime R01 + A01/A02 zweryfikowany na docelowym Stirling/Compose
  i wdrożony jako `c765ea9`. Początkowe blokady startu rozwiązano w derived image;
  OCR skanów A4 i zapis uploads non-root zweryfikowano na stagingu.
- [x] Follow-up runtime (zakres lokalny): plan `2026-10-23-stirling-nonroot.md`
  realizowany; rozszerzony patch inicjalizacji uprawnień zatwierdzony i działa.
  Staging OCR A4 PNG/JPEG/PDF oraz ACL syntetyczne PASS; poprawki po review
  zweryfikowane: 632 backend, 8 proxy/ACL/OCR, 194 frontend PASS.
- [x] Produkcyjna integracja nowego runtime/Compose i zatwierdzonych ACL,
  świeży backup/restore, rollback oraz zatwierdzenie nowej rewizji przed deployem.
  Wdrożono `c765ea9` po osobnej zgodzie; backup/restore `e45cdc85`, migracja i smoke PASS.
  Nie zamykać całego R01
  jako pełnego sandboxingu ani twardej quota filesystemu.
- [x] Krótka kontrola produkcji po wdrożeniu: brak restartów/OOM/nowych błędów,
  HTTPS/health PASS, kolejka OCR 0. RAM Stirling ok. 1,09 GiB / 2 GiB.
- [ ] Testy największych dozwolonych dokumentów przy równoległym przetwarzaniu
  w izolowanym stagingu; obecny smoke nie certyfikuje worst-case sizing.
- [ ] Rozszerzyć staging OCR o aplikacyjne helpery OCR i ekstrakcji tekstu;
  obecnie realny helper konwersji + bezpośrednie OCR/tekst Stirling, a kontrakt
  helperów OCR/tekst i ograniczenia odpowiedzi są pokryte testami jednostkowymi.
- [ ] Opcjonalny katalog szablonów Stirling: ocenić możliwość wyłączenia funkcji
  lub jawnej konfiguracji ścieżki bez osłabiania read-only root.
- [ ] P3 z review: ograniczony traversal drzewa PDF zamiast eager flatten pypdf;
  obecnie ochronę zasobów zapewniają limity subprocessu.
- [x] Poprawka lokalna konwersji OCR: domyślne `fillPage` rozciągało szerokie obrazy
  do A4 i może dać pusty tekst mimo HTTP200. Repro: 1800x700, tekst rozpoznawany
  przez Tesseract na oryginale, „Empty page” po konwersji. Oddzielna poprawka
  zachowania proporcji zatwierdzona: `maintainAspectRatio`, `autoRotate=true`.
  Unit RED→GREEN (12 worker PASS), rzeczywista geometria staging RED;
  staging GREEN: OCR szerokich PNG/JPEG i A4/PDF, geometria, hashe i zabezpieczenia.
  Gate: backend 636 PASS, frontend 194 PASS, osobno staging 1 PASS, lint/types PASS.
- [x] Zatwierdzono i wdrożono 6811809; backup/restore da7eb2d7 i smoke PASS.
  Zachowano hardening, bez migracji i ponawiania historycznych dokumentów.
- [x] Scalić/wypchnąć 6811809 do main i przygotować release z przypiętymi obrazami,
  zachowanym hardeningiem, rollbackiem oraz backup/restore 23bcbccb.
- [ ] A05–A09/A13: współbieżność ustawień, importer, granice kwot i ekran projektu.
- [ ] A10–A12: walidacja argumentów AI, policy engine i ograniczony kontekst.
- [ ] A03/A04/A14: zatwierdzanie dokumentu do księgi, retencja/GC, dostępność UI.
- [ ] R02–R05: lease workera, ochrona DB, restore hashów, alerty i provenance buildów.
- [ ] Uzgodnić semantykę pending przed zmianą raportów/prognozy.

---

## Synchronizacja repozytoriów (2026-10-22)

- [x] Zintegrowano aktualny `main` z 14 commitami `genspark_ai_developer`;
  HEAD `a115afc` jest potomkiem GitHub `main`.
- [x] Testy backend/frontend oraz lint, typecheck i build przeszły.
- [x] Dane operacyjne i wrażliwe artefakty z `webapp/` pozostają poza Git.
- [x] Przegląd bezpieczeństwa dokumentów: parser PDF i dekodowanie obrazów w
  serwisie, kontrola SHA-256 przed OCR i testy regresyjne; poprawiono whitespace/workflow.

---

## Task 5 — Security Baseline: limity i audyt za reverse proxy (2026-08-20)

- [x] npmplus przekazuje łańcuch wyłącznie do Nginx frontendu, który normalizuje
  go do jednego adresu; backend przyjmuje tylko ścisły literal IP od zaufanego
  kontenera frontend, a łańcuch/spoof wraca do peera.
- [x] Limity loginu, Advisora i uploadu są zależnościami FastAPI; odrzucenia 429
  zapisują niezależny, zredagowany event audytu.
- [x] Backend jest wyłącznie na `internal`; frontend jest jedynym serwisem na
  dedykowanych `finanse_ingress` i `internal`; npmplus ma tam stałe `172.24.0.2`.
  Wdrożono runtime i zweryfikowano zewnętrznym smoke testem.

---

## Task 4 — Automatyczny backup i restore drill na VPS (2026-08-20)

- [x] `finanse-backup.timer` (codziennie 02:30) i
  `finanse-restore-verify.timer` (pierwsza niedziela 04:30) działają w
  `Europe/Warsaw` z `Persistent=true` i współdzielonym 15-minutowym lockiem.
- [x] Instalator wdraża rootowy wrapper poza repozytorium oraz zachowuje pusty
  `root:root` `0700` parent restore wymagany przez systemd; wrapper tworzy bazę
  izolowaną przed weryfikacją i czyści zasoby po sukcesie lub błędzie.
- [x] Quality gate: backend `198 passed, 125 skipped`, frontend `129 passed`;
  lint, typecheck i `git diff --check` PASS. Backup `015211bb` i rzeczywisty
  drill przeszły; brak `finanse_restore`, parent restore pusty, journal bez
  sekretów. Wdrożenie nie spowodowało downtime aplikacji webowej.
- [x] Restore wybiera wyłącznie `RESTORE_SNAPSHOT_ID`; legacy `snapshot=` jest
  odrzucane przed runnerem/Restic. Lock obejmuje także ręczne targety Makefile,
  a retry działa po 15 minutach do 3 startów w 3 godziny.
- [x] Finalny proof: backend `201 passed, 125 skipped`, frontend `129 passed`;
  lint/typecheck/`git diff --check` PASS. Legacy guard zwrócił kod 2 bez
  runnera/Restic; backup `11fd2129` i drill `status=0/SUCCESS` potwierdziły
  pusty `root:root` `0700` parent, brak `finanse_restore` i journal bez
  sekretów.
- [x] Restic cache dla timerów jest `root:root` `0700` pod
  `/docker/finanse/data/restic-cache`, dzięki czemu zachowano `ProtectHome`.
  Produkcyjny drill uruchamia wyłącznie `finanse-restore-verify.service`; target
  Make pozostaje wewnętrzny dla wrappera.
- [x] Cache runtime proof: backup `a6e89e9d` i rzeczywisty drill przeszły
  `status=0/SUCCESS`; aktualne okno journala ma 0 komunikatów `unable to open
  cache`, parent restore jest pusty, a `finanse_restore` nie istnieje.

---

## Task 1 -- Security Baseline: backup i weryfikacja odtworzenia (2026-08-19)

- [x] Wersjonowane skrypty Restic wykonują prywatny snapshot PostgreSQL i uploads
  z manifestem SHA-256, tagami oraz retencją 7/4/6.
- [x] Izolowana weryfikacja odtworzenia wymaga loopbackowego DSN do bazy
  `_restore`/`_test`, weryfikuje checksumy przed ekstrakcją lub `pg_restore`,
  uruchamia migracje i kontrolę invariantów księgi.
- [x] Dokumentacja operacyjna, targety Makefile oraz statyczne testy zostały
  dodane; Contabo S3 skonfigurowano w root-only plikach, wykonano dwa backupy
  i rzeczywisty restore drill izolowanej bazy.

## Task 18 — Rotacja zewnętrznych kluczy (2026-08-20)

- [x] Rotacja kluczy LLM i Contabo S3 potwierdzona przez właściciela; nowych
  wartości nie zapisano w czacie ani Git.

---

## Task 17 — Ukrywanie nieaktywnych kont i kategorii (2026-08-19)

- [x] Formularze transakcji, schedulera i budżetów pokazują wyłącznie aktywne
  encje, zachowując filtrowanie typu i ograniczenie kont schedulera do PLN.
- [x] Dashboard finansów i nawigacja transakcji ukrywają nieaktywne konta;
  wybrane wcześniej konto nie jest usuwane z istniejącego widoku.
- [x] `FinanceAccounts` i API pozostawiono bez zmian.
- [x] Quality gate: frontend `106 passed`, lint/typecheck/build PASS.

## Task 16 — Usuwanie i dezaktywacja kont i kategorii (2026-08-17)

- [x] Model: `categories.is_active` (Boolean NOT NULL, default true) + migracja `1dbfe88dfb1b` (upgrade/downgrade zweryfikowane na izolowanej bazie).
- [x] Serwis: `delete_account`/`delete_category` (blokada przy powiązanych rekordach, ValueError z sugestią dezaktywacji), odrzucanie nieaktywnych kont/kategorii w transakcjach, budżetach i schedulerze.
- [x] API: `DELETE /accounts/{id}` i `DELETE /categories/{id}` (204/404/409) oraz `is_active` w `PATCH /categories/{id}`.
- [x] Frontend: hooki tworzenia/edycji/usuwania, strona `/finances/accounts` i
  link „Konta” w sidebarze; nieaktywne encje są wygaszone, a pełna lista
  pozostaje dostępna tylko na stronie zarządzania.
- [x] Quality gate: `make test` — backend `126 passed, 109 skipped`, frontend
  `106 passed`; `make test-integration` — `109 passed`; lint/typecheck/build PASS.
- [x] Produkcja: migracja `1dbfe88dfb1b`, deploy backendu/frontendu/workera i
  smoke test `GET /api/health` (HTTP 200).

## Task 15 — Budżety w prognozie płynności (2026-08-15)

- [x] Backend: `CashflowBudgetSummary` + pole `budgets` w prognozie (z `get_budget_status`).
- [x] Frontend: karta „Budżety w tym miesiącu" + ostrzeżenie o przekroczeniu płynności.
- [x] Quality gate: backend `91 integracyjnych`, frontend `80 passed`, lint/typecheck/build PASS.

## Task 14 — Przewalutowanie PLN↔EUR/USD (2026-08-15)

- [x] Backend: `create_exchange_transaction` (walidacja kont/walut, kurs NBP lub ręczny, suma zero) + `POST /transactions/exchange`.
- [x] Frontend: hook `useCreateExchange` i typ „Przewalutowanie" w formularzu (dwa konta, opcjonalny kurs).
- [x] Quality gate: backend `89 integracyjnych`, frontend `76 passed`, lint/typecheck/build PASS.

## Task 13 — Edycja i usuwanie transakcji (2026-08-15)

- [x] Backend: `delete_transaction` (kaskada postingów) + `DELETE /transactions/{id}` (204/404).
- [x] Frontend: hooki `useUpdateTransaction`/`useDeleteTransaction` + `invalidateFinanceLedger`.
- [x] Frontend: edycja inline opisu/daty i usuwanie z potwierdzeniem w liście transakcji.
- [x] Quality gate: backend `128 unit + 81 integracyjnych`, frontend `70 passed`, lint/typecheck/build PASS.

## Task 12 — Ręczne księgowanie transakcji (2026-08-15)

- [x] Frontend: helper `buildTransactionPostings` (konwencja `balance = credit − debit` dla przychodu/wydatku/transferu).
- [x] Frontend: formularz `TransactionForm` (typ, konto PLN, kategoria filtrowana, kwota, data, opis; walidacja i błąd inline).
- [x] Frontend: integracja na `/finances/transactions` + naprawa `transaction_date` w `useCreateTransaction`.
- [x] Quality gate: frontend `63 passed`, backend bez zmian (`125 unit + 79 integracyjnych`), lint/typecheck/build PASS.

## Task 11 — Miesięczne budżety z limitami (2026-08-15)

- [x] Backend: model `CategoryBudget` (limit > 0, unikalny per użytkownik+kategoria) + migracja `4340d1460982`.
- [x] Backend: serwis CRUD z walidacją własności i typu `expense`; `get_budget_status` z roll-upem potomków i zerowymi wydatkami.
- [x] Backend: endpointy `GET/POST /budgets`, `PATCH/DELETE /budgets/{id}`, `GET /budget-status`; duplikat → 422.
- [x] Frontend: hooki budżetów + `budgetProgress`; strona `/finances/budgets` z listą, edycją inline, dodawaniem, usuwaniem i sekcją bez budżetu.
- [x] Quality gate: backend `125 unit + 79 integracyjnych`, frontend `55 passed`, lint/typecheck/build PASS.

## Task 10 — Podstrony finansowe i zarządzanie płynnością (2026-08-15)

- [x] Backend: parametryzowane okresowo raporty `summary` i `category-summary` (`month`/`year`).
- [x] Backend: `DELETE /cashflow/items/{id}` oraz `POST /cashflow/items/{id}/confirm` — potwierdzenie tworzy zbilansowaną transakcję tylko dla `due`/`overdue`, odrzuca non-PLN/przyszłe/niepewne/zdublowane, blokada wiersza chroni przed podwójnym księgowaniem.
- [x] Frontend: typowane hooki ustawień, mutacji schedulera, potwierdzenia i parametrowanych raportów; centralna invalidacja cache.
- [x] Frontend: trasy `/finances`, `/finances/transactions`, `/finances/cashflow`, `/finances/budgets`, `/finances/reports` + realne linki sidebara.
- [x] Frontend: strona cashflow z formularzami ustawień/schedulera, prognozą, listą pozycji i dialogiem potwierdzenia sugestii.
- [x] Quality gate: backend `123 unit + 61 integracyjnych`, frontend `41 passed`, lint/typecheck/build PASS.

## Task 9 — Finalny przegląd: znak, invalidacja, non-PLN (2026-08-15)

- [x] Poprawiono znak transakcji per konto: income → posting `credit` (zielony „+"), expense → `debit` (czerwony „−").
- [x] Zweryfikowano i udokumentowano testem zakres invalidacji cashflow: prefiks `["finance","accounts"]` obejmuje transakcje per-konto (TanStack Query v5, prefix-match).
- [x] Ograniczono selektor konta schedulera do aktywnych kont budżetowych w PLN i zablokowano walutę na „PLN".
- [x] Quality gate frontendu: Vitest `41 passed`, ESLint, TypeScript typecheck i Vite production build.

---

## Task 6 — Spłata długu jakościowego (2026-08-12)

- [x] Przejrzano 27 commitów z zakresu `f90a4d6..ab344ad` oraz aktualną dokumentację; wcześniejszy zapis o 17 commitach był nieaktualny.
- [x] Uruchomiono izolowaną testową bazę PostgreSQL bez dotykania produkcji.
- [x] Backend: Ruff `app/ tests/` i mypy `app/` przechodzą; pytest `89 passed, 23 skipped, 5 warnings` przy niedostępnej bazie lokalnej.
- [x] Testy integracyjne: świeże uruchomienie `23 passed, 89 deselected, 11 warnings` na izolowanym PostgreSQL.
- [x] Frontend: ESLint, Vitest `4 passed`, TypeScript typecheck i Vite production build.
- [x] Dodano testy pętli tool-calling, atomiczności/rollbacku potwierdzeń oraz bezpiecznej walidacji mutacji finansowych.
- [x] Doradca odświeża oczekujące potwierdzenia pollingiem co 2 sekundy; harmonogram używa lokalnych granic dnia i offsetu DST dla konkretnej daty.
- [x] Przywrócono lokalną datę transakcji (`7cc1973`): brak jawnej daty używa bieżącego dnia użytkownika, nie dnia UTC.
- [x] Zapisano dokładne wyniki i ograniczenia w CHANGELOG/JOURNAL; porządkowe zmiany `backend/migrations/` przywrócono do `f90a4d6` bez zmiany schematu.
- [x] Frontend lint: dodano konfigurację ESLint i usunięto 7 błędów wykrytych w kodzie.

Pozostały ostrzeżenia zależności/testów, ograniczenie streamingu bez SSE, trzy daty USD bez kursu NBP oraz brak rzeczywistych danych split transactions w testach. Nie wykonano deployu ani migracji produkcyjnej.

## Iteracja 1 — Pierwszy Vertical Slice (MVP)

### Inbox → Task
- [x] Backend: endpoint `POST /api/inbox/{id}/process` — tworzy task z inbox_item
- [x] Frontend: Inbox page ładuje listę inbox_items z API
- [x] Frontend: przycisk "Utwórz zadanie" tworzy task i oznacza inbox_item jako processed
- [x] Frontend: pokaż historię (processed items)
- [x] E2E: Playwright test — wpisz w Inbox → utwórz zadanie → task w API

### Dzisiaj z live danymi
- [x] Frontend: Today ładuje taski z API (status=todo,in_progress)
- [x] Frontend: Today ładuje time_blocki z API (start_time/end_time)
- [x] Frontend: Today ładuje financial_summary z API
- [x] Backend: comma-separated status filter (status=todo,in_progress)
- [x] E2E: tasks from Inbox visible on Today with 'Inbox' badge

### Finanse CRUD
- [x] Frontend: Finances page ładuje listę kont z saldami z API
- [x] Frontend: formularz tworzenia konta (nazwa, typ, waluta)
- [x] Frontend: lista transakcji z API
- [x] Frontend: formularz transakcji
- [x] Backend: balance_pln computed from postings per account

### Doradca
- [x] Backend: integracja DeepSeek API (v4-pro)
- [x] Backend: chat endpoint POST /api/advisor/messages
- [x] Backend: conversation listing + message history
- [x] Frontend: chat UI z live odpowiedziami DeepSeek
- [x] Frontend: tworzenie nowej konwersacji + pamięć kontekstu
- [x] System prompt: polski doradca (czas, pieniądze, projekty)
- [x] E2E: DeepSeek odpowiada po polsku, pamięta kontekst rozmowy

---

## Iteracja 2 — Dokumenty i Import

### Jakość, bezpieczeństwo i deploy (2026-08-13)
- [x] Scalono gałąź `quality-advisor` do `main`.
- [x] Wdrożono backend i frontend na produkcję.
- [x] Smoke test produkcji: `/api/health` i frontend odpowiadają HTTP 200.
- [ ] Obserwacja produkcji po wdrożeniu i zebranie realnych problemów.

### Import z Actual
- [x] Skrypt migracyjny Actual → Personal Advisor
- [x] Mapowanie kont, kategorii, transakcji
- [x] Zachowanie double-entry invariant (0 błędów na 800 transakcji)
- [x] Transfery wewnętrzne (66 par)
- [x] Kursy walut NBP (EUR/USD)
- [x] Migracja produkcyjna wykonana (2026-08-11)
- [x] Uzgodnienie kategorii/grup niezależne od księgowania importu i trwałe provenance kont/kategorii.
- [~] Kontrolowana korekta produkcyjna legacy Actual: kod i quality gates gotowe; polecenie produkcyjne nie zostało uruchomione.
- [x] Preflight korekty rozpoznaje wyłącznie historyczne, syntetyczne bilanse otwarcia Actual; lookalike, rekord ręczny i niezbilansowany BO są odrzucane.

### Task 7 — Próbne uzgodnienie Actual (2026-08-14)
- [x] Uruchomiono pełny quality gate w worktree `actual-reconciliation`: lint, typecheck, backend pytest, frontend Vitest i production build.
- [x] Zastosowano migracje i utworzono wyłącznie testowego użytkownika w izolowanej bazie `finanse_test` na `127.0.0.1:55432`.
- [x] Dodano testowany fallback NBP Table A dla soboty/niedzieli: poprzedni opublikowany kurs zachowuje datę efektywną w cache i źródło `nbp_previous_business_day` w postingach; brak kursu nadal odrzuca transakcję.
- [x] Import DOM blobu z `--execute --require-reconciled` zakończył się kodem 0: 800 transakcji, 0 błędów, `is_reconciled=true`, 15 kont i 46 kategorii bez różnic. Nie wykonano operacji na produkcyjnym PA ani Actual.

### Task 8 — Kontekstowy sidebar (2026-08-14)
- [x] Zastąpiono płaski sidebar układem `IconRail + ContextualSidebar` opartym
  o jedną, typowaną konfigurację nawigacji.
- [x] Kontekst wynika z najdłuższego pasującego prefiksu URL; istniejące
  `/finances` i pozostałe route'y, auth, topbar, treść stron oraz paleta pozostały bez zmian.
- [x] Dodano tooltipy raila, dolny UserPanel i ten sam model danych dla desktopu
  oraz mobilnego drawera; przyszłe pozycje są nieklikalne i oznaczone „Wkrótce”.
- [x] Frontend quality gate: Vitest `12 passed`, ESLint, TypeScript i Vite build.

### Stirling PDF + OCR
- [x] Worker async (Redis + ARQ)
- [x] Pipeline: upload → SHA-256 → Stirling → OCR → tekst
- [x] Ekstrakcja danych przez OpenAI → inbox item
- [x] Zatwierdzenie przez użytkownika (Inbox → Utwórz transakcję)

### Doradca Level 2 — narzędzia mutujące
- [x] Tool registry: create_task, create_time_block, create_transaction
- [x] Endpointy confirm/deny tool-execution z potwierdzeniem użytkownika
- [x] Audit log dla mutacji (performed_by=human)
- [x] Frontend: przyciski potwierdzenia/odrzucenia w czacie
- [x] Frontend: polling statusu narzędzi tylko dla oczekujących potwierdzenia

### Dokumenty — ekstrakcja danych
- [x] OpenAI extraction z OCR text (structured JSON: type, amount, currency, category)
- [x] Inbox item z sugerowaną transakcją po ekstrakcji

### Kalendarz i Finanse
- [x] Kalendarz: widok miesiąca, taski z due dates, filtrowanie zakresem, kolorowane bloki
- [x] Finanse: endpoint transakcji per konto, opening balances w migracji
- [x] Finanse: redesign strony (salde, wybór konta, transakcje per konto)
- [x] Payee resolution z fallbackiem na kategorię
- [x] Finanse: pierwszy slice prognozy płynności cyklu wypłaty — ustawienia,
  miesięczne pozycje, forecast do wypłaty, trzydniowa niepewność i UI tylko do odczytu.

---

## Konfiguracja opencode (2026-08-12)

### LSP i MCP
- [x] LSP włączony (`lsp: true`) + pyright + typescript-language-server
- [x] MCP EXA (remote, klucz przez `{env:EXA_API_KEY}`)

### Komendy
- [x] `/test`, `/lint`, `/typecheck` — pytest/vitest, ruff/eslint, mypy/tsc
- [x] `/migrate`, `/migration "opis"` — alembic upgrade/autogenerate
- [x] `/deploy` — docker compose build+up na produkcję
- [x] `/docs` — aktualizacja CHANGELOG/TASKS/JOURNAL po sesji

### Narzędzia i konfiguracja
- [x] ruff + mypy w backend/.venv (Makefile lint/typecheck działają)
- [x] pyproject.toml: ruff, mypy, pytest config
- [x] Formatter po zapisie: ruff (Python), prettier (TS/JS/CSS/HTML/JSON)
- [x] References: docs + infra; watcher ignore; permissions (lsp/webfetch/websearch/gh)
- [x] Skill `session-workflow`

---

## Done

- [x] Domknięcie przeglądu jakości: historia tool calls, walidacja mutacji finansowych, oznaczenie sald PLN, aktualizacja schematu DB

- [x] Fundament backendu (7 domen, 16 tabel)
- [x] Fundament frontendu (9 stron, routing, Tailwind)
- [x] Docker: postgres, redis, backend, frontend, stirling-pdf
- [x] Auth flow (rejestracja, logowanie, cookies, redirect)
- [x] Double-entry ledger (konta, transakcje, postings, invariant)
- [x] npmplus: Actual → finanse.vps.birek.online
- [x] npmplus: PA → finanse.birek.online (HTTPS + SSL)
- [x] Docker Compose + .env + Makefile
- [x] Repo: github.com/RobertBirek/finanse
- [x] Dokumentacja: AGENTS.md, PRD.md, DB_SCHEMA.md, 9 ADR-ów
- [x] Testy początkowego vertical slice'a: 15 testów (11 unit, 4 integracyjne)
- [x] Agent OpenCode: .opencode/agent/personal-advisor.md
- [x] CHANGELOG.md, JOURNAL.md, TASKS.md
