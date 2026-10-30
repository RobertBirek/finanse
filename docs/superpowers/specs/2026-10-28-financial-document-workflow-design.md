# Obieg dokumentów finansowych: faktury, paragony i płatności

Status: zakres zaakceptowany; Tasks1–10 oprogramowania zaimplementowane i po review.
Końcowy gate941backend/278frontend/75E2E+1skip PASS; całościowy review gałęzi w toku (2026-10-30).
Certyfikacja rzeczywistych Android/iPhone pozostaje BLOCKED; viewport nie zastępuje urządzeń.
Bez zgody na deploy, import istniejących danych lub korekty księgi.
Data: 2026-10-28. Pierwszy etap przed dalszym rozszerzeniem Q7.

## 1. Intencja i decyzje użytkownika

Użytkownik dodaje dokument do aplikacji, następnie rozumie, czy trzeba coś opłacić,
czy dokument potwierdza już istniejącą operację, oraz gdzie jest jego oryginał.
PDF i zdjęcie tej samej faktury nie mogą tworzyć dwóch płatności/kosztów.

Uzgodniono: tylko dodawanie w aplikacji, bez Google Drive i innych integracji;
obsługa aparatu telefonu i zdjęć faktur/paragonów, także HEIC/HEIF; faktury nieopłacone w Nadchodzących,
częściowo opłacone z pozostałą kwotą; opłacone i paragony powiązane z rzeczywistymi
operacjami. Po przedstawieniu projektu użytkownik zaakceptował zakres, następnie
rozszerzenie o HEIC/HEIF zamiast ręcznej konwersji zdjęć; polecił kontynuować.

## 2. Punkt wyjścia potwierdzony w kodzie

- `documents`: bezpieczny upload PDF/JPEG/PNG, SHA-256 per właściciel, oryginały
  bez nadpisywania, kolejka OCR i lista statusów. Aparat już istnieje; upload pojedynczy.
- Worker: obraz→pochodny PDF→Stirling OCR→tekst; próba jednej sugestii expense/income
  do Inbox. `done` dotyczy OCR, nie kompletności rozpoznania i nie zapłaty.
- `DocumentViewer` pokazuje tekst, nie pełny oryginał; brak terminu/rozliczeń faktur.
- Inbox ma wyłączoną konwersję na transakcję. Nie aktywować jej ogólnie przy tej pracy.
- `ScheduledFinanceItem` to miesięczna reguła z `due_day`, nie jednorazowa faktura.
  Forecast obecnie dopasowuje po koncie/kategorii/kwocie i oknie dat; to nie tożsamość.
- Istniejące PDF użytkownika nie były w tej sesji przeglądane na produkcji.

## 3. Wielkość i granice pierwszego wydania — propozycje autora

Pionowy zakres: dokument→weryfikacja→rejestr→pozostała płatność→jawne rozliczenie.
To kilka domen, ale jedna funkcja użytkowa w istniejącym modularnym monolicie.

W pierwszym wydaniu: faktury zakupowe dodatnie i paragony, upload PDF/JPEG/PNG/HEIC/HEIF,
aparat/galeria, kilka plików z kolejką i wynikiem per plik; kwoty PLN/EUR/USD w rejestrze.
Jawne przypisanie istniejących płatności i tworzenie brakującej płatności początkowo
tylko PLN. EUR/USD zachowują oryginalne kwoty, widoczne ograniczenie rozliczenia;
nie przeliczać do prognozy PLN bez zatwierdzonej polityki kursu. Nigdy suma walut.

Poza zakresem: wysyłanie przelewów do banku, księgowość podatkowa/VAT/JPK/KSeF,
faktury sprzedażowe, zaliczki, korekty/zwroty i wieloterminowe raty faktury, automatyczne
księgowanie, import wyciągów/harmonogramów oraz wersjonowanie Q7. Te dokumenty można
przechować/odczytać, ale nie traktować jako zwykłego wydatku do zatwierdzenia.
Nie dodawać nowego systemu synchronizacji lub nowej kolejki poza obecnym workerem.

