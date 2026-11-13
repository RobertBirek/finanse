# Osoby w finansach: darowizny i przyszłe pożyczki

Status: użytkownik zatwierdził natywne wykonanie etapu A. NIE jest to zgoda na
wdrożenie, produkcyjną migrację, zapis historii finansowej lub etap B.

## Cel i potwierdzone wymagania

- Osoba może przekazywać darowizny wielokrotnie. Użytkownik chce historię pod jej
  nazwą, sumę otrzymanych darowizn oraz prawidłowe przychody na swoich rachunkach.
- Każdy wpływ istnieje tylko raz. Powiązanie osoby nie tworzy dodatkowego przelewu,
  postingu, przychodu, salda ani długu. Kwoty i daty bankowe pozostają nienaruszone.
- Nazwa osoby nie oznacza automatycznie darczyńcy albo pożyczkodawcy: ta sama osoba
  może mieć różne relacje. Darowizna nie tworzy obowiązku spłaty.
- Obecne wskazane wpływy zostały określone przez użytkownika jako darowizny.
  Pytanie o pożyczki jest hipotetyczne, nie zmienia ich kwalifikacji.
- Wcześniejszy pomysł konwersji na transfery jest NIEAKTUALNY. Jego prywatnego
  operatora NIE wolno odblokowywać ani uruchamiać.

## Etapy i zakres zgody

1. **Etap A, plan wykonawczy:** osoby + przypisanie darowizn + historia/sumy,
   dostępna również z istniejącego konta informacyjnego. Bez zmiany semantyki kont.
2. **Etap A2, osobna zgoda operacyjna:** korekta kategorii konkretnych historycznych
   przychodów i przypisanie do osoby. Najpierw preview, kopia, próba na odtworzeniu.
   Wdrożenie funkcji nie jest zgodą na zmianę danych użytkownika.
3. **Etap B, roadmapa, nie implementować w A:** osoba pożyczkodawcy, wypłaty kapitału,
   rzeczywiste alokacje rat. Przed B osobna specyfikacja i plan rozksięgowania.

Decyzja projektanta: nie budować nowego modułu kredytów w ramach darowizn; istnieją
`LoanAgreement`, `LoanInstallment`, `LoanPaymentLink` i ekran `FinanceLoans`.

## Semantyka pieniędzy

| Zdarzenie | Rachunek bankowy | Przychód/wydatek | Zobowiązanie |
| --- | --- | --- | --- |
| Darowizna otrzymana | rośnie | przychód Darowizna | brak |
| Otrzymany kapitał pożyczki | rośnie | nie jest przychodem | rośnie |
| Spłacony kapitał | maleje | nie jest wydatkiem | maleje |
| Zapłacone odsetki/prowizje | maleje | wydatek | nie zmniejsza kapitału |

Przykłady syntetyczne: pożyczka 120000 groszy, 12 rat kapitałowych po 10000,
bez odsetek; po pierwszej zaksięgowanej racie pozostały kapitał 110000.
Rata 12000 = kapitał 10000 + odsetki 1500 + opłata 500: spadek banku12000,
spadek kapitału10000, wydatek2000. Termin raty ani zapis planu nie księgują płatności.

**Ważne obecnie:** off-budget wyłącza rachunek z salda budżetu, nie z
`balance_all_pln`. Nie zmieniać globalnych zasad sumowania na potrzeby jednej osoby.
Profil osoby nie jest `Account` i nie jest wejściem do żadnego salda majątkowego.
Ewentualna ujemna prezentacja „osoba przekazała” byłaby tylko oznaczoną statystyką;
pierwszy etap pokazuje jednoznaczne dodatnie „Otrzymane darowizny”, nie ujemny dług.

## Etap A — modele i cykle życia

W domenie finance, PostgreSQL:

- `FinancePerson`: standardowe id/timestamps, `user_id`, `name` (1–200, strip),
  `is_active`, `version` (od1), opcjonalne `reference_account_id`.
  Nazwa nie jest identyfikatorem ani kluczem automatycznego dopasowania.
  Archiwizacja zachowuje historię; nowych przypisań do nieaktywnej osoby brak.
- `PersonTransactionLink`: standardowe id/timestamps, `user_id`, `person_id`,
  `transaction_id`, `kind='gift_received'` (CHECK; etap A obsługuje tylko ten rodzaj).
  Jedna transakcja przypisana najwyżej jednej osobie; dzielenie darowizny pomiędzy
  darczyńców poza A. Unikalność `transaction_id`; composite FK osoba/transakcja+owner.
  FK RESTRICT: nie usuwać transakcji z powiązaniem; najpierw jawnie je odpiąć.
