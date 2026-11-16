# Bilans otwarcia każdego konta

## Zakres uzgodniony w rozmowie

- Każde konto ma BO w swojej walucie: dodatnie, ujemne albo zerowe.
- Przy tworzeniu konta formularz zawiera kwotę BO i datę, domyślnie dzisiejszą.
  Pusta kwota oznacza zero.
- Kwotę i datę BO można edytować wyłącznie, gdy na koncie nie ma innych
  transakcji; sam BO nie blokuje edycji. Transakcja oczekująca również blokuje.
- BO wpływa na saldo, nie na przychody, wydatki ani wykorzystanie budżetów.
- Dla wszystkich istniejących kont inicjalizujemy BO kwotą 0, bez zmiany
  dotychczasowych sald, transakcji, postings, kategorii i powiązań.
- Implementacja i migracyjne próby lokalne. Bez wdrożenia, produkcyjnej
  migracji, zerowania sald ani korekt dawnych bilansów Actual.

## Decyzje wykonawcze — zatwierdzone z planem w rozmowie

1. Osobny rekord `AccountOpeningBalance` identyfikuje BO konta. Zawiera właściciela,
   konto, datę, wersję oraz opcjonalny odnośnik do transakcji BO. Nie przechowuje
   drugiej kopii kwoty: dla niezerowego BO kwota wynika z nogi konta w księdze,
   a brak transakcji oznacza dokładnie 0.
2. Niezerowe BO to własny, nieoczekujący rodzaj transakcji `opening_balance`
   ze źródłem `opening_balance` i dokładnie dwoma postings. Nogą przeciwną
   jest techniczna kategoria typu `transfer`, nie dodatkowe konto finansowe.
   Kategoria jest identyfikowana systemowo, niewidoczna w zwykłych wyborach,
   nieedytowalna i niedostępna dla zwykłych transakcji, reguł, AI i importów.
   Obie nogi mają `is_budget_impact=False`.
3. Zachowujemy rzeczywistą konwencję projektu: dodatnie saldo konta wynika
   z nogi `credit`, ujemne z `debit`; znak sumy księgi nadal debit+, credit−.
   Kwoty postings są dodatnimi wartościami bezwzględnymi.
4. BO=0 ma trwały rekord, ale nie tworzy fikcyjnej zerowej transakcji/postings.
   Backfill obejmuje także nieaktywne konta i karty. Datą zerowego BO istniejących
   kont jest ich `opened_at`, nie domniemana data historycznej transakcji.
5. PLN używa kursu 1. Dla niezerowego EUR/USD użytkownik podaje dodatni kurs PLN
   z maksymalnie 6 miejscami, zapisany ze źródłem `manual`; bez zgadywania kursów
   i bez zewnętrznego wywołania AI/NBP. BO=0 nie wymaga kursu.
6. Dedykowana komenda zmiany BO używa wersji i klucza idempotencji. Wspólna
   blokada mutacji właściciela oraz wyłączna blokada konta serializują ją
   z pierwszą transakcją. Nie rozpoznajemy BO po opisie ani deklarowanym przez
   klienta `source`; wykluczenie obejmuje wyłącznie powiązaną transakcję BO.
7. Zwykła edycja/usuwanie transakcji, korekta dat, kategoryzacja, alokacja faktury,
   link darowizny lub spłaty nie mogą zmieniać ani wykorzystywać BO.
8. Zmiana waluty konta z niezerowym BO pozostaje zablokowana przez jego postings.
   BO=0 nie blokuje istniejących zasad zmiany waluty ani usunięcia pustego konta.
   Rekord zerowego BO znika razem z usuwanym pustym kontem.
9. Edycja niezerowego BO aktualizuje jego dedykowaną transakcję atomowo z audytem.
   Przejście do zera usuwa wyłącznie tę transakcję i jej dwie nogi, zachowując
   rekord BO i audyt; nigdy nie usuwa innych transakcji. Nie jest to masowe DELETE.
   Brak innych transakcji jest sprawdzany w bieżącym stanie, również po usunięciu
   wcześniejszej zwykłej transakcji zgodnie z istniejącymi uprawnieniami.

## Odbiór

Testy rzeczywistego PostgreSQL: znaki, zero, waluty, atomowość, izolacja właściciela,
wyścig pierwszej transakcji, blokady wszystkich bocznych ścieżek i retencja migracji.
UI: tworzenie, edycja BO bez historii, blokada z historią i konflikt po odświeżeniu,
mobile/desktop. Backendowe sumy, budżety, prognoza i karta widzą poprawne saldo,
bez sztucznego przychodu/transferu pomiędzy kontami użytkownika.
