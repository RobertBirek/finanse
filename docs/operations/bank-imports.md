# Import wyciągów i harmonogramów kredytowych

Stan: etap A odebrany lokalnie (pełne bramki i review z naprawami), A11ad1b53f.
Dowody zarchiwizowane, własne kontenery testowe i wolumen usunięte.
Nie jest to zgoda na wdrożenie, migrację produkcji ani import rzeczywistych danych.
Etap B odebrany lokalnie: 2300 backend, 617 frontend i183 E2E PASS po poprawkach
końcowego review. Jeden desktopowy wariant testu mobile-only ma oczekiwany skip.
Nie używaj tego statusu jako zgody na realny import. Zasoby testowe etapu B są
odrębne od wcześniejszych zasobów etapu A. Własne PG/runner/wolumen B zostały usunięte
po weryfikacji; dowody zarchiwizowano bez plików prywatnych. Gałąź i worktree pozostały.

## Obsługiwane źródła

- Velo: tekstowy PDF rachunku i karty, rozpoznane wersje układu.
- ING Direct: tekstowy PDF rozpoznanego układu. ING oszczędnościowe odłożone
  do dostarczenia nieszyfrowanej próbki; nie deklarujemy jego obsługi.
- Revolut: CSV jednego rachunku/waluty PLN, EUR lub USD, rozpoznany zestaw kolumn.
  Zestawienie mieszające waluty jest odrzucane; użyj odrębnych eksportów.
- Harmonogram kredytu Velo: tekstowy PDF PLN, z rozpoznanym nagłówkiem, datą
  obowiązywania i kompletną tabelą pozostałych rat. Nie importuj go jako wyciągu.
- Nie obsługujemy Citi, skanów, OCR, AI, odszyfrowywania PDF ani pobierania z Drive.
  Nieznany układ, brakujące strony i wymagane niezgodne kontrole blokują zapis.

## Przebieg

1. W **Finanse → Import** dodaj pliki albo w Dokumentach wybierz **Użyj do importu**.
   Link z rachunku lub karty jedynie sugeruje mapowanie; serwer sprawdza właściciela,
   walutę i zgodność rachunku. Każdy plik ma własny wynik. Duplikat źródła otwiera
   istniejący import; nie tworzy ponownie wierszy lub transakcji.
2. Odczyt jest trwałym zadaniem PostgreSQL. Redis służy do dostarczenia zadania,
   a lease/fencing i ograniczone retry pozwalają wznowić pracę po przerwaniu workera.
   **Dodanie pliku i odczyt nie księgują operacji.** Źródło pozostaje prywatne.
3. Sprawdź oryginał, kontrole, daty księgowania/operacji, walutę i każdy wiersz.
   Surowych kwot, dat, opłat ani stanu bankowego nie można naprawiać formularzem.
4. Zaznacz wiersz lub komplet nóg i wybierz jawną decyzję:
   - **Nowa operacja**: wydatek, wpływ, zwrot, własny transfer lub wymiana walut;
   - **Powiąż**: sprawdź istniejącą płatność. Podobieństwo kwoty/daty jest tylko
     sugestią. Actual pozostaje niezmienione; różnica dat wymaga potwierdzenia;
   - **Pozostaw otwarte**: bez księgowania; można wrócić do decyzji później.
5. Zapisz decyzje i wybierz kompletne grupy do **Przygotuj podgląd**. Sprawdź
   liczbę nowych operacji/powiązań, obie nogi transferu/FX, opłaty oraz zamrożone
   kursy. **Podgląd nadal nie księguje.** PLN/EUR/USD pokazujemy oddzielnie.
6. Dopiero po zaznaczeniu potwierdzenia wybierz **Zatwierdź wybrane grupy**.
   Grupy, postings, dowody, audyt i trwały wynik zapisują się atomowo. Commit
   korzysta z zamrożonej wyceny, nie pobiera nowych kursów ani postingów od klienta.
   Pozostałe wiersze mogą nadal wymagać decyzji — częściowy import nie znaczy „gotowe”.

## Saldo otwarcia a błąd źródła

Kontrola źródła porównuje sumy/liczniki/obroty i rzeczywiste bankowe salda. Jej błąd
jest blokadą, której nie omija zgoda użytkownika. Różnica między bankowym saldem
otwarcia a dotychczasową księgą oznacza **otwarte uzgodnienie**, a nie błąd wyciągu.
Można ją świadomie przyjąć bez automatycznej korekty salda i bez usunięcia historii.

## Transfery, FX i opłaty

- Własny transfer, wypłata/wpłata gotówki i spłata własnej karty nie są przychodem
  lub wydatkiem. Wybierz istniejący drugi rachunek; nie twórz dodatkowego zadłużenia.
- FX zachowuje obie rzeczywiste kwoty i rzeczywisty kurs. Brakująca noga blokuje
  grupę. EUR↔USD ma wspólną wycenę PLN i jawne źródła kursów; bez fikcyjnego konta PLN.