Wielostronicowe skany składane z kilku zdjęć nie w pierwszym wydaniu. Format z aparatu
zależy od telefonu/przeglądarki: JPEG/PNG oraz HEIC/HEIF przyjmować bez wymagania
zmian ustawień telefonu. Zachować dokładne bajty oryginału, do OCR/podglądu tworzyć
pochodną JPEG lokalnie. Dekodowanie/konwersja w ograniczonym procesie, nie w event loop.
Poprawna orientacja, bez metadanych lokalizacji w pochodnej. Awaria konwersji oznacza
czytelny błąd/próbę ponowienia; nigdy utraty już zapisanego poprawnego oryginału.
Plik uszkodzony/niebezpieczny nadal może zostać odrzucony przed zapisem. Limity i
walidacja treści obowiązują także zdjęcia; nie obiecywać obsługi filmów/animacji RAW.
Sprawdzić na rzeczywistym telefonie, nie tylko fixtures. CSV bankowe pozostaje poza
tym importerem faktur: brak podpinania wyciągu jako pojedynczego expense.

## 4. Zasady nienaruszalne

- Plik != odczyt != dokument handlowy != płatność/transakcja != reguła cykliczna.
- Upload/OCR/rejestracja faktury NIE tworzą postingów i nie zmieniają sald/budżetu.
  Pierwszy etap pozostaje kasowy: koszt w raportach wynika wyłącznie z księgi.
- LLM daje propozycje z oznaczeniem niepewności; brakujące kwoty/terminy pozostają
  nieznane. Walidacja finansowa i sumy deterministyczne, BIGINT/grosze bez float.
- Dowód „zapłacono” na dokumencie to deklaracja, nie uzgodnienie z księgą.
- Wszystkie odczyty/mutacje owner-scoped, mutacje walidowane i audytowane.
- Oryginały prywatne, brak nowych publicznych URL; brak sekretów/danych bankowych w Git.

## 5. Przebieg i niezależne statusy

1. Dodanie: zapis oryginału z obecnymi limitami i walidacją; duplikat bajtowy wskazuje
   istniejący plik. Każdy upload ma własny rezultat. Żadna częściowa awaria nie ukrywa
   plików już zapisanych. Jeden plik jest jednym dokumentem handlowym; plik zawierający
   kilka faktur wymaga rozdzielenia przed rejestracją (komunikat, bez zgadywania sumy).
2. Odczyt: OCR osobno od ekstrakcji biznesowej. Zapisać propozycję, wersję i pochodzenie
   pól, błędy/niekompletność ekstrakcji pokazać jawnie. `done` OCR pozostaje kompatybilne.
3. Weryfikacja: oryginał i rozpoznane pola, ręczne poprawienie danych; obowiązkowe typ,
   waluta, dodatnia kwota do zapłaty/suma paragonu, sprzedawca/opis. Numer faktury i data
   wystawienia zalecane; brak nie blokuje ręcznego rejestru, ale osłabia deduplikację.
4. Zatwierdzenie: tworzy/aktualizuje jeden rekord rejestru, nie transakcję. Użytkownik
   wybiera: do opłacenia, deklarowane opłacone, nie ustalono. Paragon domyślnie
   deklarowany opłacony, nigdy automatycznie uzgodniony. Można zmienić na do opłacenia.
5. Rozliczenie: jawne linki do rzeczywistych płatności i opcjonalne zarejestrowanie
   brakującej płatności przez istniejący serwis księgi z audytem i potwierdzeniem.

Oddzielne osie:
- OCR: pending/processing/done/error (obecne).
- weryfikacja: wymaga sprawdzenia / zatwierdzony / odrzucony;
- deklaracja zapłaty: nieznana / do zapłaty / deklarowane opłacone;
- uzgodnienie: brak / częściowe / pełne, liczone tylko z ważnych linków księgi;
- przeterminowanie liczone z terminu i pozostałości, nie ze statusu OCR.

„Deklarowane opłacone” z niepełnym uzgodnieniem trafia do kolejki uzgodnienia, nie
do przyszłych wypłat. Nie zmienia salda, raportów wydatków ani linków bez decyzji.
Pozwala uniknąć fałszywego przyszłego wydatku, ale wymaga widocznego ostrzeżenia
o nieuzgodnieniu, nie zielonego statusu potwierdzenia przez bank.

## 6. Rejestr i odpowiedzialność domen

`documents` odpowiada za pliki, pochodne, tekst i propozycję ekstrakcji. Propozycja
przechowuje typ dokumentu, sprzedawcę/NIP (opcjonalny), numer, daty wystawienia/sprzedaży/
termin, kwotę brutto/do zapłaty, walutę, rachunek odbiorcy (opcjonalny), deklarację
zapłaty i źródło każdego pola (OCR/ręcznie). OCR nie ustala „paid” jako faktu bankowego.

