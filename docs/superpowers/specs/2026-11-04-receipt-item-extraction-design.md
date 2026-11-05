# Etap 4B — odczyt produktów i rabatów z obrazu paragonu

## Status, zgody i źródła wymagań

**Projekt i późniejszy plan zatwierdzone; implementacja4B odebrana LOCAL/OFF (2026-11-05).**
Backendf9fe4c8/UI527e92a;1628backend/493frontend/static/build/141E2E+1expectedskip PASS,
onewhole-review i Importantfix2RED→GREEN, exactsource/dist/migrationproof potwierdzone.
Raport `docs/audits/2026-11-04-receipt-read-local.md`. Nie wykonano realnegoAPI,
aktywacji celu, zmian produkcji, prywatnych zdjęć, mainmerge lub push.

Historyczna granica zgód na etapie projektu: user najpierw
odpowiedział „tak” na przygotowanie projektu, a po przekazaniu c147b85 i pięciu decyzji zakresu
zatwierdził CAŁY projekt kolejnym „tak”. Akceptacja obejmuje opisany wariant na żądanie,
dodatkowycall, anulowanie przeddispatch i nową zgodę na ponowną płatną próbę. Nie uprawnia
jeszcze do kodowania, migracji, realnych wywołańAI/OCR, aktywacji lub produkcji.

Zatwierdzony kierunek4A/4B: pozycjom przypisujemy kategorie z pomocą własnej historii jawnie
wybranego sklepu; bez pomocnej wskazówki dostępna jest pełna lista kategorii z wyszukiwarką.
Osobno zatwierdzane produkty i podział jednej całej istniejącej płatnościPLN. Model interpretuje
źródło, nie oblicza księgi, nie wybiera konta i nie otrzymuje prawa zapisu.

User poprosił o rekomendację następnego kroku i przyjął przygotowanie projektu, który ma
usunąć ręczne przepisywanie produktów, zachować kontrolę sum i oba zatwierdzenia, obejmować
zgodę wysyłki obrazu, limity kosztów i ochronę przed podwójnym odczytem. Szczegółowe wybory
poniżej są **rekomendacjami autora**, nie udawanymi wcześniejszymi decyzjami użytkownika.

Podstawa: `2026-11-04-receipt-item-categorization-design.md`, plan4A3be47c9,
backend09a624d/UI5ea6454/docs c46be4d. Lokalny4A:1506backend/476frontend/static/build/
131E2E+1expectedskipPASS; exactsource/dist/migrationproof zachowane. Nie powtarzać niezmienionego
godzinnego gate tylko dla projektu4B. Nowy plan wykonania powstanie dopiero po akceptacji projektu.

## 1. Cel i pierwsza jednostka wykonania

Własny, aktywny i zatwierdzony paragonPLN otrzymuje propozycję produktów i rabatów na podstawie
**jednego wybranego, już dołączonego obrazu**. Użytkownik ogląda wynik, poprawia niejasności,
wybiera sklep i kategorie, następnie korzysta z istniejącego4A. Nie wolno zakończyć tego kroku
automatycznym zatwierdzeniem produktów lub zastosowaniem podziału płatności.

Pierwsza jednostka4B obejmuje jeden pionowy przepływ: zgoda/uruchomienie → trwałe zadanie
→ ograniczony odczyt → niezmienna propozycja → jawne przeniesienie do nowego szkicu4A.
Jest to projekt wymagający pisemnego projektu, osobnego planu, TDD i lokalnego odbioru.

**Zakres wejścia:** dopuszczone przez istniejący upload obrazyJPEG/PNG/HEIF, także obsługiwany
wariant iPhoneJPEG/HDR. Reużyta bezpieczna normalizacja doJPEG bezEXIF, bez nadpisania oryginału.
Wybrana fotografia ma przedstawiać jeden kompletny paragon; brakujące/obcięte pozycje nie są
uzupełniane z wyobraźni. Długi/nieczytelny obraz daje częściowy wynik i korektę ręczną.

**Poza pierwszym4B:** PDF/tekstOCR, łączenie kilku zdjęć/stron, odczyt wielu paragonów z jednego
obrazu, kadrowanie w edytorze, quantity×price i kalkulacjeVAT, zwroty/ujemne pozycje, walutyFX,
split-tender, nowy katalog produktów, dopasowanie płatności etapu5 oraz przetwarzanie historii batch.
Ręczne4A nadal działa bez obrazu i bez dostępnego modelu.

