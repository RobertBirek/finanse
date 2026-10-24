# Bank statements — zatwierdzony podgląd bez zapisu

## Zakres i granice

Zgoda użytkownika: tylko podgląd CSV Revolut i tekstowych PDF rachunku/karty
VeloBank po zakończonym imporcie Actual. Porównanie z PA, kandydaci dopasowań,
nowe/niejednoznaczne operacje, transfery i salda. Brak zgody na zapis księgi,
upload dokumentów, poprawianie dat/kategorii/historii ani import harmonogramu kredytu.

Oryginały pozostały w prywatnym `/tmp/opencode/bank-import-review`. Pełne dane,
hashe i analiza wyłącznie w `/tmp/opencode/bank-preview-20261024`, nie w Git.
Nie wysyłano danych bankowych do zewnętrznych usług ani endpointów aplikacji.

## Metoda

- Świeży odczyt ORM produkcji: REPEATABLE READ + READ ONLY, potwierdzone SHOW.
  Snapshot identyczny z zakończonym importem Actual:1887 transakcji całej bazy,
  1086 właściciela. Analiza wyłącznie jego kont/postingów.
- Obliczenia w groszach/centach, Decimal do odczytu kwot. Znak kont zgodny z PA:
  credit=inflow, debit=outflow, bez zmiany domenowej konwencji księgi.
- Dopasowanie tego samego proponowanego konta,waluty,znaku i rzeczywistej kwoty
  obciążenia; daty rozpoczęcia/księgowania jawnie oddzielone. Okno3d służy wyłącznie
  wyszukaniu kandydatów,nie automatycznemu uznaniu duplikatu lub zmianie daty.
- Zachowanie liczności w obrębie skonfigurowanego okna: powtórzony wiersz lub ponowne
  użycie tego samego postingu oznacza niejednoznaczność. Równe kwoty poza oknem
  pokazano oddzielnie,nie dowodzą tożsamości. Nie stosowano zachłannego auto-skip.
- Bez trwałego bankowego ID lub potwierdzenia konta przez bankowy identyfikator
  dopasowanie finansowe nie jest dowodem identyczności. Wszystkie decyzje pozostają
  podglądem,żaden wiersz nie ma zgody na automatyczny import.

## Revolut — wynik

- 5 zakończonych wierszy,0 pominiętych stanów pending/reverted.
- 4 jednoznaczne finansowo kandydatury na dacie rozpoczęcia,nie księgowania,
  1 kandydat transferu z różnicą1d. 0 wierszy bez kandydata w zadanym oknie.
- Salda bieżące CSV spójne per waluta po uwzględnieniu prowizji. Ostatnie saldo
  każdej waluty odpowiada natywnemu saldu PA na datę ostatniego księgowania CSV.
  Salda otwarcia wyliczone z pierwszych wierszy,nie z niezależnego nagłówka bankowego.
- Jedno obciążenie PA zawiera już prowizję podaną w CSV oddzielnie. Ponowne
  dodanie kosztu/prowizji zdublowałoby istniejące obciążenie.
- Mapowanie kont po nazwie/walucie jest propozycją; CSV nie zawiera IBAN ani
  unikalnego ID transakcji. Brak podstaw do automatycznego zapisu/korekty.

## VeloBank i zamknięcie kontroli

PDF rachunku:81 wierszy za wrzesień. PDF karty:9 wierszy cyklu18.09–17.10.
Harmonogram kredytu wyłączono w całości:plan rat nie jest historią wykonanych płatności.
Niezależnie sprawdzono90 kwot i par dat względem tekstu,81 kolejnych sald rachunku
oraz kolejność wierszy/dat z lokalnego odczytu oryginalnych PDF (Ghostscript).
Każdy dokument sam w sobie spełnia opening+sum(rows)=closing. Strony źródłowe
stanowią estymaty ekstraktora; wierne odniesienie do linii tekstu pozostaje w raporcie.

| Źródło | Wiersze | Jeden kandydat finansowy | Niejednoznaczne | Bez zgodnej kwoty w oknie |
|---|---:|---:|---:|---:|
| Revolut |5|5|0|0|
| Velo rachunek |81|64|17|0|
| Velo karta |9|4|0|5|
| Łącznie |95|73|17|5|

