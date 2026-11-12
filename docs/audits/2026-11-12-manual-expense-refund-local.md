# Ręczne zwroty wydatków — implementacja lokalna

## Zatwierdzony zakres

Użytkownik chce zwrot części towaru do tej samej kategorii, np. `Dom - Naprawy`.
Wybrał konto/kategorię/kwotę bez wskazywania zakupu. Zatwierdził implementację
lokalną i testy wpływu na saldo, kategorię i budżet, **bez wdrożenia**.

## Zachowanie

- Formularz transakcji: typ **Zwrot wydatku**, aktywne konto PLN, aktywna kategoria
  wydatkowa, dodatnia kwota, data zwrotu i opis. Etykiety kategorii zachowują pełne
  ścieżki i polskie sortowanie. Zmiana typu czyści wybraną kategorię.
- Kwota zwiększa saldo konta i pomniejsza wydatki kategorii, nie zwykłe przychody.
  Zakup500zł + zwrot150zł = wydatek350zł. Budżet odzyskuje150zł dostępnej kwoty.
- Zwrot dotyczy miesiąca daty zwrotu, nie zmienia wcześniejszego zakupu. Bez linku
  do zakupu możliwy samodzielny zwrot, również większy niż wydatki danego miesiąca;
  wtedy wydatki netto mogą być ujemne. To nie jest limitowana korekta paragonu.
- Konto niebudżetowe odzyskuje saldo, ale nie wpływa na raport budżetowy.
- Brak zmian schematu lub typu transakcji w bazie: expense z odwróconymi kierunkami,
  jak istniejące zwroty importowane. Wprowadzanie zwykłych przychodów nie zmienia się.

## Granice bezpieczeństwa

`POST /finance/transactions/expense-refund` przyjmuje tylko account_id, category_id,
amount_minor, transaction_date i description. Dodatkowe pola są zabronione, kwota
jest ścisłą dodatnią liczbą całkowitą groszy <=MAX_SAFE. Postings/source/typ/kierunki
i walutę ustala serwer. Dwie pozycje: konto credit i kategoria debit, suma0.

Owner/active/type/PLN i lock konta stosują istniejące walidacje. Zwykła trasa tworzenia
transakcji nadal odrzuca odwrócony expense; klient nie może włączyć trusted flag.
Powstaje audit `create_expense_refund`; zwrot nie inicjuje reguł ani sugestii AI.
Nie powstaje dopasowanie do oryginalnego zakupu lub płatności faktury.

## Stan weryfikacji

- Baseline648vitestPASS. Refund endpoint RED22FAILmissingroute405/1PASS→GREEN23PASS.
- Formularz/hook RED3FAIL/51PASS→GREEN54PASS; brak daty RED1FAIL→dateguard.
- Ruff0.17.4/mypy193PASS. HostvenvRuff0.16.2 jest starszy niż constraint projektu;
  jego3DTZ007 w istniejących parserach nie zostały „naprawione” zmianą poza zakresem.
- Pełny backend: kolekcja wszystkich standardowych nonproxy testów i podział plików
  między8własnych PG/runner bez sieci hosta/portów. Count/JUnit/sourcehash kontrolowane.
  Pierwsza próba setup natrafiła na race pg_isready, nie uruchomiła testów; usunięto
  wyłącznie własną parę i dodano boundedreadinesswait. Produkcja nie jest używana.
- Pełnyfrontend655PASS/107plików, ESLint/tsc/buildPASS (istniejący bundlewarning>500kB).
  E2E10PASS desktop/mobile: nowyzwrot, categoryselectpaths i transactiondates.
  Screeny375/1440 obejrzane, brak horizontaloverflow.
- Jeden świeży review:0Critical/Important/Minor, Declinedtojudgepuste; bez fixpass.
  Backend2375cases: pierwsza próba2274PASS/0failedassertions/101setupERROR/0skip.
  Wszystkie101 to brak scopefixtureowner/migration przy ważonym podziale explicitfiles.
  Powtórka tylko101 z normalną kolekcją katalogu i selekcją po kolekcji: **101PASS**.
  Finalnie **2375PASS/0fail/error/skip**, pełna rozłączna tożsamość2375testów sprawdzona.
  Pierwotne błędy nie są ukryte. Kod aplikacji pozostaje bez zmian po freeze.
  Po pełnym przebiegu uporządkowano jeden import w nowym teście: identyczny zestaw
  importów i AST ciał testów; focused24 powtórzone. Zwykły zestaw wyklucza23proxy;
  testów Docker proxy nie ponawiano przy zmianie bez infrastruktury/nginx.

### Decyzje weryfikacyjne

- Ruff0.17.4 z istniejącego runnera zamiast host0.16.2: zgodność z constraintem;
  koszt ewentualnej pomyłki — różnica wersji narzędzi. Wersje i logi zachowane.
-8izolowanych części pełnego backendu: wszystkie pliki i liczba przypadków pokryte;
  koszt — brak pojedynczej kolejności szeregowej całego zestawu.
- Odbiór pełnego backendu ze wszystkich rozłącznych zielonychJUnitprzypadków,
  a nie powtarzanie zaliczonych2274. Błędyfixture101 powtarzane normalną kolekcją;
  koszt — różne tryby startu testów. Źródła i tożsamości sprawdzane. Jeden istniejący
  OCRparamname zawiera gzipmtime: wyłącznie ten wariantheaders2 kanonizowany,
  z kontrolą unikalności; pozostałe nazwy dokładne. Żadnej zmiany testu aplikacji.

## Stan integracji

Końcowy focused24PASS po uporządkowaniu importów, Ruff/mypy ponowniePASS. Usunięto
18własnych kontenerów po kontroli ID/label/noports/idle/exit!=137/absence; wcześniej
2własne kontenery nieudanej próby startu. Bezforce/prune lub ingerencji w cudze zasoby.
Raport obejmuje2375backend/655frontend/10E2E, jeden review bez uwag i zachowane dowody.

Bez merge/push/deploy i bez mutacji danych użytkownika. Po akceptacji lokalnego
wyniku przyszłe wdrożenie wymaga **spójnego backendu i frontendu**: nowy formularz
korzysta z nowego endpointu. Nie wdrażać samego frontendu jak w poprzedniej zmianie.