- Opłata jest osobnym kosztem w atomowej grupie, zwrot opłaty/zakupu odwraca koszt,
  nie tworzy dodatkowego dochodu. Ruch netto banku nie jest obciążany dwukrotnie.
- Dla walut obcych podgląd zamraża historyczny NBP albo jawny kurs ręczny. Brak
  kursu lub niezgodna precyzja blokuje zapis; LLM nie ustala wyceny ani salda.

## Karty i ponowny odczyt

Nagłówek karty jest osobnym rekordem okresu, minimum i terminu, po porównaniu
z oryginałem i potwierdzeniu znaczenia długu bieżącego cyklu. Nie jest wpisem
zadłużenia do księgi ani automatycznym rozliczeniem rat lub spłat.

**Ponów odczyt** tworzy trwały zamiar przygotowania źródła. Odczyt źródła z dowodami
nie zastępuje rewizji bieżącej: kandydat jest tylko do porównania. Potwierdzenie
porównania jest związane z konkretną rewizją; serwer nadal blokuje różnice pól
i kontroli. Stare powiązania i dowody nigdy nie są automatycznie przepinane.

## Niepewny wynik i przerwana sesja

Po utracie odpowiedzi nie zakładaj ani sukcesu, ani porażki. UI pyta o trwały wynik
tej samej komendy, zachowuje klucz zamiaru i blokuje tworzenie nowej decyzji.
Użyj **Sprawdź zapisany wynik** lub ponów to samo zatwierdzenie. Odczyt potwierdzenia
działa również, gdy inny odczyt widzi już nowszą wersję importu. Brak wyniku GET404
nie dowodzi, że trwająca komenda nie zakończy się zapisem.

Klucz oczekującej komendy jest utrzymywany w pamięci aktualnego widoku, nie
w localStorage. Po zamknięciu widoku/logowaniu zacznij od odczytu bieżącego importu
i jego rozliczonych grup; nie odtwarzaj nowego zatwierdzenia w ciemno. Przy nadal
niejasnym stanie potrzebna jest kontrola trwałego receipt przez uprawnionego operatora.
Zmiana użytkownika odcina późne odpowiedzi i nie przenosi zamiarów do nowej sesji.

## Harmonogram kredytu: wybór, porównanie, aktywacja

1. W **Ustawienia → Finanse → Kredyty i pożyczki** otwórz umowę i wybierz
   **Importuj harmonogram**. Możesz też wejść w **Finanse → Import** i zmienić rodzaj
   na **Harmonogram kredytu**. Link z umowy tylko wstępnie wybiera kredyt.
2. Dodaj tekstowy PDF Velo. Upload i odczyt przez worker nie dodają rat do aktywnego
   planu ani płatności do księgi. Duplikat tych samych bajtów prowadzi do istniejącego
   importu. Nie tworzy ponownie wersji ani rat.
3. Sprawdź oryginał i wybierz istniejącą umowę. Dla nowej umowy podaj nazwę oraz
   dwa różne, aktywne konta PLN: długu i spłaty. Konta karty nie są dozwolone.
   Nowa umowa powstaje dopiero przy aktywacji. Potwierdź przypisanie do kredytu.
4. Przygotuj podgląd. Sprawdź datę bankową oraz granicę zmiany planu:
   późniejszą z daty bankowej i bieżącego dnia aplikacji. Podgląd rozdziela zgodne
   raty, nowe raty, wycofywany przyszły ogon i zachowaną historię.
5. Zgodność oznacza tę samą datę i składniki: kapitał, odsetki, opłaty.
   Numer bankowy dotyczy konkretnej wersji i może zaczynać się ponownie od 1.
   Aplikacja zachowuje UUID oraz numery wewnętrzne istniejących rat i ich spłaty.
6. Przeszłe niepokryte raty pozostają w historii. Brak zgodności przeszłej
   niepowiązanej raty blokuje aktywację; aplikacja nie oznaczy jej jako zapłaconej.
   Pominięta lub zmieniona przyszła rata z powiązaną spłatą także blokuje całość.
   Nie odpinaj płatności tylko po to, żeby ominąć konflikt. Sprawdź źródło i historię.
7. Zaznacz potwierdzenie aktualizacji planu i wybierz **Aktywuj harmonogram**.
   Aplikacja wycofa tylko niepowiązane przyszłe raty zastąpionego zakresu. Zachowa
   ich historię, ale nie doliczy ich ponownie do aktywnych sum.

Aktywacja nie zmienia salda długu, nie księguje odsetek lub prowizji i nie tworzy
nadpłaty ani statusu „zapłacona”. Pokrycie rat nadal pochodzi z istniejących przelewów
i jawnych powiązań. Do dodania rzeczywistej spłaty służy księga i operacje płatności.

### Blokady i ponowny podgląd