## 2. Uruchomienie i świadomy koszt — rekomendowany wariant

Rekomendacja: **odczyt na jawne żądanie w paragonie, nie automatycznie po każdym uploadzie**.
Użytkownik wskazuje konkretny załącznik i uruchamia „Odczytaj produkty ze zdjęcia”.
Backend zwraca przed zgodą właścicielski podgląd eksportu: źródło, docelowy provider/model,
zakres danych, bieżącą wersję polityki i dostępny limit. Klient nie podaje modelu, URL ani limitów.
Ostateczny przycisk „Wyślij zdjęcie i odczytaj produkty” zatwierdza ten konkretny eksport.

Wysyłana jest znormalizowana pochodna **całego wybranego obrazu**, więc także widoczne na nim
dane osobowe/NIP/treść nagłówka. Nie należy sugerować, że eksportujemy wyłącznie już wycięte
wiersze. Nie dołączamy katalogu kategorii, historii zakupów, danych konta, postings ani innych
załączników. `store=false`, brak narzędzi, brak dowolnych URL/SQL i bez przekazywania instrukcji
z obrazu jako poleceń aplikacji.

**Ważny kompromis do potwierdzenia:** obecny automatyczny vision odczytuje nagłówek, nie produkty.
Pierwszy odczyt produktów ze zdjęcia już odczytanego nagłówkowo jest zatem **dodatkowym płatnym
wywołaniem**, nie darmowym odzyskaniem brakujących pól. Ten projekt nie obiecuje jednego wspólnego
wywołania nagłówek+produkty dla każdego nowego uploadu. Wspólny przyszły przebieg ograniczyłby
koszt nowych zdjęć, ale rozszerza istniejący automatyczny eksport i sprzęga review nagłówka z4B;
to alternatywa, nie ukryty zakres pierwszego wdrożenia. Nie uruchamiamy kolejnego odczytu nagłówka
w ramach4B. Gotowy wynik produktów wykorzystujemy ponownie bez następnego wywołania.

Zgoda startowa wiążeowner, kanonicznybillID, wybranydocumentID/sourcehash, cel`receipt_items`,
politykęepoch/configfingerprint oraz wersję komunikatu zgody. Zmiana źródła/destynacji/modelu/
promptu/schematu wymaga świeżego podglądu i potwierdzenia; nie wystarcza stary ekran lub zgoda3B.
Wyłączenie funkcji nie może zmienić zgód dla dotychczasowego odczytu nagłówków ani doradcy.

## 3. Jedna intencja, jedno zarezerwowane wysłanie

PostgreSQL przechowuje trwałą intencję, tożsamość wejścia i rezerwację użycia. Redis jest wyłącznie
mechanizmem dostarczenia sygnału; ponowne dostarczenie nie uprawnia do kolejnego HTTP.

- Zapis intencji, zgody, outbox/sygnału oraz audytu jest atomowy i owner-scoped. Replay z tym
  samym kluczem i identycznymbody zwraca to samo zadanie; innybody pod tym kluczem →409.
- Oprócz klucza klienta istnieje serwerowy klucz treści: owner/bill/purpose/sourceSHA i fingerprint
  polityki odczytu (provider/model/prompt/schema/normalizacja). Różne klucze z dwóch kart nie
  tworzą dwóch równoległych odczytów tego samego materiału w tym paragonie. Gotowy, także
  częściowy wynik jest ponownie pokazywany zamiast automatycznego ponowienia.
- Krótka transakcja przedHTTP jeszcze raz sprawdza zgodę, źródło, aktywność i zgodność polityki,
  rezerwuje limity i ustawia trwały znacznikdispatch. SDK i transport mają retrywyłączone.
- Po znacznikudispatch nie ma automatycznego ponowienia wywołania: timeout, restartworkera,
  zgubiona odpowiedź albo wygasły lease nie oznaczają „niewysłane”. Stan „wynik nieznany” jest
  terminalny dla wysyłki tej intencji. Nie obiecujemy niemożliwego exactly-once u providera.
- Awaria przed znacznikidispatch może ponowić bezpieczne przygotowanie bez nowej zgody,
  przy ograniczonej liczbie prób i bez naliczenia dodatkowej rezerwacji.