`finance` odpowiada za rekord dokumentu handlowego/rejestru, zobowiązanie i rozliczenie.
Nowe modele (nazwy techniczne do dopracowania w planie):
- FinancialDocument: owner, typ, zatwierdzone pola, stan weryfikacji/deklaracji,
  dodatnia kwota/waluta, opcjonalny termin/kategoria/planowane konto, wersja optymistyczna.
- FinancialDocumentSource: owner, rekord rejestru, Document; kilka oryginałów może
  dokumentować jeden zakup. Jeden oryginał jest przypisany najwyżej do jednego rekordu
  w całym cyklu życia, również po odrzuceniu/archiwizacji (unikalność Document ID).
  Ponowna praca otwiera ten sam rekord/draft, nie zakłada nowego. Błędne przypisanie
  źródła można jawnie przenieść: audyt, blokady obu rekordów, kontrola alokacji;
  nigdy kopiowanie obowiązku finansowego. Odrzucenie draftu nie usuwa źródła.
- DocumentPaymentAllocation: owner, rekord rejestru, ID kontowego postingu, kwota
  alokacji w PLN; unikalność para rekord/posting; wiele płatności na dokument i wiele
  dokumentów na jeden posting. Kwoty nie mogą przekroczyć żadnej z obu pojemności.
- RecurringOccurrenceCoverage: owner, ScheduledFinanceItem, konkretna data wystąpienia,
  rekord faktury; jawne zastąpienie konkretnej estymaty, nie całej serii.

Plan płatności faktury jest odczytem pozostałości rekordu, NIE kopią w
ScheduledFinanceItem. Nie trzeba osobnej tabeli jednorazowych płatności dla tego etapu.
Modele relacyjne i PostgreSQL są źródłem prawdy; JSON propozycji OCR nie jest księgą.

## 7. Nadchodzące i prognoza — jedno źródło kwoty

- Zatwierdzona faktura „do zapłaty”, z terminem i pozostałością >0: jedna pozycja
  Nadchodzących z identyfikatorem źródła faktury i oryginalną walutą.
- Brak terminu: rejestr „uzupełnij termin”, bez zgadywania go z daty wystawienia.
- Nieznana deklaracja zapłaty: „ustal płatność”, wyłączona z sum prognozy.
- PLN + jawnie wybrane aktywne budżetowe konto PLN: pozostałość w cashflow raz,
  w dniu terminu; przeterminowana na dziś (raz, niezależnie od miesiąca).
- PLN bez konta lub konto pozabudżetowe: widoczne w Nadchodzących, ale bez wpływu
  na prognozę budżetową, z jawnym powodem. Nie dobierać rachunku automatycznie.
- EUR/USD: widoczne oryginalne kwoty i wyłączenie z sum PLN, bez fałszywego safe limit.
  Prognoza ma informować o nieujętych zobowiązaniach, nie obiecywać pełnej płynności.
- Uzgodnienie częściowe zmniejsza przyszłą kwotę, pełne ją usuwa; rzeczywisty posting
  jest już w saldzie początkowym, więc nie odejmować zapłaconej części drugi raz.
- Rozszerzyć kontrakt forecast źródłem `recurring|financial_document` i osobnymi ID;
  nie wkładać invoice ID w scheduled_item_id. Endpoint potwierdzenia cyklicznego nie
  obsługuje faktur; akcje dokumentowe kierować wyłącznie do nowego serwisu.

### Konflikt z istniejącą płatnością cykliczną

Przy zatwierdzaniu zobowiązania pokazać kandydatów wystąpienia reguły z tego miesiąca
(konto/kategoria/kwota/termin to wskazówka, nie dowód). Jeśli kandydat istnieje,
użytkownik jawnie wybiera „zastępuje to wystąpienie” lub „odrębna płatność”; do czasu
wyboru pozycja faktury jest widoczna, ale bez wpływu na prognozę (flaga do wyjaśnienia).
Przy zastąpieniu suppress tylko estymatę tego occurrence, kwotą rządzi faktura.
Wystąpienie może być pokryte najwyżej jedną aktywną fakturą w pierwszej wersji.
Nie tłumić całej serii ani opłat innego miesiąca. Wystąpienie cykliczne objęte fakturą
nie pozwala księgować przez stary `/confirm`; komunikat przekierowuje do rozliczenia.
Walidacja blokuje usunięcie/zniszczenie tożsamości pokrytej reguły bez jawnego odpięcia.

