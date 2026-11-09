# Import wyciągów bankowych i harmonogramów kredytowych

Data: 2026-11-08.
Status: pełny opis działania zaakceptowany w rozmowie („tak”) po prezentacji zakresu;
trwa przygotowanie planów implementacji. Użytkownik zrezygnował z makiet.
Brak zgody na produkcyjną migrację, import danych lub deploy; wykonanie planów wymaga handoffu.

## 1. Intencja i ustalenia użytkownika

Użytkownik chce samodzielnie dodawać nowe wyciągi w aplikacji, zamiast przekazywać
je agentowi do operatorskiego importu. Potrzebuje także importu harmonogramu kredytu
na przyszłość, w tym nowego harmonogramu po nadpłacie lub zmianie oprocentowania.

Użytkownik jawnie wskazał **Velo, ING i Revolut, bez Citi**. Zatwierdził formaty:

| Rodzina | Pierwsze obsługiwane źródła |
| --- | --- |
| Velo | oryginalny tekstowy PDF rachunku i karty |
| ING | oryginalny nieszyfrowany tekstowy PDF rachunku bieżącego Direct; oszczędnościowe odłożone decyzją użytkownika 2026-11-09 |
| Revolut | CSV rachunków PLN, EUR i USD |
| Harmonogram kredytu | tekstowy PDF z terminami, kapitałem, odsetkami i opłatami; pierwszy zweryfikowany układ Velo |

CSV Velo/ING oraz PDF Revolut wymagają później próbek i odrębnego rozszerzenia.
Zmiana zakresu 2026-11-09: po wykryciu szyfrowania wszystkich pięciu próbek ING
oszczędnościowego użytkownik wybrał „Odłóż oszczędnościowe”. Pozostały importer
powstaje dalej; oszczędnościowe jest jawnie nieobsługiwane do otrzymania odpowiedniej
nieszyfrowanej próbki i osobnego rozszerzenia parsera. Nie odszyfrowujemy oryginałów.
Zdjęcia, skany, Excel i dowolny nierozpoznany układ nie są importerem pierwszej wersji.
Nie obiecujemy poprawnego odczytu każdego PDF tylko na podstawie rozszerzenia pliku.
Nowy układ harmonogramu może być zapisany jako źródło, ale nie jest zatwierdzany
do planu, dopóki parser i kontrole nie potwierdzą pełnej tabeli. Harmonogramy PLN;
rozszerzenie kredytów na inne waluty nie jest ukrytym skutkiem importu wyciągów.

## 2. Nienaruszalne granice

- PostgreSQL jest źródłem prawdy. Oryginał pliku, wynik odczytu, decyzja importu,
  transakcja księgi, wyciąg karty i harmonogram kredytu mają oddzielne cykle życia.
- Upload i przygotowanie propozycji nigdy nie tworzą transakcji/postings/sald.
- Każda operacja finansowa przechodzi istniejące serwisy domeny finance:
  min. dwa postings, BIGINT w najmniejszej jednostce, suma base PLN = 0.
- Transfer własny i spłata karty/kredytu nie są nowym przychodem/wykorzystanym kosztem.
  Opłata bankowa jest osobnym kosztem. Przewalutowanie zachowuje obie rzeczywiste kwoty.
- Nie nadpisujemy istniejących kwot, dat, sald, powiązań, mapowań Actual lub odsetek.
  Różnica z bankiem nie tworzy automatycznej korekty wyrównującej.
- Bez automatycznego zakładania kont; użytkownik wskazuje własne istniejące konta.
- LLM nie rozpoznaje tożsamości wpłat, nie oblicza sum ani kursów i nie wykonuje SQL.
  Pierwsza wersja parserów jest deterministyczna; bez wysyłania dokumentów do AI.
- Każdy odczyt i zapis owner-scoped, autoryzowany, audytowany, z ochroną CSRF,
  przed równoległą zmianą i ponowieniem tego samego zatwierdzenia.
- Brak integracji z Google Drive, bankami lub wysyłania przelewów. Pliki dodaje się
  bezpośrednio w aplikacji. Specyfikacja nie jest zgodą na import istniejącej historii.