- Jawne „Odczytaj ponownie” jest nową intencją/generacją, dopiero po zakończeniu poprzedniej,
  z nowym podglądem zgody i ostrzeżeniem o możliwym dodatkowym koszcie. Nie nadpisuje dawnych
  wyników. Kliknięcie „Ponów” po utracie odpowiedzi startowej najpierw odtwarza TĘ SAMĄ intencję,
  a nie uruchamia nową generację.

Nieznany koszt liczy się konserwatywnie jako zużyta rezerwacja. Spóźniony wynik nie może odzyskać
prawa zapisu po zmianieepoch/claimtoken/cancel; aktywne zadanie ma wyraźny stan i kontrolowany
watchdog. UI nie polluje wiecznie technicznie zakończonego zadania.

### Dwa rodzaje niepewności i konkretne akcje

| Sytuacja | Akcja użytkownika | Skutek |
| --- | --- | --- |
| Utracona odpowiedź aplikacji na start; nie znamy jobID | „Sprawdź tę samą próbę” z pierwotnymbody/key | Replay tej samej intencji, bez nowej generacji lub drugiego dispatchu. |
| Znamy jobID; zadanie oczekuje/pracuje | Odczyt statusu | GET bez wysyłki zdjęcia i bez dodatkowego kosztu; żadnego ponawiania POST przy pollingu. |
| Technicznie zakończone`unknown` po znacznikudispatch | „Sprawdź wynik” | GET tej samej terminalnej próby; nie zamienia się w wysłanie. |
| User chce nowej próby po`unknown`/błędzie/częściowym wyniku | Osobne „Odczytaj ponownie — możliwy kolejny koszt” | Nowy exportpreview, osobna zgoda, nowa generacja i nowa rezerwacja; nigdy automatyczny kolejny krok poprzedniej akcji. |
| User ma gotowy wynik i chce go użyć | „Użyj w szkicu” | Kontrolowana komenda importu, bez wywołania modelu. |

Nowa generacja po terminalnymunknown nie daje gwarancji, że provider nie dokończył poprzedniego
żądania i nie naliczył kosztu. Zgoda musi to wyraźnie mówić. Spóźniona odpowiedź starej generacji
nie zastępuje wyniku nowej ani własnego szkicu; po finalnymunknown nie wraca ona do`ready`.

### Anulowanie — rekomendowany zakres pierwszego4B

Rekomendacja autora: użytkownik może **anulować niewysłane zadanie**, także podczas lokalnego
przygotowania obrazu. Komenda właścicielska i idempotentna współdzieli barierę admission/job
z rezerwacjądispatch. Jeśli wygrywa przed znacznikidispatch, stan`cancelled` jest terminalny,
nie maHTTP i rezerwacji płatnej próby; spóźniony lokalnyworker nie odzyskuje claimu.

Jeżeli dispatch wygrał, anulowanie zwraca kontrolowany konflikt „Zdjęcie zostało już przekazane;
nie można cofnąć wysyłki”. Nie pokazujemy fałszywego „anulowano”, nie zwracamy limitu i nie
tworzymy kolejnej próby. Trwający odczyt kończy się według dotychczasowych reguł. Zamknięcie
panelu nie jest anulowaniem. Wyłączenie polityki przez operatora pozostaje osobnym mechanizmem
bezpieczeństwa i nie oznacza cofnięcia już przekazanych bajtów. To propozycja do akceptacji
razem z całym projektem, nie funkcja uznana za wcześniej uzgodnioną.

## 4. Co model może zwrócić i co sprawdza backend

Oddzielny wersjonowany, strictStructuredOutput: typ`receipt|unsupported`, waluta i widoczny
printedtotal (tylko jako dowód), uporządkowane wiersze, rabaty oraz zamknięta lista ostrzeżeń.
Pozycja: lokalny numer/klucz z odpowiedzi, przepisana nazwa, **wydrukowana łączna kwota wiersza**
lubnull, krótki ograniczony fragment źródłowy, informacja o nieczytelności/niejasnej podstawie kwoty.
Rabaty: nazwa, dodatnia przepisana kwota lubnull, ewentualne odniesienie do wydrukowanych wierszy.
Brak categoryID/storeID/accountID, confidence dającego uprawnienia, computednet albo postings.

