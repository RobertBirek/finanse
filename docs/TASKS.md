# Tasks

Backlog zadań ze statusami.

Statusy: `[ ]` pending, `[~]` in progress, `[x]` done, `[-]` cancelled

## Waluty i zobowiązania (2026-10-27)

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