## 3. Stan bazowy i materiał do odbioru

Wdrożenie 7801ba5 ma prywatne oryginały dokumentów, wersje ekstrakcji, worker,
polecenia z potwierdzeniami idempotencji, serwisy księgi i przewalutowań, ręczne
wyciągi kart, umowy/raty kredytów oraz jawne linki do płatności. Nie ma importera
wyciągów; upload faktury/paragonu nie może go udawać.

Prywatne próbki w `/opt/finanse/webapp/maintenance/statements-review-20261028/`:
Velo rachunek i karta, ING Direct/oszczędnościowe oraz Revolut CSV w trzech walutach.
Zawierają nakładające się okresy, duplikaty plików oraz rzeczywiście powtórzone
wiersze wydruku karty. Powtórzenie tekstu nie dowodzi duplikatu operacji.
Harmonogramy Velo z różnych dat są dostępne w tym pakiecie; nowszy oryginał również
w `/opt/finanse/webapp/maintenance/velo-q7-setup-20261108/originals/`.
Oryginały, identyfikatory, transakcje i osobowe dane źródeł nie trafiają do Git.

Istniejąca umowa Q7 ma 59 rat i jedną powiązaną spłatę. Pierwsze wdrożenie importera
nie może ich przeklasyfikować, nadpisać, ponownie utworzyć ani automatycznie zaimportować.

## 4. Obieg i decyzje użytkownika — proponowane zasady autora

Jeden obszar **Finanse → Import**, rozdzielający „Wyciągi bankowe” i
„Harmonogramy kredytów”. Przycisk importu harmonogramu jest też dostępny przy umowie;
przycisk importu wyciągu przy rachunku/karcie kieruje do tego samego obiegu.
To oddzielny obieg od faktur/paragonów, bez zmiany ich dotychczasowego działania.

1. Dodanie jednego lub kilku plików; odrębny wynik dla każdego pliku, bez utraty
   poprawnie zapisanych źródeł przy błędzie innego pliku.
2. Odczyt w workerze i walidacja układu, pełności, walut, okresu i sum kontrolnych.
3. Wskazanie rachunku dla każdego rozpoznanego konta/waluty. Zapamiętane mapowanie
   jest propozycją do sprawdzenia, nie uprawnieniem do automatycznego księgowania.
4. Weryfikacja propozycji: nowe, już powiązane, możliwe duplikaty, transfery/FX,
   opłaty, nierozstrzygnięte. Zachowany dostęp do źródłowej strony/wiersza.
5. Jawne wybranie kompletnych poprawnych operacji lub grup i zatwierdzenie ich listy.
   Można pozostawić nierozstrzygnięte pozycje do później; żadne nie znikają bez śladu.
6. Potwierdzenie wyniku z liczbą nowych transakcji, połączeń ze starymi operacjami,
   nadal otwartych pozycji oraz stanem uzgodnienia. Każda operacja ma ślad źródłowy.

Wybrane grupy są zapisywane atomowo. Przelew/FX/opłata wymagające wspólnego rozliczenia
nie mogą zostać zatwierdzone w połowie. Reszta pliku pozostaje przygotowana.
Nowe pozycje są księgowane jako wykonane tylko dla jednoznacznie zaksięgowanych
źródeł; pending/reverted/cancelled/nieznany stan nie staje się posted.

## 5. Parsowanie i kwoty

- Rodziny parserów: Velo rachunek PDF, Velo karta PDF, ING Direct PDF,
  ING oszczędnościowe PDF, Revolut CSV i Velo harmonogram PDF. Układ i wersja parsera
  zapisane z wynikiem; rozpoznanie banku i rodzaju dokumentu nie jest dowolnym promptem.
- Rozpoznajemy nagłówki oraz stopki, przeniesienia wierszy przez stronę, rachunek,
  walutę, okres, datę księgowania i datę operacji/waluty, znaki i separatory kwot.
  Zachowujemy surowe dane i pochodzenie pól. Żadnych float ani gubienia groszy.
