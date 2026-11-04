# Etap 4 — produkty paragonu, historia sklepu i zatwierdzany podział

## Status i zgody

Projekt do akceptacji, nie zgoda na implementację. Po lokalnym odbiorze3B user:
„ok, działaj dalej”. Doprecyzowania:

- Najtrudniejsze jest dopasowanie produktów do kategorii; dotąd nie było takiej możliwości.
- Przy skróconej/niejasnej nazwie: „sprawdzaj historię zakupów z tego sklepu i zaproponuj kategorię”.
- Bez pomocnej historii: „wyświetlić wszystkie kategorie”.
- Bez makiety: „ma wyświetlać listę z wyszukiwarka, która zawęża kategorie do wpisywanych nazw”.

Fresh buildercheck `ses_e58a87357ffeRN9tjWrIHZ12UA` zakończony. Pytania dotyczą
potwierdzenia pięciu jawnych decyzji zakresu: ręczne4A przed4B, wybierana tożsamość sklepu,
jawne udziały rabatów, exact/prefixhistory z konfliktami i dwa zatwierdzenia z singlefull
allocationgate. Nie utożsamiać tego wyniku z akceptacją użytkownika. Przed planem trzeba
potwierdzić te propozycje albo zmienić projekt zgodnie z jego odpowiedzią.

To wymagania użytkownika. Poniższe ograniczenie pierwszego slice'a, identyfikacja sklepu,
algorytm dopasowania i szczegóły rabatów to propozycje projektowe autora, nie już uzyskane zgody.
Pełny kontrakt nadrzędny: `2026-11-03-smart-categorization-design.md`.
Baseline3B: backend8a9560f/UI0347e58/docs0cd6bb1;1406backend/456frontend/static/build/
127E2E+1expectedskip PASS, exactsource/dist/migrationproof zachowane. Nie powtarzać
niezmienionego godzinnego baseline tylko po to, aby napisać projekt.

## 1. Cel, kolejność i wielkość pracy

Jednemu produktowi przypisać sensowną kategorię, wykorzystując własne wcześniejsze
zatwierdzenia z tego samego sklepu. Użytkownik widzi propozycję i jej źródło, może ją
zmienić przez przeszukiwaną listę. Dopiero po osobnym sprawdzeniu sum i świadomym
zatwierdzeniu powstaje podział kategorii **istniejącej** płatności. Jedna płatność
pozostaje jedną płatnością; pozycje paragonu nie są drugim ledgerem.

To projekt wieloetapowy. **Pierwsza jednostka wykonania4A** to kompletny lokalny pionowy
slice: ręczne pozycje/rabaty, przechowywanie zatwierdzeń, propozycje z historii sklepu,
wyszukiwarka kategorii oraz preview/apply na już rozliczonej pojedynczej płatnościPLN.
Wspomaga ponowne zakupy bez nowego providera albo nowego płatnego wywołania.

**Świadomy koszt4A:** obecny odczyt dokumentów nie zawiera pozycji. Pierwsze produkty
trzeba wpisać/poprawić ręcznie, korzystając z zachowanego dokumentu/istniejącego tekstu.
Nie udajemy, że obecny OCR rozpoznaje wiersze. **4B** to osobny następny projekt odczytu
pozycji z obrazu/tekstu do tej struktury. Dopiero4A+4B zamykają cały etap4; nie oznaczać
go jako ukończonego po samym edytorze.4B wymaga określenia limitów, zgody eksportu,
wersji ekstrakcji/polityki/usage i jednorazowego dispatchu, nie rozszerzenia istniejącej
zgody3B, która obejmuje tylko opis płatności i nazwy kategorii.

Pierwszeństwo wariantu4A nad od razu pełnym odczytem jest rekomendacją autora:
sprawdzamy model produktów i ludzkie decyzje przed dodaniem kosztownej ekstrakcji.
Alternatywa pełny odczyt+klasyfikacja od razu zwiększa zakres polityki i ryzyko podwójnego
wywołania; alternatywa samej wyszukiwarki nie spełnia wymagania historii/rabatów/podziału.

## 2. Co już istnieje i czego nie duplikować

- `Document` i `DocumentExtractionRevision` przechowują oryginał i historię odczytu
  dokumentu. ReviewFields/VisionFields mają nagłówek/total, **nie produkty**.