Pierwszeństwo: jawne coverage zawsze wyłącza estymatę danego wystąpienia, nawet gdy
stary matcher zwrócił `matched_actual`. Pozycją faktury rządzą wyłącznie jawne alokacje
i deklaracja, nie kwota/kategoria/data. Matcher innych niepokrytych wystąpień pomija
transakcje z choć jedną alokacją dokumentową, aby nie używać tej samej operacji do
ukrycia innej estymaty. Pozostałej heurystyki w tym etapie nie przebudowujemy.
Transakcja już heurystycznie pasująca do innej reguły to ostrzeżenie przy alokacji;
pokazać prognozę przed/po i wymagać potwierdzenia. Pokrywanie dwóch reguł jedną
alokowaną transakcją nie jest wspierane w pierwszym wydaniu.

Coverage pozostaje związane z wystąpieniem również po rozliczeniu/archiwizacji/
anulowaniu faktury: estymata nie może samoistnie wrócić. Odpięcie to osobna akcja
z potwierdzeniem skutku prognozy. Anulowanie zostawia widoczny ślad „wystąpienie
zastąpione/anulowane”, nie ukryty powód pominięcia. Ponowne otwarcie używa tego samego
coverage, bez nowego wystąpienia lub obowiązku.

## 8. Rozliczenie bez podwójnego kosztu

Pierwszy zakres PLN: wyłącznie rzeczywiste expense, nie pending, data <= dziś,
z dokładnie jednym kontowym debetem PLN i poprawną zbilansowaną księgą; kategoria
może być podzielona. Nie alokować transferów/przychodów/future/FX ani postingów
użytych w rozliczeniach kredytu. Konto właściciela może być aktywne lub archiwalne
(historyczny link), nie wymagamy budżetowości; kategoria płatności nie musi zgadzać
się z proponowaną na fakturze. Konto karty kredytowej expense może dowodzić zakupu,
jej późniejszy transfer spłaty NIE jest drugim kosztem lub drugą zapłatą faktury.

Brak dopasowania nie tworzy transakcji. Akcja „Zarejestruj płatność” wymaga daty,
konta PLN, kwoty i kategorii; pokazuje kandydatów zanim pozwoli utworzyć nową.
Wyraźnie mówi, że NIE zleca przelewu. Tworzy zwykłą expense przez istniejący serwis
finance, min2 postings/suma0, i alokację w jednej transakcji DB. Nowa płatność
nie może mieć przyszłej daty; częściowe i gotówkowe wymagają jawnego wskazania.

Alokacje <= pozostałość faktury i <= nieprzydzielona pojemność kontowego postingu.
Nie ma nadpłat faktur w tej iteracji. Zwroty/FX oznaczone jako poza zakresem.
Wiele dowodów tego samego zakupu (paragon+faktura) przypinać do jednego rekordu,
nie alokować po raz drugi. Podejrzenie duplikatu wymaga decyzji użytkownika.

Blokady i integralność: lock rekordów dokumentów, transakcji i postingów w stałej
kolejności; kwoty ponownie czytane po locku. Wspólny limit pojemności sprawdzany także
przy równoległym alokowaniu do różnych faktur. Klucze idempotencji scoped owner+akcja,
hash payloadu, unikalność w DB; retry z innym payloadem=konflikt. Stare wersje formularzy
odrzucone jako409. Create expense+allocation+audit atomowe; rollback nie zostawia kosztu.

Usuwanie/zmiana daty, pending, konta, kwot/walut/kierunku/transakcji/postingu
wykorzystanego do alokacji zablokowane we wszystkich mutatorach (także importerach),
dopóki alokacja jawnie nieodpięta. Niezmienione wartości mogą być idempotentne.
Odpięcie jest audytowane i odtwarza pozostałość, nigdy nie usuwa istniejącej płatności.
Zmniejszenie kwoty faktury poniżej alokacji lub zmiana waluty przy linkach zabronione.
Archiwizacja/anulowanie do zapłaty wymaga potwierdzenia skutku prognozy; alokacje
zachowane, brak fikcyjnej korekty księgi. Ponowne otwarcie także audytowane.

## 9. Duplikaty, istniejące uploady i OCR

