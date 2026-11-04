# Zatwierdzane kategorie i splity: lokalny odbiór etapu 2

## Status

Kod i testy odebrano lokalnie po końcowym pełnym gate. Użytkownik zatwierdził plan656e9e6
słowem „tak”. Nie wdrożono funkcji i nie uruchomiono migracji produkcyjnej, AI/OCR
ani partii historii. Stary release810/schema2f pozostaje poza tą zmianą.
Kod funkcji: `9fef438`. Tylko28własnychplików; unrelatedVelo/Q7 pozostały nietknięte.

Plan: `docs/superpowers/plans/2026-11-03-approved-category-splits.md`.
Spec: `docs/superpowers/specs/2026-11-03-approved-category-splits-design.md`.

## Zaimplementowany kontrakt

- Kontekst wydatku → niemutujący podgląd → osobne „Zatwierdź podział”. Kwota100PLN
  może otrzymać80PLN spożywka/20PLN chemia i później wrócić do jednej kategorii.
- Backend zmienia tylko stronę kategorii. Zachowuje ID i wszystkie kolumny postingu
  kontowego, daty/proweniencję, liczbę płatności i alokacje dokumentów. Kwoty raportów
  pochodzą nadal z księgi, nie z równoległej tabeli splitów.
- Własne istniejące aktywne kategorie expense, dokładne kwoty w groszach. Brakujący
  lub nadmiarowy grosz blokuje operację. Backend nie zgaduje rabatów ani pozycji.
- Obsługa zaksięgowanych wydatkówPLN ze źródełmanual/document_payment. Transfery,
  income, FX/refundy, pending, pożyczki, transakcjeActual/mappingi i uszkodzone układy
  pozostają chronione. Sam wybór aktywnej kategorii zaimportowanej zActual jest dozwolony.
- Ręczna proweniencja i wersja w osobnym stanie1:1 chronią przyszłą automatyzację.
  Brak stanu nie oznacza, że starą kategorię można uznać za nieskategoryzowaną.
- Token podglądu obejmuje księgę, daty, konto, powiązania oraz docelowe kategorie i ich
  ścieżki. Stara decyzja→409. Po409 UI zachowuje wpisy i wymaga odświeżenia; po niepewnym
  błędzie sieci ta sama decyzja używa tego samego Idempotency-Key.
- FinanceCommandReceipt przechowuje potwierdzenie powtórzenia. Replay nie wykonuje
  zmiany drugi raz i nie nadpisuje cache starym stanem. Nowy zatwierdzony no-op nie
  mnoży audytu. Ledger/state/audit/receipt tworzą jedną transakcję.
- Kasowanie kategorii korzysta z tego samego category-tree lock i sprawdza świeże
  użycie; ONDELETESETNULL nie może wyzerować kategorii z równolegle zatwierdzonego splitu.

## Weryfikacja i review

- Initial20RED→20GREEN dla API/płatności/replay/kwot/ochron. Rozszerzony focused140PASS
  obejmuje nowe zachowanie, Actualpins, stare billguards/loans, daty, raporty/budżety,
  równoległe zatwierdzenia/delete i rollback przy błędzie audytu.
- Dodatkowe7eligibilityPASS (loan/refund/niezbilansowane/brak kategorii/mieszany wpływ
  na budżet/archiwalne konto/document_payment) oraz1real-session/productionCSRF/authPASS.
- UI:5initialRED→GREEN, przed/po i blokadaEscape podczas zapisu2RED→GREEN, wejście
  ze szczegółów1RED→GREEN. Full429frontend/lint/tscPASS przed końcowym gate.
- Browser375/1440: pełne107E2EPASS+1expectedskip, split→podgląd→akceptacja→raporty/
  budżety→scalenie, jedna płatność, a11y/nooverflow/focus i brak backend/providertraffic.
  FreshbuildPASS. Niezmienione ostrzeżenie Vite o chunku524kB; nie ukrywano go limitami.
