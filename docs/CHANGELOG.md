# Changelog

Wszystkie istotne zmiany w projekcie.

## [Production, 020c229] — 2026-11-08 — Karty kredytowe

### Changed
- Po jawnej zgodzie: FF i push `main` do `020c229`, wdrożone backend/worker/frontend
  oraz osobno zatwierdzona migracja `f3a9d17c2e4b → 00a9ccb532b9`.
- Dwa świeże backupy odtworzone w wyłącznie własnych bazach loopback; próby migracji
  zachowują 56 starych tabel, sześć nowych pustych, księga zbilansowana. Retencja
  ponownie potwierdzona na produkcji przed otwarciem ruchu; bez zmian historii/sald.
- Dokładne odebrane źródła/obrazy, non-root import gate i świeże 952 backend unit,
  555 frontend, lint/types/build PASS; HTTPS/assets/auth/browser 375/1440 PASS.
- Pierwsza próba wycofana przed migracją: zaplanowany cron błędnie blokował kontrolę
  bezczynności. Operatorowy fix RED→GREEN; kolejka zachowana, produkt bez zmian.
- Obserwacja 312s/31kontroli PASS: health200, restarty0/błędy0, ledger0naruszeń,
  Redisgotowy i niezmienione usługi danych. Active metadata atomowo `verified-live`,
  dowody zarchiwizowane; usunięte wyłącznie dwie własne bazy restore po kontroli OID.
- Bez konfiguracji samego konta Velo lub odtwarzania starych planów.
- Raport: `docs/audits/2026-11-08-credit-cards-production.md`.

## [Local, odebrane] — 2026-11-07 — Karty kredytowe i plany ratalne

### Added
- Konfiguracja istniejącego konta PLN jako karty: limit, zaksięgowane zadłużenie,
  rezerwacje, dostępny limit, nadpłata i przekroczenie. Wyciągi z rzeczywistym
  terminem/minimum oraz jawną różnicą uzgodnienia z księgą.
- Wiele planów na karcie, każdy z własną stopą/prowizją; szacunkowy harmonogram
  zastępowany bankowym, powiązania częściowych i wcześniejszych spłat bez
  ponownego księgowania kapitału lub wydatku. Rozliczona historia chroniona.
- Odsetki/opłaty/korekty jako dwustronne zapisy lub powiązanie istniejącego kosztu;
  zwrot pozostaje korektą expense, nie przychodem. Kalkulator ACT/365 tylko szacuje.
- Addytywna migracja `00a9ccb532b9`: sześć tabel, ochrona danych przy downgrade;
  próba zachowania 56 starych tabel/wierszy/kolumn/indeksów i pusty roundtrip PASS.
- Ekran kart w ustawieniach, podsumowanie przy transakcjach, oddzielne warunki
  planów, formularze kosztów/wyciągów/spłat i bezpieczne ponowienia żądań.

### Verification
- Końcowy pełny backend1847PASS (dwa izolowane rozłączne przebiegi, zero pominiętych
  integracjiDB), frontend555PASS, E2E159PASS/1expectedskip, lint/types/build PASS.
  Important z review oraz regresje kontraktu/klucza po odpięciu/prywatności
  odtworzone i naprawione przed finalnym gate. Wczesne błędy i przerwania opisane
  w raporcie, nie zastępują świeżego PASS. Dwie własne bazy testowe usunięte.
- Commity backend09d1d79/frontend7aa1629. Bez scalenia/push, konfiguracji konta,
  migracji produkcyjnej lub deploy. Szacunki nie są bankowymi odsetkami ani postingami.
- Raport: `docs/audits/2026-11-07-credit-cards-local.md`;
  instrukcja i ograniczenia: `docs/operations/credit-cards.md`.

## [Operator tools, e8f6714] — 2026-11-07 — Zabezpieczenie przyszłych wdrożeń

### Changed
- Po „scal i wdróż”: FF do main i push e8f6714, aktywacja poprawionego prepare_release,
  verify_release oraz obowiązkowej bramki w instrukcji /deploy na serwerze.
- Świeże931backendunit/540frontend/6Docker/lint/types PASS na scalonym checkout;
  nowy verifier z rzeczywistymi users finalnegoCompose i exactcurrentimageIDs PASS.
- Nie odtwarzano usług: aplikacja nadal a68d9e4;6containerIDs/images/starttime/restarts
  i active metadata bez zmian, health/login200/auth401. Bez migracji lub zapisów danych.
- Raport `docs/audits/2026-11-07-release-nonroot-integration.md`.

## [Local, odbiór] — 2026-11-07 — Non-root bramka pakietów backend/worker

### Fixed
- Normalizacja uprawnień tylko kopii backendu po ekstrakcji archiwum Git przyumask077:
  dirs0755/files0644/executables0755, zachowane bajty/oryginały/private root0700.
  Odrzucenie archive links przed ekstrakcją zabezpiecza normalizację poza drzewem kopii.

### Added
- `ops/verify_release.py`: offline kontrola gotowych imageIDs/OCIrevision jako jawny
  docelowy UID:GID, odczyt źródeł i importentrypointów bez sieci/hostmount/envfile/DB.
  Nonzero przy błędzie/timeout; obowiązkowy krok /deploy i runbook przed Composeup.
- 46opsunit i6realDocker PASS, odbiór niezależnego review bez uwag. Bez zmian
  applicationcode, DB, main/push/deploy lub aktywnej produkcji. Końcowy unit/static
  gate931backendunit/540frontend/lint/types PASS; integracjeDB nieuruchamiane.
  Wyniki, początkowe guardfailures przy wyborze testów bezDB i ograniczenia w raporcie
  `docs/audits/2026-11-07-release-nonroot-local.md`.

## [Zakres, do zatwierdzenia] — 2026-11-07 — Uprawnienia kodu pakietu i import non-root

### Added
- Po zgodzie na przygotowanie krótkiego zakresu: normalizacja wyłącznie skopiowanego
  backendu, zachowanie hashów/executable/private root oraz offline bramka importu
  gotowych obrazów jako docelowy non-root użytkownik, przed przełączeniem usług.
- Rozpoznano istniejące testy prepare_release: frontend ma normalizację/nginxgate,
  backend/worker nie mają analogicznej kontroli. Bez zmian kodu/testów/produkcji.

## [Production, a68d9e4] — 2026-11-07 — Dopasowanie dokumentów i płatności 5A

### Changed
- Po zgodzie użytkownika: fast-forward i push do main oraz spójne wdrożenie
  backend/worker/frontend a68d9e4. Bez migracji; schematf3a9 i usługi danych bez zmian.
- Świeży backup/restore/checksums/ledger PASS, HTTPShealth200/APIauth401/assets/browser
  375/1440 i errorlogs0/restart0 PASS; active metadata i trwałe dowody zapisane.

### Fixed
- Pierwszą próbę wycofano pod osłoną503: katalogi kodu pakietu0700 blokowały non-root
  import. Poprawiono wyłącznie uprawnienia kopii kodu w pakiecie (bez zmian treści),
  potwierdzono offline imports UID10001/networknone i skutecznie wdrożono ponownie.
- Pełny raport: `docs/audits/2026-11-07-document-payment-matching-production.md`.

## [Local, odebrane] — 2026-11-07 — Czytelne dopasowanie dokumentów do płatności 5A

### Added
- Dowody dopasowania PLN: jawne daty zakupu/księgowania i źródła, opis płatności,
  kwota pierwotna/wolna, ostrożna wskazówka nazwy w opisie, zgodność planowanego konta.
- Deterministyczna kolejność legacy/kwota/nazwa/data/IDs; zakup rozszerza okno wyników
  bez zawężania starego zakresu. Osobne powody niedostępności dokumentu i stany listy.

### Fixed
- Nieaktualny wybór nie pozwala wysłać alokacji po zmianie filtrów/strony/refetch,
  także dla identycznej odpowiedzi i przed rerenderem. 409 wymaga ponownego wyboru;
  identyczny retry zachowuje klucz idempotencji. Brak automatycznej nowej transakcji.

### Changed
- Lokalny odbiór:1788backend/540frontend/153E2E+1oczekiwanyskip, lint/types/build PASS;
  niezależny końcowy review bez uwag. Dodatkowy frontend run wykazał niestabilność
  istniejącego DocumentList.test.tsx; izolowany i pełny rerun540PASS bez zmian kodu.
- Raport `docs/audits/2026-11-07-document-payment-matching-local.md` opisuje wyniki,
  decyzje i ograniczenia. Bez migracji, AI/OCR, pracy na historii lub wdrożenia.
- Usunięto wyłącznie własny efemeryczny testDB po odbiorze; istniejące bazy i produkcja
  nietknięte. Kod i build zgodne z manifestami testowanego pakietu; commity lokalne.

## [Implementacja, przygotowanie] — 2026-11-07 — Dopasowanie płatności 5A

### Changed
- Użytkownik zatwierdził plan i wykonanie natywne. Zweryfikowano izolację worktree
  i interfejsy zadań. Przed testami/kodem blokada bezpieczeństwa: oba dopuszczone
  porty testowej bazy zajęte przez wcześniejsze kontenery. Oczekiwanie na zgodę na
  własny efemeryczny PostgreSQL bez publikacji portów; żadnych zmian produktu/baz.

## [Plan, do zatwierdzenia] — 2026-11-07 — Dopasowanie dokumentów i płatności 5A

### Added
- Plan `docs/superpowers/plans/2026-11-07-document-payment-matching.md`: cztery
  sekwencyjne zadania TDD, dokładny kontrakt dowodów, integracja GET, stany dialogu
  i aktualność wyboru, testy/regresje oraz końcowy review. Bez implementacji produktu.

### Changed
- Użytkownik zatwierdził zakres odpowiedzią „tak”; spec oznaczony jako zaakceptowany.
  Plan czeka na akceptację i wybór native/subagent-driven. Bez zgody na deploy,
  migracje, AI/OCR i operacje na historii. Testów aplikacji w tej sesji nie uruchamiano.

## [Projekt, do zatwierdzenia] — 2026-11-07 — Dopasowanie dokumentów i płatności 5A

- Po zgodzie na przygotowanie zakresu przejrzano obecny backend i frontend. Istnieją
  już bezpieczne ręczne alokacje; główne luki to niewidoczne reasons, nieopisane daty,
  niewykorzystana data zakupu, brak wskazówki nazwy i rozróżnienia błędu/pustej listy.
- Propozycja `docs/superpowers/specs/2026-11-07-document-payment-matching-design.md`:
  rozszerzenie istniejącego odczytu i dialogu, daty z proweniencją, ostrożna nazwa
  w opisie, deterministyczna kolejność, zachowane ręczne linkowanie i PLN-only.
- Niezależny read-only builder check: „nothing important left”. Projekt czeka na
  akceptację całego zakresu, potem osobny plan. Bez kodu produktu, uruchamiania
  testów, migracji, AI, prywatnych danych lub zmian produkcji.

## [Production, frontend ebe441e] — 2026-11-07 — Edytowalny HEX

### Fixed
- Po zgodzie na dokładne `ebe441e`: wdrożono wyłącznie frontend z ręcznym
  wpisywaniem/wklejaniem koloru `#RRGGBB`, także `#000000`, walidacją i resetem.
- Pakiet odpowiada odebranym518unit/145E2E+1expectedskip/static/build; rzeczywista
  bramka odczytu nginx podczas budowy i SHA wszystkich zasobów PASS.
- Świeży backup odtworzono na własnej bazie loopback: checksum/schemaf3a9/ledger PASS,
  bez Alembic. Publiczne HTTPS/health200/auth401/assets/browser375/1440/logi PASS.
- Backend i worker pozostają95f8380; nie zmieniono ich kontenerów, obrazów, ustawień
  lub schematu `f3a9d17c2e4b`. Nie wykonano migracji ani zapisów danych użytkownika.

## [Local, odebrane] — 2026-11-07 — Ręczne wpisywanie koloru HEX

- Operator zgłosił brak możliwości edycji wyświetlanego kodu koloru. Potwierdzona
  przyczyna: wspólny `FinanceColorPicker` renderuje kod jako tekst `span`, nie input.
- Po zatwierdzeniu „tak”: edytowalny `#RRGGBB`, wpisywanie/wklejanie, walidacja i
  synchronizacja z paletą/resetem dla tworzenia/edycji kont i kategorii. Niepełny
  draft pozostaje widoczny; zapis zablokowany również w handlerach, payload uppercase.
- TDD12RED→41focusedPASS; początkowy pełny518frontend/145E2E+1skip/static/buildPASS.
  Jeden review0Critical/0Important/2Minor poprawione: mobilne16px (2browserRED14px→GREEN)
  oraz rzeczywisty clipboardCtrl+V dla małych liter z uppercase payloadem.
  Końcowy518frontend/145E2E+1expectedskip/ESLint/tsc/freshbuild/sourceSHA PASS;
  mobile375/desktop1440/light/dark, axe serious/critical0. Screenshoty obejrzane.
  Bez zmian backendu, schematu lub produkcji; poprawka nie jest jeszcze wdrożona.

## [Local, odebrane] — 2026-11-06 — Uprawnienia plików pakietu release

### Fixed
- `prepare_release.py` normalizuje wyłącznie skopiowany publiczny dist:
  katalogi0755/pliki0644, bez zmiany wejściowego archiwum, treści lub prywatnego
  katalogu pakietu0700. Prywatne0600/0700 nie przechodzą już bezpośrednio do nginx.
- Wygenerowany Dockerfile frontendu odczytuje index i wszystkie zagnieżdżone
  zasoby jako nginx przed zakończeniem budowy, bez zmiany odziedziczonego USER.
- Regresje3unit +2 rzeczywiste Docker RED→GREEN;29ops/2Docker/Ruff/mypy147 PASS.
  Pełny gate1737backend/507frontend/ESLint/tsc PASS, źródła przed/po identyczne.
  Jeden read-only review bez blokad. Runbook opisuje bramkę i osobny test `proxy`.
  Bez ponownego wdrożenia, migracji lub zmian działającej aplikacji95f8380/f3a9.

## [Production, 95f8380] — 2026-11-06 — Kolory kont i kategorii

### Added
- Wdrożono wybór koloru kont/kategorii, dziedziczenie/reset oraz spójne akcenty
  dashboardu, raportów i budżetów. Ustawienia: Finanse → Konta i kategorie.

### Changed
- Po osobnym zatwierdzeniu dokładnej rewizji: trzy zgodne obrazy i jedna migracja
  `7b57 → f3a9`, świeże backupy/odtworzenia i próba na kopii. Stare wiersze56 tabel,
  ledger, salda, pliki, drzewo kategorii i polityki AI zachowane. Maintenance zdjęty.
- Publiczne HTTPS/health200, auth401, dokładne zasoby, browser375/1440, odczyty
  domenowe, logi i identyfikatory usług danych PASS.5 testów operatora PASS.

### Fixed
- Pod blokadą wykryto i poprawiono uprawnienia publicznych plików w obrazie
  frontendu (bez zmiany bajtów dist) oraz fałszywe alarmy weryfikatora dotyczące
  kolejności ENV i prawidłowych wpisów audytu401. Nie powtarzano migracji.
- Raport: `docs/audits/2026-11-06-finance-colors-production.md`.

## [Local, odebrane] — 2026-11-06 — Kolory kont i kategorii

### Added
- Po „działaj”: wspólny wybór koloru (paleta + dowolny HEX), tryb automatyczny konta,
  dziedziczenie najbliższego rodzica i własne nadpisanie/reset podkategorii.
- Kolory w ustawieniach, kontach/ostatnich transakcjach/budżecie dashboardu oraz
  słupkach kategorii i budżetów. Etykiety i kwoty pozostają czytelne, ostrzeżenia
  przekroczenia budżetu nadal czerwone. Zapis samego koloru wysyła minimalny PATCH.
- Finalny frontend507testów/lint/types/freshbuild oraz145browser+1expectedskipPASS,
  w tym light/dark375/1440 i axe serious/critical0 dla pickera; source/distfreeze zachowany.
- Backend: nullablecolor waccounts/categories, canonical#RRGGBB/null, ownerAPI i minimalnyPATCH.
  Migracjaf3a9 od7b57 addytywna; isolatedAlembicupgrade zachował wszystkie projekcje56tabel.
  Jedenwhole-review:1Important (downgrade traciłzapisane kolory)→2RED→guardrefusal przed
  DROP, emptydowngrade/reupgrade zachowane. TestfixtureDBguard5RED→GREEN.
  Końcowy pełny **1734backend/507frontend/145E2E+1expectedskip/lint/types/build PASS**,
  dokładne źródła/testowanydist i migrationproof zgodne. Raport
  `docs/audits/2026-11-06-finance-colors-local.md`; **nie wdrożono na produkcję**.

## [Production, data operation] — 2026-11-06 — Drzewo kategorii uporządkowane

### Changed
- Po osobnym „tak” na dokładną operację i maintenance: jeden produkcyjny APPLY,
  30 minimalnych aktualizacji +14nowych, 79kategorii (73expense/6income), zachowane
  65oryginalnychID/35nietkniętychwierszy/HOLD/KEEP.45audytówoperatora+1trwałyreceipt.
- READONLYverify, niezależne kontrole DB/global/foreignowner/ledger/ref/AIpolicy i plików PASS.
  Kwoty, salda, postings, FX, daty, źródło Actual i mappings bez zmian; brak markerów,
  reguł, zgód AI, nowych kont lub przetwarzania historii. Importer Actual bez zmian.
- Fresh fenced encrypted backup0c121fec + guarded isolatedrestore/schema/ledgerPASS;
  te same kontenery/obrazy/config, oryginalnynginx przywrócony. PublicHTTPS200/health200/
  anonymous401/jobs0/queue0/errors0PASS. Aplikacja nadal8121512, bez release/deploy.
- Raport `docs/audits/2026-11-06-category-tree-production.md`; bez prywatnych etykiet/UUID
  w Git. Pierwszy probe podczas nginxreload503, późniejszy200 potwierdzony bez nowegoAPPLY.

## [Local, odebrane] — 2026-11-06 — Operator drzewa kategorii

### Added
- Po zatwierdzeniu planu9f51686 i wykonania Native: cztery moduły operator-only,
  anonimowa fixture65→79, weryfikacja wejścia, read-only guard i atomowe serwisy/
  audyt/receipt. Bez endpointów, UI, modeli, migracji lub zmian importera Actual.
- 94testy operatora PASS, w tym rollback po trzech punktach awarii, utrata odpowiedzi,
  replay bez dodatkowych zapisów, konkurencyjny verify i prawdziwa ścieżka CLI na testDB.