- `FinancialDocument` jest kanonicznym dokumentem finansowym; wiele źródeł wskazuje
  ten sam dokument przez `FinancialDocumentSource`. Nie tworzyć pozycji osobno dla
  każdej fotografii ani kopii tego samego dokumentu.
- `DocumentPaymentAllocation` wiąże dokument ze stroną kontową płatności.4A nie tworzy,
  nie poprawia i nie usuwa alokacji. Używa jej tylko jako istniejącego, jawnego powiązania.
- Stage2 `_write_category_parts` i `_record_human_assignment` umożliwiają kontrolowaną
  zmianę wyłącznie kategorii; mają pozostać jedyną drogą tego zapisu.3B supersede helper
  zamyka konkurencyjne pendingproposals po rzeczywistej ludzkiej decyzji.
- `CategoryPicker` już ma pole wyszukiwania i listę drzewa. Rozszerzać/reużyć zamiast
  budować drugi katalog kategorii. Jego obecne zachowanie zachowuje wybraną opcję poza
  filtrem; w edytorze produktów wybór może być pokazany osobno, ale **lista wyników**
  musi naprawdę zawężać się do wyszukiwanej nazwy/ścieżki.

Nie zmieniać schematów ekstraktorów, promptów, politykiVision/Advisor ani jobów3B w4A.
Bez nowych usług, bibliotekruntime, Supabase lub bazy pozaPostgreSQL.

## 3. Przebieg i dwa oddzielne zatwierdzenia

1. Na istniejącym paragonie użytkownik otwiera „Produkty i kategorie”.4A dotyczy dokumentu
   finansowego `kind=receipt`, aktywnego, zatwierdzonego iPLN; inne dokumenty dostają jasne
   wyjaśnienie, nie pozornie pustą listę. Brak źródłowego obrazu nie blokuje ręcznej pracy,
   o ile istnieje taki własny dokument finansowy; nie wymyślać strony uploadu w tym slice.
2. Wybiera/potwierdza sklep i wpisuje nazwy oraz łączne kwoty wierszy (nie cenę jednostkową
   razy ilość). Ilość/jednostka/cena mogą być pominięte;4A nie wyprowadza z nich kwoty.
   Roboczy zapis może być niekompletny. Oryginalnego dokumentu/tekstu nie nadpisujemy.
3. Dla konkretnego produktu żąda propozycji z historii sklepu. To bounded odczytDB,
   nie LLM ani ponownyOCR. Odpowiedź pokazuje wcześniejszą nazwę, kategorię, datę i
   źródłowy paragon. Propozycja nie jest automatycznie przyjęta.
4. Każdy wiersz ma listę wszystkich dopuszczalnych własnych kategorii wydatków i
   wyszukiwarkę filtrującą podczas pisania, także gdy istnieje propozycja. Puste zapytanie
   pokazuje pełną listę; brak wyników daje „Brak pasujących kategorii”, nie wybór ukryty
   ani utworzenie nowej kategorii. Zmiana nazwy produktu/sklepu unieważnia jego sugestię.
5. Po sprawdzeniu produktów/rabatów i ich kategorii użytkownik zatwierdza **pozycje**.
   Powstaje niezmienna wersja ludzkiego rozpoznania, dostępna jako przyszły materiał
   historyczny; ten krok sam nie zmienia księgi, budżetu ani statusu zapłaty.
6. Osobny „Sprawdź podział płatności” pokazuje stare kategorie → nowe agregaty wraz
   z produktami/rabatami, całkowitą kwotą i wyraźną informacją, co nie zostanie zmienione.
   Osobne „Zatwierdź podział” zapisuje kategorie na istniejącej płatności.

Ręczny zapis produktów ma sens także bez dopasowanej płatności. Wtedy krok6 jest
zablokowany z przyczyną; można użyć istniejącego rozliczenia dokumentu, a następnie
wrócić do nowego preview. Nie dodajemy automatycznego wyszukiwania lub tworzenia płatności
(to etap5). Nowa kategoria wymaga oddzielnego istniejącego formularza i powrotu do wyboru;
nie tworzymy jej przez sugestię ani razem z podziałem.

## 4. Sklep i historia produktów — zakres uprawnień, brak zgadywania