Model nie mnoży ilości przez cenę, nie oblicza salda, brakującego totalu lub udziałów kuponu.
Kwoty są kanonicznymi tekstami dziesiętnymi, bezfloat/wykładnika/grupowania, maks.2miejsca.
Zerowy produkt dopuszczony; rabat ma dodatnią wartość, znak z druku zachowany w dowodzie jako
rabat, nie ujemny produkt. Backend przelicza do safeBIGINT groszy dokładnie, odrzucając bool,
coercion, overflow i nadmiarową precyzję. Niepoprawny niepusty zapis nie staje się0.

### Rabat już w cenie i rabat osobny

- Kwota wiersza oznacza kwotę przed **oddzielnie przenoszonymi** rabatami, jak w4A.
- Jeżeli wydruk jednoznacznie pokazuje tylko kwotę już po rabacie, przenosimy tę kwotę wiersza,
  a informacji o rabacie już wliczonym nie odejmujemy ponownie. Dowód/ostrzeżenie pozostaje.
- Jeżeli podstawa jest niejasna, propozycja zachowuje przepisany tekst, ale blokuje gotowość
  zatwierdzenia; użytkownik potwierdza/poprawia kwotę i sposób ujęcia. Nie zgadujemy grossnet.
- Osobny rabat z jednoznacznie wydrukowanym pojedynczym powiązaniem może mieć propozycję
  udziału z druku. Użytkownik nadal przegląda je w4A. Globalny kupon bez wydrukowanych udziałów
  pozostaje z pustymi udziałami do ręcznego rozdzielenia, **bez proporcjonalnego algorytmu AI**.
- Częściowo nieczytelny rabat lub wiersz nie znika dla „zgadzającej się sumy”. Oznaczamy brak,
  nie pomijamy go po cichu. Wyjścieucięte/limitwierszy jest jawnie niekompletne.

Backend wyznacza arytmetykę kalkulatorem4A. Różnica choćby1grosz, missingvalues, niewłaściwa
waluta lubunsupportedreceipt blokują zatwierdzenie/aplikację, nie dostęp do ręcznej korekty.
Odczyt może technicznie się udać i jednocześnie wymagać uzupełnienia — to dwa różne statusy.

## 5. Własność danych i połączenie z4A

Documents odpowiada za zachowany oryginał, przebieg odczytu i niezmienną propozycję. Finance
odpowiada za szkic i zatwierdzone produkty/kategorie. Postings pozostają jedynym źródłem raportów.

Istniejące `DocumentProcessingJob.kind` dopuszcza tylko`vision|local_ocr`, a jegoFKrevision oraz
`DocumentExtractionRevision.data` obsługują obecny nagłówek. **Nie dopisujemy produktów do starej
rewizji i nie podszywamy się pod nagłówek, który pokaże obecny reviewrouter.** Rekomendowane
oddzielne modele przebiegu/niemutowalnego wyniku/zgodypolityki/rezerwacji dla celu`receipt_items`,
w domenieDocuments; dokładne nazwy i liczba nowych tabel są zadaniem planującego. Reużywamy
sprawdzone prymitywy odczytu pliku, normalizacji, klienta Responses i ochrony transportu,
nie kopiujemy automatycznych retry istniejącego headerworkera do4B.

Wynik zawiera source/derivativeSHA, wersje prompt/schema/normalizatora, provider/model,
policyepoch/configfingerprint, grant/usage/jobIDs i ostrzeżenia oraz ograniczony payload po
walidacji. Metadane pochodzenia ustawia serwer, nie model. Oryginał i wcześniejsze wyniki nigdy
nie są nadpisywane; rawresponse nie trafia do logów/audytu. Retencja i kontrola właściciela jak
dla prywatnych dokumentów. Zmniejszenie limitów nie unieważnia odczytu historycznego wyniku.

Przeniesienie wyniku jest oddzielną kontrolowaną komendąFinance: owner/source/bill/grant,
aktualny stan paragonu, documentlink, immutableextractionhash i expecteditemstateversion.
Powstaje **nowy szkic4A**, bez zmianycurrentapproved/lastapply, bez zmiany nagłówka/alokacji/księgi.
W szkicu zapisujemy trwałe odniesienie do rewizji ekstrakcji i mapę pochodzenia wierszy/rabatów;
edytowanie nie może fałszywie udawać niezmienionego odczytu. To audytowalny dowód, nie drugi ledger.