- SHA chroni tylko identyczny plik. Sprzedawca/NIP+numer+waluta+data+kwota dają
  kandydatów biznesowych, nie automatyczne merge. Brak numeru: słabsza wskazówka.
- PDF i inne zdjęcie można jawnie przypiąć jako dodatkowy dowód do istniejącego
  rekordu. „Odrębny dokument” wymaga potwierdzenia ostrzeżenia; nie blokować legalnych
  powtarzalnych rachunków o tej samej kwocie. Równoległe review tego samego oryginału
  kończy się jednym rekordem dzięki lock/unikalności źródła.
- Istniejące uploady widoczne bez ponownego wgrywania. Akcja „Przygotuj do rejestru”
  per plik używa zachowanego tekstu, o ile dostępny. Brak tekstu/wyczerpane OCR mają
  osobne jawne retry; nie ponawiać starych OCR/LLM masowo ani w migracji.
- Dla nowych faktur/paragonów worker przygotowuje dedykowany draft rejestru zamiast
  równoległego nowego Inbox expense. Legacy sugestia powiązana po document_id staje
  się odsyłaczem/oznaczona zastąpiona dopiero w tej samej transakcji zatwierdzenia
  draftu; nie usuwać cudzych/niepowiązanych wpisów ani aktywować ogólnej konwersji.
- Przetworzony legacy Inbox: zachować historię/status/target bez przepisywania;
  dodać osobną relację/odsyłacz. Jeśli target wskazuje transakcję, sprawdzić właściciela,
  istnienie i kwalifikację; pokazać ją jako kandydata jawnej alokacji, nie auto-paid.
  Nieprawidłowy/usunięty target oznacza „wymaga uzgodnienia”, nie błąd uploadu.
  Dawna ręczna transakcja bez linku jest szukana w zwykłych kandydatach. Brak dopasowania
  nie dowodzi braku kosztu. Nowa płatność wymaga potwierdzenia ostrzeżenia o możliwym
  wcześniejszym księgowaniu oraz wskazania konta/dat/kwoty.
- Ponowna ekstrakcja tworzy wersję propozycji, nie nadpisuje ręcznych zatwierdzeń.
  Kategorie/rachunki z AI tylko propozycje; nie tworzyć automatycznie kont/kategorii.

## 10. Bezpieczeństwo, obrazy i audyt

Obecne limity uploadu/przestrzeni i odizolowana walidacja pozostają. Dodać bezpieczny
oryginał pod autoryzowanym endpointem z kontrolą właściciela, bez ścieżek storage
w publicznym kontrakcie, `nosniff`, bez cache publicznego. Pochodne miniatur/obrotu
nie zastępują oryginału. Limity wymiarów/pikseli i czasu dla obrazów, bezpieczna EXIF
orientacja; metadane lokalizacji usuwać z pochodnych, oryginał nadal prywatny.
Odczyt plików i wydobytych pól traktować jak dane niezaufane, bez wykonywania linków.
Podejrzany rachunek odbiorcy zawsze do kontroli; system nie inicjuje płatności.

LLM: korzystać z istniejącej konfigurowalnej usługi i jasno opisać wysyłanie tekstu
do zewnętrznego dostawcy (lokalny OCR nie oznacza lokalnej ekstrakcji). Nie dodawać
nowego zewnętrznego OCR. Wyłączenie/błąd LLM nie blokuje ręcznego rejestru. Nie logować
tekstów/surowych odpowiedzi. Kwoty i daty walidowane ścisłymi schematami i zakresami
bezpiecznymi dla JS; cichy brak rozpoznania zastępuje jawna niekompletność.

Powiązanego oryginału nie usuwać obecnym DELETE: RESTRICT/admission check dla źródła
rekordu, także legacy API. Użytkownik może archiwizować rejestr bez niszczenia dowodów.
Retencja/uprzątnięcie fizycznych plików nie jest częścią tego wdrożenia.
Audyt create/approve/edit/allocate/unlink/archive/reopen/coverage: owner, actor,
ID źródeł, wersja, zmienione pola; brak sekretów i niepotrzebnego pełnego tekstu OCR.

## 11. Weryfikowalne scenariusze akceptacji

1. Nowa faktura100 PLN za10 dni po weryfikacji: rejestr i jedna pozycja forecast,
   zero zmian ledger. Brak zatwierdzenia: tylko draft, zero wpływu na prognozę.