- Brak daty obowiązywania, nieznany układ, niepełny ogon lub niezgodne kontrole
  blokują aktywację. Nie wpisuj brakującej daty ręcznie ani nie używaj daty pisma.
  Uzyskaj kompletny dokument bankowy. Importer nie korzysta z OCR lub AI.
- Zmiana dnia, źródła, kont, rat lub powiązań po podglądzie daje konflikt HTTP409.
  Przygotuj i sprawdź nowy podgląd; poprzednie potwierdzenie nie upoważnia do zapisu.
- Ponowny odczyt istniejącego źródła pozostaje kandydatem. W polu **Odczyt
  harmonogramu** wybierz kandydata, porównaj obie tabele z oryginałem i zaznacz
  potwierdzenie porównania. Podgląd wiąże wybór z konkretną rewizją, datą i kontami.
  Aplikacja nie nadpisuje poprzedniego odczytu. Jeśli zmieniły się fakty bankowe,
  sprawdź zwykły diff i potwierdź nową wersję planu. Nie omijaj konfliktów spłat.
- Gdy nowy odczyt zachowuje fakty już zatwierdzonego źródła, podgląd pokaże
  **Odczyt zgodny z zapisaną wersją** i poprzedni receipt. Nie tworzy kolejnego planu,
  rat ani nowej aktywacji. Zmiana wersji parsera lub fizycznego położenia wierszy
  nie wystarcza do utworzenia nowego harmonogramu.
- Przy niepewnym wyniku użyj **Sprawdź potwierdzenie** lub **Ponów tę samą decyzję**.
  Aplikacja zachowuje ten sam klucz komendy. Receipt po udanym zapisie działa także
  następnego dnia. Nowy zamiar dla starego podglądu wymaga nowego potwierdzenia.
- Klucz komendy żyje w pamięci widoku. Po zamknięciu widoku otwórz istniejący import:
  odczyt źródła pokaże zapisany receipt i wersję bez znajomości klucza. Ten sam plik
  prowadzi do istniejącego źródła i potwierdzenia; nie aktywuj go ponownie.
  W razie niejasności operator powinien sprawdzić trwały receipt i historię umowy.

### Plan ręczny i historia wersji

Przed pierwszą aktywacją możesz edytować ręczne raty. Przy aktywacji aplikacja
zapisuje ich bazę historyczną, bez backfillu innych kredytów. Gdy umowa ma wersję
bankową, aktualizuj plan następnym PDF zamiast zmieniać raty w miejscu. Nadal możesz
kontrolować powiązania płatności zgodnie z regułami domenowymi.

Otwórz **Historia wersji harmonogramu** przy umowie. Wybierz wersję aktywną,
zastąpioną lub bazę ręczną. Tabela pokazuje snapshot tej wersji, nie bieżące saldo.
Przy wersji bankowej pobierz przypisany oryginał. Baza ręczna nie ma bankowego PDF.
Nie sumuj wersji historycznych z aktywnym planem.

## Ochrona i cofanie

Oryginały źródłowe nie są nadpisywane. Źródeł importu nie wolno archiwizować,
usuwać ani kierować do OCR/AI zwykłą ścieżką dokumentów. Archiwizacja samego
batcha nie usuwa źródeł lub transakcji. Dowód chroni tożsamość płatności przed
usunięciem, zmianą dat/stanu lub waluty rachunku; opis i dozwolona kategoryzacja
pozostają edytowalne przez kontrolowane serwisy.

Nie ma automatycznego rollbacku importu ani masowego usuwania transakcji.
Korekta finansowa wymaga osobnej decyzji domenowej. Migracja stagingu jest addytywna;
downgrade po zapisaniu danych importu odmawia usunięcia tabel. Nie uruchamiaj go
jako sposobu „cofnięcia importu”.

Migracja wersji harmonogramów również odmawia downgrade, gdy istnieje choć jedna
wersja lub membership. Operator musi oddzielnie uzgodnić rollback aplikacji i schematu;
nie kasuj wersji, receiptów, powiązań lub oryginałów w celu obejścia retencji.

## Weryfikacja operatorska (bez produkcyjnych mutacji)

Syntetyczne PDF/CSV przechodzą upload HTTP → worker z ograniczonym parserem →
utrwalona rewizja → decyzja → preview → commit → nowa sesja DB. Testy obejmują
overlap z jawnym linkiem, replay, uszkodzone źródła, owner-scope, księgę i retencję.
Prawdziwe prywatne próbki wolno badać tylko read-only; poza Git przechowujemy hash,
układ, liczbę wierszy i kontrole, nie kopie danych bankowych w repo/E2E/testowej DB.
Pełne dowody lokalnego odbioru: `docs/audits/2026-11-08-bank-imports-local.md`.
Harmonogramy i końcowy odbiór B: `docs/audits/2026-11-08-loan-schedule-import-local.md`.