- W CSV zachowujemy wszystkie źródłowe kolumny, stany i znaczniki czasu z ich strefą
  lub jawną informacją o braku strefy. Brak strefy nie jest automatycznie UTC.
  Daty lokalne finansów stosują dotychczasową strefę aplikacji; źródło pozostaje dostępne.
- Kontrole wewnętrzne pliku: liczba/kompletność wierszy, otwarcie + obroty = zamknięcie,
  salda po kolejnych operacjach, sumy wpływów/obciążeń, gdy źródło je udostępnia.
  Dla brakującego salda lub bankowej referencji zapisujemy brak, nie zero.
- Jeśli format nie daje odpowiednich sum kontrolnych, kompletność weryfikujemy
  pozostałymi udokumentowanymi polami; brakujące kontrole są widoczne i nie udają PASS.
  Niekompletna tabela lub sprzeczne sumy blokują zatwierdzenie tego źródła.
- Powtórzone sekcje karty Velo wymagają reguł konkretnego układu i zgodności sum.
  Nie ma globalnego usuwania identycznych napisów; niejednoznaczność blokuje odczyt.
- Klasyfikację konto/kategoria/opis można poprawić. Kwoty i daty odczytane z banku
  nie są swobodnie poprawianym formularzem pozwalającym obejść błędy parsera.
  Ponowienie poprawionego parsera tworzy nową wersję propozycji z jawnym porównaniem.

## 6. Duplikaty i istniejąca historia

SHA-256 oryginału rozpoznaje identyczny plik per właściciel. Ponowne dodanie otwiera
istniejący import/źródło, nie tworzy ponownie operacji; nie ujawnia cudzego pliku.
Dokument wcześniej dodany do ogólnych Dokumentów może być wskazanym źródłem importu,
bez drugiej kopii bajtów i bez traktowania go jako faktury.

Tożsamość operacji:
- mocna bankowa referencja w kontekście bank/rachunek/waluta, jeżeli jest dostępna;
- wcześniej zatwierdzone powiązanie źródła z transakcją;
- w pozostałych przypadkach pełne znormalizowane pola, saldo/sekwencja i kontekst
  okresu służą wykrywaniu kandydatów, nie bezwarunkowemu pomijaniu po hashu.

Identyczna data, opis i kwota nie wystarczają do pominięcia wpisu. Prawdziwe powtórne
zakupy muszą zachować liczność i własne pochodzenie. Nakładający się eksport Revolut
nie może ani dodać znanych wierszy drugi raz, ani usunąć dwóch rzeczywistych zakupów.

Stare dane z Actual nie mają automatycznie bankowej tożsamości. Propozycja dopasowania
do nich wymaga jawnego potwierdzenia, a konflikt kwoty/waluty/konta nie może być
zamaskowany jako poprawne uzgodnienie. Rozbieżne daty są widoczne z obu źródeł;
nie zmieniamy daty starej transakcji tylko dlatego, że bank pokazuje datę księgowania.
Decyzje: powiąż z właściwą istniejącą operacją, zarejestruj odrębną lub pozostaw otwartą.
Powiązanie dodaje pochodzenie, nie nadpisuje transakcji ani istniejących linków.

Obsługujemy zarówno nowe okresy, jak i pliki historyczne nakładające się na Actual.
To nie jest zgoda na automatyczne ponowne importowanie dawnych danych. Dla starego
okresu obowiązuje ten sam review i jawne rozstrzygnięcie każdej niepewnej tożsamości;
nie ustawiamy tajnej daty granicznej pomijającej stare wiersze lub kasującej historię.

Commit ponownie sprawdza tożsamość, wersję decyzji i bieżącą księgę pod blokadami.
Równoległe zatwierdzenie tego samego wpisu/grupy i ponowienie HTTP nie tworzą duplikatu.

## 7. Transfery, waluty i uzgodnienie

- Własne konta mapujemy jawnie; zgodne referencje pomagają zaproponować parę.
  Dopasowanie wyłącznie po kwocie lub końcówce rachunku nie wystarcza.
- Jedna operacja transferu może mieć dwa dowody z różnych wyciągów. Drugi dowód
  jest połączeniem z już istniejącym transferem, nie nową transakcją.