- Nie przechowywać kopii kwoty ani ręcznie aktualizowanych sum darowizn.
- `reference_account_id`: wyłącznie skrót nawigacyjny od istniejącego konta do
  osoby. Nullable, globalnie unique dla non-NULL, composite FK accounts(id,user_id)
  RESTRICT; dodać unique accounts(id,user_id) addytywnie. Konto własne i pozabudżetowe
  przy przypisaniu. Zachować konto, jego postingi, importrefs i rzeczywiste saldo.
  Nie usuwać/archiwizować/zmieniać typu konta automatycznie.
- Nowe konto bankowe ani nowy finansowy typ konta nie są potrzebne do utworzenia osoby.
  Osobę i rachunek archiwizuje się niezależnie. Zmiana konta na budżetowe wymaga
  uprzedniego odpięcia skrótu; nie wolno osierocić powiązania usunięciem konta.

Nazwy plików i dokładne kontrakty wykonawcze określa plan. Limity stron 1–100,
offset>=0 są decyzją projektanta zgodną z istniejącą paginacją.

## Etap A — polecenia i odczyty

- Własność z sesji, nie z body. Inny owner →404, nieprawidłowy kształt →422,
  konflikt wersji/przypisania/stanu →409. CSRF i auth jak finance.router.
- Jawny wybór osoby i istniejącej transakcji; bez dopasowania po opisie, tagu
  lub kwocie. Potwierdzony gift: posted income, dokładnie dwa zbilansowane postingi
  w jednej walucie; credit realnego konta i debit kategorii typu income.
  Kwoty źródłowe/PLN, FX i właściciele muszą przejść istniejące walidatory.
  Imported source jest dozwolone, ale bankowa proweniencja jest nietknięta.
- LoanPaymentLink, dokumentowe alokacje, refundy, exchange i transfery odrzucać.
  Nie używać linku osoby do obejścia ochron finansowych.
- Link/unlink zmieniają tylko metadane, audit i receipt. Ponowienie tego samego
  klucza/żądania odtwarza wynik; zmiana payload pod tym kluczem →409.
- Przy link/unlink/archiwizacji stosować wspólny istniejący owner mutation lock,
  następnie person, transaction w stabilnym porządku; odczyt po lock odświeżony.
  Całość w jednej transakcji bez commit w serwisie. Person update z expected_version.
- Blokować usunięcie i mutacje finansowe/daty/pending linked transaction; opis własny,
  tagi i notatka nadal dozwolone. Nie zmieniać przy tym source description.
- Historia `(date DESC, created_at DESC, id DESC)` po stronie serwera, paginowana.
  Summary dotyczy całej historii, nie bieżącej strony; count distinct transactions,
  sum jednego account credit posting w base_amount_pln. Sumy walut źródłowych osobno.
  Nie sumować obu stron ledger. Obsłużyć stronę bez wyników i archiwalną osobę.
- PLN baza; FX darowizn dopuszczone tylko przy poprawnym istniejącym, dwupostingowym
  income. Prezentować PLN + oryginalną walutę, nie mieszać kwot źródłowych walut.
- Profile osób nie trafiają do istniejących total/report queries. Testy porównują
  ledger, salda, income/expense przed i po linkowaniu oraz odpinaniu.

## Etap A — interfejs bez zmiany znaczenia sald

- Osobny ekran „Osoby”, lista, nowa osoba, profil i historia darowizn.
- Profil: „Otrzymane darowizny”, liczba operacji, daty, realne konto otrzymujące,
  oryginalne/własne opisy według istniejącej projekcji transakcji.
- W istniejącym widoku `AccountTransactions` konto ze skrótem do osoby otrzymuje
  przycisk „Historia darowizn od tej osoby”. Nagłówek salda konta nadal pokazuje
  wyłącznie prawdziwe saldo ledger, a nie statystykę darowizn.
- Przypisanie osoby i odpięcie w osobnym dialogu dla istniejącej transakcji income.
  Gdy stara kategoria jest expense: wyjaśnić błąd i wymóg osobnej korekty kategorii;
  nie przekwalifikowywać automatycznie. Następny wpływ przypisuje się tym samym dialogiem.
- Ekran osoby nie pokazuje fikcyjnej zakładki działających pożyczek przed etapem B.
- UI wykonuje obliczenia prezentacyjne; autorytatywne sumy pochodzą z backendu.