71 z73 pojedynczych kandydatów ma zgodną jedną z jawnych dat źródłowych;2 są
near-date. Nie są to bankowe identyfikatory duplikatów. Na rachunku17 niejednoznacznych
wierszy ma powtarzalne kwoty; liczności grup2/13/2 odpowiadają kandydatom PA i istnieje
pokrycie1:1,ale nie ustalono tożsamości pojedynczych wierszy. Nie wolno ich ponownie
dodawać tylko dlatego,że opis PA jest ogólną kategorią zamiast nazwy sklepu.

### Rozbieżności blokujące zapis

- Rachunek:wszystkie81 wierszy ma kandydatów,ale PA i bank różnią się na otwarciu
  i zamknięciu. Dwa dodatkowe postingi PA w końcu września nie mają odpowiednika
  w tym wyciągu. Nie oznacza to,że są błędne:mogą wymagać wyciągu następnego okresu
  i odrębnej kontroli dat. Nie usuwać i nie kompensować.
- Karta:4 dodatnie korekty odsetek nie mają zgodnej kwoty w PA. Dla jednego zakupu
  istnieje obciążenie tego samego dnia,ale z inną kwotą; to konflikt do wyjaśnienia,
  nie bezpieczna nowa operacja. Opis PA jest nazwą kategorii,nie dowodem sklepu.
- Końcowe saldo karty jest zgodne,ale różnica otwarcia dokładnie kompensuje różnicę
  zmian w okresie. Zgodność samego końca NIE stanowi pełnego uzgodnienia.
- Sześć istniejących transakcji transferowych ma potwierdzające wiersze bankowe.
  Spłata karty i zasilenie Revolut mają obie strony w dostarczonych źródłach;
  nie traktować ich jako kolejnych przychodów/wydatków. Pozostałe to kandydatury
  transferów znanych PA,bez importowania harmonogramu kredytu.

**Rekomendacja:nie importować i nie korygować księgi.** Najpierw poprzedni wyciąg
karty (do17.09),sierpniowy rachunku i odpowiednie księgowania początku października,
oraz potwierdzenie proponowanych mapowań kont. Pełne kwoty/ID pozostają prywatne.
4 korekty odsetek to kandydaci brakujących zdarzeń,nie zatwierdzony zakres zapisu.

## Kontrole końcowe

Niezależny przegląd wykrył nieprecyzyjne oznaczenie dat rozpoczęcia jako same-date,
nadmierne twierdzenie o globalnej liczności oraz brak komentarza do odcięcia USD.
Poprawiono etykiety i oba odcięcia salda. Walidacja kwot jawnie odrzuca ułamki centa
i niefinitywne wartości; oba skrypty Revolut/dopasowań odmawiają pracy przy Python-O. Lokalne kontrole
odrzucają ponowne użycie postingu,niewłaściwą walutę/konto i kwotę bez prowizji.

Pierwszy snapshot kontroli bezpieczeństwa obejmował wszystkich właścicieli;
lokalną kopię ograniczono następnie do analizowanego właściciela. Dalszy odczyt ma
filtr owner w ORM. Wszystkie prywatne pliki0600,katalog0700. Nie zmieniono oryginałów,
wcześniejszych dowodów importu ani aplikacji.

Końcowy świeży READ ONLY potwierdził niezmienność1086 pełnych zapisów właściciela,
jego kont/kategorii/mapowań. Hashe wszystkich7 zastanych oryginałów identyczne.
Niezależny końcowy review potwierdził95 wierszy,klasyfikacje i rachunek rozbieżności;
rekomendacja NO IMPORT/NO AUTO CORRECTIONS potwierdzona. Nie uruchamiano bankowego
importera ani próbnego zapisu na produkcji. Kod backend/frontend/ops niezmieniony.
Przed commitem dokumentacji:96 testów finansowej historii/integracji i194frontend,
Ruff/mypy/ESLint/tsc PASS. To gate niezmienionego produktu,nie dowód istnienia
lub certyfikacja importera bankowego.

Trwały pakiet audytowy poza Git:
`/opt/finanse/webapp/imports/bank-preview-20261024` (0700/0600,manifest hashów).
To prywatne źródła i dowody podglądu,nie źródło prawdy finansowej. PostgreSQL
pozostaje bez zmian. Żaden plik bankowy ani snapshot nie trafia do commitu.