- Gdy brakuje wyciągu drugiej strony, użytkownik może wskazać drugie własne konto
  i zatwierdzić kompletny transfer na podstawie jednoznacznych danych pierwszej strony.
  Nieznany odbiorca/niepewna własność pozostaje nierozstrzygnięta, bez zgadywania kosztu.
- Bankowe słowo „przelew” nie znaczy automatycznie transferu między własnymi kontami.
  Użytkownik może jawnie sklasyfikować taki wiersz jako płatność zewnętrzną (expense
  z kategorią), zewnętrzny wpływ (income), własny transfer (drugie własne konto) albo
  odłożyć decyzję. Nie wymuszamy dowodu tożsamości zewnętrznego odbiorcy do zwykłego
  wydatku, ale zapisujemy decyzję i pochodzenie; nie ma domyślnego transfer→expense.
- FX wymaga rzeczywistych dwóch kwot/walut i identyfikowalnego połączenia nóg.
  Używamy istniejącego serwisu przewalutowań; brak nogi/kursu uniemożliwia zatwierdzenie
  jako FX. Nie zastępujemy rzeczywistego kursu dzisiejszym kursem referencyjnym.
- Dla zwykłej operacji EUR/USD wymagana jest zatwierdzona wycena base PLN według
  istniejącej polityki kursowej i zapisanym źródłem. Brak kursu oznacza „uzupełnij”,
  nie losowy kurs, kurs1 lub pominięcie base_amount_pln. PLN/EUR/USD nie są sumowane.
- Proponowana polityka pierwszej wersji korzysta z istniejącego NbpRateProvider:
  kurs tabeli A dla daty księgowania operacji, a dla weekendu istniejący fallback
  do wcześniejszego dnia publikacji. Brak notowania w innym dniu/błąd dostawcy blokuje
  automatyczną propozycję; użytkownik może podać jawny kurs ręczny zgodny z istniejącą
  walidacją. W preview są utrwalone wartość, waluta, data notowania, źródło i wycena
  wyliczona Decimal z istniejącym ROUND_HALF_EVEN. Commit nie pobiera nowego kursu
  pod blokadami i nie podmienia zatwierdzonej wyceny. Nie jest to polityka podatkowa.
  Operacji już zapisanej/Actual nie wyceniamy ponownie; dodajemy jedynie pochodzenie.
  Zagraniczny zakup rozliczony przez bank na rachunku PLN pozostaje postingiem PLN
  w rzeczywiście pobranej kwocie; waluta sprzedawcy jest dodatkową informacją źródła.
- Jawna bankowa opłata jest osobnym kosztem, ze wskazaną kategorią; parser rozróżnia,
  czy kwota źródłowa już zawiera fee, aby nie obciążyć rachunku drugi raz.
  Przewalutowanie z fee nie staje się prostym transferem z ukrytą różnicą.
- Wpłata na kartę lub kredyt z własnego rachunku jest transferem. Planowane odsetki
  harmonogramu nie są naliczonym kosztem. Wyciąg kredytu nie zmienia starych podziałów.

Źródłowe kontrole pliku i uzgodnienie z księgą są oddzielne. Niezgodne otwarcie
księgi, luka okresu lub wcześniejszy import pokazują ostrzeżenie/otwarte uzgodnienie.
Po jawnym potwierdzeniu tego stanu można zatwierdzić niezależnie sprawdzone nowe
pozycje; nie tworzymy salda otwarcia/korekty i nie oznaczamy całości jako uzgodnionej.
Wyciąg karty może również dodać jawnie zatwierdzony rekord okresu/minimum/terminu.
Bankowa definicja zadłużenia (bieżące vs całość z kapitałem niewymagalnym) musi być
ustalona; nie utożsamiamy nieznanego nagłówka z zadłużeniem aplikacji.

Rekord wyciągu karty tworzymy tylko po osobnym jawnym potwierdzeniu okresu, terminu,
minimum oraz etykiety/znaczenia zadłużenia odpowiadającego istniejącemu kontraktowi
CardStatement. Całkowity dług, saldo cyklu i kapitał przyszłych rat są oddzielnymi
polami źródła, nie zamiennikami. Niejednoznaczny nagłówek blokuje tworzenie tego
rekordu; nie blokuje niezależnie poprawnej tabeli operacji, jeżeli jej własne kontrole
przeszły. Rekord wyciągu nie jest automatyczną korektą salda ani potwierdzeniem spłaty.