„Ten sam sklep” oznacza własną, jawnie wybraną tożsamość sklepu, nie fuzzy porównanie
supplier_name. Proponowany mały model `ReceiptStore`: owner, UUID, nazwa wyświetlana,
wersja i active. Przy pierwszym paragonie użytkownik tworzy sklep lub wybiera istniejący;
przy kolejnych wybiera go z własnej listy. Nazwa dostawcy/NIP mogą pomóc w wyborze, ale
nie powodują automatycznego połączenia sieci, oddziałów lub właścicieli.4A nie dodaje
aliasów/merge sklepów, globalnego katalogu produktów ani translacji skrótów przez LLM.

Historia pochodzi wyłącznie z własnych, **ludzko zatwierdzonych**, bieżących wersji
pozycji **innych** paragonów w tym sklepie. Robocze, zastąpione, odrzucone, archiwalne,
anulowane dokumenty i nieaktywne sklepy/kategorie nie są materiałem do sugestii.
Czytanie tych zatwierdzeń jest zgodą na wskazówkę, nie zgodą na przeliczenie/mutację
dawnych płatności, odczyt niezwiązanych kont albo batchprocessing historii.

W4A proponowany deterministyczny algorytm, z wersją w dowodzie sugestii:

- Normalizacja wyłącznieNFKC/casefold/białe znaki; zachować cyfry, rozmiary i warianty
  („MLEKO2%” nie staje się „MLEKO3,2%”). Oryginalna nazwa pozostaje widoczna.
- Najpierw dokładna znormalizowana nazwa. Gdy jej brak, słabsza wskazówka po prefiksie
  pełnej nazwy (jedna nazwa jest początkiem drugiej), tylko dla konfigurowalnej minimalnej
  długości. Żadnego podobieństwa sklepu do kategorii całego koszyka.
- Identyczne nazwy z różnymi zatwierdzonymi kategoriami pokazują konflikt i możliwości;
  nie uznajemy ostatniej kategorii za pewnik. Słabsze/prefiksowe dopasowanie jest jawnie
  opisane jako przybliżone. Potwierdzenie nadal perwiersz; brak autozapisu lub nowej reguły3A.
- Bounded zapytania z indeksami owner/store/normalizedname i limitami wyników/wierszy.
  Ograniczony rezultat ma `has_more`/oznaczenie niepełnej historii; nie deklaruje, że
  dopasowania nie istnieją. W razie braku/dwuznaczności/limitu/błędu lista kategorii
  pozostaje dostępna. Limity są serwerowe i konfigurowalne, nie przyjmowane od klienta.

Wskazówka historyczna nie jest źródłem kwot/discountów ani autoryzacją kategorii. Jeżeli
źródło/kategoria zmieniło się podczas review, zapis wymaga ponownego sprawdzenia; przyjęta
sugestia zapisuje dowód, którą wersję użytkownik widział. Historia nie dubluje tabelą
„uczenia”: wynika z kanonicznych zatwierdzonych pozycji i ich wersji.

## 5. Kwoty, rabaty i kontrola sum

Każda kwota przechowywana jakoBIGINT groszy, limit doMAX_SAFE_MINOR dlaAPI/JS. Input
frontendowy przeliczać dokładnie, bezfloat; backendStrictInt odrzuca bool/string/coercion.

- Wiersz ma `amount_minor`: łączna kwota tego wiersza **przed rabatami wpisanymi osobno
  poniżej**. Rabatu już uwzględnionego w kwocie wiersza nie wpisuje się ponownie.
  Nazwa, kwota, kolejność i pochodzeniemanual pozostają w zatwierdzonej wersji.
- Osobny rabat ma nazwę i dodatnią kwotę oraz jawne udziały przypisane do pozycji.
  Rabat pojedynczego produktu ma jeden udział; ogólny kupon może mieć wiele.
- Backend sprawdza `sum(udziały rabatu)=kwota rabatu`, brak obcych/powtórzonychwierszy,
  i `netto_wiersza=amount_minor-sum(udziały)>=0`. Nie zaokrągla, nie rozdziela rabatu
  proporcjonalnie bez decyzji i nie dopisuje „różnicy” do ostatniej pozycji/kategorii.