- Próba rzeczywistego zatwierdzonego mapowania na świeżo odtworzonej kopii PASS:
  30minimalnychupdates+14creates, 65oldIDs/79total, verify/replay i niezmienione referencje/
  ledger/HOLD/KEEP. Produkcyjny READ ONLY preflight:65kategorii, brak blokerów.
- Runbook `docs/operations/category-tree.md`: immutable runtime, prywatne dowody,
  osobna zgoda na produkcyjny APPLY/maintenance i recovery przez DBreceipt.

### Changed
- Produkcja pozostajeverified-active8121512; **nie wykonano produkcyjnego APPLY**,
  stopu aplikacji, aktywacji markerów/zgód AI, push/merge/deploy lub napraw historii.
- Pełny finalny gate **1722backend/493frontend/lint/types PASS**; osiem testów proxy
  wyłączonych zgodnie z projektowym `-m 'not proxy'`, brak nieoczekiwanych skipów.
  Sourcefreeze zgodny z testowanym pakietem i runtime kopii. Jeden whole-review wskazał
  eagerimport globalnego engine przed walidacją CLI; poprawiono7RED→GREEN przez pure
  kontrakt i lazyimport po autoryzacji, bez zmiany app/**. Brak Critical/minor/declined.
  Powtórzona próba nowego digestu i świeży READONLYpreflight produkcji PASS; także wszystkie
  fingerprinty referencji zgodne z odtworzoną kopią. **Produkcja nadal bez reorganizacji**.

## [Plan do zatwierdzenia] — 2026-11-06 — Kontrolowana zmiana kategorii

### Added
- Użytkownik zatwierdził pełny projekt drzewa jako podstawę odrębnego planu, bez APPLY.
  Plan `docs/superpowers/plans/2026-11-06-category-tree.md`: walidator, read-only preflight,
  atomowe serwisy/audyt/receipt, próba na kopii i osobna zgoda przed produkcją.
- Wyliczono rzeczywiste operacje: 38 zmienionych ścieżek oznacza30aktualizacji istniejących
  kategorii i14nowych węzłów; 8zmian ścieżki wynika tylko ze zmiany nazwy rodzica.

### Changed
- Wyjaśniono z użytkownikiem zależność Actual: migracja zakończona, kolejnych importów
  nie planuje. Guard hierarchii i mapowania pozostają bez zmian; reimport po przeniesieniu
  grup może odmówić. Zapis zgody prywatny; nie zmieniono zaakceptowanych artefaktów.
- W tej sesji tylko plan/dokumentacja i obliczenia offline; bez kodu narzędzia, zapisów
  do DB, zgód aplikacji, nowych kont, migracji lub wdrożenia.

## [Projekt do zatwierdzenia] — 2026-11-06 — Pełne drzewo kategorii

### Added
- Po zgodzie na przygotowanie: projekt drzewa i kompletna tabela65→65 istniejących ID,
  z16KEEP/38EDIT/11HOLD oraz14nowymi węzłami expense. Wariant bez scaleń, usunięć,
  dezaktywacji, zmiany typu lub przepisywania postings; 79 węzłów łącznie z grupami.
- Uwzględniono ustalenia o własnych projektach AI, opłacie bankowej zawieszonej firmy,
  subskrypcjach Apple i prostych kategoriach rodzinnych. Kont pożyczek nie tworzy agent.
- Prywatne nazwy/ID i pełne mapowanie pozostają poza Git w root-only katalogu operatora;
  spec `docs/superpowers/specs/2026-11-06-category-tree-design.md`. Tylko właścicielski
  READ ONLY/rollback i walidacja dokumentu; żadnych zmian produktu, danych lub polityk.

## [Audyt read-only] — 2026-11-05 — Użyteczność po wdrożeniu

### Added
- Po zgodzie i jawnym wyborze konta: izolowane właścicielem odczyty READ ONLY/rollback,
  publiczny browser375/1440 oraz przegląd źródeł UI. Brak zmian danych, AI lub autoryzacji.
- Potwierdzono: obecne transakcje z Actual, brak konfiguracji kategorii technicznej/zgody
  AI i próbki paragonu, invariant księgi bez naruszeń. Nie są to błędy migracji.
- Trzy drobne uwagi źródłowe: komunikat grosze/PLN, pusty stan źródeł, ponowny wybór
  próby po stronicowaniu. Bez napraw i bez twierdzenia o teście zalogowanej produkcji.
  Raport `docs/audits/2026-11-05-finance-readonly-review.md`.

## [Production 8121512] — 2026-11-05 — Etapy finansów 1–4B aktywne

### Added
- Po jawnej zgodzie na rewizję wdrożono spójne backend/worker/frontend: daty zakupów,
  zatwierdzane kategorie/splity, reguły3A, propozycjeAI3B, produkty/rabaty4A i odczyt4B.
- Serwerowe cele AI3B/4B włączone, oba epoch1; zachowano wymagane indywidualne zgody,
  osobny eksport zdjęcia, ręczne zatwierdzenia, limity i brak historii batch.

### Changed
- Sześć migracji2f→7b57, zachowane stare dane32tabel i oryginalne uploady. Zaszyfrowany
  backup a4ca11f6 z izolowanym restore/migracjami/invariantem księgi PASS.
- HTTPS/health/assets/auth401, browser375/1440, obrazy i logi PASS; aktywne metadane8121512.
  Zachowano usługi danych, poprzednie obrazy i schema-aware STOP zamiast utraty nowych danych.

### Fixed
- Host checkout fast-forward do zatwierdzonej8121512 naprawił rozjazd migracji restore.
  Raport `docs/audits/2026-11-05-finance-production-release.md`; prywatny pilot nadal niewykonany.

## [Wydanie requested, preflight blocked] — 2026-11-05 — Gotowe etapy finansów

- User polecił wdrożyć i włączyć gotowe funkcje. Kandydat exact8121512, etapy1–4B,
  sześć migracji2f→7b57, zachowane zgody i brak historii batch. Wymagana finalna zgoda
  exactrewizji/scope według/deploy. Liveproduction8106532/schema2f odczytane bez mutacji.
- Backup świeży7e2c0b91/exit0; wymagany restore drill zablokowany: hostcheckout1865d90
  nie zna już produkcyjnej migracji2f. Nie wykonano migracji lub wymiany usług/aktywacji.
- Pakiet wersjonowany przygotowany, stare runtimeimages zachowane; raport
  `docs/audits/2026-11-05-finance-all-production-preflight.md`. Nie omijać restoregate.

## [Dobór pilota, bez eksportu] — 2026-11-05

- Po zgodzie na użycie wcześniej przekazanego zdjęcia stwierdzono lokalnie, że JPEG
  diagnostyczny przedstawia fakturę, nie paragon. Read-only metadane aplikacji nie
  wykazały aktywnych źródeł receipt/imagePLN. Nie wykonano nowego requestuAI,
  importu/księgowania/aktywacji ani zmian produkcji; prywatny pilot4B niewykonany.

## [Live syntetyk PASS, aplikacja OFF] — 2026-11-05 — Jedna próba API4B

- User uchylił bramkę2PLN, zachowano1request/1syntetyk i pozostałe limity.
  Istniejący klient4B z `gpt-6.1-terra`:dokładnie1request/HTTP200/strictpayloadPASS,
  lokalny kalkulator7200/1800,total9000,difference0. Input2075/output221; koszt naliczony
  USD/PLN niepotwierdzony, cachewriteusage jawnie zachowane.
- Tymczasowy harness:10offline testów i jeden wąski readonly reviewPASS; marker przedHTTP
  blokuje ponowienie. Zero zmian produktu, DB/Redis/ledgeru lub aktywacji aplikacji.
- Raport `docs/audits/2026-11-05-receipt-read-api-result.md`; bez prywatnych zdjęć,
  dodatkowego calla, wdrożenia, merge lub push. Retainedexactsource4B bez zmian.

## [Preflight STOP, bez requestu] — 2026-11-05 — Próba API4B

- User zatwierdził jedną syntetyczną próbę na warunkach c6d687d, z wiarygodną wyceną≤2PLN.
- Potwierdzono oficjalne stawki exactmodel `gpt-6.1-terra`:1USD input/5USD output za1M.
  Sprawdzona dokumentacja vision nie potwierdziła sizing/multiplier dla tego exactID;
  brak podstaw do górnej wyceny obrazu. Zgodnie z warunkiem zgody zatrzymano przed wysyłką.
- 0requestów próby doOpenAI, bez odczytu klucza, harnessu/obrazu lub zmian aplikacji.
  Raport `docs/audits/2026-11-05-receipt-read-api-preflight.md`; cel nadal OFF.

## [Propozycja próby, bez wykonania] — 2026-11-05 — Syntetyczny test API4B

- Po „co proponujesz teraz?” user zatwierdził wyłącznie przygotowanie zakresu/limitów,
  nie wywołanie API. Dokument `docs/audits/2026-11-05-receipt-read-api-probe-scope.md`.
- Propozycja:1syntetyk/1request Terra,2048edge/1MiB/2048outputtokens/retry0,
  bez DB/Redis/uploadu/importu/aktywacji/produkcji. Próg2PLN dopiero po wiarygodnym
  sprawdzeniu taryfy/obrazu i przeliczenia; bez tych danych STOP, nie obietnica hard capu.
- Tylko dokumentacja; retained exactsource4B1628/493/141+1skip potwierdzony,
  bez nowego kodu, obrazu, użycia klucza, API lub ponownego godzinnego gate.

## [Unreleased, local] — 2026-11-05 — Odczyt pozycji paragonu 4B odebrany lokalnie

### Added
- Po „tak” na plan4a41000: osobny domyślnie wyłączony cel odczytu jednego zdjęcia,
  podgląd eksportu i zgoda na cały obraz/dodatkowy koszt, trwałe próby z rezerwacją
  przed wysyłką, brak automatycznego retry po dispatch, cancel tylko przed nim.
- Immutable wynik i jawny import do nowego szkicu4A, pochodzenie wierszy/poprawki,
  potwierdzenia niejasności wiązane z wersją wpisów. Oba zatwierdzenia finansowe bez zmian.
- Migracja7b57f2f0bde6: siedem nowych tabel, retencja starego schematu/danych/indeksów,
  empty rollback/reupgrade i odmowa cofnięcia po dodaniu dowodów sprawdzone tylko
  w izolowanym schemacie finanse_test; bez backfillu lub zmian produkcji.
- Jeden niezależny whole-review:1Important (utrata niepewnej intencji po reload), jeden
  fixpass2RED→GREEN; recovery owner/bill/tab przed POST, bez autoPOST, czyszczenie po
  sessionreplacement/jawnym porzuceniu. Brak Critical, deferred minors i declined behaviors.
- Pełny gate **1628backend/493frontend/lint/types/freshbuild/141E2E+1expectedskip PASS**,
  exactsource/dist/migrationproof i zgodność commitów z zamrożonymi bajtami PASS.
  Backend `f9fe4c8`, frontend `527e92a`; raport `docs/audits/2026-11-04-receipt-read-local.md`.
- Odbiór wyłącznie LOCAL/OFF. Zachowano branch/worktree/Velo/Q7 dirty. Bez aktywacji,
  prawdziwego API, prywatnych zdjęć, mainmerge/push lub wdrożenia produkcyjnego.

### Fixed
- Zachowany replay dawnych komend ręcznego szkicu bez nowego opcjonalnego pola zgody.
- Nieprawidłowe obiekty w kursorze odczytów dają kontrolowane422 zamiast błędu500.

## [Plan] — 2026-11-04 — Odczyt pozycji paragonu 4B

### Added
- User zatwierdził CAŁY projektc147b85 kolejnym „tak”, w tym odczyt na żądanie jednego
  zdjęcia, dodatkowy koszt względem nagłówka, cancel przeddispatch i nową zgodę na reread.
- Plan `docs/superpowers/plans/2026-11-04-receipt-item-extraction.md`:7zadań native/TDD,
  7addytywnychtabel, strictadapter bezretry, zgoda/polityka/contentstream, jednokrotnydispatch,
  jawny import/provenance i warningreview, UI oraz końcowy whole-review/frozengate.
- Self-review autora: zgodnośćspec/interfejsów/5ReviewFocus, konkretne limity i lockgraph.
  Plan wymaga osobnej akceptacji przed wykonaniem. Kod4A i jego retainedproof bez zmian;
  bez nowych testów produktu, migracji, AI/OCR lub produkcji.

## [Design candidate] — 2026-11-04 — Odczyt pozycji paragonu 4B

### Added
- Po rekomendacji następnego kroku user zatwierdził przygotowanie projektu4B („tak”),
  nie implementację lub wywołania modelu. Projekt odczytu jednego wybranego obrazu,
  propozycji produktów/rabatów i jawnego przeniesienia do nowego szkicu4A.
- Oddzielna zgoda celu eksportu, limity i trwały znacznik pojedynczego dispatchu;
  unknown po wysłaniu nie uruchamia automatycznego ponowienia. Dwa zatwierdzenia4A zachowane.
- Wariant na żądanie może oznaczać dodatkowe płatne wywołanie względem obecnego odczytu
  nagłówka; kompromis oznaczony jako propozycja do potwierdzenia. Buildercheck zakończony:
  doprecyzowano cancel przeddispatch/odmowę po i oddzielne status/replay/nowąpłatnągenerację.
- Projekt czeka na akceptację całego opisanego zakresu; dopiero potem osobny plan.
- Bez zmian kodu/testów/migracji/AI/OCR/produkcji; retainedexactsource4A pozostaje zgodny.

## [Unreleased, local] — 2026-11-04 — Produkty paragonu 4A odebrane

### Added
- Po kolejnym „tak” na plan3be47c9: ręczne produkty/rabaty i własne sklepy,
  immutable rewizje, wskazówki exact/prefix z historii i osobny przegląd podziału płatności.
- Migracjaa3ffcaf427aa sprawdzona tylko w nowym izolowanym schemacie testowym:
  sześć tabel bez backfillu, zachowane stare dane/indeksy, odmowa cofnięcia po dodaniu dowodów.
- Jeden niezależny whole-review i poprawka statusu aktualności dowodu4RED→5GREEN.
  Pełny gate1506backend/476frontend/lint/types/freshbuild/131E2E+1expectedskip PASS;
  exactsource/dist/migrationproof PASS, także po commitachbackend09a624d/UI5ea6454.
- Raport: `docs/audits/2026-11-04-receipt-items-local.md`. Zachowano branch/worktree,
  niepowiązane Velo/Q7 dirty oraz dawne dowody; nie powtarzać niezmienionego gate.
- Bez AI/OCR, przetwarzania historii, mainmerge/push i produkcji;4B pozostaje osobne.

## [Plan] — 2026-11-04 — Ręczne produkty paragonu i historia sklepu, etap 4A

### Added
- User zatwierdził projektb972368 słowem „tak”, w tym ręczne4A przed odczytem4B,
  jawny wybór sklepu, udziały rabatów i dwa osobne zatwierdzenia.
- Plan `docs/superpowers/plans/2026-11-04-receipt-item-categorization.md`:6zadań,
  native/TDD i jedno końcowe whole-review;6nowych tabel, kontrolowany odczyt historii,
  humanapply jednej całej płatnościPLN, UI wyszukiwanej listy kategorii. Samodzielny
  self-review planu względem zatwierdzonej specyfikacji; bez kolejnego review projektu.
- Plan czeka na akceptację przed kodem/testami/migracją. Źródła3B i retainedproof bez
  zmian; nie uruchomiono providerów/OCR, historii lub produkcji.

## [Design candidate] — 2026-11-04 — Produkty paragonu i historia sklepu, etap 4

### Added
- Doprecyzowany przez użytkownika kierunek: proponować kategorię produktu na podstawie
  własnych zakupów z tego sklepu; przy braku wskazówki pokazywać pełną listę kategorii
  z wyszukiwarką zawężającą wyniki podczas pisania. Makieta nie jest potrzebna.
- Projekt etapowania:4A ręczne pozycje/rabaty, zatwierdzona historia produktów i osobny
  preview/apply kategorii istniejącej całej płatnościPLN;4B oddzielny odczyt pozycjiOCR/AI.
  Ten podział jest rekomendacją autora do akceptacji, nie już zatwierdzonym zakresem.
- Projekt `docs/superpowers/specs/2026-11-04-receipt-item-categorization-design.md`
  po buildercheck: do potwierdzenia5decyzji zakresu, w tym ręczne4A przed odczytem4B.
  Brak nowych zmian aplikacji, testów produktu, migracji, wywołań
  providerów albo produkcji. Pełny odbiór3B pozostaje dowodem niezmienionego baseline.

## [Unreleased] — 2026-11-04 — Propozycje kategorii AI, etap 3B ukończony lokalnie

### Added
- Oddzielna zgoda na generowanie propozycji dla nowych ręcznych wydatków PLN,
  domyślne OFF, wersjonowana polityka serwera i jawne limity/nieznane zużycie.
- Trwałe zadania utworzenia, rezerwacje quota i pojedyncze dopuszczenie wysyłki.
  Niepewny dispatch nie jest ponawiany; późne usage nie przywraca publikacji.
- Kolejka propozycji, preview i rzeczywiste ludzkie zatwierdzenie jednej kategorii,
  immutable receipt/audyt i approved_llm origin z chronionym stanem manualnym.
- UI skończonego przeglądu wybranych pozycji, częściowe wyniki, zachowane klucze
  ponowienia i izolacja sesji. Nowa kategoria nadal wymaga osobnego utworzenia
  i ręcznego przypisania; brak splitów lub automatyzacji historii.

### Fixed
- Ręczne potwierdzenie tej samej kategorii zastępuje approved_llm origin manualnym.
  Zmiana konfiguracji blokuje stare zgody także po przywróceniu poprzedniej konfiguracji,
  jeśli worker zaobserwował zmianę; GET nie zapisuje polityki.
- Lokalne testy TDD i próba migracji243aa1d9461c zachowują dawną księgę/proweniencję.
  Jeden whole-review: Critical0/Important0/Minor0. Pełny końcowy gate1406backend/
  456frontend/lint/types/freshbuild/127E2E+1expectedskip PASS. Exactsource/dist i hash
  migracji z dowodem retencji PASS, bez powtarzania rehearsal. Backend8a9560f/UI0347e58.
  Odbiór wyłącznie lokalny: bez realnych AI/OCR, aktywacji modelu, zmian produkcji lub historii.
  Raport: `docs/audits/2026-11-04-reviewed-ai-categorization-local.md`.

## [Design] — 2026-11-04 — Propozycje kategorii AI i przegląd, etap 3B

### Added
- Rozpoczęto szczegółowy projekt3B po zgodzie na dalszy krok: trwałe propozycje,
  niezależna zgoda na ograniczony kontekst, nowe źródła tylko przez creationhook,
  quota/dispatch fencing i peritemakceptacja wybranych pozycji po ludzkim przeglądzie.
- Spisany projekt przeszedł read-only buildercheck bez pytań blokujących i został
  zaakceptowany słowem „tak”. Szczegółowy plan pięciu etapów zapisano w
  `docs/superpowers/plans/2026-11-04-reviewed-ai-categorization.md`; wymaga akceptacji
  przed kodem. Zachowany native/TDD i jeden końcowy niezależny review.
- Plan rozdziela zgodę na generowanie od ludzkiego zatwierdzenia, księgowanie usage
  od publikacji wyniku i zamrożony wybór UI od bieżącego cache. Uwzględnia zgodność
  istniejących zdarzeń3A przy snapshotv3 oraz brak ponownej wysyłki po uncertain.
  To wyłącznie dokumentacja, nie implementacja/aktywacjaAI: kod3A i produkcja bez zmian.

## [Unreleased] — 2026-11-04 — Zatwierdzone reguły kategoryzacji, etap 3A lokalnie

### Added
- Jawna kategoria techniczna, domyślnie wyłączone reguły i zatwierdzany exactdescription
  dla przyszłych ręcznych wydatkówPLN. Osobnyorigin/immutablegrant i trwałe zdarzenia
  z lease/CAS/retry; bez AI, historii i zmiany strony kontowej płatności.
- UI w ustawieniach finansów: szkic/podgląd/zgoda, pause/edit/retire, idempotentne retry,
  sessionfences, batchedorigin i eventwatcher. Addytywna migracjac063 tylko izolowanytest.

### Fixed
- Whole-review: informacja o regule dołączana także w historii konkretnego konta;
  freshidentitymap regresjaRED→GREEN. Manualny audyt zachowuje poprzedni ruleorigin.
- Pełny końcowy gate po review:1303backend/439frontend/lint/typesPASS, freshbuild/
  111E2E+1expectedskip i2dodatkowebrowseroriginPASS. Exactsource/dist/migrationhashPASS;
  odbiór lokalny zamknięty.3B/providery/historia/produkcja poza zakresem.
  Raport: `docs/audits/2026-11-04-approved-categorization-rules-local.md`.
  Kod lokalny: backend28ce7f0, UI2b960ee; brak wydania produkcyjnego.

## [Design] — 2026-11-04 — Hybrydowa kategoryzacja, projekt etapu 3

### Added
- Użytkownik zatwierdził politykę: autozapis tylko z wcześniej zaakceptowanej reguły
  na nowym nieskategoryzowanym wydatku; LLM proponuje do ludzkiego przeglądu, także
  wybranej partii. Pewność nie daje prawa zapisu, ręczne decyzje pozostają chronione.
- Spec etapu3 i plan niezależnego3A: jawna kategoria techniczna, exactdescription,
  zatwierdzane reguły, osobnyorigin i creationoutbox.3B propozycje/LLM/usage ma własny
  późniejszy odbiór. Reguła nie fałszuje manualstate etapu2 i nie dotyka historiiActual.
- Szczegółowy plan gotowy po read-only buildercheck i walidacji spisanego dokumentu:
  osobny zapis błędu po rollbacku, loadedpostings, aktualny marker, trwały grant i
  ścisłe retry/CAS. Oczekuje zatwierdzenia przed implementacją. To dokumentacja,
  nie implementacja: brak zmian kodu/bazy, providerów, realnychAI/OCR i produkcji.

## [Unreleased] — 2026-11-04 — Zatwierdzane kategorie i podziały płatności, etap 2

### Added
- Podgląd i ręczne zatwierdzanie rozkładu kategorii wydatkuPLN, w tym100→80/20→100.
  Ledger jest jedynym źródłem kwot; ID i kolumny płatności/alokacje/daty bez zmian.
- Wersjonowane manualstate, snapshot, audyt i FinanceCommandReceipt do bezpiecznego
  ponowienia. Addytywna migracja2268bca97cb8 sprawdzona wyłącznie w ownedfinanse_test,
  bez backfillu lub zmiany zachowanej historiiActual.

### Fixed
- Serializacja usuwania kategorii z zatwierdzaniem splitu chroni przed wyścigiemSETNULL.
- Important review: zwykłe edycje konta serializowane z zatwierdzonym snapshotem,
  oba porządki odtworzone2RED→GREEN/focused28PASS; bez późnego account-row lock.
- Końcowe pełne6gate po review:1250backend/429frontend/lint/typesPASS, freshbuild
  i107E2E+1expectedskipPASS. Manifest potwierdza dokładne źródła/dist i hash migracji.
  Produkcja bez zmian, AI/OCR/historybatch niewykonane.
  Raport `docs/audits/2026-11-04-approved-category-splits-local.md`.

## [Design] — 2026-11-03 — Zatwierdzane kategorie i splity, etap 2

### Added
- Projekt i plan następnego lokalnego etapu: jedna płatność, kategorie100→80/20→100,
  ręczna proweniencja, niemutujący podgląd i jawne zatwierdzenie. ReuseFinanceCommandReceipt
  do idempotencji; accountposting/alokacje/daty bez zmian.
- Read-only buildercheck zakończony bez pytań blokujących. Plan obejmuje dodatkowo
  wspólny lock kasowania kategorii i regresjęONDELETESETNULL. Chroni transakcjeActual,
  pożyczki/FX/pending; pozwala wybrać istniejącą aktywną kategorię zaimportowaną zActual.
- Plan `docs/superpowers/plans/2026-11-03-approved-category-splits.md` czeka na
  zatwierdzenie przed implementacją. Brak zmiany kodu aplikacji, schematu lub danych,
  nowych AI/OCR i działań produkcyjnych; etap1/63e2b9c pozostaje sprawdzonym baseline.

## [Unreleased] — 2026-11-03 — Daty zakupu i księgowania (lokalny etap 1)

### Added
- Jawne daty zakupu/księgowania dla ręcznych wydatków, proweniencja i wersja w osobnej
  tabeli `transaction_date_metadata`; addytywna migracja84f28fe23ab8, bez backfillu.
- Oddzielne polecenie korekty dat: owner/version/snapshot, locks, audyt/no-op oraz
  ochrona importu Actual, płatności dokumentów i pożyczek. Kwoty/postings bez zmian.

### Changed
- Wydatki i budżety według daty zakupu, a historia banku nadal według księgowania.
  Jawny fallback i etykieta nieustalonego typu daty dla starych danych, bez zgadywania.
- Formularze tworzenia/korekty dat; po409 zachowanie wartości i konieczne ponowne
  sprawdzenie świeżych danych. Nowa data nie tworzy kolejnej transakcji.

### Fixed
- Po niezależnym review izolacja QueryClient per generacja sesji zapobiega pokazaniu
  finansów poprzedniego właściciela; same-session `/auth/me` nie resetuje cache ani
  dialogu korekty. Regresje3RED→GREEN,14focusedfrontendPASS po poprawce.
- Końcowy pełny gate po poprawkach:1205backend/420frontend, lint/types/buildPASS,
  105E2E+1expectedskipPASS. Manifest potwierdza dokładne źródła i dist.
  Migracja sprawdzona tylko w izolowanymfinanse_test: dane zachowane, brak backfillu.
- Nie wdrożono. Agent kategoryzacji, zatwierdzane splity/paragony i historia to następne
  etapy2–6. Raport: `docs/audits/2026-11-03-transaction-dates-local.md`.

## [8106532] — 2026-11-03 — Archiwum dokumentów na produkcji

### Changed
- Po „zatwierdzam” i „akceptuję” dla migracji/wdrożenia oraz maintenance/recovery
  wydano spójny backend/worker/frontend8106532 i addytywną migrację2f4b2c2a527c.
- Backup4e7b441f/installedrestore, dodatkowy isolatedrestore92→2f, exactimage210plików,
  12offlineguardów i niezależny operationsreview PASS. Dane/finanse/linki/usage/policy
  i oryginały zachowane; bez nowych AI/OCR, replay, cleanupu lub historycznych napraw.
- HTTPS/assets/authrejection, browser375/1440, workerreadiness i11próbek/343s obserwacji
  PASS; active-release sfinalizowany13:53:23UTC. Generic rollback do starego backendu
  wyłączony; zachować archived_at, przy problemie fence i naprawa zgodna z archiwum.
- Raport: `docs/audits/2026-11-03-document-archive-deployment.md`.
  Bez push/mainmerge; trzy drobne follow-upy pozostają w TASKS.

## [Unreleased] — 2026-11-03 — Bezpieczne archiwum dokumentów, odebrane lokalnie

### Added
- Archiwizacja/przywracanie zamiast harddelete, nullablearchived_at (migracja2f4b2c2a527c),
  owner-scoped API, idempotentne audyty i widokArchiwum. Pliki/historia/finanse bez kasowania.
- Duplikat zarchiwizowanego pliku wymaga jawnegoPrzywróć, nie tworzy odczytu ani refunduquota.

### Fixed
- Aktywna durable/legacy/text praca blokuje archiwizację409, także gdy worker trzyma
  rowlock. Czytelne powody blokady; brak FK500 przy zachowanej historii.
- Cache listy/tekstu/review/podglądu/oryginału izolowany perowner+generacja sesji,
  spóźnione intencje/statusy nie odtwarzają pracy po archiwizacji.
- Oba istotne findings niezależnego review poprawione RED→GREEN. Końcowe wyniki:
  1183 testy backendu, 410 frontendu, lint/types obu warstw, build i 103 E2E PASS
  (1 celowe pominięcie E2E). Manifest potwierdza zgodność źródeł i distu.
- Pierwszy pełny gate ujawnił oczekiwanie starego headu Alembic w teście; poprawiony
  test nadal sprawdza jedną liniową historię. Powtórny pełny gate PASS.
- Odbiór i dwie drobne odroczone uwagi: `docs/audits/2026-11-03-document-archive-local.md`.
  Produkcja pozostaje bez zmian; migracja i wdrożenie wymagają osobnej zgody.

## [Diagnosis] — 2026-11-03 — Usuwanie dokumentów

### Changed
- Ostatni produkcyjny DELETE409 ma rzeczywiste powiązanie z zatwierdzonym dokumentem
  finansowym; blokada jest prawidłowa, ale UI pokazuje wyłącznie ogólny błąd.
- Lokalnie13przypadków +2FKprobes potwierdziły oddzielny błąd500 przy harddelete
  niepowiązanego dokumentu z rewizją/jobem AI/OCR (FK RESTRICT) oraz niepoprawny
  detail409 dla aktywnego jobu. To diagnoza, nie naprawa. Bez kasowania na produkcji,
  zmian kodu aplikacji, AI/OCR lub wdrożenia.
- Raport: `docs/audits/2026-11-03-document-delete-diagnosis.md`.
- Po prośbie „zaproponuj bezpieczny wariant” zapisano propozycję archiwizacji/przywracania
  zamiast harddelete: zachowane oryginały/historia/finanse, blokada aktywnej pracy,
  jawne archiwum i ochrona przed ponownym AI przy duplikacie. Spec/plan w docs/superpowers;
  oczekuje zatwierdzenia pełnego zakresu. Bez implementacji, migracji i zmian produkcji.

## [69b6f3d] — 2026-11-03 — Znacznik pracy AI/OCR i globalny toast na produkcji

### Changed
- Użytkownik potwierdził lepszy odczyt; IBAN i data sprzedaży puste już w zapisanym
  wyniku, nie ukryte przez formularz. Diagnoza wyłącznie read-only/bez wartości/bez AI.
- Po zgodzie użytkownika lokalna implementacja monitora w Layout, znacznika AI/OCR,
  globalnego toastu z otwarciem dokumentu również spoza pierwszej strony. Powiadomienie
  nie oznacza poprawności ekstrakcji; rozróżnia propozycję, niepełny wynik, błąd i pauzę.
- Rzeczywisty najnowszy job OCR i jego identyfikator zamiast hardcodedNone; paginowany,
  owner-scoped odczyt aktywnej pracy bez mutacji. Izolacja sesji, deduplikacja operacji,
  status nieznany przy błędzie sieci i portal toastu w natywnym dialogu.
- Niezależny review: poprawiona regresja podglądu używającego starych etykiet zamiast
  stanu pracy, 4RED→GREEN. Pełny gate1151backend/388frontend/lint/types PASS;
  build i mockedE2E97PASS+1celowy skip (desktop/mobile). Dostosowane stare atrapy API,
  świeże frontend388/lint/types PASS; backend/aplikacja byte-identical z pełnym gate.
  Bez nowegoAI/OCR, migracji lub zmiany ekstrakcji IBAN/daty sprzedaży.
- Po jawnej zgodzie użytkownika wdrożono dokładne69b6f3d backend/worker/frontend.
  Backup e0963350 + installedsame-snapshotrestore PASS; operationsreview/15offlineguards/
  exactimage203filesEachBackendWorker/API4casesEachImage PASS. HTTPS/assets/auth,
  browser375/1440 i ponad5min/10próbek PASS; active-release sfinalizowany09:09:22UTC.
  Schema/policyepoch4/dane/oryginały/dataIDs niezmienione, rollbackd7a2432 zachowany.
  Raport: `docs/audits/2026-11-03-document-processing-deployment.md`.

## [d7a2432] — 2026-11-03 — Kontrakt kwoty na produkcji

### Changed
- Użytkownik zatwierdził dokładny pakiet, nowe etykiety prompt/schema i kontrolowane
  CAS policyoff/on, bez wywołań AI lub ponawiania historycznych dokumentów.
- Kontroler wdrożenia:23offlinePASS, scoped applyreviewPASS i hashbinding. Jednorazowe
  wdrożenie z blokadą driftu, świeżości backupu i policy-aware rollbackiem zakończone
  PASS/exit0. Policyenabled/epoch4, exactimages i reszta danych/originals/schema PASS.
  Browser375/1440 i ponad5min/9próbek obserwacji PASS. Active-release atomowo
  sfinalizowany06:10:33UTC, świeżeHTTPS/liveimageIDs/OCIrevision/contractpolicy zgodne.
- Nowy kontrakt vision-openai-responses-2/vision-2, policyepoch4; dwa zaplanowane
  audyty policy i22 własne security401, reszta user/doc/job/usage/ledger/originals/schema
  i dataIDs bez zmian. Rollback d9a5797 zachowany z monotoniczną procedurą CAS.
- Bez AI/OCR/retry/reuploadu w diagnozie/wdrożeniu. Poprawność rzeczywistego odczytu
  faktury nadal do potwierdzenia jedną jawną próbą użytkownika.

## [Prepared] — 2026-11-02 — Pakiet kontraktu kwoty, bez wdrożenia

### Changed
- Osobna zgoda użytkownika dotyczy wyłącznie przygotowania `d7a2432`, backup/restore
  oraz kontroli wersji i polityki AI. Produkcja pozostaje d9a5797, bez AI/OCR.
- Końcowy gate i tożsamość źródeł ponownie sprawdzone; świeży build/E2E93PASS+1skip.
  Backup9832d2c6 i installed restore tego samego snapshotu success/0; bez ponawiania usług.
- Nieaktywny pakiet d7a2432 zbudowany i digest-pinned; 202 pliki backendu w obu
  obrazach zgodne ze źródłami. Po 21 syntetycznych przypadków na dokładnym backend/
  worker PASS, networknone/zeroAI/zeroDB. Bazowy render nie zmienia konfiguracji.
- Oddzielny overlay proponuje promptvision-openai-responses-2/schema vision-2;
  zmienia wyłącznie dwie etykiety backend/worker, wymaga osobnej zgody na config/CAS
  policy przy przyszłym wydaniu. Read-only stan danych/originals/containers/policy
  niezmieniony. Operations review PASS do przedstawienia zgody, nie do samoczynnego apply.
- Raport: `docs/audits/2026-11-02-vision-amount-release.md`. Bez wdrożenia lub AI.

## [Unreleased] — 2026-11-02 — Ścisły kontrakt kwoty w odczycie obrazu

### Fixed
- Po zatwierdzeniu zakresu przygotowano lokalnie wzorzec dodatniej, kanonicznej kwoty
  w nullable `VisionFields.total` oraz zgodną instrukcję dla modelu: cyfry ASCII,
  kropka dziesiętna, maksymalnie dwa miejsca, bez separatorów grupowania, waluty,
  znaków lub exponent. Nieznana/niejednoznaczna kwota pozostaje `null`.
- Bez normalizowania błędnej odpowiedzi, obliczania sum lub zaokrąglania. Dotychczasowa
  dokładna konwersja na grosze, limit kwoty, ręczne zatwierdzanie i bezpieczne błędy
  pozostają niezmienione.
- Test-first: brak reguły wykazany 27 błędami nowych testów; po poprawce 94 testy
  adaptera/kontraktu PASS. Pierwszy pełny gate: 1146 backend, 335 frontend, lint/types
  PASS. Po review doprecyzowano opcjonalną kropkę dla kwot całkowitych oraz `null`
  dla niejednoznacznych separatorów: 2 RED → 95 focused PASS. Końcowy gate PASS:
  1147 backend (8 proxy deselected, 10 warnings), 335 frontend, lint/types obu;
  dokładny manifest testowanych źródeł bez zmian. Scoped review rozliczony.
- Brak wywołań AI/OCR, zmian dokumentów/produkcji i wdrożenia. Lokalna poprawka nie
  potwierdza prawidłowego odczytu faktury; wydanie i wersje prompt/schema wymagają
  osobnego procesu z kontrolą policy fingerprint.

## [Diagnosed] — 2026-11-02 — Jedna zatwierdzona próba: odrzucona kwota AI

### Changed
- Po osobnej zgodzie wykonano dokładnie jedno diagnostyczne wywołanie AI dla
  istniejącego dokumentu. Wynik: etap `amount`, pole `total`, typ `invalid_amount`.
  JSON przeszedł walidację; odmowa nastąpiła przy konwersji kwoty na grosze.
- Nie zachowano wartości ani odpowiedzi modelu. Nie ustalono konkretnego wariantu
  błędnej kwoty i nie przypisano tego wyniku retrospektywnie wcześniejszym próbom.
- Jednorazowy, audytowany odczyt: limit użycia +1, trwały znacznik wykonania +1,
  audyt rezerwacji i zakończenia +1 każdy. Brak nowych zadań/rewizji, ponowień,
  zmian pól dokumentu, walidacji, konfiguracji lub wdrożenia. Oryginał zweryfikowany.

## [Investigating] — 2026-11-02 — Odrzucona odpowiedź AI po naprawie pełnego obrazu

- Dwie jawne próbyvision zakończone invalid_model_output/1attempt; log wskazuje bramkę
  payload/kwota/review, ale nie konkretne pole. Brak podstaw do następnej poprawki dat
  lub kwot bez dokładniejszego dowodu. Późniejszy lokalnyOCR zakończony technicznie.
- Diagnoza tylko read-only/bezpieczne kody, bez wartości faktury i kolejnych AIcalls.
  Do ustalenia zgodny kontrakt i jedna uzgodniona diagnostyczna próba, bez wyłączania
  walidacji, automatycznych ponowień lub obchodzenia policy/quota/audit.

## [d9a5797] — 2026-11-02 — Pełna pochodna JPEG i jawne PonówAI na produkcji

### Fixed
- Przygotowano naprawę odbioru stdout konwertera: czytanie doEOF zlimit+1,
  równoległe stdin/stdout, timeout/kill/drain/reap i SOI/EOI zamiast uciętych64KiB.
- Dla incomplete/image/unreadable lub brakującychpól przygotowano wyjaśnienie i jawne
  PonówAI bez kasowania/reuploadu/autoretry. Usuwanie dokumentów poza tym zakresem.
- TDD3backend/2UIRED→61backend/33frontendGREEN, lint/typesPASS; publiczne asyncAPI
  kandydata zwraca pełne644947B/1536×2048, zgodnechild/decodePASS, zeroAI/OCR/DB.
  ImportantUI zreview poprawiony4RED→GREEN,38frontend/lint/typesPASS. Końcowy1080backend/
  335frontend/lint/types/build/93E2E+1skipPASS. Kod d9a5797 i dokładny pakiet/trueasync
   stream/date/400smokePASS; po zgodzie exactSHA wdrożone. Browser375/1440,
   HTTPS/assets/auth/10próbek obserwacji i atomoweactive-release20:08:59Z PASS.
- Dane/originals/schema/policy bez zmian, rollback5d5b82f zachowany. Bez AIretry,
  migracji lub kasowania; dalszy odczyt wyłącznie jawną decyzją użytkownika.
  Raport complete-image-stream2026-11-02.

## [Diagnosed] — 2026-11-02 — Ucinanie pochodnej przed AI w odczycie stdout

- Lokalna analiza bezAI/OCR wykazała poprawny pełnyJPEG644947B/1536×2048, lecz
  aplikacyjne normalize_image odbiera tylko65536B, nie kończyEOI i nie daje się
  dekodować. Skrót tego fragmentu zgodny z pochodną zapisaną przy ostatnim odczycieAI.
- Przyczyna: pojedyncze StreamReader.read(n) zwraca fragment, nie gwarantuje EOF;
  aplikacja nie doczytuje stdout konwertera. Oryginał niezmieniony, zero nowegoAIcall.
  Nie zmieniono limitów lub rozdzielczości; poprawka granicy procesu do zatwierdzenia.

## [Diagnosed] — 2026-11-02 — Nieczytelny wynik AI i blokada ponowienia/usunięcia

- Odczyt zakończył się technicznie, lecz model zgłosił unreadable/brak wymaganych pól.
  UI ukrywa PonówAI dla incomplete bez errorcode, co blokuje jawne ponowienie.
- Próby usuwania zwracają500/ForeignKeyViolation; lifecycle nowych trwałych zadań/
  rewizji nie jest uwzględniony w usuwaniu dokumentu. Bez kasowania danych lub AIretry
  w diagnozie; poprawki do zaprojektowania i zatwierdzenia.

## [5d5b82f] — 2026-11-02 — Bezpieczna walidacja dat wyniku AI na produkcji

### Fixed
- Po zgodzie użytkownika doprecyzowano nullableISO kontrakt dat i objęto konwersję
  ReviewFields bezpieczną granicą błędów, bez inputów/tracebacków i lease-exhaustion.
- UI odróżnia błędny wynik AI od braku dostępności dostawcy; dla starego przerwanego
  odczytu dostępne wyłącznie jawne PonówAI lub ręczna edycja, bez automatycznego retry.
- Focused36backend/51frontend i lint/types PASS; source review bez findings,16guardów,
  backup8d9d72db/restore PASS. Kod5d5b82f: pełny1070backend/325frontend/lint/types
  i końcowybuild/93E2E+1skipPASS. Dokładny pakiet/syntheticdate/HTTPsmokePASS,
  po zgodzie exactSHA wdrożone. HTTPS/assets/auth/browser375/1440 i10próbek
  obserwacjiPASS; active-release sfinalizowany2026-11-02T18:34:03Z.
- Bez migracji/policychange/automatycznego replay dokumentu. Oryginały i dane zachowane,
  rollback45c8c2d dostępny. Dalszy odczyt wyłącznie jawnym PonówAI użytkownika.
  Raport: `docs/audits/2026-11-02-vision-date-validation.md`.

## [Diagnosed] — 2026-11-02 — Mylące „AI niedostępne” po udanym uploadzie

- JPEG zapisany poprawnie; odpowiedź AI dochodzi do konwersji pól, ale data sprzedaży
  odrzucona przez walidatorISO powoduje nieobsłużony ValidationError, a następnie
  wyczerpanie2prób/lease. UI pokazuje ogólny komunikat AI niedostępne.
- Odtworzono lokalnie na syntetycznych danych; diagnoza bez ponownego AI, zmiany
  danych dokumentu lub osłabiania walidacji. Poprawka kontraktu/granicy błędów do zgody.

## [45c8c2d] — 2026-11-02 — JPEG/MPO z mapą HDR iPhone na produkcji

### Fixed
- Po zgodzie użytkownika przygotowano wąską obsługę AppleJPEG z głównym obrazem
  i pomocniczą mapą HDR, bez globalnego dopuszczenia dowolnych plików wieloobrazowych.
- Zachowane limity, oryginał i istniejąca normalizacja głównego obrazu. TDD i poprawki
  po niezależnym review:91focusedPASS, lint/typesPASS; udostępniony JPEG lokalniePASS,
  bez AI/DB. Build/93E2E+1skip i świeży backup b9b3a8d5/restore PASS.
- Kod45c8c2d: pełny gate1057backend/316frontend/lint/typesPASS. Dokładne obrazy
  i lokalny smoke JPEG/pochodnej oraz4kodówHTTP PASS. Po zgodzie użytkownika scalono
  na lokalny main i wdrożono spójny pakiet bez migracji lub zmiany polityki AI.
- Produkcyjne HTTPS/assets/auth, browser375/1440 i10próbek obserwacji PASS;
  active-release sfinalizowany2026-11-02T14:00:26Z. Dane i oryginały zachowane,
  rollback9369b5d dostępny. Pozostaje jedna rzeczywista próba telefonu.
  Raport: `docs/audits/2026-11-02-iphone-gainmap-jpeg.md`.

## [9369b5d] — 2026-11-02 — Diagnostyka uploadu z iPhone na produkcji

### Fixed
- Bezpieczne kody odrzucenia400 i polskie komunikaty zamiast jednego ogólnego błędu.
  Log zawiera wyłącznie kod, kategorie MIME i liczbę bajtów, bez treści dokumentów.
- Wdrożone spójne obrazy9369b5d;1036backend/316frontend/93E2E+1celowy skip,
  lint/types/build, niezależny review, backup c3935c47/restore i smoke PASS.
- Produkcyjna przeglądarka375/1440 i10próbek obserwacji PASS; schemat, polityka vision,
  oryginały i stare dane bez zmian. Bez migracji lub wywołania AI w diagnozie.
- To diagnostyka, nie potwierdzona naprawa Safari. Potrzebna jedna próba użytkownika.
  Raport: `docs/audits/2026-11-02-upload-rejection-diagnostics.md`.

### Kontekst diagnozy

- Dostarczony JPEG pozwolił odtworzyć błąd: biblioteka rozpoznaje MPO/2obrazy,
  główny obraz decode/verifyPASS, a obecny walidator odrzuca taki format/liczbęobrazów.
  Test dokładnegoobrazu produkcji z rzeczywistymi limitami, networknone/bezAI/DB.
  Potwierdzona przyczyna dla dostarczonego pliku; poprawka jeszcze nie wdrożona.
- Próba przez Pliki też odrzucona; log12:50:25UTC ma te same parametryJPEG/3809248B.
  Obejście niepotwierdzone. Dalsza diagnoza wymaga dokładnego pliku z tej próby;
  nie wdrożono kolejnej zmiany ani nie osłabiono walidacji.
- Po wdrożeniu użytkownik potwierdził komunikat validation_failed. Dwie próby
  12:45:26/12:45:59UTC: deklarowany image/jpeg,3809248B, detected=unknown.
  To inna reprezentacja niż lokalnie sprawdzony HEIF3675697B. Przyczyna odrzucenia
  przez parser nadal niepotwierdzona; bez zmian walidacji i bez wywołania AI.

- Zgłoszony błąd przesyłania; logi wskazują400 przedAI. Syntetyczny JPEG12MP przechodzi
  rzeczywisty parser. Przyczyna konkretnego odrzucenia w trakcie ustalania, bez zmian
  kodu, runtime lub oryginałów; brak twierdzenia o naprawie.
- Oryginał HEIF udostępniony do lokalnego testu także przechodzi walidację w dokładnym
  runtime (UID10001/networknone), bez wysyłki doAI lub zapisu doaplikacji. Do rozstrzygnięcia
  pozostaje typ/zawartość faktycznie przesyłana przez Safari; wymagana dokładniejsza
  bezpieczna diagnostyka400, a nie podnoszenie limitów.
- Po zgodzie użytkownika wdrażana mała diagnostyka kodów400/logów bez treści dokumentu
  i przetłumaczonych komunikatówUI; nie zmienia warunków akceptacji pliku. Backup
  c3935c47/restore PASS; wydanie zakończone, brak twierdzenia o naprawie uploadu.

## [84c9c27] — 2026-11-02 — Dokumenty i całe AI na OpenAI, produkcja

### Added
- Doradca/tool calling GPT6.1Sol, ekstrakcja tekstu i nowych zdjęć GPT6.1Terra,
  Responses/store=false, jawna polityka visionepoch2, bez fallbacku DeepSeek.
- Wydany wcześniej odebrany obieg faktur/paragonów i wizualny odczyt JPEG/PNG/HEIF;
  oryginały prywatne, propozycje nadal do ręcznego zatwierdzenia.

### Fixed
- Obsługa skompresowanych odpowiedzi OpenAI, stateless replay narzędzi i reasoning,
  bez wykonania mutacji przy odmowie/incomplete; testy CLI niezależne od scratch.
- Gate1031backend/308frontend, lint/types/build/93E2E+1skip, live syntetyczne API,
  backup a82d4237/restore, rehearsal c2→92 i finalne obrazy PASS. Po wydaniu backup
  e037d2e8/restore, HTTPS/assets/auth/browser oraz10próbek obserwacji PASS.
- Dane historyczne/originals/usługi danych zachowane; końcowy active-release zapisany
  atomowo, rollback zachowany. Pierwszy automatyczny rollback wynikał wyłącznie
  z nieuwzględnionych własnych audytów401; kontrolowanyresume odebrany. Bez importów.
- Raport `docs/audits/2026-11-02-openai-production-release.md`. Lokalny main
  zaktualizowany dla restore drill, bez push; preview i inne aplikacje bez zmian.

## [Deployment requested] — 2026-11-02 — Produkcja zamiast pilotażu

- Użytkownik zatwierdził kierunek bezpośredniego wydania; kandydatbb831ce.
  Preflight bez zmian runtime: produkcja9db255b nie ma konfiguracji vision.
  Następnie rozszerzył zakres na całe AI aplikacji na OpenAI. Inwentaryzacja trzech
  klientów zakończona; brak klucza OpenAI w konfiguracji produkcyjnej. Nowe modele
  wymagają weryfikacji parametrów i Responses dla narzędzi; samą podmianę nazwy
  modelu odrzucono jako niewystarczającą. Brak deployu lub migracji na tym etapie.
- Dobór Sol/Terra zatwierdzony, klucz OpenAI dodany poza czatem; dostęp do obu modeli
  potwierdzony bez generacji. Migracja klientów w toku; backupa82d4237/restore i
  frontendbuild/93E2E+1skip PASS. Produkcyjne aplikacje i polityka jeszcze bez zmian.

## [Unreleased] — 2026-11-02 — Automatyczny odczyt zdjęć ukończony lokalnie

### Added
- Automatyczny vision dla nowych JPEG/PNG/HEIF po aktywacji osobnej konfiguracji,
  strict schema i ręczne zatwierdzenie bez automatycznych płatności.
- Trwałe zadania/rewizje, limit wywołań, lease/recovery i atomowy policy epoch CAS;
  brak niejawnego odczytu starych zdjęć/GET/duplikatów. Lokalne OCR jako jawna alternatywa.

### Fixed
- EXIF i prywatna pochodna bez GPS, zachowanie oryginału, ręcznej edycji i pustej
  waluty; czytelne błędy terminalne oraz polling tylko aktywnych zadań.
- Osiem etapów i końcowe review odebrane. Gate1017backend/308frontend, lint/types/
  build PASS; pełne93E2E+1celowy skip ponownie na końcowym kodzie. Migracja i rzeczywisty
  dump/restore29tabel na syntetykach PASS. Raport document-vision-verification2026-10-31.
- Brak push/merge/deploy/migracji runtime lub aktywacji AI w preview/produkcji;
  zgodność konkretnego dostawcy i testy prawdziwych telefonów pozostają osobnym gate.

## [Unreleased] — 2026-10-31 — Odczyt zdjęć: pierwsze trzy etapy

### Added
- Modele trwałych zadań, polityki/epoki i limitów oraz addytywna migracja92eef8e8086c.
- Oddzielna konfiguracja vision i kontrolowany adapter obrazu ze ścisłym schematem,
  bez narzędzi agenta, redirectów i niejawnych ponowień SDK.

### Fixed
- Orientacja EXIF także dla JPEG/PNG przed OCR, bez zmiany oryginału/metadanychGPS.
- Zmiana celu/modelu unieważnia starą epokę; odmowa modelu nie staje się gotowym
  odczytem nawet przy równoczesnym content. Task1–3 po niezależnym review.
- Ostatni pełny gate978backend/279frontend i lint/types PASS. Task4–8 w toku;
  bez aktywacji AI, migracji preview/produkcji lub deklaracji pełnej gotowości funkcji.

## [Planned] — 2026-10-31 — Plan automatycznego odczytu zdjęć

- Użytkownik zatwierdził pełny projekt vision; przygotowano8 zadań TDD z dokładnymi
  interfejsami, addytywną migracją, normalizacją EXIF, limitami/lease i testami UI.
- Plan `docs/superpowers/plans/2026-10-31-automatic-document-vision.md` sprawdzony
  względem projektu. Brak implementacji lub zmiany podglądu/produkcji; realny model,
  klucz, retencja i egress pozostają osobnym warunkiem aktywacji.

## [Designed] — 2026-10-30 — Automatyczny odczyt zdjęć przez AI

- Po decyzji użytkownika „automatycznie” przygotowano projekt odczytu nowych obrazów
  przez model wizyjny, bez obowiązkowego OCR, z ręcznym zatwierdzeniem i bez księgowania.
- Projekt po builder check: osobna konfiguracja modelu, limity, trwałe rewizje,
  normalizacja EXIF, prywatność i brak niejawnego przetwarzania starych zdjęć.
  Pełny zakres czeka na zatwierdzenie; bez implementacji, migracji i aktywacji AI.

## [Diagnosed] — 2026-10-30 — Zdjęcia telefonu w podglądzie

- Po zgodzie porównano bezpośredni odczyt obrazów przez asystenta z zapisanym OCR
  dwóch zdjęć: upload działa, lecz tekst OCR jest mocno zniekształcony przy tekście
  bokiem. Puste pola review mają osobny powód: celowo wyłączony LLM w podglądzie.
- Obecna integracja LLM otrzymuje tekst, nie obraz; nie wystarczy samo dodanie klucza.
  Diagnoza bez zmian aplikacji, oryginałów i danych finansowych; szczegóły prywatnie.

## [Preview] — 2026-10-30 — Izolowany test dokumentów na telefonie

### Added
- Zatwierdzony podgląd `https://finanse-test.birek.online` z fikcyjnymi danymi,
  osobnym stackiem/bazą/uploadami i lokalnym OCR, bez kluczy LLM i rejestracji.
- Rzeczywiste HTTPS uploadPDF/JPEG/HEIF, OCR, prywatny oryginał/preview, ręczne review
  bez zmiany księgi oraz przeglądarka375/1440 PASS. Niezależny odbiór do testów właściciela.

### Changed
- Dodano tylko nowy host i dedykowany ingress w Caddy; stare trasy/HTML/ID i czasy
  startu produkcji bez zmian. Brak merge/deploy/migracji/importu produkcji.
- Test prawdziwych telefonów nadal wymaga użytkownika; raport
  `docs/audits/2026-10-30-isolated-document-preview.md`, bez sekretów w Git.

## [Unreleased] — 2026-10-30 — Obieg faktur i paragonów

### Publication
- Po osobnej zgodzie użytkownika wypchnięto `feat/financial-document-workflow`
  i utworzono draft PR [#5](https://github.com/RobertBirek/finanse/pull/5) do `main`.
  Bez scalania, wdrożenia lub operacji na danych produkcyjnych. CI przy utworzeniu
  w kolejce; test prawdziwych Android/iPhone pozostaje BLOCKED.

### Added
- Prywatny oryginał i podgląd, bezpieczna pochodna HEIC/HEIF oraz wersjonowane
  propozycje OCR z ręcznym retry. Rejestr faktur/paragonów ze źródłami i duplikatami.
- Jawne częściowe alokacje istniejących wydatków PLN i osobna, potwierdzana rejestracja
  nowej płatności. Sam upload lub zatwierdzenie dokumentu nie tworzy kosztu.
- Faktury w Nadchodzących z pozostałą kwotą, konkretnym zastąpionym wystąpieniem
  reguły, jawną decyzją replace/separate i powodami wyłączenia z prognozy PLN.
- Interfejs aparatu i galerii, globalna kolejka wielu plików, prywatny podgląd,
  ręczne sprawdzanie danych, jawne ponowienie OCR i decyzje attach/separate duplikatów.
- Rejestr z filtrami, historią alokacji i źródłami, osobnym zapisem płatności,
  coverage oraz jawnym odświeżeniem/porównaniem po konflikcie wersji409.

### Fixed
- Ochrona powiązanych transakcji i metadanych, wspólne blokady konkurencyjnych mutacji.
  Etapy1–10 i końcowy review po poprawkach; gate949backend/
  279frontend/75E2E+1celowydesktopskip, lint/types/build PASS.
- Brak podwójnej prognozy przed decyzją coverage; jawne ostrzeżenie rzeczywistego
  skutku alokacji dla estymaty cyklicznej i potwierdzenie przed przypisaniem.
- Stabilne klucze zagnieżdżonych decyzji i ponowione409 wymagające właściwego refetch.
- Lokalny parserDocker i izolowana syntetyczna migracja/dump-restore PASS.
- Końcowa wspólna poprawka domyka backendfilters/exclusionreasons, guard tożsamości
  pokrytej faktury i server-enforced potwierdzenie wpływu archiwizacji/anulowania.
- Funkcja pozostaje niewdrożona; całościowy przegląd gałęzi PASS. Certyfikacja
  rzeczywistych Android/iPhone BLOCKED (brak urządzeń). Raport:
  `docs/audits/2026-10-28-financial-document-workflow-verification.md`.
  Bez importu, migracji produkcji lub zmian dokumentów użytkownika.

## [Discussed] — 2026-10-28 — Dokumenty z aplikacji i zdjęć telefonu

### Added
- Projekt rejestru faktur/paragonów, jawnych alokacji istniejących płatności i integracji
  z Nadchodzącymi bez powielania estymat cyklicznych. Dwa przebiegi builder check;
  końcowo brak istotnych pytań. Zakres zaakceptowany przez użytkownika.
- Plan implementacji10 zadań z kontraktami i gate testów, w tym HEIC/HEIF, częściowe
  rozliczenia, ochrona księgi, brak podwójnej prognozy i obsługa istniejących uploadów.

### Changed
- Zakres przyszłego obiegu: wyłącznie dodawanie plików w aplikacji, bez Google Drive;
  zdjęcia faktur/paragonów wymagane. Rozpoznano lukę między istniejącym OCR/Inbox
  a rejestrem faktur, rozliczaniem i Nadchodzącymi. Bez implementacji lub zmian danych.
- Użytkownik zatwierdził pierwszeństwo obiegu faktur i paragonów przed dalszym Q7.
- Do pierwszego wydania włączono HEIC/HEIF: zachowanie oryginału i lokalna pochodna
  JPEG bez danych lokalizacji, bez wymagania ręcznej konwersji na telefonie.
- Po wyborze wariantu z niezależnymi przeglądami rozpoczęto implementację w lokalnej
  gałęzi, od bezpiecznej obsługi zdjęć. Bez wdrożenia lub zmian dokumentów użytkownika.

## [Reviewed] — 2026-10-28 — Dodatkowe wyciągi bankowe, bez importu

### Added
- Inwentaryzacja46 plików z folderu użytkownika, kontrola SHA i prywatny pakiet.
  Odczyt nowych dokumentów Velo/ING/Citi/Revolut, sald, okresów i nakładania źródeł.
- Dowody rozdzielonej wypłaty Q7 oraz wrześniowej raty/nadpłaty; porównanie z dawnym
  snapshotem wskazuje istniejące wpłaty i odsetki, bez ponownego księgowania.

### Changed
- Częściowo uzupełniono blokady Velo: sierpień rachunku i cykl karty do17.09 są już
  dostępne. Październik rachunku nadal brakujący; NO IMPORT / NO AUTO CORRECTIONS.
- Powtórzenia plików/CSV i niejednoznaczne powtórzenia wewnątrz wydruku karty opisane
  osobno, bez globalnej deduplikacji. Raport: `docs/audits/2026-10-28-additional-statements-review.md`.

## [Reviewed] — 2026-10-28 — Q7: dwie nadpłaty i początkowy kredyt

### Added
- Uzgodnienie offline deklarowanej kwoty początkowej, dwóch rat i dwóch nadpłat
  z oboma PDF. Wszystkie trzy punkty kontrolne kapitału zgodne co do grosza.
- Jawne oznaczenie interpretacji dat OCR i wyliczonego, niepotwierdzonego bankowo
  podziału pierwszej raty. Bez księgowania, importu lub korekty produkcji.

## [Reviewed] — 2026-10-28 — Porównanie dwóch harmonogramów Q7

### Added
- Odczytowe porównanie wcześniejszego i późniejszego PDF z folderu użytkownika:
  zgodna umowa/rachunek, po59 rat, identyczne terminy, mniejszy kapitał i raty.
- Niezależna kontrola118 wierszy, sum i mostów kapitału do zera; późniejszy plik
  identyczny z poprzednio zweryfikowanym źródłem. Prywatne dowody poza Git.

### Changed
- Rozróżniono efekt nadpłaty widoczny w planie od dowodu wykonania przelewu.
  Bez importu planów/płatności, korekt księgi lub zmian produkcji.

## [Reviewed] — 2026-10-28 — Podgląd harmonogramu Q7 bez zapisu

- Po zgodzie użytkownika przygotowano komplet59 rat z oryginalnego PDF, z kontrolą
  hashów i niezależną ekstrakcją. Sumy składników, mosty kapitału i finał0 zgodne.
- Właścicielski READ ONLY odczyt potwierdził kandydata istniejącej pierwszej płatności
  oraz różnicę planu i księgi odpowiadającą jej odsetkom. Bez automatycznej korekty.
- Nie zapisano umowy/rat/linków ani prognozy; księga i audyt identyczne przed/po.
  Pełny podgląd, CSV i propozycja importu tylko w prywatnym pakiecie poza Git.
- Zgoda na zapis została uzależniona od obsługi nadpłaty i zmian harmonogramu;
  zapis wstrzymany do doprecyzowania danych i projektu wersjonowania/spłat kapitału.

## [Corrected] — 2026-10-28 — Potwierdzona waluta EUR i wycena NBP

- Po potwierdzeniu kwot EUR i osobnej zgodzie na wycenę NBP skorygowano jedno konto
  i obie strony6 operacji. Kwoty źródłowe/ID/daty/kategorie/mapowania zachowane,
  PLN przeliczone oficjalnymi kursami; ledger zbilansowany i audit old/new zapisany.
- Operator-only serwis: pełny backend858/frontend243, lint/types, backup1732c2cc/
  restore, kopia produkcji i świeży odczyt po commicie PASS. Bez importu, migracji,
  zmiany zwykłych guardów lub wdrażania nowych obrazów. Kod lokalnie w51bf351.
- Raport: `docs/audits/2026-10-28-confirmed-currency-correction.md`; prywatne dane
  i identyfikatory pozostają poza Git.

## [9db255b] — 2026-10-28 — Plan rat i powiązania płatności Q7

### Added
- Umowy kredytów/pożyczek PLN, raty z kapitałem/odsetkami/opłatami i jawne powiązanie
  istniejących przelewów. Pokrycie częściowe/pełne wyliczane z postingów, bez duplikatów.
- Ustawienia finansów → Kredyty i pożyczki: formularze, kandydaci z paginacją,
  odpinanie metadanych i wyraźne rozróżnienie planu, księgi i uzgodnionego kapitału.
- Addytywna migracja trzech pustych tabel `c2d7e9a4f801` po `b8e4c2f1a7d9`.

### Fixed
- Blokady waluty/usunięcia obu kont umowy, także archiwalnej; ochrona powiązanego
  przelewu przed zmianą daty/pending i usunięciem. Niezmienione wartości są idempotentne.
- Ścisłe kwoty całkowite, konflikt bez ujawniania SQL, odświeżanie ORM po blokadzie;
  serializacja przypisywania/odpinania i ochrony przed nadmiernym pokryciem raty.
- Pełny backend844 PASS (8 proxy deselected,2 znane warningi bibliotek), osobno
  proxy5 PASS; Ruff/mypy PASS. Frontend243/E2E59+1skip, lint/types/build PASS.
  Po zgodzie użytkownika main/push i wdrożenie9db255b z addytywną migracją:
  backup6ebdef50/restore i rehearsal PASS, CI obu domen success, HTTPS/assets/auth/
  browser oraz niezmienność historii/uploads/usług danych PASS. Obserwacja5-min10/10
  PASS, metadane runtime zaktualizowane atomowo, rollback zachowany.
  Raport: `docs/audits/2026-10-28-release-loans.md`.
- Sam plan/link nie rozksięgowuje dawnych odsetek i nie tworzy kosztu ani prognozy.
  Brak importu rzeczywistego harmonogramu lub korekt Velo.

## [9db255b] — 2026-10-28 — Bezpieczna edycja waluty konta

### Added
- Waluta PLN/EUR/USD w edycji ustawień konta; backend wylicza możliwość zmiany
  z historii i powiązań, nie z salda. UI przy braku capability blokuje zmianę.
- Ochrona przed równoczesną zmianą waluty i pierwszym postingiem/harmonogramem:
  blokady wierszy kont oraz odświeżenie danych ORM po oczekiwaniu.

### Fixed
- PATCH waluty nie jest już ignorowany. Null/nieobsługiwane wartości odrzucane,
  historia/pending/zerowe saldo z postingami/harmonogram/import blokują zmianę409.
  Konflikt nie zmienia innych pól; obecna waluta może być przesłana ponownie.
- Sam slice walut nie wymaga migracji, przeliczania historii ani importu. Lokalnie
  gotowy27.10; wydany28.10 razem z metadanymi Q7 w9db255b. Pozostałe zobowiązania
  pozostają kolejnymi iteracjami.
- Frontend: 235 testów jednostkowych, 47 E2E + 1 celowy desktop skip,
  ESLint/tsc/build i axe edycji PASS; niezależne review bez blokad.
- Backend: 812 PASS (8 proxy deselected, 2 znane warningi bibliotek), Ruff/mypy PASS;
  końcowe ponowienie 25 testów walut/queries po uzupełnieniu typowania PASS.

## [Reviewed] — 2026-10-27 — Pogłębienie uzgodnienia Velo

- Read-only odświeżenie i mosty sald rachunku/karty; zlokalizowano składniki różnic
  oraz potwierdzono daty/kwoty trzech spornych operacji w dostarczonym eksporcie Actual.
- Brak nowych wyciągów nadal blokuje uzgodnienie otwarcia i zapis; bez importów,
  automatycznych korekt ani zmian kodu. Końcowy guard rekordów/originals PASS.
- Raport bez prywatnych kwot: `docs/audits/2026-10-27-velo-reconciliation.md`.
- Ponownie udostępniony folder Drive zawiera cztery identyczne hashami źródła;
  brak nowych dokumentów do rozstrzygnięcia różnic. Bez ponawiania importu/analizy.

## [e5ce5f5] — 2026-10-27 — Poprawki po przeglądzie finansów

### Fixed
- Okres finansów zapisany w URL, zachowany po odświeżeniu, powrocie z historii
  i przejściu przez zakładki/linki przeglądu; bez przenoszenia filtrów transakcji.
- Pełny kontrast tekstu i aktywnych przycisków kont archiwalnych w obu motywach.
- Dostępny komunikat kopiowania IBAN-u, obsługa odmowy/braku Clipboard API
  i ręczne kopiowanie z możliwością ponownego ukrycia numeru.

### Added
- Regresje jednostkowe i E2E na fikcyjnym API, w tym axe dla kont archiwalnych.
- Weryfikacja: frontend 230 unit / 43 E2E + 1 celowy skip,
  lint/typecheck/build PASS; niezależne review bez blokad.
- Po osobnej zgodzie scalono/push main i wdrożono sam frontend. Backup 0c35f0fe
  i izolowany restore PASS, CI obu domen PASS; bez migracji i importów.
  HTTPS/assets/auth/browser i niezmienność danych/usług poza frontendem PASS.
  Pięciominutowa obserwacja 11/11 PASS, bez restartów i nowych błędów aplikacji;
  metadane wydania zaktualizowane, rollback zachowany.
  Raport: `docs/audits/2026-10-27-release-ui-fixes.md`.

## [Reviewed] — 2026-10-27 — Przegląd użyteczności po wdrożeniu

- Przegląd40 kombinacji widok/szerokość/motyw na dokładnym frontendzie wydania
  z fikcyjnym API. Potwierdzono gubienie okresu raportu, kontrast archiwalnych kont
  i brak obsługi odmowy kopiowania IBAN-u. Bez zmian kodu, danych lub deployu.
- Brak zalogowanej sesji produkcyjnej; nie deklarujemy testu rzeczywistych danych.
  Raport i kolejność poprawek: `docs/audits/2026-10-27-finance-ui-review.md`.

## [1b42e34] — 2026-10-26 — Nowy interfejs finansów i ustawień

### Added
- Opcjonalne dane bankowe kont: bank, właściciel, IBAN/NRB, BIC i notatka;
  walidacja oraz nullable migracja `b8e4c2f1a7d9` po dotychczasowym head `c7f8c620460d`.
- Źródłowe salda kont, serwerowe agregaty sald ogólnych/budżetowych, głębokie drzewo
  raportu oraz filtry podkategorii i kont budżetowych.

### Changed
- Jeden sidebar, dolna nawigacja mobilna, jasny/ciemny motyw i wspólne powierzchnie.
  Przegląd z rzeczywistych API, wykres prognozy, szybkie operacje i panel szczegółów.
- Konta, drzewo kategorii, limity, harmonogramy i parametry prognozy w ustawieniach;
  historyczne adresy zachowane, dane finansowe i mapowania Actual bez przekształceń.
- Limit dziecka jako podlimit rodzica: agregaty budżetu/cashflow nie liczą gałęzi
  podwójnie. Linki z raportów zachowują ich zakres kont i podkategorii.
- Raport wdrożeniowy i rozstrzygnięcia: `docs/audits/2026-10-26-finance-ui-implementation.md`.
  Weryfikacja: backend790/frontend220/E2E31+1skip, lint/types/build PASS.
  Po osobnej zgodzie scalono/push main i wdrożono backend/worker/frontend oraz
  addytywną migrację b8. Backup c5520a46+restore i próba na kopii PASS;
  HTTPS/assets/auth/browser PASS, stare dane i oryginały bez zmian. Rollback obrazów
  zachowany, bez importu księgi. Raport: `docs/audits/2026-10-26-release-finance-ui.md`.
  Pięciominutowa obserwacja11/11 PASS, bez restartów i nowych błędów aplikacji.

## [Prototype] — 2026-10-26 — Makieta nowego UI finansów

### Added
- Po zgodzie użytkownika opublikowano klikalny, polski prototyp pod `/makieta/`:
  przegląd, transakcje, budżet, nadchodzące, raporty i ustawienia finansów.
- Ustawienia oddzielają konfigurację kont/danych bankowych, drzewa kategorii,
  limitów i harmonogramów. Fikcyjne dane w pamięci; brak API i trwałego zapisu.
- Weryfikacja lokalna i HTTPS: 60 kombinacji widok/szerokość oraz główne interakcje
  PASS; brak błędów JS/CSP i żądań API. Axe 8 widoków bez naruszeń badanych reguł.
- Publikacja wyłącznie nowych plików statycznych, bez restartów/migracji/importu
  ani dostępu do bazy. Istniejące assets/Nginx oraz kontenery niezmienione.
  Frontend 194 testy i lint/typecheck/build PASS. Docelowy interfejs jeszcze nie wdrożony.
  Raport i ograniczenia: `docs/audits/2026-10-26-finance-mockup.md`.

## [Reviewed] — 2026-10-24 — Podgląd wyciągów bankowych, bez importu

### Added
- Po zgodzie przeanalizowano95 wierszy:5 CSV Revolut,81 PDF rachunku VeloBank,
  9 PDF karty.73 pojedyncze kandydatury finansowe,17 niejednoznacznych powtórzeń,
  5 bez zgodnej kwoty:4 korekty odsetek i1 konflikt kwoty zakupu.
- Dokumenty same w sobie spójne; Revolut odpowiada saldom PA. Rachunek Velo ma
  różnicę otwarcia/zamknięcia; zgodny koniec karty maskuje różnice otwarcia i zdarzeń.
  Nie jest to zatwierdzony zakres zapisu. Rekomendacja:wyjaśnić różnice,nie importować.
- Świeże odczyty READ ONLY potwierdziły niezmienność księgi właściciela i oryginałów.
  Bez deployu,migracji,uploadu,importu,korekt ani transakcji z harmonogramu kredytu.
  Raport:docs/audits/2026-10-24-bank-preview.md;dane szczegółowe tylko prywatnie.

## [Imported] — 2026-10-24 — Actual uzupełniony na produkcji

- Po jawnej zgodzie i świeżym backupbd201f28+restore success/0 zapisano286 nowych
  operacji,799 pominięto jako istniejące,0 błędów. Wcześniejsze1601 pełnych zapisów
  transakcji/postingów niezmienione; obowiązkowe invariants i zakres sprawdzone przed commitem.
- Augmented16/16 kont,54/54 kategorii,9/9 grup zgodne; raw Actual nadal jawnie pokazuje
  zachowaną przypiętą historię.1085 mapowań idempotencji poprawnych,2 konta zamknięte
  pozostają inactive. Bez replacement,korekt,migracji,deployu i importu bankowego.
- Niezależny fresh-process READ ONLY potwierdził cały snapshot,salda,invariants1887,
  pin i1085 mapowań. Dodatkowy backup po imporciec69299d0 i restore success/0.
  Raport:docs/audits/2026-10-24-actual-production-import.md.

## [Verified] — 2026-10-24 — Aktualność przed importem Actual

- Kontrola tylko do odczytu:serwer Actual nie ma komunikatów po watermarku zatwierdzonego
  eksportu; ZIP/pin i produkcyjne konta,kategorie,mapowania oraz1601 pełnych zapisów
  transakcji/postingów są identyczne z baseline próby.
- Zakres nadal286 nowych operacji+1 zachowana source-absent. Wspólne operacje zgodne;
  poprzednie21 różnic opisów odtworzono jako efekt brakujących nazw zamkniętych kont
  w starym parserze. Obecnie0 różnic opisów,bez aktualizacji danych.
- Raport:docs/audits/2026-10-24-actual-current-preflight.md. Brak importu produkcyjnego;
  potrzebna osobna zgoda i świeży backup/restore przed ewentualnym wykonaniem.

## [d3c2c68] — 2026-10-24 — Wdrożona aplikacja, bez importu księgi

### Changed
- Po jawnej zgodzie scalono/push main i wdrożono backend/worker/frontendd3c2c68.
  Gate main:backend778/frontend194/E2E29+1skip,lint/types/build i GitHub CI PASS.
- Backupfa1551c7 i restore drill success/0. Zachowano hardening, dane/env/usługi danych;
  bez migracji, importu Actual/bankowego i resetu retry.
- Dwie wycofane próby opisano jawnie w raporcie: poprawiono uprawnienia wygenerowanej
  kopii kodu dla UID10001 i rozdzielono zmienną metrykę cron od niezmienności księgi.
  Końcowy HTTPS/health/assets/auth/browser375+1440 PASS; dane/pliki bez zmian.
- Raport:docs/audits/2026-10-24-release-d3c2c68.md; active metadata zaktualizowane,
  poprzednie obrazy i rollback do backend6811809/frontend8a7cda5 zachowane.

## [Unreleased] — 2026-10-24 — Jawne uzgodnienie zachowanej historii Actual

### Added
- Użytkownik zatwierdził uzgodnienie eksportu plus dokładnie jednej zachowanej
  lokalnej operacji z kontrolą ID i hasha. Zapisano projekt i plan actual-preserved-history.
  Manifest tylko identyfikuje zaakceptowany zapis; kwoty nadal z PostgreSQL.
- Plan zakłada osobny surowy raport, pełną kontrolę pozostałych różnic i próbę wyłącznie
  na kopii. Rozpoczęto zatwierdzone wykonanie natywne: moduł manifestu/fingerprintu/
  blokad i wkładu postingów przeszedł66 testów RED → GREEN (3266377).
  Backend tego modułu748 PASS (8 proxy deselected,2 znane warningi), frontend194 i lint/types PASS.
- Integracja CLI/niezmiennego ZIP/raportu raw_actual+augmented:30 nowych testów PASS,
  łącznie206 finansowych/kontraktowych PASS. Po końcowym review naprawiono kontrolę
  obecności pinu także w drugiej stronie transferu/dzieciach splitów i pomijanych
  przez rekonstrukcję wierszach. Regresje RED3 → GREEN, Ruff/mypy PASS.
- Próba na kopii z przypiętym manifestem PASS:286 nowych operacji,0 błędów;
  powtórzenie0 nowych/1085 pominiętych, identyczny raport i wiersze. Augmented zgodne
  dla16/16 kont,54/54 kategorii i9/9 grup; surowe różnice nadal jawne.
- Pełne fingerprinty1601 wcześniejszych transakcji/postingów niezmienione,2 zamknięte
  konta nieaktywne. Obie izolowane kopie zatrzymane. Raport:
  docs/audits/2026-10-24-actual-preserved-history-rehearsal.md.
  Końcowy backend778 PASS (8 proxy deselected,2 znane warningi), frontend194 i lint/types PASS.
  Brak zgody na import produkcyjny.

## [Unreleased] — 2026-10-24 — Historia zamkniętych kont Actual

### Fixed
- Parser uwzględnia wszystkie nietombstonowane konta, także zamknięte, w metadanych,
  walutach, nazwach transferów i saldach. Zamknięte konta są tworzone jako nieaktywne;
  import nie otwiera ponownie lokalnie zarchiwizowanych kont ani nie wymyśla dat zamknięcia.
- Jawny, wewnętrzny tryb importu historii Actual pozwala użyć nieaktywnego konta
  bez jego aktywacji. Zwykłe API i sam parametr source nadal nie omijają blokady;
  pozostałe walidacje księgi/własności pozostają włączone.
- Regresje RED → GREEN; 90 testów importera (w tym świeża sesja po rollbacku),
  110 testów z uzgodnieniami/kontraktami, backend682 PASS (8 proxy deselected,
  2 znane warningi), Ruff/mypy i ESLint/tsc/194 Vitest PASS. Review bez blokad.
- Próba na kopii: 16 kont, 0 błędów importu. Pozostała jedna różnica konta/kategorii/
  grupy, dokładnie odpowiadająca zachowanej operacji nieobecnej w eksporcie.
  require_reconciled wycofał całość; potwierdzono niezmienność1601 transakcji/postingów
  oraz metadanych kont i mapowań. Bez importu produkcyjnego i deployu.

## [Unreleased] — 2026-10-24 — Przyrostowe mapowanie Actual

### Fixed
- Po zgodzie użytkownika poprawiono rozpoznawanie nowych kont/kategorii przy
  kompletnych istniejących mapowaniach; brakujące historyczne referencje nadal blokują import.
- Regresje nowych encji, brakujących/błędnych mapowań, jednoznaczności postingów,
  rodzica kategorii, źródła bez grup i zachowania operacji nieobecnej w eksporcie:
  oraz nieużytych mapowań stale/unowned/wrong-model: RED → GREEN, 74 testy importera PASS.
  Walidacja wszystkich zapisanych referencji źródła odbywa się przed tworzeniem encji.
  Zachowano bezpieczne odtwarzanie brakującej grupy w częściowo zmapowanej historii legacy.
  Ruff/mypy i frontend ESLint/tsc/194 Vitest PASS;
  pełny backend666 PASS (8 proxy deselected, 2 znane ostrzeżenia), niezależny review bez blokad.

### Changed
- Ponowiona próba wyłącznie na kopii PA przeszła mapowanie, ale wymuszone uzgodnienie
  sald zatrzymało import: 7 transferów odwołuje się do 2 zamkniętych kont pomijanych
  przez parser. To osobna blokada; nie zmieniano jeszcze obsługi zamkniętych kont.
- Potwierdzono pełny rollback transakcji/postingów kopii i zatrzymano kontener próbny.
  Bez zapisu do produkcji, replacement, migracji ani wdrożenia.

## [Preflight] — 2026-10-23 — Aktualizacja z Actual

- Zweryfikowano lokalne źródło Actual: snapshot wymaga późniejszych komunikatów
  synchronizacji. Nie uruchomiono importu nieaktualnego snapshotu do księgi.
- Backup PA12055508 i izolowany restore drill success/0. Prywatne kopie źródła
  poza repozytorium; potrzebny kompletny zsynchronizowany eksport budżetu.
- Dostarczony świeży eksport zweryfikowany; próba na izolowanej kopii PA zatrzymana
  na mapowaniach legacy (nowe encje źródłowe). Backup/restore bc2a3f05 PASS.
  Brak importu produkcyjnego; dalszy krok wymaga poprawki importera i ponownej próby.

## [Verified] — 2026-10-23 — Testy aplikacji po wdrożeniu UI

- Produkcyjny smoke na320/375/768/1440px PASS: logowanie anonimowe, brak overflow/
  błędów JS, lokalne fonty i ochrona API. Bez mutacji danych.
- E2E na pakiecie produkcyjnym29 PASS +1mobile-only skip; Vitest194 PASS,
  ESLint/tsc PASS. Raport: docs/audits/2026-10-23-webapp-test.md.
- Nie testowano operacji na zalogowanym koncie produkcyjnym (brak sesji).

## [8a7cda5] — 2026-10-23 — UI/UX wdrożone

### Changed
- Wdrożono wyłącznie frontend8a7cda5; backend/worker nadal6811809.
  Backup/restore cfc7102f, HTTPS/health, hashe JS/CSS/fontów i logowanie PASS.
- Backend/worker/Stirling/PostgreSQL/Redis bez restartu. Bez migracji i zmian danych.
  Smoke UI obejmuje anonimową stronę logowania; zalogowane widoki testowano na fixtures.

## [Unreleased] — 2026-10-23 — UI/UX pulpitu osobistego

### Release preparation
- `8a7cda5` scalono do main i wypchnięto. Przygotowano frontend-only image
  z przypiętym digestem, rollback do 6811809 i backup/restore cfc7102f PASS.
  Backend/worker i wcześniejszy refaktor finansów poza zakresem wydania.

### Fixed
- Na telefonie nazwy kont i kategorii nie konkurują z przyciskami działań;
  długie nazwy zawijają się. Przyciski wspólne i kontrolki kalendarza mają min. 44 px.
- Formularz transakcji i przegląd finansów pozwalają ponowić błędne odczyty;
  ładowanie ma tekst dostępny dla czytników ekranu.
- Mobilna agenda mieści puste dni w zwartych wierszach, bez ukrywania wpisów.

### Changed
- Dzisiaj pokazuje działania i chronologiczny plan przed statystykami także w DOM;
  bieżący blok oznaczony „Teraz”. Nowa granatowo-łupkowa paleta i lokalne fonty
  Barlow Semi Condensed / Source Sans 3 (licencje OFL w public/fonts).
- Audyt/screenshoty na danych syntetycznych, bez odczytów prywatnych danych ani deployu.
  Gate: backend642, frontend194, E2E29 PASS +1 celowe pominięcie testu mobile
  na desktopie; lint/types/build PASS. Axe na 8 widokach bez naruszeń wybranych
  reguł WCAG A/AA; review bez blokad. Bez wdrożenia.

## [Unreleased] — 2026-10-23 — Podział serwisu finansów

### Changed
- `finance.service` pozostaje publiczną fasadą; implementacje przeniesiono do
  modułów transactions, reporting, budgets i cashflow, daty do dates.
- Bez zmiany schematów/API, SQL, reguł księgi, zaokrągleń i blokad potwierdzeń.
  Wydzielono czyste obliczanie potomków kategorii z testem zachowania.
- Baseline finansów/integrity 207 PASS, kontrakty i jednostkowe FX 15 PASS;
  backend 642 PASS (8 proxy deselected), frontend 194 PASS, lint/types PASS.
  Niezależny review bez ustaleń blokujących. Brak migracji i deployu.

## [6811809] — 2026-10-23 — Wdrożona poprawka proporcji OCR

### Fixed
- Wdrożono zachowanie proporcji obrazów OCR i automatyczny dobór orientacji A4.
  Backup da7eb2d7 i restore drill PASS; HTTPS/health/assets i odrzucanie anonymous PASS.
- Zmieniono tylko obrazy backend/worker/frontend. Hardening zachowany;
  Stirling, PostgreSQL i Redis bez restartu. Bez migracji, zmian ACL i resetu retry.

## [Unreleased] — 2026-10-23 — Proporcje obrazów OCR

### Changed
- Rewizja 6811809 scalona do main i wypchnięta; pakiet produkcyjny oraz rollback
  przygotowane, backup/restore 23bcbccb PASS. Produkcja nadal działa na c765ea9.

### Fixed
- Konwersja PNG/JPEG przed OCR jawnie zachowuje proporcje i dobiera orientację
  strony A4 zamiast rozciągania obrazu. Oryginały, limity i retry pozostają bez zmian.
- Regresja multipart oraz rzeczywistej geometrii PDF odtworzyła wcześniejszy błąd.
  Staging OCR PASS: szerokie PNG/JPEG, pionowe PNG/JPEG i skan PDF, także polski
  tekst; geometria i niezmienność oryginałów potwierdzone. Poprawka niewdrożona.
- Gate: backend 636 PASS (8 proxy deselected), osobno staging OCR 1 PASS,
  frontend 194 PASS; Ruff/mypy/ESLint/tsc i diff check PASS.

## [c765ea9] — 2026-10-23 — Wdrożenie pakietu bezpieczeństwa dokumentów

### Changed
- Wdrożono backend, worker, frontend i przypięty Stirling non-root/read-only;
  zachowano cap-drop, no-new-privileges i limity zasobów.
- Zastosowano ACL uploads bez default inheritance, zmiany właścicieli i treści;
  migracja `c7f8c620460d` wykonana jawnie. Stirling wystartował przed workerem.
- Backup `e45cdc85` i izolowany restore drill PASS. HTTPS/health/zasoby 200,
  anonimowe dokumenty 401; obrazy, UID, mounty, logi i niezmienione data IDs sprawdzone.
- Pozostają: szerokie obrazy fillPage, walidacja worst-case sizing oraz komunikat
  Stirling o opcjonalnym katalogu szablonów na read-only root.
- Kontrola po wdrożeniu (12:31 CEST, ok. 9–11 min pracy): brak restartów/OOM
  i nowych błędów, kolejka OCR pusta, HTTPS/health poprawne. To krótka obserwacja
  bez obciążenia, nie test wydajności ani gwarancja długoterminowej stabilności.

## [Unreleased] — 2026-10-23 — Pakiet bezpieczeństwa dokumentów (niewdrożony)

> Historyczny zapis przygotowania; aktualny status wdrożenia znajduje się powyżej.

- Follow-up na osobnej gałęzi: derived Stirling z przypiętym modelem pol,
  hash-guarded patchem init i ścisłą walidacją uprawnień przeszedł rzeczywisty
  staging OCR PNG/JPEG/PDF dla skanów A4. Produkcyjne Compose i dane bez zmian.
- Finalny gate follow-up: 632 testy backendu, 8 proxy/ACL/OCR i 194 frontend PASS;
  lint/typecheck/build OK. Niezależny review i poprawki pokrycia zakończone.
- Dodano testy ACL/restore non-root na syntetycznych plikach. Wykryto osobno
  zniekształcanie szerokich obrazów przez domyślne fillPage; pozostaje w backlogu.
- Przygotowano projekt kompatybilnego runtime Stirling i stagingu uprawnień
  uploads; implementacja w toku na osobnej gałęzi. Dalszy staging ujawnił
  konflikt vendor chmod z wymaganą polityką uprawnień; runtime nie jest zatwierdzony.
- Release `f256a10` wypchnięto do `main`; wdrożenie zatrzymane na stagingu:
  docelowy Stirling 2.14.3 nie uruchamia się z profilem read-only/non-root.
  Bez migracji produkcyjnej ani zmiany aktywnych usług.
- Po review objęto limitem Nginx 21 MiB obie ścieżki uploadu (z końcowym `/`
  i bez); regresja na rzeczywistym Nginx odtworzyła wcześniejsze odrzucenie 2 MiB.
- Walidacja PDF/PNG/JPEG w ograniczonym procesie potomnym (RAM, CPU, timeout,
  concurrency, limity stron/pikseli/klatek), środowisko bez sekretów aplikacji.
- Limity body przed multipart, spójny limit Nginx 21 MiB/plik 20 MiB,
  serializowana kontrola logicznych quota i rezerwy miejsca przed zapisem.
- Strumieniowe, ograniczone odpowiedzi OCR; nieoczekiwana kompresja odrzucana
  przed dekodowaniem. SHA-256 i oryginalne bajty zachowane.
- Retry błędów przejściowych przechowywane w PostgreSQL (3 próby, 30/120 s);
  błędy integralności/limitu/permanentne kończą przetwarzanie. Re-upload nie resetuje budżetu.
- Migracja `c7f8c620460d` dodaje metadata retry; przetestowano wyłącznie izolowaną bazę.
- UI pokazuje termin ponownej próby oraz odróżnia 413 od niedostępności 503/507.
- Dodano niewłączony profil hardeningu Compose i oddzielne kontenerowe testy w CI.
  Profil wymaga staging z docelowym obrazem Stirling; subprocess nie jest pełnym sandboxem.

## [Unreleased] — 2026-10-22

### Audit
- Po zgodzie na pakiet 1 przygotowano plan izolacji walidacji, limitów uploadu/OCR,
  storage admission i trwałego retry. Implementacja i deploy jeszcze nierozpoczęte.
- Przeprowadzono przekrojowy audyt rewizji `7cde5ac`: finanse, auth/AI,
  dokumenty/worker, frontend, CI i wybrane aspekty operacyjne.
- Raport: `docs/audits/2026-10-22-audit.md` — 14 ustaleń i 5 grup ryzyk,
  dowody, ograniczenia oraz kolejność proponowanych napraw. Bez zmian aplikacji.
- Potwierdzono CI tej rewizji: 582 backend, 189 Vitest i 18 Playwright PASS;
  produkcyjne obrazy pozostają starsze. Nie wykonano deployu ani migracji.

### Changed
- Zintegrowano zmiany z `genspark_ai_developer` z najnowszym `main` do
  wspólnej wersji `a115afc`; wdrożenie produkcyjne pozostaje poza zakresem.

### Fixed
- Upload dokumentów parsuje PDF-y i dekoduje PNG/JPEG przed storage w serwisie;
  odrzuca pliki uszkodzone i niezgodne z deklarowanym MIME przed zapisem.
- Worker weryfikuje SHA-256 oryginalnych bajtów przed OCR i przekazuje te same
  zweryfikowane bajty do parsera, aby nie odczytywać ponownie zmienionego pliku.
- Usunięto nadmiarowe puste linie EOF i poprawiono opis aktywnego workflow CI.

### Verified
- Backend: `381 passed, 182 skipped`; Ruff i mypy PASS.
- Frontend: Vitest `189 passed`; ESLint, TypeScript i build PASS.
- `git diff --check` PASS. Pominięto produkcyjne/operacyjne artefakty z
  nieśledzonego katalogu `webapp/` — nie należą do repozytorium.
- Po poprawkach: backend `400 passed, 182 skipped`; Ruff i mypy PASS. Testy
  integracyjne są wykonywane w GitHub Actions na osobnym Postgresie.

Format oparty na [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Wersjonowanie: [Semantic Versioning](https://semver.org/).

## Aktywacja CI i przenośny test migracji — 2026-10-21 (niewdrożone)

- Właściciel dodał `.github/workflows/ci.yml` na gałęzi PR #4. CI jest aktywne;
  opis wcześniejszej blokady poniżej przedstawia stan historyczny.
  Uprawnienia aplikacji GitHub nie zostały rozszerzone.
- Pierwszy przebieg: frontend przeszedł wszystkie kroki, backend miał 561 PASS
  i jeden błąd testu migracji sesji: sztywna ścieżka `.venv/bin/alembic`
  nie istnieje na runnerze GitHub. Ruff, mypy i połączenie testowej bazy przeszły.
- Test uruchamia teraz `sys.executable -m alembic`, z tego samego środowiska co
  pytest. Dodano regresję wyboru interpretera i przekazania testowej bazy
  zamiast domyślnego DATABASE_URL. Nie zmieniono migracji ani workflow właściciela.
- Lokalnie Ruff, mypy (53 moduły) oraz 5 testów modułu sesji PASS, w tym pełny
  cykl migracji na odizolowanym `finanse_test` (loopback, port 55432).
  Pełny przebieg GitHub Actions po poprawce jest weryfikowany w PR #4.
- Bez wdrożenia, migracji produkcyjnej i zmian danych produkcji. PR nadal draft.

## Tailwind 4 i weryfikacja gotowości CI — 2026-10-20 (niewdrożone)

### Migracja i testy
- Tailwind 3 zastąpiono Tailwind **4.3.3** i natywnym pluginem Vite.
  Usunięto stary plugin PostCSS, konfigurację PostCSS i zbędne bezpośrednie
  zależności autoprefixer/postcss. Plik JS z paletą marki ładowany jest jawnie
  przez `@config`; skanowanie klas ograniczono do źródeł i index.html.
- Zachowano dotychczasową paletę sRGB, style przycisków, placeholderów i granic.
  Zaktualizowano nazwy utility zaokrągleń i focus outline zgodnie z v4;
  gradient pozostaje w sRGB. Nie zmieniano logiki finansowej ani API.
- **npm audit całego drzewa, także dev: 0 zgłoszeń**. Tym samym zamknięto
  poprzednie 7 zgłoszeń w łańcuchu Tailwind 3, bez `audit fix --force`.
- **189 testów Vitest PASS**, ESLint, TypeScript, build i diff check PASS.
  **18 testów Playwright PASS** (wcześniej 12): dodano kontrolę skompilowanych
  kolorów/paddingów, nawigacji responsywnej, focus klawiatury oraz geometrii modala.
- Porównano 31 scenariuszy/zrzutów przed i po migracji w Chromium przy 375/1440 px:
  strony, formularz edycji, szczegóły transakcji i menu mobilne, bez overflow.
  Nie jest to deklaracja zgodności piksel w piksel: natywne pola daty różnią się
  o 2 px, a modal nie dziedziczy już dawnego przesunięcia 16 px z odstępów rodzica;
  test potwierdza pełny viewport, wycentrowanie, Escape i focus.
- CSS buildu wzrósł z ok. 28.84 kB (gzip 5.82) do 37.34 kB (gzip 7.26).
  Backend niezmieniony; nie powtarzano jego poprzednich 562 testów w tej iteracji.
- Tailwind 4 wymaga nowoczesnych przeglądarek: Safari 16.4+, Chrome 111+,
  Firefox 128+. Lokalnie sprawdzano Chromium; Safari/Firefox nie były testowane.

### CI nadal wymaga działania właściciela
- Odczyt GitHub API `user/installations` potwierdził, że instalacja
  `genspark-ai-developer` ma contents/administration/issues/pull_requests,
  lecz **nie ma uprawnienia workflows**. API wykazało zero workflow w repo.
  Nie próbowano obejścia ograniczenia ani samodzielnego rozszerzania uprawnień.
- Zaktualizowano dostarczany osobno szkic `ci.yml`: Python 3.12, PostgreSQL 16,
  Node 22, lint/typecheck/test/build/audit/Playwright, minimalne contents:read,
  bez sekretów produkcji i bez wdrożenia. Szkic odrzuca pominięte testy integracyjne.
  Sprawdzono strukturę YAML i składnię osadzonego Pythona, nie wykonanie na GitHub.
- Właściciel musi dodać szkic jako `.github/workflows/ci.yml` lub nadać aplikacji
  uprawnienie workflows:write. **CI nie jest aktywne**, PR pozostaje draft.
- Migracja ma wydzielony commit w istniejącym PR #4; nie tworzono fikcyjnego
  osobnego PR z tej samej gałęzi. Bez wdrożenia, migracji bazy i zmian danych produkcji.

## Domknięcie walidacji backendu — 2026-10-20 (niewdrożone)

### Poprawki i kontrakty
- PATCH kont: jawny `null` dla `name`, `type`, `is_active`, `is_budget_account`
  zwraca 422 przed odczytem/zapisem encji. Pominięte pola nie są aktualizowane;
  `closed_at=null` oraz wartości `false` pozostają poprawne.
- PATCH inbox: analogicznie chronione `content` i `is_processed`; nadal można
  wyczyścić `target_id`/`target_type`. Test integracyjny potwierdza brak częściowego
  zapisu, gdy poprawne i błędne pola znajdują się w jednym żądaniu.
- Naprawiono dodatkowo 500 dla poprawnego PATCH inbox: po UPDATE jawnie
  odczytywany jest serwerowy `updated_at`, bez asynchronicznego lazy-load
  podczas synchronicznej walidacji odpowiedzi.
- Starsze endpointy list transakcji, inbox, zadań i bloków czasu wymagają
  `limit >= 1`; zachowano górne granice 200/500, wartości domyślne i `offset=0`.
  Testy obejmują dolne/górne granice, domyślne limity i błędne parametry.
- Ekstrakcja LLM ma ścisły schemat: rzeczywiste boolean `detected`, typ
  income/expense, dodatnia całkowita kwota do granicy BIGINT (bez konwersji
  string/bool/float), PLN/EUR/USD, ograniczony niepusty opis, data YYYY-MM-DD
  lub null i opcjonalna kategoria. Dodatkowe pola są zabronione.
- Błędny/niepełny JSON jest traktowany jako brak rozpoznania. Brakujące kwoty,
  waluty i daty nie są zgadywane. Ponowna walidacja przed dostępem do bazy
  chroni również bezpośrednie wywołania tworzenia sugestii.
- Zachowano JSON mode dostawcy i limit tekstu OCR; klient jest zamykany w
  `finally`. Logi odrzuceń nie zawierają tekstu OCR ani odpowiedzi modelu.
- Kwoty sugestii są zapisywane i formatowane bez float, również na granicy
  BIGINT. Sugestia nadal nie jest zatwierdzoną transakcją. Odrzucenie sugestii
  nie cofa OCR, a ponowne przetworzenie nie duplikuje istniejącego inbox item.

### Weryfikacja
- **562 testy backendu PASS, bez pominięć** (137 więcej niż po poprzednim etapie).
  Wyłącznie odizolowany PostgreSQL `finanse_test`, `127.0.0.1:55432`.
- Ruff, mypy (53 moduły), `pip check` i `git diff --check`: PASS.
- Frontend bez zmian kodu: ponownie **189 testów PASS / 23 pliki**, ESLint,
  TypeScript i produkcyjny build PASS. Playwright nie był powtarzany w tej iteracji.
- Wywołania LLM/OCR w testach są mockowane; nie zużywano API ani danych produkcji.
- Brak migracji, aktualizacji zależności i wdrożenia w tej iteracji.
  Zgłoszenia Tailwind zamknięto w późniejszym etapie opisanym powyżej;
  blokada uprawnień CI pozostaje otwarta.

## Audyt i refaktor — 2026-10-20 (niewdrożone)

### Zakres i poprawki
- Przegląd repozytorium: sesje, CSRF/Origin, limity Redis, izolacja właściciela,
  księga finansowa i raportowanie, zatwierdzanie narzędzi AI, dokumenty/worker,
  frontend, zależności i skrypty operacyjne. To lokalny audyt kodu i regresji,
  nie test penetracyjny produkcji ani gwarancja braku wszystkich podatności.
- Naprawiono `TypeError`/500 dla dowodów CSRF spoza ASCII: jawne 403 przed
  odczytem sesji; trzy nowe testy regresyjne.
- Naprawiono renderowanie strukturalnych błędów API (np. tablicy `detail` z 422)
  i błędów sieciowych na ekranie kont; cztery nowe testy regresyjne.
- Wydzielono `finance/entities.py` i `finance/ledger_validation.py`, zachowując
  fasadę serwisu i kontrakty routerów/importera/AI. Serwis: 1251 → 983 linie.
- Wydzielono wiersze kont/kategorii i normalizację błędów do komponentów;
  `FinanceAccounts.tsx`: 819 → 318 linii.
- NBP: zamykanie klienta HTTP także przy błędzie/braku kursu, odrzucanie
  NaN/Infinity oraz Decimal/half-even zamiast mnożenia float. Regresja:
  `75 * 4.1` ma dawać 308 groszy, nie 307. Dziewięć nowych testów.
- Zaktualizowano React Router 7, Vite 7, Vitest 4, TypeScript ESLint 8
  i zgodne zależności przechodnie; dostosowano konfigurację i testy routera.
- Zaktualizowano FastAPI/Starlette/Pydantic, certifi/Mako i pytest/pytest-asyncio;
  ujednolicono deklaracje zależności, dodano brakujące arq i narzędzia dev.
  Określono zakres pętli fixture asyncio. Nie zmieniono współdzielonego venv.

### Końcowa weryfikacja lokalna
- Backend: **425 PASS, zero pominięć** na PostgreSQL `finanse_test`, loopback
  `127.0.0.1:55432`. Początkowe 177 pominięć wynikało z domyślnego portu 5432.
- Frontend: **189 PASS / 23 pliki**; Playwright: **12 PASS** (desktop/mobile).
  Testy przeglądarkowe używają produkcyjnego buildu i mocków API, nie produkcji
  ani pełnej integracji z zewnętrznymi dostawcami.
- Ruff, mypy (53 moduły), ESLint, TypeScript, build, `pip check`,
  `git diff --check` i kontrola składni skryptów Bash: PASS.
- Audyt npm `--omit=dev`: zero zgłoszeń. Zapytanie OSV dla pakietów faktycznie
  zainstalowanych w nowym, odizolowanym środowisku Python: zero zgłoszeń.
  Wyniki są migawką baz podatności z dnia audytu, nie certyfikatem bezpieczeństwa.

### Pozostałe ryzyka i ograniczenia
- **Historyczne: 7 zgłoszeń npm w narzędziach deweloperskich**
  (5 high, 2 moderate), łańcuch Tailwind 3 / braces / parser selektorów.
  Zamknięto je migracją do Tailwind 4 opisaną powyżej; pełny audyt npm: 0.
  Nadal nie należy udostępniać narzędzi developerskich publicznie ani budować
  niezaufanych źródeł z poświadczeniami/sekretami.
- Wskazane wtedy braki walidacji (`null` w kontach/inbox, dolne granice limitów
  starszych list i schemat ekstraktora LLM) zamknięto w kolejnym etapie
  „Domknięcie walidacji backendu” opisanym powyżej.
- Pozostają ostrzeżenia deprecacji Passlib i nazwy stałej HTTP 422.
- Nie wykonano live testów LLM/NBP/Stirling/Redis, restore drill ani zmian
  konfiguracji produkcyjnej. Historyczna blokada zapisu workflow GitHub Actions
  opisana w PR nadal obowiązuje; wyniki powyżej są lokalne, nie z CI.
- **Brak wdrożenia, migracji i zmian danych produkcyjnych.** Zmieniły się
  zależności runtime, więc przed ewentualnym wdrożeniem wymagany jest nowy,
  zweryfikowany obraz backendu i workera, a nie samo podmienienie źródeł.

## [Unreleased] — 2026-08-15

### Added
- **Automatyczne backupy produkcyjne**: systemd uruchamia `finanse-backup.timer`
  codziennie o 02:30 i `finanse-restore-verify.timer` w pierwszą niedzielę o
  04:30 (`Europe/Warsaw`, `Persistent=true`). Usługi dzielą 15-minutowy lock;
  rootowy wrapper jest instalowany poza repozytorium, a failure unit zapisuje
  zredagowane zdarzenia do journala.
- Restore wybiera snapshot wyłącznie przez `RESTORE_SNAPSHOT_ID`; legacy
  `snapshot=` jest fail-closed. Usługi i ręczne targety Makefile współdzielą
  lock, a usługi retry po 15 minutach, maksymalnie 3 starty w 3 godziny.
- **Cache Restic dla timerów**: unit i Make używają
  `/docker/finanse/data/restic-cache` (`root:root`, `0700`), zachowując
  `ProtectHome=true`. Produkcyjny restore drill uruchamia wyłącznie service z
  wrapperem; niskopoziomowy target Make jest wewnętrzny.
- **Security baseline wdrożony**: produkcja używa fail-fast konfiguracji,
  zamkniętej rejestracji, unieważnialnych sesji server-side, CSRF/Origin,
  limitów Redis i zredagowanego audytu bezpieczeństwa. Backup Restic do
  Contabo S3 obejmuje PostgreSQL i uploady; restore drill przeszedł kontrolę
  checksum, migracji i invariantów ledgeru.
- **Sesje serwerowe — zmiana niekompatybilna**: migracja unieważnia wszystkie
  historyczne ciasteczka przeglądarkowe JWT i po wdrożeniu wymusza ponowne logowanie.
  Publiczne uwierzytelnianie Bearer JWT zostało usunięte na rzecz ciasteczka
  `advisor_session`; audyt repozytorium nie wykazał zewnętrznych konsumentów.
- **Security baseline -- backup and restore verification**: versioned scripts
  `ops/backup.sh` and `ops/restore-verify.sh` create encrypted Restic snapshots
  of PostgreSQL and uploads, retain 7 daily/4 weekly/6 monthly snapshots, and
  perform a checksum-verified restore only to a loopback `_restore`/`_test`
  database. Operations documentation describes external credential setup, the
  monthly drill, RPO 24h and RTO 2h. The external Docker Makefile exposes
  `backup` and `restore-verify` targets.
- **Usuwanie i dezaktywacja kont i kategorii**: kolumna `categories.is_active`
  (migracja `1dbfe88dfb1b`), `DELETE /accounts/{id}` i `DELETE /categories/{id}`
  (204; brak/cudzy → 404; rekordy powiązane → 409 z sugestią dezaktywacji),
  dezaktywacja kategorii przez `PATCH /categories/{id}` (`is_active`).
  Usunięcie blokuje się przy istniejących postingach/pozycjach schedulera/
  budżetach/kategoriach-dzieciach; nieaktywne konta i kategorie są odrzucane
   przy tworzeniu transakcji, budżetów i pozycji schedulera.
- **Zarządzanie kontami i kategoriami**: strona `/finances/accounts` umożliwia
  tworzenie, edycję, aktywację/dezaktywację i bezpieczne usuwanie kont oraz
  kategorii. Dodano hooki TanStack Query dla tych operacji, link „Konta” w
  sidebarze i komunikaty o blokadzie usunięcia rekordów z historią.
- **Budżety w prognozie płynności**: prognoza zawiera podsumowanie budżetów
  bieżącego miesiąca (limit, wydano, pozostało) oraz ostrzeżenie, gdy pozostałe
  budżety przekraczają prognozowane saldo przed wypłatą.
- **Przewalutowanie (exchange)**: `POST /finance/transactions/exchange` z kursem
  NBP (automatycznym) lub ręcznym; zapisuje obie rzeczywiste kwoty i kurs jako
  transakcję `exchange` (PLN↔EUR/USD, suma zero zachowana). Formularz
  „Przewalutowanie" w `/finances/transactions`.
- **Edycja i usuwanie transakcji**: `DELETE /transactions/{id}` (kaskada postingów)
  oraz edycja inline opisu i daty w liście transakcji; usunięcie z potwierdzeniem.
- **Ręczne księgowanie transakcji**: formularz na `/finances/transactions` tworzy
  przychód, wydatek i transfer między kontami przez istniejący `POST
  /finance/transactions` (double-entry zachowany po stronie serwisu). Helper
  `buildTransactionPostings` koduje konwencję `balance = credit − debit`
  (przychód: konto `credit`/kategoria `debit`; wydatek: odwrotnie; transfer:
  źródło `debit`/cel `credit`). Kwoty w PLN.
- **Miesięczne budżety z limitami**: tabela `category_budgets` (limit `BIGINT > 0`
  per kategoria, unikalny na użytkownika i kategorię) z migracją
  `4340d1460982_category_budgets`. Endpointy `GET/POST /budgets`,
  `PATCH/DELETE /budgets/{id}` oraz `GET /budget-status` (wydane i pozostało,
  roll-up wydatków potomków dla kategorii-grup, kategorie z limitem i zerowymi
  wydatkami nadal widoczne). Strona `/finances/budgets` pokazuje limity, wydane,
  pozostało i pasek postępu z edycją inline, dodawaniem i usuwaniem.
- **Finanse — podstrony i zarządzanie płynnością**: rozdzielono widok finansów
  na realne trasy `/finances`, `/finances/transactions`, `/finances/cashflow`,
  `/finances/budgets` i `/finances/reports`; kontekstowy sidebar prowadzi do
  istniejących tras, a pozycje niezrealizowane pozostają oznaczone „Wkrótce".
- **Cashflow — formularze**: ustawienia dnia wypłaty, konta wpływu, horyzontu i
  tolerancji opóźnienia; CRUD miesięcznych pozycji przychodu/wydatku z metodą
  kwoty `fixed` lub `last_actual`, dezaktywacja oraz jawne usuwanie.
- **Cashflow — potwierdzanie sugestii**: endpoint
  `POST /cashflow/items/{item_id}/confirm` przelicza sugestię po stronie serwera
  i tworzy zbilansowaną transakcję wyłącznie przez serwis domeny finance;
  blokada wiersza chroni przed równoległym podwójnym księgowaniem.
- **Raporty z wyborem okresu**: `GET /summary` i `GET /category-summary`
  przyjmują `month`/`year` (z walidacją zakresu) i zwracają wartości wyłącznie
  wybranego miesiąca; domyślnie pozostaje bieżący miesiąc.
- Endpoint `DELETE /cashflow/items/{item_id}` do jawnego usunięcia własnej pozycji.

### Changed
- Frontend i npmplus komunikują się przez dedykowaną sieć
  `finanse_ingress`; backend jest wyłącznie na `internal`. Nginx normalizuje
  IP klienta przed przekazaniem do backendu.
- Operacyjne listy finansowe ukrywają nieaktywne konta i kategorie; strona
  `/finances/accounts` pozostaje bez zmian i nadal pokazuje pełną listę zarządzania.
- Potwierdzenie schedulera odrzuca pozycje nie-PLN (brak zweryfikowanego kursu),
  przyszłe, `overdue_uncertain`, `amount_unknown` i `matched_actual`; przyjmuje
  wyłącznie `due`/`overdue` z wyliczoną kwotą i ponownie waliduje powiązane konto
  i kategorię pod blokadą wiersza.
- Formularz schedulera ogranicza konta do aktywnych kont budżetowych w PLN.
- Wydzielono współdzielone komponenty finansowe (`formatPLN`, `SummaryCard`,
  `MonthPicker`, `CategorySpendTree`, `AccountTransactions`) oraz poprawiono
  znak transakcji per konto zgodnie z konwencją `balance = credit − debit`.

### Verified
- Automatyzacja na VPS: świeże `make test` przeszło (backend `198 passed, 125
  skipped`; frontend `129 passed`), a lint, typecheck i `git diff --check`
  przeszły. Oba timery są enabled. Ręczny backup utworzył `015211bb`; restore
  drill zakończył się sukcesem, nie pozostawił `finanse_restore` ani outputu,
  tylko pusty `root:root` `0700` parent. Statusy i journal nie zawierały
  sekretów. Wdrożenie nie spowodowało przerwy aplikacji webowej.
- Finalny proof po retry/lock hardening: backend `201 passed, 125 skipped`,
  frontend `129 passed`; lint, typecheck i `git diff --check` PASS. Legacy
  `snapshot=deadbeef` zakończył się kodem 2 przed runnerem/Restic. Backup
  utworzył `11fd2129`, a restore service zakończył się `status=0/SUCCESS`;
  parent restore pozostał pusty `root:root` `0700`, baza nie istnieje, journal
  nie zawiera sekretów.
- Cache proof: backend `201 passed, 125 skipped`, frontend `129 passed`; lint,
  typecheck i `git diff --check` PASS. Po instalacji cache `root:root` `0700`
  backup utworzył `a6e89e9d`, a restore service zwrócił `status=0/SUCCESS`.
  Bieżące okno journala nie zawiera `unable to open cache`; parent jest pusty,
  `finanse_restore` nie istnieje, a logi nie zawierają sekretów.
- Security baseline: backend `192 passed, 125 skipped`; integracyjne
  `125 passed`; frontend `129 passed`; Ruff, mypy, ESLint, TypeScript i build
  PASS. Snapshoty Contabo S3: `922d1aba` (przed migracją) i `63145774` (po
  migracji); pierwszy przeszedł rzeczywisty restore drill.
- Produkcja: migracja `c9d8e7f6a5b4` zastosowana, wszystkie usługi Up;
  health i frontend HTTP 200. Rejestracja zwraca 404, błędny login z zaufanym
  Origin 401, a bez Origin 403.
- Backup/restore static tests: `6 passed`; full backend unit suite:
  `132 passed, 109 skipped, 3 warnings`; Ruff and `bash -n` pass.
  ShellCheck is not installed. No Restic credentials, production backup,
  production restore, migration, or deploy was run.
- CRUD kont i kategorii: `make test` — backend `126 passed, 109 skipped` i
  frontend `106 passed`; `make test-integration` — `109 passed`; `make lint`,
  `make typecheck` i frontendowy production build PASS.
- Produkcja: migracja `1dbfe88dfb1b` zastosowana, backend/frontend/worker
  przebudowane i uruchomione; `https://finanse.birek.online/api/health` zwraca
  HTTP 200.
- Backend: `make lint` i `make typecheck` PASS. `make test`: `125 passed,
  79 skipped, 3 warnings`. `make test-integration` na izolowanej bazie:
  `79 passed, 125 deselected, 11 warnings`; migracja `4340d1460982` zastosowana,
  kontener testowy usunięty.
- Frontend: `npm run lint`, `npm run typecheck`, `npm run test` (`14 plików,
  63 passed`) i `npm run build` PASS.
- Naprawiono przekazywanie `transaction_date` (wcześniej `date`) w
  `useCreateTransaction` — wybrana data transakcji jest teraz zapisywana.
- Nie wykonano migracji produkcyjnej ani deployu dla ręcznego księgowania.

### Fixed
- Restore drill jawnie przekazuje bezpieczną nazwę bazy do `pg_restore`,
  izoluje środowisko Alembic i obsługuje zakodowany parametr `passfile`.
- **Ingress isolation**: final Task 7 rollout now has a documented dedicated
  `finanse_ingress` bridge (`172.24.0.0/24`), where only static npmplus
  `172.24.0.2` is trusted by the frontend. Backend remains internal-only.
- **Security baseline — limity za reverse proxy**: npmplus może przekazać łańcuch
  wyłącznie do frontendu, który normalizuje go modułem Nginx realip i wysyła do
  backendu pojedynczy adres. Backend akceptuje tylko jeden ścisły literal IP od
  aktualnie rozwiązanego kontenera `frontend`; łańcuch, whitespace lub bezpośredni
  peer wraca do adresu peera. Limity logowania, Advisora i uploadu są współdzielonymi
  zależnościami FastAPI. Backend usunięto z zewnętrznej sieci `proxy`; frontend
  pozostaje jedynym ingress do API.
- `PATCH /accounts/{id}` odświeża konto przed zwróceniem odpowiedzi
  (`db.refresh`), eliminując MissingGreenlet na `updated_at` po flush UPDATE
  (analogicznie do naprawionego wcześniej PATCH kategorii).
- Odwrócony znak transakcji per konto (`AccountTransactions`): przychód
  (income) z postingiem `credit` renderuje zielony „+", a wydatek (expense)
  z `debit` czerwony „−", zgodnie z konwencją `balance = credit − debit`.
- Formularz pozycji schedulera ogranicza wybór konta do aktywnych kont
  budżetowych w walucie PLN i blokuje walutę na „PLN", eliminując pozycje
  niemożliwe do potwierdzenia przez backend (non-PLN).
- Udokumentowano testem zakres invalidacji cashflow: w TanStack Query v5
  prefiks `["finance","accounts"]` obejmuje także transakcje per-konto
  (`["finance","accounts", id, "transactions", ...]`), więc centralna
  invalidacja po confirm/delete/create/update jest kompletna bez zmian.

### Added
- **Frontend — contextual sidebar**: jedna konfiguracja danych zasila desktopowy
  `IconRail`, menu kontekstowe i mobilny drawer; kontekst wybiera URL według
  najdłuższego pasującego prefiksu. Przyszłe moduły nie mają route'ów i są
  oznaczone jako „Wkrótce”.
- **Finanse — prognoza płynności cyklu wypłaty**: ustawienia dnia wypłaty,
  konta wpływu, horyzontu i tolerancji opóźnienia; miesięczne pozycje
  przychodu/wydatku powiązane z kontem budżetowym i kategorią.
- Migracja `8a6d0c1e2b3f` tworzy `finance_settings` i
  `scheduled_finance_items` z ograniczeniami dni, typów, metod kwot i własności
  relacji.
- Endpointy `cashflow/settings`, `cashflow/items` i `cashflow/forecast` oraz
  karta i lista prognozy na stronie Finanse.

### Changed
- Prognoza wykorzystuje wyłącznie salda kont budżetowych, kwotę stałą lub
  ostatnią zgodną transakcję, rozpoznaje rzeczywisty wpis w oknie trzech dni i
  nie dubluje go w projekcji. Po trzech dniach od terminu pozycja ma status
  `overdue_uncertain` i nie wpływa na saldo.
- Odczyt prognozy nie tworzy transakcji, postingów ani domyślnych ustawień;
  UI nie oferuje akcji księgowania.

### Verified
- Frontend: Vitest `12 passed`, ESLint, TypeScript typecheck i Vite production
  build przeszły. Testy routingu obejmują najdłuższy prefiks URL, active state,
  tooltip raila oraz zablokowane pozycje przyszłych modułów.
- Migracja izolowanej bazy `finanse_test` na `127.0.0.1:55432` doszła do
  `8a6d0c1e2b3f`; nie uruchomiono migracji produkcyjnej.
- `make VENV=/opt/finanse/backend/.venv/bin lint` i `typecheck`: PASS.
- `make VENV=/opt/finanse/backend/.venv/bin test`: backend `123 passed,
  47 skipped, 3 warnings`; frontend Vitest `7 passed`.
- `make VENV=/opt/finanse/backend/.venv/bin test-integration`: `47 passed,
  123 deselected, 11 warnings`; kontener testowy został usunięty.
- `npm run build` w `frontend`: PASS. Nie wykonano deployu.

### Fixed
- Domknięto historię tool calls Advisora dla kolejnych tur, walidację własności i walut transakcji w serwisie domenowym oraz oznaczenie sald `balance_pln` jako PLN.
- Fixture testowej bazy wiąże aplikacyjny session factory z izolowanym silnikiem per test.
- Import Actual rozpoznaje sobotnio-niedzielne HTTP 404 z NBP Table A, używa poprzedniego opublikowanego kursu z ograniczonego zakresu i zapisuje źródło `nbp_previous_business_day` zamiast odrzucać transakcję lub używać kursu 1.0.
- Reconciliation Actual wylicza oczekiwane salda kategorii bez `build_pa_postings`, raportuje agregaty grup kategorii i blokuje commit przy każdej różnicy grupy.
- Konta i kategorie importowane z Actual mają trwałe `source='actual'`; tryb zastąpienia odrzuca transakcję poza wskazanym blobem i każde ręczne użycie kandydata legacy.
- Preflight korekty legacy Actual rozpoznaje wyłącznie syntetyczny bilans otwarcia
  `source='actual'` z prefiksem `[BO] Bilans otwarcia`, dwiema przeciwnymi nogami
  tego samego konta i bez kategorii; każdy inny niepasujący rekord nadal blokuje korektę.

### Changed
- `DB_SCHEMA.md` opisuje rzeczywiste statusy `ToolExecution`.

### Added
- Testy pętli tool-calling Advisora: odpowiedź Level 0 po wykonaniu narzędzia, błędny JSON, nieznane narzędzie, błędy executora, limit iteracji oraz oczekiwanie na potwierdzenie Level 2.
- Testy potwierdzania mutacji: blokada ponownego confirm/deny, izolacja użytkownika, odrzucenie błędnego wyniku oraz rollback częściowej mutacji, gdy executor lub audit log zakończy się błędem.
- Izolowana baza PostgreSQL do testów integracyjnych na `127.0.0.1:55432`; fixture tworzy i usuwa schemat, a `make test-integration` sprząta kontener i sieć po zakończeniu.
- Flagi korekty `--replace-legacy-actual --backup-path`: wymagają `--execute --require-reconciled`, tworzą custom-format `pg_dump`, weryfikują go przez `pg_restore --list`, a dopiero potem otwierają transakcję zastąpienia.

### Changed
- **Doradca — bezpieczne mutacje finansowe**: `create_transaction` wymaga jawnego `account_name`, akceptuje wyłącznie dodatnie kwoty całkowite i odrzuca niezgodność waluty konta oraz walutę bez zweryfikowanego kursu FX.
- **Doradca — atomiczność potwierdzeń**: blokada wiersza chroni przed równoległym potwierdzeniem, a savepoint wycofuje częściowe zapisy executora i audit logu.
- **Frontend Advisora**: polling aktywnej rozmowy co 2 sekundy działa wyłącznie przy `pending_confirmation`; po rozstrzygnięciu polling się zatrzymuje.
- Poprawiono lokalne granice dnia i obsługę zmian czasu w harmonogramie, w tym offset DST zależny od konkretnej daty.
- Przywrócono lokalną semantykę daty transakcji (`7cc1973`): brak jawnej daty używa bieżącego dnia użytkownika zamiast daty UTC.
- Dodano konfigurację ESLint 8 z parserem TypeScript, regułami React Hooks/Refresh oraz środowiskiem browser/ES2022.

### Fixed
- Usunięto 7 błędów frontendowego lintowania.
- Spłacono backendowy dług Ruff i mypy: `ruff check app/ tests/` oraz `mypy app/` przechodzą.
- Poprawiono ochronę fixture testowej bazy: schemat można tworzyć i usuwać tylko w lokalnej bazie `finanse_test` na zatwierdzonym porcie; niedostępna baza powoduje pominięcie testów integracyjnych zamiast ingerencji w inną bazę.

### Verified
- Task 7 Actual reconciliation against isolated `finanse_test` on `127.0.0.1:55432`: migrations reached `e7a4b2c6d8f0`, and `--execute --require-reconciled` completed with exit code 0. No production PA database or Actual write API was used.
- `/tmp/actual_migration/reconciliation.json` has `is_reconciled=true`: all 15 account rows and all 46 category rows have zero difference; `Revolut USD` is `Actual 290`, `PA 290`, `diff 0`.
- The four formerly rejected USD expenses were imported using verified prior business-day rates and `fx_rate_source=nbp_previous_business_day`; the import wrote 800 transactions with 0 errors.
- Fresh quality gate in `actual-reconciliation`: Ruff, ESLint, mypy and TypeScript passed; backend pytest passed (`110 passed, 40 skipped, 5 warnings`); frontend Vitest passed (`6 tests`); Vite production build passed.
- Wdrożenie produkcyjne: obrazy backend/frontend zbudowane i uruchomione; `/api/health` oraz frontend zwracają HTTP 200.
- Smoke test produkcji: backend zgłasza `status=ok`, `environment=production`; kontenery backend/frontend działają.
- Historia sesji `f90a4d6..ab344ad` obejmuje 27 commitów; wcześniejszy zapis o 17 commitach był nieaktualny. Bieżący corrective docs commit nie należy do tego zakresu.
- Backend Ruff: PASS, bez błędów.
- Backend mypy: PASS, `46 source files`, bez błędów.
- Backend pytest: PASS, `89 passed, 23 skipped, 5 warnings`; testy zależne od niedostępnej lokalnie bazy zostały pominięte.
- Testy integracyjne z izolowanym PostgreSQL: PASS, `23 passed, 89 deselected, 11 warnings` w świeżonym uruchomieniu.
- Frontend: `npm run lint`, `npm run typecheck`, `npm run test` (`1 test file, 4 tests`) oraz `npm run build` przeszły.
- Zmiany wyłącznie porządkowe w `backend/migrations/` przywrócono do `f90a4d6`; nie zmieniono schematu.
- Nie wykonano migracji produkcyjnej; deploy aplikacji wykonano po scaleniu do `main`.

### Known Limitations
- Backend i frontend korzystają w tym worktree z zależności poza repozytorium: backend z `/opt/finanse/backend/.venv`, frontend z lokalnego `node_modules`.
- Testy zgłaszają ostrzeżenia dotyczące domyślnego scope event loop w `pytest-asyncio`, deprecacji `crypt`/Argon2 i `datetime.utcnow` w zależnościach oraz `RuntimeWarning` w mocku NBP.
- Parser split transactions nie został zweryfikowany na rzeczywistych danych użytkownika.
- Brak SSE/streamingu dla zmian innych niż polling oczekujących potwierdzeń.

## [0.3.0] — 2026-08-12

### Added
- **Doradca Level 2 — narzędzia mutujące z potwierdzeniem użytkownika**
  - `create_task`, `create_time_block`, `create_transaction` w tool registry
  - Endpointy `POST /api/advisor/tool-executions/{id}/confirm` / `/deny`
  - Status `pending_confirmation` → `completed` / `denied` + audit log
  - Frontend: przyciski potwierdzenia/odrzucenia mutacji w czacie
- **Ekstrakcja danych finansowych z dokumentów (OpenAI/DeepSeek)**
  - `documents/extractor.py`: OCR text → structured JSON (type, amount w groszach, currency, category_suggestion)
  - Tworzy inbox item z sugerowaną transakcją → zatwierdzenie przez użytkownika w Inbox
- **Stirling PDF + OCR pipeline (dokończenie Iteracji 2)**
  - Worker async (Redis + ARQ), pipeline: upload → SHA-256 → Stirling → OCR → tekst
  - Frontend Dokumenty: upload, lista, podgląd plików
- **Rozbudowany kalendarz**: widok miesiąca, taski z due dates, filtrowanie po zakresie dat, kolorowane bloki czasowe
- **Finanse**: endpoint transakcji per konto, opening balances w migracji z Actual
- **Konfiguracja opencode pod projekt**
  - LSP: pyright (Python) + typescript-language-server (TS) — `lsp: true` + jawny override TS
  - MCP EXA: remote `https://mcp.exa.ai/mcp`, klucz przez `{env:EXA_API_KEY}` (bez sekretu w repo)
  - 7 komend: `/test`, `/lint`, `/typecheck`, `/migrate`, `/migration "opis"`, `/deploy`, `/docs`
  - Formatter: ruff (Python) + prettier (TS/JS/CSS/HTML/JSON) po zapisie
  - References (docs, infra), watcher ignore, permissions (lsp/webfetch/websearch/gh)
  - Skill `session-workflow` (inicjalizacja sesji + aktualizacja docs)
- **Narzędzia dev**: ruff 0.16.2 + mypy 2.3.0 w `backend/.venv`; config w `pyproject.toml`
  (ruff line-length 100, mypy `explicit_package_bases`, pytest `pythonpath`); Makefile naprawiony (jawne ścieżki `.venv/bin/`)

### Changed
- **Finanse — redesign strony**: uproszczona z 470 → 86 linii (widok sald, wybór konta, transakcje per konto)
- **Stirling OCR**: pipeline dwustopniowy — najpierw OCR dokumentu, potem ekstrakcja tekstu
- Frontend: lista kont z saldami, sekcja przychodów/wydatków

### Fixed
- **Statusy narzędzi Doradcy**: polling aktywnej rozmowy co 2 s tylko dla `pending_confirmation`, precyzyjne invalidacje po confirm/deny i obsługa błędów w bannerze
- **Payee resolution** w imporcie z Actual (fallback na kategorię)
- **Opening balances** poprawnie zapisywane przy migracji
- **Frontend nie ładował danych z API** — ostatecznie naprawione (wszystkie strony na TanStack Query)
- **Eager-loading tool_executions** w `get_conversation_messages` (ToolCallBanner po przeładowaniu)

## [0.2.0] — 2026-08-11

### Added
- **Import z Actual Budget**: skrypt CLI `scripts/migrate_actual.py`
  - Parser Actual SQLite (konta, kategorie, transakcje, transfery, splity)
  - Provider kursów NBP z cache (EUR, USD)
  - Double-entry invariant zachowany — 800 transakcji zaimportowanych (0 błędów)
  - Idempotentność przez `[actual:{uuid}]` prefix w description
  - Tryb `--dry-run` do walidacji przed zapisem
  - Raporty `migration_report.txt` + `migration_log.json`
- **22 testy** dla importu (unit + integracyjne)

### Changed
- Actual Budget dane zaimportowane do PA (15 kont, 46 kategorii, 800 transakcji)
- Backend ma dostępne narzędzia importu w `scripts/`

## [0.1.0] — 2026-08-10

### Added
- **Backend**: FastAPI + SQLAlchemy 2.x async + Alembic
  - 7 domen: identity, finance, work, inbox, advisor, documents, audit
  - Double-entry ledger: konta, kategorie, transakcje, postings (BIGINT)
  - Auth: Argon2id, JWT w HttpOnly Secure SameSite=Strict cookies
  - Policy engine dla Advisor (poziomy autonomii 0-4)
  - Audit log dla operacji mutujących
- **Frontend**: React 18 + Vite + TypeScript + Tailwind CSS
  - TanStack Query + React Router v6 + Zustand
  - 9 stron: Login, Today, Inbox, Projects, ProjectDetail, Calendar, Finances, Advisor, Settings
  - Dark theme (gray-950), responsive layout
  - PWA-ready (manifest, theme-color)
- **Docker**: postgres:16, redis:7, backend, frontend (nginx+SPA), stirling-pdf
  - Wzorzec: kod w `/opt/finanse/`, infrastruktura w `/docker/finanse/`
  - Reverse proxy: npmplus (Nginx Proxy Manager fork)
- **Dokumentacja**: AGENTS.md, PRD.md, DB_SCHEMA.md, 9 ADR-ów
  - CHANGELOG.md, JOURNAL.md, TASKS.md
  - Agent OpenCode: `.opencode/agent/personal-advisor.md`
- **Testy**: 15 testów (11 unit + 4 integracyjne wymagające DB)
  - Double-entry invarianty, hashowanie haseł, tokeny, auth middleware

### Changed
- Actual przeniesiony z `finanse.birek.online` na `finanse.vps.birek.online`

### Verified
- E2E: rejestracja → logowanie → redirect /today → sesja cookie
- E2E: tworzenie konta → tworzenie transakcji (double-entry, suma=0)
- Frontend: wszystkie assety ładują się (302 KB JS + 21 KB CSS)
- Backend: health check, wszystkie endpointy auth i finance