### Minimalne kontrole kwalifikujące format

Każdy parser ma wersjonowany kontrakt wymaganych pól; brak poniższych danych to
nieobsługiwany/niekompletny układ, nie przycisk omijania kontroli:
- Velo rachunek i ING: rozpoznany rachunek/waluta/okres, każdy kompletny wiersz,
  salda otwarcia/zamknięcia i publikowane sumy stron WN/MA. Wszystkie dostępne
  kontrole muszą się zgadzać; publikowane salda po wierszu są również sprawdzane.
- Velo karta: poprawny okres i identyfikacja karty, kompletna tabela operacji
  z oznaczeniem sekcji oraz uzgodniona bankowa relacja otwarcia/obrotów/zamknięcia.
  Gdy wydruk powiela sekcję, rozstrzygnięcie wymaga sprawdzonej reguły tego układu;
  użytkownik nie może usunąć wierszy tylko po to, by dopasować sumę.
- Revolut: komplet dziesięciu kolumn wspieranego eksportu, poprawne typy/stany,
  daty, waluta, kwoty/fee i pełny odczyt każdego rekordu. Dla zaksięgowanych pozycji
  wymagana sprawdzalna sekwencja opublikowanych sald z udokumentowaną semantyką fee.
  Saldo przed pierwszym wierszem może być wyprowadzone z niego i musi być oznaczone
  jako wyprowadzone, nie niezależnie potwierdzone. Brak salda w pending nie uprawnia
  do księgowania pending; brak wymaganych sald completed blokuje tę wersję parsera.
- Harmonogram: pełna identyfikowalna tabela, okres/wersja i waluta, daty/numery,
  kapitał/odsetki/opłaty z ich sumą; publikowane salda rat i sumy zbiorcze muszą się
  zgadzać. Brak kolumny fee może oznaczać zero tylko, gdy kontrakt układu dokumentu
  jednoznacznie potwierdza ratę złożoną wyłącznie z kapitału i odsetek.

Dokładne wzorce etykiet i równania kontroli każdego układu wykonawca ustala na
prywatnych próbkach i zamraża w fixture kontraktowych, zanim parser otrzyma ready.
Niedostępność odpowiedniego pola w kolejnym formacie nie rozszerza automatycznie
kontraktu tej rodziny ani nie osłabia obowiązkowych kontroli.

## 8. Import harmonogramu i kolejne wersje

Harmonogram jest planem, nie wyciągiem wykonanych operacji. Osobny typ importu nie
tworzy postingów, kosztów, salda długu, nadpłat, prognoz ani oznaczeń „zapłacono”.
Wybranie istniejącego kredytu nie tworzy drugiej umowy. Przy pierwszym harmonogramie
nowego kredytu użytkownik może jawnie dodać umowę, wskazując dwa istniejące konta PLN;
brak identyfikacji umowy/konta w PDF wymaga sprawdzenia mapowania przez użytkownika.
Wspólne wzorce numeru umowy/daty nie pozwalają użyć cudzego kredytu.

Odczyt zachowuje numerację bankową, datę wersji/obowiązywania, liczbę rat, terminy,
kapitał/odsetki/opłaty, bankowe saldo po racie, jeśli występuje. Kwota raty = suma
składowych. Kwoty nieujemne, terminy i numery jednoznaczne; kapitał przechodzi między
ratami zgodnie z tabelą i kończy się zgodnie ze źródłem (nie zawsze zero, np. rata balonowa).
Brakującej opłaty nie wymyślamy; zero wymaga potwierdzonego znaczenia kolumn źródła.
Nie wyliczamy oprocentowania ani nowego harmonogramu z samej wartości raty.

Każdy zatwierdzony harmonogram ma niezmienną wersję i oryginał. Przed aktywacją
nowego widać porównanie dat i składowych oraz datę, od której zmiana obowiązuje.
Powtórzenie tego samego źródła/układu i decyzji nie dodaje drugiego planu.

