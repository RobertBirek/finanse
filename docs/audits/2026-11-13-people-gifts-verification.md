# Osoby i darowizny — odbiór etapu A

Status: implementacja lokalna i odbiór etapu A zakończone; kod79011bc.
Nie scalać, nie wdrażać, nie wykonywać produkcyjnej migracji lub korekty danych
na podstawie tego dokumentu. Etap B (pożyczki osobiste/rozksięgowanie rat) poza wdrożeniem.

## Zgoda i rozstrzygnięcie

Użytkownik zatwierdził wykonanie etapu osób i darowizn natywnie, z jednym przeglądem
całości. Historia darczyńcy jest oddzielona od kont i sald. Darowizna to istniejący
income na rzeczywistym rachunku, nie sztuczny transfer i nie zobowiązanie do zwrotu.
Pomysł starej konwersji income→transfer został wycofany; nie ma zgody na jej wykonanie.

## Wprowadzone elementy

- `FinancePerson`, `PersonTransactionLink`, composite FK owner, unikalne przypisanie
  transakcji i skrótu do informacyjnego rachunku. Profil bez własnego salda finansowego.
- Polecenia tworzenia/edycji/archiwizacji osoby i przypisania/odpięcia darczyńcy,
  wspólna owner mutation lock, CAS/snapshoty, audit, idempotentne receipty link/unlink.
- Próby powiązania nieprawidłowego income, refundu, transferu, exchange, loan/doc payment
  są odrzucane. Starej kategorii expense nie poprawiamy automatycznie.
- Chronione delete/date/pending linked gifts, jawne odpięcie przywraca poprzednie
  uprawnienia edycji. Opisy/oznaczenia pozostają niezależne od źródła bankowego.
- Historia i agregaty backendowe: jedna noga konta, cała historia poza paginacją,
  oddzielne waluty źródłowe i PLN baza; brak wpływu na globalne total/report queries.
- Ekran Osoby, profil, edycja i archiwizacja, darczyńca w szczegółach przychodu,
  nawigacyjny skrót z istniejącego konta informacyjnego. Jego saldo pozostaje ledgerowe.

## Migracja

`3254a4781542 → 2c77e935ee39`: dwie nowe tabele i unique accounts(id,user_id).
Alembic autogenerate przejrzany: usunięto niezwiązany drift indeksów schedules;
unique kont utworzone przed composite FK. Bez backfillu użytkowników, osób,
transakcji, kategorii, tagów lub kont. Downgrade odmawia, jeśli nowe tabele mają dane.
Realny test na własnej scratch bazie: wszystkie stare tabele identyczne, nowe puste,
empty downgrade/upgrade poprawny, populated downgrade odrzucony bez utraty rekordu.

## Dowody odbioru

- Baseline przed kodem: backend2422 + migration7 PASS; frontend667 PASS.
  Pierwszy backend run użył starego lokalnego venv; naprawiono wyłącznie runner.
  Migration fixtures wymagały własnej roli/flag; ustawiono je na izolowanym kontenerze.
- Nowe modele7, migracja1, komendy16, guards9 i istniejące loans23, API3/read2 PASS.
- Pełny backend2468 PASS,0 failed/error/skip,4 rozłączne grupy po617.
  Manifesty potwierdzają pełną unię testów, niezmienny kod79011bc i status0 każdej grupy.
- Frontend677/110plików PASS, tsc/eslint/build PASS.
- Playwright4 PASS: nowa historia i regresja oznaczeń, desktop1440/mobile375.
  To testy produkcyjnego buildu z kontrolowanymi fixture API, nie realny backend ani
  produkcyjne operacje. Backend weryfikowany osobno na prawdziwym PostgreSQL.
- Rozszerzony pełny Playwright:201 PASS,1 planowy skip (mobilny kalendarz w projekcie
  desktop),0 failed,9.9min. Wcześniejszy300s timeout runnera po85PASS nie był
  porażką asercji; pełne ponowienie ukończone bez timeoutu i bez zmiany aplikacji.
- Ponadto RED→GREEN: brak modeli/endpointów, brak ochrony pending, błąd kolejności
  unique/FK migracji, oraz reset szkicu darczyńcy przy zmianie cached transaction.
- Ruff na zmienionych plikach i pełny mypy205 PASS. Pełny bazowy Ruff wskazuje
  3 wcześniejsze DTZ007 w nietkniętych parserach ING/Revolut/Velo. Nie przypisywać
  tych naruszeń tej funkcji; nie deklarować całego projektu lint-clean.

### Korekta runnera końcowego (bez zmiany aplikacji)

Pierwszy podział2468testów po jawnych argumentach plikowych dał2333PASS i135błędów
setupu: fixtures z podkatalogów nie były zarejestrowane. Nie uznano go za pełny PASS.
Suma i unikalność2468były zgodne, ale display nodeid jednego parametru gzip zawierał
bieżący mtime i różnił się między procesami; również nie pominięto tego w dowodzie.