- Brak automatycznego scalania z ręcznym szkicem. Przed zastąpieniem zapisanych lub lokalnych
  roboczych pozycji pokazujemy ostrzeżenie; stary zapis zostaje w historii. Konfliktwersji→409,
  propozycja i własne wpisy nie giną. Unikalne nowe klucze wierszy generuje serwer.
- Przenosimy nazwy/kwoty/rabaty/dowody, nie modelowe kategorie. Sklep pozostaje świadomym
  wyborem użytkownika, bez automerge poNIP/nazwie zdjęcia.
- Wskazówki kategorii pobierane przez istniejącą historię4A wybranego sklepu. Propozycja pozostaje
  propozycją, pełna wyszukiwarka działa zawsze; potwierdzenie kategorii nadal przez użytkownika.
- Zmiana wyboru zdjęcia/nowy wynik nie przepisuje samoczynnie żadnego szkicu. Gotowy wynik
  nie zastępuje dirtyformularza przy refetchu. Dawny commandreceipt nie jest bieżącym cache.
- Po akceptacji szkicu użytkownik klika istniejące „Zatwierdź pozycje”, a potem oddzielnie
  „Sprawdź podział płatności”/„Zatwierdź podział”. Import nie jest trzecią zgodą finansową,
  tylko jawnym użyciem propozycji; oba istniejące zatwierdzenia pozostają wymagane.

## 6. Limity i polityka eksportu

Osobna serwerowa aktywacja dla`receipt_items`, domyślniewyłączona, osobnyepoch i fingerprint,
oraz świadoma zgoda konkretnego odczytu. Nie dziedziczymy automatycznie aktywacji odczytu
nagłówków, kategoryzacji3B lub doradcy. Provider/model i parametry pochodzą z backendconfig,
nie są hardkodowane w aplikacji.
Rekomendowane reużycie już skonfigurowanego provideraOpenAI z wersjonowaną konfiguracją celu,
ale zmiana runtime/aktywacja i test prawdziwegoAPI wymagają odrębnej zgody po lokalnym odbiorze.

Gotowy wynik zapisany przed wyłączeniem polityki nadal można obejrzeć i świadomie przenieść
do szkicu po aktualnej walidacji właściciela/źródła/Finance — bez nowego eksportu. Wyłączenie
nie usuwa historycznych dowodów. Inaczej traktujemy pracę jeszcze niezakończoną podczas zmiany
epoch: jej spóźniony wynik nie staje się nowym zaakceptowanym wynikiem pod inną polityką.

Obowiązkowe konfigurowalne limity: oryginalnychbajtów/pikseli, edge/pochodnejJPEG, wejściowego
budżetuobrazu, outputtokens/responsebytes, lines/discounts/shares/namechars, timeout i CPU/RAM
normalizatora, równoległości, kolejkidługości oraz dziennychdispatchów peruser i globalnie.
Limity wyników nie mogą przekraczać storagecaps4A.1600tokenów nagłówka nie zakładamy jako
wystarczających dla produktów: planujący dobierze jawne konserwatywne wartości i testlimitów.

Koszt ograniczamy w pierwszym4B twardą liczbądispatchów i maksymalną wielkością każdego
wejścia/wyjścia; użycie provideratokens zapisujemy, jeżeli dostępne, i odróżniamy od rezerwacji.
UI pokazuje faktyczną znaną wielkość/limit oraz że wywołanie jest płatne. Nie obiecujemy ścisłego
budżetuPLN bez aktualnego cennika/usage — stawki nie są wpisywane na stałe. Operator ustala
aktywację i limity przed wydaniem. Providerusageunknown nie jest kosztem0 ani wolną rezerwacją.

Limit/admissionerror przed wysłaniem nie otwiera automatycznegofallbacku do innegomodelu lubOCR.
Ręczny edytor pozostaje dostępny, a błąd ma bezpieczny kod bez prywatnego tekstu i szczegółówHTTP.

## 7. Aktualność, archiwizacja i współbieżność