Proponowane bezpieczne zasady aktualizacji:
1. Wszystkie powiązane raty (także częściowo opłacone), ich UUID i linki pozostają
   niezmienione. Nie wolno przenosić wpłaty na inną ratę po samym numerze bankowym.
2. Jeżeli nowy PDF obejmuje taką ratę, wymagamy jednoznacznej zgodności daty i trzech
   składowych; zapisujemy nowy dowód tej samej raty, nie drugą ratę.
3. Jeśli rata jest pominięta w nowym PDF, zachowujemy ją w historii/pokryciu i pokazujemy
   zakres nowego planu. Nie uznajemy jej za spłaconą ani anulowaną z samego pominięcia.
4. Niepowiązane stare raty zastępujemy wyłącznie w jawnym, ciągłym przyszłym zakresie
   nowej wersji od potwierdzonej daty obowiązywania. Są archiwizowane, nie usuwane.
   Przeszłe niepokryte raty pozostają otwarte; nie wolno ich ukryć nowym PDF.
   „Przyszłe” ustalamy względem daty aktywacji w strefie aplikacji, nie daty uploadu
   ani samej daty dokumentu. Harmonogram wystawiony wcześniej nadal można odczytać:
   historyczne wiersze są porównaniem/dowodem, a automatyczne zastąpienie zaczyna się
   nie wcześniej niż dzisiaj i nie wcześniej niż bankowa data obowiązywania.
5. Konflikt z powiązaną ratą, niepełny zakres lub brak daty granicznej blokuje aktywację
   całej nowej wersji. Oryginał/draft pozostają dostępne; bez automatycznego odpinania,
   dzielenia lub rozksięgowania starych płatności. Rozwiązanie historycznych konfliktów
   jest oddzielną czynnością, nie boczną furtką importera.

Bank może renumerować raty od1 po nadpłacie. Numer bankowy jest pochodzeniem w ramach
wersji, nie tożsamością raty. Wewnętrzne ID/numery istniejących rat nie są przepisywane.
Widok czynny obejmuje zachowaną historię oraz raty obowiązującego zakresu, bez drugiego
sumowania wycofanych przyszłych rat. Dane obu wersji są dostępne do porównania.
Istniejące API bez wersji zachowuje dotychczasowe działanie do czasu jawnego importu;
ręczne wpisy traktujemy jako bazową wersję. Nie generujemy nowych wersji w produkcji
przy samej migracji i nie dotykamy istniejącej konfiguracji Q7.

## 9. Architektura i trwałość — decyzje autora do dopracowania w planie

Pozostaje modularny monolit z siedmioma domenami. To moduł wewnątrz **finance**, nie
ósma domena ani osobny serwis. **documents** przechowuje oryginały i bezpiecznie
udostępnia tekst/plik; **finance** posiada bankowy wynik, decyzje i commit do księgi.
**audit** zapisuje pochodzenie i decyzje. Używamy istniejącego workera i kolejki.

Minimalne pojęcia relacyjne (nazwy techniczne do planu):
- ImportBatch: właściciel, typ wyciąg/harmonogram, stan przygotowania, wersja decyzji.
- ImportSource: prywatny Document, hash, rodzina/wersja parsera, okres/konto/waluta,
  podsumowania i status walidacji. CSV ma dedykowany dopuszczony upload importera;
  nie rozszerzamy przyjmowania CSV jako faktury/paragonu.
- ExtractionRevision/SourceRow: niezmienny wynik konkretnej próby odczytu, oryginalne
  pola i lokalizacja strony/wiersza, znormalizowane kwoty/daty/stany. JSONB w PostgreSQL
  dla surowych pól jest dopuszczalne; pliki JSON nie są stanem procesu ani księgą.
- ImportDecision/Group: wersjonowane mapowanie kont/kategorii, powiązania istniejące,
  decyzje o odrębności/odłożeniu, grupy transfer/FX/fee i wskazany kurs.
- ImportPostingLink: pochodzenie do konkretnej transakcji/postingu, bez prawa do
  nadpisania księgi; wiele źródeł dla tego samego transferu bez nowego transferu.
