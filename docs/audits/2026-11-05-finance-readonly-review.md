# Przegląd powdrożeniowy finansów — tylko odczyt

## Zakres i ograniczenia

Użytkownik zaakceptował przegląd interfejsu i istniejących danych bez zmian,
księgowania, importu lub wywołań AI. Produkcja nadal `8121512`, schema `7b57f2f0bde6`,
trzy usługi aplikacji zgodne z aktywnym wydaniem.

Pierwszy preflight wykazał więcej niż jedno aktywne konto. Zatrzymano odczyt szczegółów
do czasu jawnego wskazania konta przez użytkownika. Po ponowieniu pytania użytkownik
wskazał konto; dalsze SELECT-y miały parametr właściciela znalezionego po tym adresie.
Nie publikować identyfikatora/adresu, treści transakcji lub prywatnych obrazów w repo.

Źródła dowodów:
- produkcyjne HTTPS/health i publiczny browser375/1440;
- SELECT-y z `REPEATABLE READ READ ONLY`, limitem czasu zapytania i końcowym rollback;
- przegląd źródeł wdrożonego interfejsu, bez modyfikacji produktu.

Nie tworzono, nie odzyskiwano i nie podmieniano sesji. **Nie wykonano testu zalogowanego
interfejsu na produkcji**; uwagi o takich ekranach pochodzą ze źródeł, nie z przeglądarki
z sesją użytkownika. To nie odbiór płatnego odczytu zdjęcia lub mutujących zatwierdzeń.

## Wynik odczytu danych wybranego konta

- Wszystkie obecne transakcje mają źródło Actual; nie ma ręcznych wydatków do pilota
  nowych reguł/propozycji. Aktualne automatyzacje są future-only dla nowych ręcznych
  wydatków PLN. Brak automatycznej zmiany historii jest zamierzony.
- Brak wpisu ustawień kategorii technicznej, reguł i indywidualnej zgody na propozycje AI.
  Serwerowa dostępność AI nie zastępuje ustawień i zgody użytkownika; nie dopisywano ich.
- Brak nowych metadanych dat. Stara data działa jako jawny fallback, nie dowód daty zakupu
  lub księgowania. To oczekiwany skutek migracji bez backfillu, nie utrata dat.
- Jest zatwierdzona faktura PLN, ale brak kwalifikującego źródła paragon/obraz PLN
  i brak zadań odczytu produktów. Faktury nie potraktowano jako próbki paragonu.
- Invariant księgi: zero transakcji z mniej niż dwoma postings lub niezbilansowanymi postings.
- Nie ujawniano sald, opisów, kwot lub nazw rachunków. Prywatny wynik zawiera agregaty.

Helper pierwszego odczytu użył błędnej nazwy `state` zamiast `status` dla zadań propozycji.
PostgreSQL odmówił SELECT; poprawiono wyłącznie helper i powtórzono transakcję read-only.
Nie był to błąd aplikacji ani migracji; nie wykonywano operacji naprawczych na bazie.

## Uwagi do użyteczności ze źródeł

### 1. Niska: sprzeczna jednostka w komunikacie walidacji podziału

Pola mają etykietę „Kwota PLN”, a parser przyjmuje kwotę PLN i przelicza ją na grosze.
Przy błędnym wpisie pojawia się „Uzupełnij poprawne kwoty w groszach”. To może skłaniać
do wpisania 100 razy większej kwoty. Źródła: `CategorySplitEditor.tsx:43–58` oraz
`TransactionCategorizationDialog.tsx:87,159–163`. Do osobnej poprawki tekstu z testem.

### 2. Niska: brak jasnego pustego stanu przy braku obrazu paragonu

`ReceiptReadPanel.tsx:302–370` wyjaśnia wyłączoną politykę, lecz przy aktywnej polityce
i pustej liście źródeł pozostawia pusty selektor i nieaktywny przycisk. Brakuje informacji,
że najpierw potrzebny jest kwalifikujący załącznik. Na wybranym koncie nie ma takiego
paragonu, więc problemu nie odtworzono w zalogowanej produkcyjnej przeglądarce.

### 3. Niska, warunkowa: ponowny wybór próby przy stronicowaniu załączników

Wybrana próba ustawia zdjęcie i jobID, ale źródło wyszukiwane jest tylko w aktualnej
stronie załączników. Zmiana strony czyści wybór (`ReceiptReadPanel.tsx:95,104–110,
329–349,380–392,444–452`). Odczyt historyczny z innej strony wymaga przejścia do jej
załącznika i ponownego kliknięcia próby. Agent źródłowy ocenił to jako utratę możliwości
odczytu; po sprawdzeniu kodu obniżono ocenę: historia pozostaje dostępna i ponowny wybór
jest możliwy. Nie ma dowodu trwałej utraty wyniku lub blokady ponownego odczytu.

Nie wykryto w tym ograniczonym przeglądzie potwierdzonego błędu krytycznego. Nie jest
to zapewnienie o braku błędów w ścieżkach niewykonanych po zalogowaniu.

## Weryfikacja publiczna i następny krok

Produkcyjne health200, login375/1440, brak overflow/pageerrors/obcego ruchu/mutacji;
chronione ścieżki przekierowują do logowania. Nie omijano autoryzacji w celu testu.
Prywatne dowody: `/tmp/opencode/finance-readonly-review-20261105/`.

Rekomendacja: najpierw świadoma konfiguracja kategorii technicznej i zgody AI w panelu
użytkownika oraz zwykłe nowe ręczne wydatki; nie uruchamiać historii. Drobne poprawki UI
wymagają osobnej zgody/planiku, a pilot 4B prawdziwego paragonu i osobnej zgody eksportu.
Żadnych zmian produktu, danych, polityk, grantów, wdrożenia lub modeli w tej sesji.