Nie trzymamy transakcjiDB podczas normalizacji/pliku/HTTP. Oddzielne krótkie fazy: trwały start,
claim i walidacja, CPU/file, ostateczna rezerwacja/dispatch, HTTP, warunkowy finalny zapis wyniku.
Checkpointy wiążą claimtoken, requesthash, sourcehash oraz wersjepolityki. Wyłączenie/podmiana
destynacji przeddispatch blokuje eksport; po faktycznymHTTP nie da się cofnąć wysłanych bajtów,
ale stare odpowiedzi nie mogą zostać zaakceptowane pod nową polityką ani automatycznie importowane.

Start/wysyłka wymagają istniejącego własnego aktywnego source dołączonego do własnego aktywnego
approvedreceiptPLN. Import ponownie sprawdza aktualne linki, aktywność i semantykę nagłówka.
Zmiana samych produktów podczas odczytu nie niszczy wyniku, lecz blokuje import na starą wersję;
zmiana samej wersji bill przez alokację nie wymaga nowego płatnego odczytu tego samego obrazu.
Zmieniony total/nagłówek nie jest nadpisywany przez model; wymaga świeżego przeglądu zgodności.

Archiwizacja dokumentu źródłowego zachowuje istniejącą zasadę: aktywna praca→kontrolowane409,
nie ukryte skasowanie. `documents.lifecycle._has_active_work` musi uwzględniać nowy przebieg;
terminalne unknown/paused/cancelled nie uruchamiają ponownie eksportu po restore. Archiwizacja/
anulowanie bill lub odłączenie source blokują następnecheckpointy/import; nie usuwają dowodów.
Przy późniejszym ponownym połączeniu pliku nie ma samoczynnego wznowienia/modelcall.

Plan ma jawnie zachować graf istniejących locków: Document/source→bill w attach_source,
ownerallocation→tree→bill→itemstate→store→ledger w4A. **Nie dodawać bill→Document edge**.
Komenda importu najpierw krótko uzyskuje zgodny porządek blokad źródła, dopiero potem istniejące
gatesFinance, i nigdy nie uzyskuje Document po bill; dokumentarchival nie uzyskuje później
financegate. Dokładny wspólny porządek/advisorykeys planujący opisze i udowodni DBbarierami
obu admissions, także z attach_source/unlink/archival, przed implementacją.

## 8. Stany i zachowanie użytkownika

Widoczne rozróżnienie: „oczekuje”, „odczyt w toku”, „wynik gotowy do przejrzenia”, „wynik
częściowy”, „nie udało się”, „wynik wysłania nieznany”, „wstrzymane/nieaktualna polityka”.
„Gotowe do przejrzenia” nie oznacza zatwierdzonych produktów ani opłacenia dokumentu.

Pokazujemy pochodzenie i ostrzeżenia przy polach, sumę po jawnych rabatach i różnicę do
kanonicznego nagłówka; kwoty z obrazu nie poprawiają nagłówka bez osobnej istniejącej operacji.
Nie ma przycisku automatycznego naprawiania różnicy. Proponowane dane ogląda się obok już
istniejącego prywatnego podglądu źródła, bez ponownegoOCR lub wysyłki przy otwieraniu widoku.
Wersjonowane joby/wyniki nie pollują całyczas po stanachterminalnych; błędy nie udają pustych
produktów. Nowa sesja ignoruje stare odpowiedzi; refresh tej samej sesji zachowuje ręczne wpisy.
Nieznana mutacja start/import freezeintencji: te same body/key, brak automatycznychretry,
bez podmiany lokalnego szkicu pod nieobecność użytkownika.

Makieta nie jest wymagana: user wcześniej odrzucił ją dla tego przebiegu. Reużywamy istniejący
edytor4A i podgląd źródeł, bez nowej globalnej strony lub alternatywnego katalogu kategorii.

## 9. Kryteria odbioru i regresje

- Syntetyczne zdjęcie produktów8000/2000 i rabatu1000 z wydrukowanymi udziałami800/200:
  backendpotwierdza7200/1800 i total9000; nigdy model nie jest kalkulatorem księgi.
- Kwota już po rabacie, globalny kuponbezudziałów, nieczytelny fragment, obcięte zdjęcie,
  ±1grosz, gratis0, amountnull, overflow/invalidnumeric, unsupportedPDF/zwrot/FX, limitwierszy/
  outputtruncation. Brak zaokrąglania, proporcji, ciszy o pominiętych pozycjach lub drugiegoodjęcia.