- ImportCommit: niezmienny receipt action/key/request_hash, wyniki i audyt.
- LoanScheduleRevision oraz pochodzenie wierszy: proponowana/aktywna/zastąpiona wersja,
  źródło, okres obowiązywania, powiązanie z niezmiennymi ID rat. Mechanizm wycofania
  niepowiązanych przyszłych rat musi być jawny i uwzględniony we wszystkich sumach/API.

Unikalności i FK pilnują ownera, źródła, numeracji w wersji i powtórek poleceń.
Nie dodajemy globalnej unikalności samego amount/date/description lub surowego row_hash.
Implementacja wybierze szczegółowy schemat wersji/membership, pod warunkiem zachowania
istniejących UUID, linków i jednoznacznej projekcji aktywnych rat opisanej wyżej.

Oddzielne stany: odczyt queued/processing/ready/error/unsupported; walidacja
passed/needs_review/blocked; commit not_committed/partial/committed. Udany odczyt nie
oznacza pełnego uzgodnienia. Worker nie wywołuje mutującego serwisu księgi.
Ponowienie odczytu nie kasuje zatwierdzonych decyzji/źródeł; zablokowany draft ma wersję.
Śmierć workera, retry, restart serwera i przeładowanie strony nie gubią stanu importu.

Commit jest jednym kontrolowanym poleceniem: autoryzacja→walidacja→blokady→ponowna
kontrola wersji/tożsamości→serwisy domenowe→provenance+audit+receipt→jedna transakcja DB.
Powtórzony klucz z inną treścią daje konflikt; z tą samą zwraca poprzedni wynik.
Niejasny wynik po utracie połączenia jest sprawdzany odczytem receipt, nie kolejnym
tworzeniem finansów. Zmiana kategorii po commit to zwykła kontrolowana edycja księgi,
nie ponowne uruchomienie importu. Brak masowego rollbacku/importu kasującego historię.

Wersja podglądu jest związana z ownerem, Document ID i SHA bajtów, konkretną rewizją
ekstrakcji/wersją parsera, wersją mapowań/decyzji, grupami oraz zatwierdzoną wyceną.
Serwer wylicza request_hash kanonicznej treści, a nie ufa hashom od klienta.
Zmiana któregokolwiek składnika unieważnia preview i wymaga nowego potwierdzenia.
Samo równe SHA nie jest dowodem wyboru właściwego rachunku ani tożsamości transakcji.
Referencje do oryginału mają RESTRICT: ogólne usunięcie Document użytego w imporcie
jest blokowane; nie może skasować draftu/receiptu lub pochodzenia z księgi. Archiwizacja
importu jest oddzielną operacją bez usunięcia dowodów. Uszkodzony/brakujący oryginał
przed commit blokuje zapis i nie zostaje zastąpiony nowym plikiem pod tym samym ID.

## 10. Bezpieczeństwo, zgodność i regresje

- Nie ufamy MIME, nazwie pliku, treści PDF/CSV ani nazwom kolumn. Ograniczenia
  rozmiaru/stron/wierszy/czasu/pamięci konfigurowalne, bez nowych nieograniczonych zadań.
- Bounded lokalna ekstrakcja tekstowych PDF bez OCR; uszkodzony, zaszyfrowany lub
  obrazowy dokument ma czytelny błąd i brak mutacji. Nie przechowujemy haseł do PDF.
- CSV jest tekstem do parsowania, nie arkuszem do wykonania. Poprawne BOM, cytowanie,
  separatory i kodowanie dla wspieranego układu; formuły/HTML są tekstem, nigdy kodem.
- Prywatne pliki, limitowany owner-scoped streaming, brak nowych publicznych URL,
  logowania bankowych danych lub sekretów i brak oryginałów w repo/E2E snapshots.
- Mapowania kont i receipts izolowane między użytkownikami; nieaktywny lub cudzy
  rachunek nie przyjmuje importu. Archiwizacja draftu nie usuwa dowodów zatwierdzenia.
- Addytywne migracje i kontrola zachowania wszystkich istniejących danych. Brak
  automatycznego backfillu, importowania plików lub przepisywania harmonogramów Q7.
  Produkcyjny upgrade/deploy oraz jakiekolwiek korekty starych danych wymagają osobnej zgody.

