# Velo — pogłębienie uzgodnienia bez zapisu (2026-10-27)

## Zakres

Użytkownik zaakceptował analizę pozostałych rozbieżności Velo, bez importu
i zmian danych. Wykorzystano dotychczasowy wrześniowy PDF rachunku, cykl karty
18.09–17.10 i dostarczony wcześniej eksport Actual. Nie otrzymano nowych wyciągów.
Pełne kwoty, identyfikatory i snapshoty pozostają poza Git.

Użytkownik ponownie udostępnił folder Drive i zaznaczył, że ma tylko te pliki.
Bezpośrednio sprawdzono jego cztery dokumenty: CSV, PDF rachunku, PDF karty
i harmonogram. SHA-256 wszystkich czterech identyczne z poprzednim manifestem.
Nie są to nowe źródła; nie ponawiano parsowania ani importu. Rozbieżności pozostają
otwarte do czasu dostępności dodatkowych wyciągów, bez zgadywania brakujących zdarzeń.

## Metoda i bezpieczeństwo

- Świeży, ograniczony do właściwego właściciela odczyt ORM: REPEATABLE READ,
  READ ONLY potwierdzony przez SHOW; 1086 rekordów właściciela.
- Historia, konta, kategorie i mapowania identyczne z dowodami 24.10 po wyłączeniu
  nowych kolumn metadanych przy porównaniu ze starym schematem. Porównanie przed/po
  bieżącej analizie obejmuje już wszystkie kolumny i pełne rekordy.
- Hashe siedmiu zachowanych plików wejściowych zgodne z pierwotnym manifestem;
  hashe dotychczasowych podstawowych dowodów również zgodne.
- Kwoty obliczane skryptami w groszach. Bankowe daty księgowania i waluty oddzielone
  od dat PA. Dopasowanie finansowe nadal nie jest bankowym identyfikatorem operacji.
- Pochodzenie trzech spornych zapisów odczytano istniejącym parserem Actual,
  z eksportu SQLite otwartego w trybie read-only/immutable, bez uruchamiania importera.

## Potwierdzone ustalenia

### Rachunek

- Różnica zamknięcia jest dokładnie sumą różnicy otwarcia i zmiany w okresie,
  a nie osobną trzecią usterką.
- Całą różnicę wrześniowych obrotów lokalizują dwa obciążenia PA z 29.09,
  bez odpowiednika kwotowego w dostarczonym wrześniowym PDF rachunku.
- 81 bankowych wierszy ma wykonalne pokrycie w 81 postingach PA; dwa dodatkowe
  postingi wyjaśniają różnicę agregatu. Nadal 17 powtarzalnych wierszy bez
  rozstrzygniętej tożsamości. To nie zgoda na automatyczny skip/import.
- Jednodniowe przesunięcie dopasowanego transferu pozostaje wewnątrz września
  i nie wyjaśnia różnicy miesięcznej. Pierwsze bankowe wiersze z sierpniową datą
  waluty są ujęte we wrześniu również w PA, więc nie wyjaśniają otwarcia.
- Nie znaleziono dokładnych przeciwstawnych odwróceń dwóch wskazanych kwot
  w dostarczonej historii PA tego rachunku. Brak bankowych danych października
  nie pozwala uznać tych obciążeń za błędne ani usunąć ich.

### Karta

- Cztery dodatnie korekty odsetek bez zgodnych kwot w PA oraz różnica kwoty
  jednego zakupu dokładnie wyjaśniają różnicę obrotów cyklu.
- Ta różnica obrotów jest kompensowana odmiennym otwarciem. Zgodne zamknięcie
  nadal nie jest pełnym uzgodnieniem. Sama równa kwota resztowa nie dowodzi
  konkretnej brakującej subskrypcji lub duplikatu.
- Hipotetyczne dodanie korekt i zmiana zakupu bez wyjaśnienia otwarcia zepsułyby
  zgodność końca. Nie jest to proponowany ani zatwierdzony zakres zapisu.

### Pochodzenie z Actual

Trzy wskazane operacje PA (dwie rachunku i jedna karty) zachowują daty i kwoty
kont z dostarczonego eksportu Actual po prawidłowym przeliczeniu jego konwencji
postings. Nie stwierdzono dowodu, że różnice tych trzech operacji powstały wskutek
importera lub nowego UI. Nie oznacza to poprawności danych Actual względem banku.

Początkowy check lokalnego narzędzia lineage porównywał także kategoriowe postingi
parsera jak postingi kont i nie odwracał konwencji debit/credit. Assertion zatrzymał
analizę; po sprawdzeniu istniejącego mapowania importera poprawiono wyłącznie
narzędzie audytowe. Nie był to błąd księgi ani produktu.

## Brakujące dowody i decyzja

1. Wyciąg rachunku za sierpień, wraz z saldami otwarcia i zamknięcia.
2. Historia rachunku co najmniej 01–06.10: daty księgowania i waluty, kwoty,
   saldo i referencje dla dwóch wskazanych obciążeń.
3. Poprzedni wyciąg karty, zamykający cykl 17.09.
4. Potwierdzenie przypisania dwóch produktów bankowych do kont PA;
   bankowe identyfikatory nie są uzupełnione w metadanych tych kont.

**NO IMPORT / NO AUTO CORRECTIONS.** Wyjaśniono strukturę arytmetyczną różnic,
nie ich niezależne źródło bankowe. Potrzebne dokumenty, nie korekta wyrównawcza.

## Weryfikacja i artefakty

- Końcowy świeży READ ONLY: wszystkie rekordy i snapshot właściciela identyczne
  z początkiem analizy; hashe oryginałów bez zmian.
- Bez importu/uploadu/OCR, edycji sald/dat/kwot, migracji, deployu ani zewnętrznych
  wywołań z danymi bankowymi. Backend/frontend/ops bez zmian.
- Niezależny przegląd odtworzył obie arytmetyki i pochodzenie trzech operacji:
  bez blokad rachunkowych. Potwierdzono ograniczenia tożsamości/mapowania i zakaz
  traktowania braku dopasowania jako dowodu brakującego zdarzenia bankowego.
- Prywatne dowody: `/tmp/opencode/velo-reconciliation-20261027/`;
  kwoty i praktyczna lista dokumentów w `CONCLUSIONS.md`.
- Trwały prywatny pakiet poza Git:
  `/opt/finanse/webapp/imports/velo-reconciliation-20261027` (0700/0600, manifest hashów).