- `sum(netto_wierszy)=FinancialDocument.total_minor`. Każdy niezerowy wiersz wymaga
  aktywnej własnej kategorii wydatku i aktywnych rodziców. Bez kategorii technicznej
  „nieskategoryzowane”; zerowy/free wiersz może pozostać bez kategorii, nie uczy historii.
- Kategorie agregowane backendowo: np.8000spożywka+2000chemia, rabat1000 z jawnym
  podziałem800/200 →7200spożywka+1800chemia, razem9000. Nie tworzyć osobnego ujemnego
  expense ani income z rabatu. Każda część księgi>0; zerowe agregaty pomijane.
- Nieczytelna/brakująca kwota lub różnica choćby1grosz blokuje zatwierdzenie pozycji i
  apply, ale nie zapis roboczy. Pokazać sumę i różnicę. Użytkownik może skorygować dane
  jawnie; korekta total nagłówka to osobny istniejący proces, nie efekt edytora produktów.
- Zwroty, ujemne produkty, wielowalutowość/FX, rata, split-tender/częściowe opłacenie,
  napiwki nieznanej wysokości i rabaty wymagające wyliczenia podatku poza4A. Kaucję/opłatę
  można ująć jako jawnie nazwaną dodatnią pozycję z kategorią, jeśli zgadza się z dokumentem;
  wydanej reszty nie traktować jako produktu.

## 6. Przechowywanie i cykle życia

Finance jest właścicielem zatwierdzonych pozycji/kategorii i sklepu; Documents pozostaje
właścicielem oryginałów/ekstrakcji. Zatwierdzone pozycje nie są kolejną prognozą, płatnością
ani równoległym źródłem raportów. **Tylko postings zasilają finanse**.

Model konceptualny (dokładne nazwy/podział modułów zostają do planu):

- Własny `ReceiptStore` oraz unikalny stan pozycji perFinancialDocument: owner, version,
  currentapprovedrevision, currentdraftrevision. Brak duplikowania total/currency jako
  konkurencyjnego nagłówka; niezmienna wersja może przechować snapshot nagłówka jako dowód.
- Kolejne niezmienne rewizje zestawu: dokument, sklep/version, wersja nagłówka/hash,
  autor/czas, poprzedniarewizja, rodzajdraft/approved, dowód decyzji/receipt. Poprawka
  tworzy nową rewizję; nie nadpisuje starej ani jej provenance. Osobny wskaźnik current
  daje jednoznaczne najnowsze zatwierdzenie i porządek wersji.
- Znormalizowane wiersze + rabaty + udziały w tabelachPostgreSQL z jawnymiFK, pozycją,
  identyfikatorem w obrębie rewizji i checkami kwot. Każdy udział odnosi się do wiersza
  **tej samej** rewizji i właściciela (walidacja i klucze złożone lub równoważne constraints).
- Po zmianie nagłówka/store/category nie przepisywać rewizji w tle. Aktualność jest
  wyliczana z bieżącego fingerprintu i jawna dla użytkownika. Nowy draft nie usuwa
  poprzedniego zatwierdzenia, ale blokuje apply dopóki jest niezatwierdzony; historia
  wykorzystuje nadal ostatnią ważną zatwierdzoną wersję, z wyłączeniem bieżącego paragonu.
- Nowa approvedrewizja zastępuje starą jako źródło przyszłych wskazówek. Nie przepisuje
  historycznych decyzji ani podziału już zastosowanego w księdze. Pokazać rozbieżność
  „pozycje zmienione od ostatniego podziału”; nowe apply znów wymaga preview+akceptacji.
- Category/storeFK RESTRICT dla dowodów; deletionendpoint zwraca kontrolowane409,
  archiwizacja jest alternatywą. Bez cascade usuwającego dowody. Rewizje wymagają
  owner-scope przy każdym powiązaniu, nawet gdyUUID już istnieje wFK.

## 7. Dopuszczenie podziału istniejącej płatności

4A stosuje podział wyłącznie, gdy:

- Własny aktywny zatwierdzony paragonPLN, aktualna approvedrewizja produktów i brak
  nowszego draftu; suma/wybory/store i wszystkie dowody są nadal aktualne.