## 11. Odbiór i granice następnego planu

Plan implementacji ma podzielić zakres na pionowe, testowalne etapy: fundament
trwałego importu, kolejne rodziny wyciągów, wspólne uzgodnienie/commit, harmonogramy
i regresje/odbiór. Wszystkie wymienione rodziny należą do wydania; „na przyszłość”
oznacza możliwość samodzielnego dodania kolejnego harmonogramu, nie pusty przycisk.

Wymagany odbiór:
- rzeczywiste prywatne próbki każdego wspieranego układu + syntetyczne/anonymizowane
  fixtures bez danych osobowych; PDF→wiersze i sumy są sprawdzane, nie mockowane;
- Velo powtórzone sekcje oraz poprawne podobne zakupy; ING okres wielomiesięczny;
  Revolut overlap CSV, fee, stany i trzy waluty; puste/ucięte/błędne źródła;
- upload/odczyt/mapowanie/retry nie zmieniają księgi; preview i commit mają ten sam
  request_hash/wersję; revalidation wykrywa zmianę księgi między nimi;
- podwójny upload, inna nazwa tego samego pliku, retry/double click/race, konflikt
  payloadu, dwa dowody transferu oraz brak auto-pomijania prawdziwych równych zakupów;
- transfer != income/expense, FX zachowuje kwoty, fee nie księguje się podwójnie,
  brak kursu blokuje zapis; każda nowa transakcja zachowuje ledger invariants;
- zgodne i rozbieżne otwarcie źródła vs księga, luki okresu, częściowy commit
  z wyjaśnioną listą pozostałych grup; brak automatycznej korekty;
- Q7 i ogólny kredyt: pierwszy import, ponowienie, nowsza wersja, renumeracja,
  powiązana/partial/niepokryta przeszła rata, konflikt wersji i brak podwójnych sum;
- zachowanie existing accounts/postings/transactions/Actual mappings/rat/linków
  po migracji i przed zatwierdzeniem jakiegokolwiek rzeczywistego importu;
- izolacja ownerów, prywatne pliki/CSV, limity, dostępność, mobile/desktop, oba motywy,
  poprawne komunikaty częściowych błędów i wznowienie po restarcie;
- pytest backend, vitest frontend, E2E, lint/typecheck oraz testy prawdziwej migracji
  wyłącznie na osobnym zatwierdzonym środowisku testowym, nigdy na produkcji.

Nie wchodzą: Citi, dowolne kolejne banki/układy bez próbek, OCR/skany/zdjęcia/Excel,
automatyczne księgowanie lub korekty, synchronizacja bankowa/Drive, KSeF/JPK/podatki,
rozksięgowanie historycznych rat Q7 ani przebudowa wszystkich prognoz finansowych.

## 12. Zgoda i decyzje pozostawione autorowi

Banki/formaty i cały przedstawiony opis działania zostały zaakceptowane w rozmowie
(„tak” po pytaniu „Zatwierdzasz całość, żebym przygotował plan implementacji?”).
Zatwierdzenie obejmuje per-grupa commit, jawne mapowania, brak nadpisywania historii,
reguły FX i wersji rat; nie oznacza zgody na wdrożenie lub import danych.
Autor proponuje powyższe bezpieczne zachowania; nie zapisujemy ich jako wcześniejszych
ustaleń użytkownika. Nazwy tabel/API, konkretna biblioteka parsera, indeksy, kolejność
blokad, mechanika aktywnej projekcji rat oraz kolejność etapów należą do wykonawcy
i muszą spełnić opisane invariants, testy i istniejące granice domen.

Builder check: ses_e4410b324ffensLNrwj20uc3gf. Pełną akceptację uzyskano;
doprecyzowano jawnie zakres historyczny, istniejącą politykę NBP,
związanie preview ze źródłami, zewnętrzne płatności, minimalne kontrole formatów
i oddzielną zgodę na metadane wyciągu karty. Szczegółowe mechanizmy techniczne
są decyzjami autora, nie twierdzeniem, że użytkownik sam wybrał ich implementację.