- Doubleclick, dwie karty/różneklucze, ponowne dostarczenieworkera, restartprzed/po znaczniku,
  timeout, spóźniony wynik, quota/contentkeyrace. **Licznik transportu≤1 na jedną generację**,
  a nie tylko sprawdzenie liczby jobów. Unknown po rezerwacji nigdy nie powoduje autoresend.
- Anulowanie vs dispatch w obu admissions: cancelwygrywa→0HTTP/0płatnychrezerwacji;
  dispatchwygrywa→odmowacancel i brak udawania cofniętegoeksportu. Replaystart/GETunknown
  nie tworzą generacji; ponowny płatny odczyt wymaga osobnej akcji/preview/zgody.
- Oba porządki sourcearchive/linkunlink/billheaderchange/policydisable vs start/dispatch/import;
  stateversionkonflikt nie gubi szkicu, joba, użycia ani audytu. Działające blokady źródła nie
  powodują cyklu bill→Document. Dwa równoległeimporty nie nadpisują nowszej ręcznej pracy.
- IDOR źródła/joba/wyniku i import innegobill; prawdziwyCSRF, strictbody i UI sessionfences.
  Model nie może przemycić kategorii/konta/sklepu/toolcall/promptcommands do mutacji.
- Approved4A + odczyt/import nowegoszkicu: stara księga i approvedversion bez zmian; oba
  zatwierdzenia wymagane. Brak nowej płatności/alokacji, niezmienne daty/accountpostings/oryginał.
- Policy3B/header/advisor bez niejawnej zmiany, ręczne4A działa przyAIoff i błędach; stare
  DocumentExtractionRevision/review, imagegainmap i źródła zachowują zgodność.
- Nowa migracja tylko addytywna, brak backfillu/ponownego wysłania dawnych dokumentów;
  lokalny isolatedtestschemarehearsal/retention, fulltests/static/build/E2E375/1440 i dokładnyproof.
  Runtimeoff dla nowego celu na starcie, bez realnegoproviderAPI w testach bez osobnej zgody.

## 10. Co pozostaje do planu i co wymaga decyzji użytkownika

Plan wybierze konkretne nazwy modeli/tabel/endpointów/workerów, ścisłe DTO i schematy z limitami,
minimalne rozszerzenie metadanych pochodzenia4A, wartości konfiguracyjne w storagecaps,
dokładny lockgraph i testy barierowe, małe jednostki TDD i strategię lokalnych dowodów. Nie może
odwrócić zgód, dodać automatycznegoapply lub aktywować providera/produkcji pod pozorem detalu.

Do potwierdzenia przy odbiorze projektu: pierwszy4B na żądanie wybranego obrazu już dołączonego
paragonu, z ewentualnym dodatkowym płatnym odczytem względem istniejącego nagłówka; tylko
jedno zdjęcie, bezPDF/multipage; jawne użycie wyniku zamiast automatycznego scalenia szkicu;
brak automatycznego ponawiania po niepewnej wysyłce. To całościowa propozycja zakresu,
nie uruchomienie ekstrakcji. Anulowanie możliwe tylko przeddispatch; po nim odmowa bez
zwrotu rezerwacji i bez twierdzenia, że cofnięto eksport.

## Builder check i decyzje autora

Readonlybuildercheck `ses_e57fccadfffeJPFI7tUzO5vrP8` zakończony. Trzy pytania:
1. Czy cały proponowany zakres/on-demand/dodatkowycall został zaakceptowany? Przy buildercheck
   jeszcze nie; po przekazaniu c147b85 user potwierdził całość kolejnym„tak”.
2. Czy i do kiedy anulowanie? Autor rekomenduje jawne anulowanie przeddispatch, odmowę po;
   opisano skutki stanów/rezerwacji/audytu i bariery, do potwierdzenia w pełnym zakresie.
3. Co oznacza „Ponów” pounknown? Doprecyzowano osobno utraconą odpowiedź startową, statusGET
   i nową płatną generację z nową zgodą. Żaden status/replay nie staje się automatycznymcall.

Pozostałe detale implementacyjne świadomie zostają do planu; nie wykonano kodu, migracji aniAI.