- Dokładnie jedna alokacja tego dokumentu wskazuje własną stronę kontowąPLN i ma kwotę
  równą total dokumentu **oraz całej płatności**. Ta strona kontowa nie jest przydzielona
  żadnemu innemu dokumentowi. Wieloalokacja/część płatności/wiele dokumentów→blokada,
  nie arbitralny podział reszty. Sprawdzane również obce/nieprawidłowe linki, nie tylko
  poprawny ownerfilter w wynikuGET.
- Płatność przechodzi istniejące Stage2eligibility, w tym źródło manual/document_payment,
  bezActualmapping/loan/FX/pending, poprawny bilans i układ kategorii. Nie poszerzać
  allowlistyActual ani historycznychimportów w tym slice.

Istniejące ręczne lub approved_llm kategorie **nie są zmieniane w tle**. Jawny preview
starego podziału i świadome humanapply mogą je zastąpić tak jak obecny ręczny edytor2.
Sama sugestia/akceptacja pozycji nie ma tej władzy. Brak płatności albo niepełna alokacja
nie odbiera możliwości zapisania i sprawdzenia produktów, tylko blokuje apply.

Previewtoken wiąże owner, bill/version/fingerprint, store/version, approvedrevision/hash,
pełne drzewo dopuszczalnych kategorii, alokacje i kompletny ledgercontextStage3Bv3,
zagregowane parts i istniejący Stage2preview. Apply odczytuje wszystko ponownie pod
lockami, porównuje wersje/hash i wylicza kwoty samodzielnie. Klient nie może podmienić
parts, pochodzenia, sklepu ani kwot przez sam token; requeststrict i confirmed musi byćtrue.

Apply używa istniejących prywatnych writerów i zapisuje stan source=manual oraz
origin=manual;4A nie dodaje originapproved_llm dla historii produktowej. Immutable
FinanceCommandReceipt zawiera receipt-revisionID/hash, mapę wiersz→kategoria→netto,
udziały rabatów, store, przed/po, osobę/czas i aktualny ledgerhash. Audyt i receipt,
metadata wyniku oraz księga atomowo; awaria audytu→rollbackwszystkiego. Pending3Bproposals
superseded jak po innym humanapply. Dowód pochodzenia paragonowego nie wymaga nowej
kolumny ledgerorigin; odsyłacz „ostatni zastosowany podział” wynika z właścicielskich
receipts i porównania bieżącego snapshotu, nie z drugiego rejestru kwot.

Bez zmian accountpostingID/kolumn, transactionID/kwoty/source/dat, oryginału, alokacji,
coverage i paymentcount. Categorypostings mogą zmienić liczbę jak wStage2; nadal min2
i suma=0. Nigdy nowego expense, zmiany daty zakupu lub potwierdzenia zapłaty przy apply.

## 8. Polecenia, współbieżność i bezpieczeństwo

Osobne owner-scoped granice: GETcontext/history, zapiszrobocze, zatwierdźpozycje,
previewpodziału i applypodziału.4A nie dodaje mutującegoGET, batchapply ani endpointuSQL.
Zapisy wersjonowane i receipt-backed z Idempotency-Key; replay exactbody zwraca historyczny
wynik, nie instaluje go jako aktualny stan; changedbody409. Brak automatycznych retry.
Niepewny zapis→ten sam body/key. Freshauth/CSRF/rate limits z istniejącej aplikacji.

Wspólna kolejność mutacji: command-idempotencylock → ownerallocationlock → categorytree
lock → document/bill/itemstate i właściwe ledgerrowlocks w stałym porządku. Dopasować
istniejące mutacje nagłówka/lifecycle/store oraz apply tak, aby nie powstało nowe
bill↔ledger/category↔revision odwrócenie locków. DDL/historyqueries nie potrzebują
globalnego policylocku;4A nie ma providera ani sieci pod lockiem. Szczegółowy graf
locków/interfejs writerów musi być częścią planu, nie doraźnym wyborem przy kodowaniu.

Preview może brać krótkie locki w transakcji, ale nie zapisuje statusu/receipt ani niczego
nie rezerwuje na czas ludzkiego przeglądu. Kategorie/store/archive/approval/manualapply/
unlink lub nowy draft po preview unieważniają decyzję. Race zawsze prowadzi do serialnego
wyniku albo409, nie częściowo nowej rewizji i starej księgi. Dane query muszą zostać
odświeżone po locku (nie stare obiektyidentitymap).