## A2 — historyczna korekta, osobna operacja produkcyjna

Wcześniejsza próba transferów ujawniła income z legacy category.type=expense;
pełny rollback potwierdzono i nie wykonano produkcyjnego zapisu. Nie zakładać,
że zamiana kategorii będzie neutralna w historycznych raportach.

1. Świeży readonly preview przypiętych transakcji, oznaczeń, kategorii, dat,
   kont, mapowań i ledger; szczegóły finansowe/ID wyłącznie poza repo.
2. Pokazać miesięczne delty income/expense/net i wszystkie salda dla docelowej
   kategorii income. Income liczy transaction.date, expense purchase_date — nie
   ograniczać kontroli do jednego typu daty. Osobna jawna zgoda na ten raport.
3. Prywatna mała komenda domenowa zmienia tylko category_id istniejącej nogi
   kategorii, zachowuje type=income i nogę bankową, potem tworzy person link.
   Źródłowe opisy, kwoty, kursy, kierunki, daty, IDs i importrefs bez zmian.
   Zakazane generic SQL i rozluźnianie publicznych guardów dla operatora.
4. Backup bez retencji, restore isolated clone, test commit/replay/retention,
   niezależny safety review, ponowny pin check, jedna atomowa operacja produkcyjna.
5. Niezależny readonly post-check: wpływy jako income, donor summary, brak
   zdublowania, sum(postings)=0, wszystkie konta bez zmian, zgodne raportowe delty.
   Przy timeout nie ponawiać w ciemno: sprawdzić receipt i committed state.

## Etap B — pożyczki od tej samej osoby (osobny projekt wykonawczy)

- Rozszerzyć `LoanAgreement` opcjonalnym, owner-safe `lender_person_id`.
  Pozostawić stare umowy z NULL; nie utożsamiać osoby z kontem zadłużenia.
  Jedna osoba może mieć wiele umów i niezależną historię darowizn.
- Wykorzystać istniejące raty: number, due_date, principal_pln, interest_pln, fees_pln.
  Zero odsetek/opłat dozwolone, nie przyjmować domyślnych odsetek bez ustaleń.
- Otrzymanie pożyczki: bank credit i konto zobowiązania debit według konwencji
  istniejącej aplikacji, sum signed postings=0. Saldo banku rośnie, zobowiązanie
  jest ujemne, netto majątku się nie zwiększa. Nie jest to income/Darowizna.
  Nowy owner-safe, unikalny link wypłaty do umowy, nie do raty.
- Spłata kapitału: bank debit, zobowiązanie credit. Odsetki i opłaty osobnymi
  kategoriami kosztów i postingami credit (konwencja tej aplikacji). Jedna faktyczna płatność bankowa,
  bez dodatkowego, ponownie odliczanego bankowego obciążenia dla kosztów.
- Istniejący `LoanPaymentLink` akceptuje tylko dwupostingowe transfery, a
  `requires_accounting_review=True` oznacza brak dowodu prawidłowego rozdziału.
  NIE obiecywać, że obecny harmonogram już księguje koszty/kapitał.
- Dla rzeczywistych rat konieczny osobny kontrakt alokacji kapitał/odsetki/opłaty,
  częściowych spłat i ewentualnych nadpłat. Kwoty alokacji muszą zgadzać się z
  konkretnymi postingami, nie samym harmonogramem. Równoległe płatności nie mogą
  spłacić tej samej części dwa razy. Dług z ledger nie jest kopią sum planu rat.
- Wpływ/spłata już w imporcie: klasyfikacja i link do TEJ SAMEJ transakcji, nie nowa.
  Reklasyfikacja dawnego income/expense wymaga oddzielnego uzgodnienia i zgody.
- Profil osoby: darowizny osobno, każda pożyczka osobno, wypłacony kapitał,
  spłacony kapitał, do zwrotu, zapłacone koszty, następna rata; dane nieuzgodnione
  jawnie oznaczone, bez fałszywego „do zwrotu” z samego planu harmonogramu.

Poza A/B bez dodatkowej decyzji: pożyczki udzielane innym przez użytkownika,
automatyczne przelewy, automatyczne konwersje gift↔loan, podatki od darowizn,
wyliczanie oprocentowania, umorzenie długu, FX pożyczek i dzielenie jednej
bankowej płatności pomiędzy wiele umów. Nic z tego nie wynika z pytania użytkownika.