2. Zapłata40: po linku pozostaje60; koszt istnieje tylko raz. Pełne uzgodnienie:
   zero przyszłej wypłaty. Odpięcie ponownie odsłania60 bez kasowania płatności.
3. Opłacony paragon i późniejsza faktura: dodatkowy dowód do tego samego zakupu,
   zero duplikatu kosztu i zobowiązania. Sama deklaracja paid nie jest uzgodnieniem.
4. Dwa dokumenty i jeden zbiorczy przelew: suma alokacji nie przekracza postingu,
   nawet przy dwóch równoległych żądaniach i retry. Zero nadmiernego rozliczenia.
5. Reguła miesięczna100 i faktura120: po jawnym zastąpieniu w danym occurrence tylko
   120; następny miesiąc reguły bez zmian. Stary confirm nie tworzy drugiej płatności.
6. Termin29/30/31 lub zaległość sprzed miesięcy: prawdziwa data, zaległość raz na dziś,
   nie miesięczna replika. Brak terminu/stanu zapłaty/konta/FX: jawny powód wyłączenia.
7. Stary PDF z OCR widoczny w rejestracji bez reuploadu; error ekstrakcji nie oznacza
   „brak faktury”. Ręczna obsługa działa bez LLM. Nieobsługiwany dokument nie daje expense.
8. SHA duplicate, inne zdjęcie tego samego dokumentu, równoległe zatwierdzenie,
   stale version i próba zmiany/usunięcia linked transaction: bez podwójnych zapisów.
9. PDF/JPEG/PNG/HEIC/HEIF: działający aparat/galeria na telefonie; nieczytelny tekst
   i awaria konwersji mają czytelny komunikat. Oryginał tylko dla właściciela,
   niezmieniony; JPEG pochodny ma poprawną orientację i nie zawiera EXIF lokalizacji.
10. Same kwoty EUR/USD w rejestrze nie wchodzą do sum PLN; link PLN→EUR blokowany.
    Zakup kartą i jej późniejsza spłata nie są dwoma kosztami dokumentu.
11. Testy migracji addytywnej: istniejące dokumenty/księga/inbox niezmienione,
    brak OCR/LLM w migracji; backfill tylko przez osobną jawną akcję.

Testy: backend unit/integration/property dla alokacji i braku duplikacji, konkurencja
PostgreSQL, frontend Vitest oraz E2E z telefonem/viewport, kontrola IDOR/limitów/retry.
Pełny lint/typecheck/test przed commitem implementacji. Produkcyjnych dokumentów nie
wykorzystywać jako publicznych fixtures; fixtures syntetyczne. Osobna zgoda na deploy
i jakiekolwiek realne mutacje istniejących danych użytkownika.

## 12. Kolejność dalszych prac i decyzje pozostawione wykonawcy

Po builder check i akceptacji projektu: osobny szczegółowy plan, następnie małe slice'y:
oryginał+review starego PDF/zdjęcia → rejestr → alokacje → forecast/coverage → regresja.
Q7 pozostaje następny; te same oryginały i mechanizm pochodzenia można później powiązać
z harmonogramami, ale dzisiejszy moduł nie interpretuje wyciągów jako jednej faktury.

Wykonawca wybiera nazwy tabel/endpointów, schematy indeksów i podział komponentów,
wersję audytu oraz szczegóły layoutu zgodne z istniejącym design systemem. Nie może
zmienić zasad rozliczenia, scope PLN, braku automatycznej księgi ani braku integracji.
Projekt nie oznacza zgody na masowy import obecnych dokumentów lub korektę Velo/Q7.

## 13. Builder check

Pierwszy niezależny przegląd wskazał trzy istotne pytania: pierwszeństwo coverage nad
heurystyką, unikalność źródła po archiwizacji i obsługa przetworzonego legacy Inbox.
Rozstrzygnięcia autora dopisano w sekcjach6,7,9 i objęto przedstawionym zakresem.
Ponowny niezależny przegląd:
„nothing important left” — brak istotnych pytań blokujących plan. Brak implementacji.

Po przeglądzie użytkownik zaakceptował projekt oraz zmianę zakresu zdjęć na HEIC/HEIF.
Zmiana wymaga dodatkowego gate walidacji/konwersji obrazów w planie i review przed
wdrożeniem, nie samodzielnej konwersji po stronie użytkownika.