Frontend przechowuje draft i intencję z sessionVersion, pendingbody i key. Same-session
authrefresh ich nie kasuje; logout/login i późne odpowiedzi nie mieszają użytkowników.
Odświeżenie listy nie zastępuje podglądu/draftu bez decyzji. Zmiana kategorii lub sklepu
kasuje stary preview. Błędy403/409/5xx są różne od pustej historii. Zapis starszego wyniku
powoduje odświeżenie kanonicznychGET, nie podmianę cache na staryreceipt.

Oryginalne produkty/nazwy są niezaufanym tekstem; renderować escaped, bezHTML/SQL/logowania
zawartości paragonu do telemetry. Historia wyłącznie tego właściciela i sklepu. Bounded
read produkthistory tylko po celowym żądaniu; nie skan całej bazy przy każdym renderze
lub każdym znaku wyszukiwarki kategorii (filtrowanie własnego drzewa lokalne).

## 9. Weryfikacja i granice odbioru

Wymagany TDD/manual-proof: firstpurchase→pełnalista; filtrowanie fragmentu nazwy/ścieżki
i klawiatura; historia sameowner/samestore/exact/prefix/conflict/incomplete i brak
przecieków otherstore/foreign/draft/replaced/archived. Przyjęcie sugestii nic nie zapisuje
do księgi. Po błędzie historii ręczny wybór nadal działa.

Kwoty: exactgrosze, produkt0, discounts1000→800/200, kilka rabatów tego samego produktu,
przekroczenie ceny, doubleincludeddiscount, niedopasowanytotal±1, unknownamount, strict
typy i limity. Backend liczy, nie klient. Atomicdraft/approve/replay/auditrollback.

Apply: dokładnie jeden dokument/jedna cała płatność; blokady częściowej/wielodokumentowej/
FX/Actual/loan/pending i historymanual bez świadomego apply. Obie kolejności wyścigów:
draft/approve/categoryarchive/storechange/billtotal/unlink/manualapply i2równoległeapply.
Zachować accountposting wszystkie kolumny/ID, daty, alokacje, sumzero i paymentcount.

UI: loading/error/empty, przeszukiwana pełna lista, zachowany draft, źródło sugestii,
konflikty, difference i odrębne dwa zatwierdzenia; unknownretry ten sam key/body,
sesja/refetch/busyguard,375/1440/keyboard/focus/main-areaAxe/nooverflow.

Migracja addytywna po243aa1d9461c: żadnego backfillu ani zapisu starych kwot/kategorii/
originów/produktów. Jedno autogenerate w nowym ownedtestschema, usunąć niepowiązanydrift.
Retencja starych kolumn/indeksów/danych, emptydowngrade/reupgrade i populateddowngrade
odmawia pod lockami przedDDL. Zachować audit/receipt. Tylko lokalnyfinanse_test.

Jedno końcowe niezależne whole-review plus pełne backend/frontend/lint/types/build/E2E,
source/dist/migrationhashproof. Odbiór4A jawnie **bez automatycznego odczytu pozycji**,
bezAIcalls/OCR/provideractivation/produkcji/historybatch/mainmerge/push. Velo/Q7 nietknięte.

## 10. Do decyzji autora planu; następny krok

Nazwy tabel/modułów/DTO/routes, konkretne bounded limity i indeksy, układ modułów/testów
oraz realizacja wyszukiwarki w istniejącymCategoryPicker należą do buildera, przy powyższym
kontrakcie i bez nowych runtimepackages. Nie należą do niego zmiana zakresu4A/4B,
domyślnegooff, autoapprove, globalnego sklepu, wyliczanie rabatów za użytkownika lub
zniesienie ochrony importów.

Projekt przeszedł jeden fresh buildercheck; pięć zaproponowanych decyzji zakresu zostaje
przekazanych userowi razem do akceptacji. Dopiero jego akceptacja prowadzi do osobnego
szczegółowego planu4A; plan także przedstawiamy do
akceptacji przed kodem/testami/migracją. Realny odczyt pozycji4B ma odrębny projekt,
zgody/koszty/dispatch i odbiór. Żadne zdanie tego projektu nie uruchamia przetwarzania.
