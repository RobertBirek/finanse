# Uzgodniona migracja Actual Budget — specyfikacja

Data: 2026-08-13  
Status: approved for implementation and isolated dry-run

## Problem potwierdzony audytem

Migracja snapshotu Actual `DOM` zaimportowała wszystkie 800 logicznych
transakcji, ale nie odwzorowała ich ekonomicznego wpływu na konta. Dla
przychodów i wydatków importer utworzył parę debit/credit na tym samym koncie,
więc saldo konta pozostaje bez zmian. Transfery między kontami są jedyną klasą
transakcji wpływającą na salda. Dodatkowe bilanse otwarcia również księgują
obie strony na tym samym koncie i mają zerowy wpływ.

Importer dodatkowo spłaszcza strukturę kategorii Actual i gubi semantyczną
flagę `offbudget` konta.

## Cel

Zbudować poprawną, powtarzalną i sprawdzalną migrację Actual Budget do Personal
Advisor, która zachowuje:

- salda każdego konta w jego walucie źródłowej;
- double-entry invariant w PLN;
- konta pozabudżetowe jako dane informacyjne;
- grupy oraz podkategorie Actual;
- audytowalny raport uzgodnieniowy przed jakąkolwiek korektą produkcji.

## Zakres danych

Źródłem próbnej migracji jest snapshot Actual budżetu `DOM` z blobu
`file-1bdc93e7-2c30-473e-b538-740a6b6021dc.blob`. Import obejmuje historię
snapshotu, a nie bieżący log synchronizacji. Produkcyjna baza i dane Actual
pozostają tylko do odczytu do czasu osobnej zgody na korektę.

## Model kont

### Konto budżetowe

`is_budget_account=True` oznacza konto uwzględniane w majątku netto,
przychodach, wydatkach, budżetach i danych analitycznych Doradcy.

### Konto pozabudżetowe

`is_budget_account=False` odwzorowuje `Actual.accounts.offbudget=1`.

- Importujemy pełną historię i wyświetlamy saldo/transakcje w sekcji
  „Pozabudżetowe / informacyjne”.
- Konta nie wchodzą do majątku netto, przychodów, wydatków, budżetów ani
  podsumowań Doradcy.
- Transfer między kontem budżetowym a pozabudżetowym nie jest przychodem ani
  wydatkiem. Pozostaje transferem widocznym po obu stronach.
- Flaga jest właściwością modelu `Account`, nie heurystyką nazwy ani typu.

## Model kategorii

Grupa kategorii Actual jest importowana jako kategoria nadrzędna. Kategorie
transakcyjne są jej dziećmi przez istniejące `Category.parent_id`.

Przykład:

```text
Transport
├── Paliwo
├── Parking
└── Serwis
```

Tylko kategorie transakcyjne mogą być przypinane do postingów. Raporty i
podsumowania agregują dzieci do ich grupy, umożliwiając analizę zarówno
„Paliwo”, jak i całego „Transportu”. Kategorie bez grupy pozostają kategoriami
głównymi.

## Reguły księgowania importu

### Przychód i wydatek

Każda zwykła transakcja ma dwie strony:

- posting konta finansowego zmienia saldo konta zgodnie z kwotą Actual;
- przeciwstawny posting kategorii ma `category_id`, lecz nie ma `account_id`.

`Posting.account_id` staje się opcjonalne. Posting konta finansowego ma
`account_id` i nie potrzebuje kategorii; posting kategorii ma `category_id` i
nie potrzebuje konta. Dzięki temu saldo konta jest liczone wyłącznie z
postings kontowych, a transakcja nadal ma co najmniej dwa postings i sumę PLN
równą zero. Transfer ma dwa postings kontowe i nie ma postings kategorii.

### Transfer

Transfer zapisuje rzeczywiste konto źródłowe i docelowe. Nie jest przychodem
ani wydatkiem, niezależnie od tego, czy jedna strona jest pozabudżetowa.

### Waluty

- `source_amount` i `source_currency` zachowują kwotę oraz walutę konta Actual.
- `base_amount_pln` korzysta z kursu NBP dla daty transakcji lub z jawnie
  zarejestrowanego zweryfikowanego fallbacku.
- Brak kursu nie może być zastępowany relacją `1.0` dla EUR/USD.
- Transfer w różnych walutach zachowuje obie kwoty Actual. Różnica między
  przeliczonymi wartościami PLN jest zapisywana jako jawny posting kategorii
  „Różnice kursowe”, bez naruszania sumy PLN postings.

### Bilanse otwarcia

Przy imporcie pełnej historii nie tworzymy dodatkowych bilansów otwarcia.
Jeżeli import od daty granicznej będzie potrzebny w przyszłości, bilans
otwarcia musi księgować konto finansowe przeciwko dedykowanemu kontu otwarcia,
nigdy dwa razy na tym samym koncie.

## Raport uzgodnieniowy

Dry-run i import próbny generują raport per konto zawierający:

- ID i nazwę konta Actual oraz PA;
- walutę;
- `offbudget` / `is_budget_account`;
- saldo Actual w walucie źródłowej;
- saldo PA w walucie źródłowej;
- różnicę;
- saldo PA w PLN oraz metodę kursową;
- liczbę transakcji zwykłych, transferów, splitów i pominiętych rekordów.

Raport zawiera też agregaty kategorii (kategoria i grupa) oraz listę wyjątków:
brak kursu, nieobsłużony split, niejednoznaczny transfer, niesparowane konto
lub kategoria. Import zapisujący jest dozwolony dopiero, gdy różnice sald
źródłowych dla wszystkich kont wynoszą zero, poza jasno zaakceptowanymi
wyjątkami opisanymi w raporcie.

## Bezpieczny workflow

1. Dodać model, parser, księgowanie i raport z testami.
2. Uruchomić dry-run i pełny import do izolowanej bazy PostgreSQL.
3. Porównać wynik z Actual konto-po-koncie oraz kategoria-po-kategorii.
4. Przedstawić raport użytkownikowi.
5. Dopiero po osobnej akceptacji wykonać backup produkcyjnej bazy oraz
   kontrolowaną korektę wyłącznie danych Actual wskazanego użytkownika.
6. Po korekcie ponownie uruchomić raport uzgodnieniowy na produkcji.

Nie stosujemy masowego `DELETE`, `TRUNCATE` ani ręcznych transakcji korygujących
bez tej osobnej zgody.

## Kryteria akceptacji

- Każde konto Actual ma zgodne saldo źródłowe w PA.
- Każda transakcja ma co najmniej dwa postings, a suma `base_amount_pln` z
  kierunkami debit/credit wynosi zero.
- Konta pozabudżetowe są widoczne, ale wykluczone z analiz budżetowych.
- Kategorie zachowują grupy i agregację rodzic-dziecko.
- Każdy brak kursu, split lub różnica jest raportowany; nic nie jest ukrywane
  przez kurs `1.0` ani zerujący zapis na tym samym koncie.
- Produkcja nie zmienia się przed zaakceptowanym raportem próbnym.