- Jedno whole-review `ses_e5c6ac4e2ffeY67NUsPOSm3fwl`: Critical0, Important1 TOCTOU
  stanu konta. Oba porządki accountupdate↔approval odtworzone2RED→GREEN; focused28PASS.
  Wszystkie edycje konta biorą istniejący owner-document mutex przed odczytami/lockami.
  Podgląd widzi edycję dopuszczoną wcześniej i odmawia409; edycja dopuszczona później
  czeka na koniec zatwierdzania. Nie dodano późnego account-row lock ani drugiego review.
- Minor dotyczący „source=base” wynikał z niejednoznacznego skrótu planu: chodzi o
  source_amount==base_amount_pln, nie wymóg etykietyfx_rate_source="base". Doprecyzowano
  zapis, zachowano dotychczasową ręczną proweniencjęPLN. Nie ma odroczonej zmiany kursu.
- Końcowe6gate po poprawce:1250backend/429frontend/ruff/mypy/eslint/tscPASS.
  `verify-final.py` potwierdził niezmienione testowane źródła, dist,107E2E+1expectedskip
  i hash migracji/retention. Strict-contract probes bez DB potwierdziły też zły token,
  spoofsource/account/FX, boolversion/limitparts i literaltrueapproval.

## Migracja i trwałość danych

Addytywna2268bca97cb8 po84f28fe23ab8 tworzy tylko transaction_categorization_states
i jej index. Żadnych nowych mappedcolumns transakcji/postings lub backfillu. Autogenerate
wykonano w owned schema category_splits_stage2_test w identity-checked finanse_test
na localhost55432; usunięto niezwiązany stary drift indexów scheduleditems.

Rzeczywisty rehearsal zachował wszystkie istniejące wiersze, kolumny i indexy. Po upgrade
liczba metadanych=0. Emptydowngrade/reupgradePASS; populateddowngrade odmawia pod
EXCLUSIVElock, zachowując head/stan. Finalny dowód wiąże hash pliku migracji.
Oryginały/dokumenty/Actualmanifesty/produkcyjne dane nie uczestniczyły w tej próbie.

Przyszłe wydanie wymaga osobnej zgody, backupu/rehearsal i spójnego kodu rozumiejącego
daty oraz stan kategoryzacji. Nie usuwać metadanych, audytu lub receiptów dla rollbacku.
Nie zmieniać istniejącego mechanizmu archiwum lub uruchamiać starego rollbacku release810.

## Decyzje i granice odbioru

- Oddzielny categorization_context.py utrzymuje odczyt/tokeny poza serwisem mutacji.
  Koszt pomyłki: dodatkowy moduł, bez innego kontraktuAPI.
- Użyto szczegółowych endpointów GET/context i POST/preview/apply z planu; skrót
  GET/PATCH w mapie plików nie tworzy dodatkowego PATCH. Koszt: klient używa tych URLi.
- „source=base” pozostaje równością kwot, a nie nową taksonomią etykiet FX. Zmiana
  tej taksonomii wymagałaby osobnej decyzji i nie może przepisywać dzisiejszych zapisów.
- Reviewer nie uruchamiał finalnych suite, migracji, produkcji ani providerów. Własny
  migration-proof stanowi dowód próby; finalne gate’y i manifest źródeł pozostają
  obowiązkiem agenta wykonawczego. Odbiór produkcyjny pozostaje osobnym przyszłym krokiem.
- Macierz weryfikacji łączy nowe testy z pełnymi odziedziczonymi suite finansów/dat/auth
  oraz dodatkowymi niemutującymi próbami strict DTO. Nie powielano osobnego testu dla
  każdej kombinacji tego samego wspólnego guardu. Koszt pomyłki: ewentualny brakujący
  wariant wymaga dedykowanej regresji; nie ma znanego pominiętego failure lub wyciszenia.

Dowody: `/tmp/opencode/category-splits-20261103/` (logs, migration-proof.json,
dist-final, E2E outputs, contract-probes.log i final-proof.json).
Etapy3–6, agentLLM, pozycjeparagonu i historybatch pozostają niewykonane.