Próba kontrolna: ten sam bank-import test przy pełnej kolekcji z selekcją -k PASS.
Poprawiony runner zbiera całą kolekcję w każdym workerze przed późnym podziałem,
zachowując conftesty. Tożsamość testu: parent + originalname + callspec.indices,
nie zmienne etykiety danych. Dwa niezależne collecty2468unikalnych tożsamości są
zgodne; canary pełnej kolekcji + późnego filtrowania PASS. Cały zestaw ponowiony;
do pełnego odbioru nadal wymagane wszystkie statusy0, rozłączna unia2468 i niezmienny kod.
Kod aplikacji przy obu przebiegach:79011bc; zachowano dowody odrzuconego runner-v1.

V2 zakończony:2468PASS, unia tożsamości pełna i rozłączna, wszystkie cztery statusy0,
kod niezmieniony. Poprzedniego przebiegu nie wliczano do zielonego wyniku.

Dowody robocze: `.superpowers/sdd/2026-11-12-finance-people-gifts/` (przed końcowym
sprzątaniem skopiować potrzebne logi i receipty do osobnego katalogu odbioru).

Zachowany katalog dowodów: `/tmp/opencode/people-gifts-stage-a-20261113-x33_jtbi/`.
Zawiera pełny manifest,4XML/logi backendu, frontend/UI logi, stan sprzed poprawki
runnera i ledger decyzji. Brak danych produkcyjnych; testy syntetyczne.

## Niezależny review i poprawka

`ses_e2be0d190ffedxWw2ZQAQ4WJ92`:0Critical,1Important,0Minor. Istniejący
`currency_correction.apply_correction` omijał ochronę linked gifts. Regresja
`test_linked_gift_blocks_currency_correction_without_changing_money` najpierw
RED (DID NOT RAISE), potem GREEN: wspólny guard po lockach, przed dowolną zmianą
waluty/kwot.24 testy guard/currency i końcowa pełna kolekcja2468PASS po poprawce.
Nie wykonywano drugiego review zamiast testów. Brak odłożonych uwag Minor.

## Decyzje wykonawcze i ich koszt

1. Brak dostępnego narzędzia slash: użyto definicji komend projektu w bieżącym
   worktree i własnych bazach networkless, nie testów w produkcyjnym checkout.
   Koszt: osobny, jawny runner do utrzymania w dowodach.
2. Sprostowano znak przyszłych postingów odsetek/opłat w projekcie B na credit,
   zgodnie z obecną konwencją expense. Koszt błędu: B musi nadal udowodnić sumę0.
3. Per-task testy zadania + statyka, pełna kolekcja raz po finalnym fixie, zamiast
   110min serialnego pełnego testu przy każdym commicie. Koszt: regresje globalne
   mogą ujawnić się dopiero na końcu; końcowy gate zachowano.
4. Nawigacja zmieniona w rzeczywistym ownerze `navigation.ts`, nie Layout.tsx.
   Koszt błędu: regresja menu, kontrolowana przez677frontend/pełne UI201PASS.
5. Review nie oceniał produkcji/A2: pozostają poza zgodą na implementację i wymagają
   oddzielnego potwierdzenia. Koszt: gotowy kod nie oznacza wdrożenia/poprawionej historii.
6. B pozostaje roadmapą bez księgowania pożyczek. Koszt: brak nowej obsługi rat w A.
7. Pełna kolekcja podzielona na4 własne networkless PG bez nowych zależności.
   Koszt błędu: manifest pokrycia lub statusy blokują odbiór, bez udawanego PASS.
8. Po błędzie runner-v1 wszystkie workery zbierają całą kolekcję przed podziałem;
   tożsamość opiera się o scope/function/paramindices, bez zmiennego mtime etykiety.
   Koszt błędu: dowód jest odrzucany; canary i manifest2468 potwierdziły poprawkę.

## A2 — warunki osobnej korekty historycznej

Nie wykonano świeżego produkcyjnego preview ani zapisu w ramach implementacji A.
Operator A2 ma powstać dopiero po uzgodnieniu zakresu operacyjnego. Docelowo:

1. Świeży owner-scoped snapshot dokładnie zatwierdzonych income, kont, kategorii,
   postingów, dat/oznaczeń oraz importrefs. ID/kwoty poza repozytorium.
2. Docelowa kategoria income Darowizna; type=income zachowane, noga bankowa nietknięta.
3. Preview miesięcznych różnic income/expense/net i wszystkich sald, bez założenia
   neutralności. Income używa transaction.date, expense purchase_date; sprawdzić oba.
4. Nowa zgoda na konkretny preview, backup/restore, clone commit/replay/retention,
   safety review, atomowe wykonanie i niezależny odczyt po commicie.
5. Żadnych nowych transakcji, ponownego podnoszenia sald bankowych, przepisywania
   oryginalnych opisów lub dawnych manifestów/receiptów importu.

## Stan odbioru i dalsze zgody

- [x] Final review całego zakresu db3a4b3..HEAD i jeden fix pass RED→GREEN.
- [x] Końcowa pełna kolekcja backendu, typecheck/lint diff, UI regressions.
- [x] Raport wyników i osobny katalog dowodów; zastane dirty docs pozostają zachowane.
- [x] Cleanup wszystkich własnych testDB; worktree i zasoby produkcji zachowane.
- [x] Dokumentacja odbioru przygotowana do selektywnego commitu bez zastanych zmian.
- [ ] Osobna decyzja użytkownika o merge/push/deploy; brak automatycznej zgody.
