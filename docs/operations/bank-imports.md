# Import wyciągów bankowych

Stan: etap A zweryfikowany lokalnie (pełne bramki i review z naprawami);
zapis odbioru i cleanup są domykane.
Nie jest to zgoda na wdrożenie, migrację produkcji ani import rzeczywistych danych.
Importer harmonogramów kredytowych (etap B) nie jest jeszcze dostępny.

## Obsługiwane źródła

- Velo: tekstowy PDF rachunku i karty, rozpoznane wersje układu.
- ING Direct: tekstowy PDF rozpoznanego układu. ING oszczędnościowe odłożone
  do dostarczenia nieszyfrowanej próbki; nie deklarujemy jego obsługi.
- Revolut: CSV jednego rachunku/waluty PLN, EUR lub USD, rozpoznany zestaw kolumn.
  Zestawienie mieszające waluty jest odrzucane; użyj odrębnych eksportów.
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

## Weryfikacja operatorska (bez produkcyjnych mutacji)

Syntetyczne PDF/CSV przechodzą upload HTTP → worker z ograniczonym parserem →
utrwalona rewizja → decyzja → preview → commit → nowa sesja DB. Testy obejmują
overlap z jawnym linkiem, replay, uszkodzone źródła, owner-scope, księgę i retencję.
Prawdziwe prywatne próbki wolno badać tylko read-only; poza Git przechowujemy hash,
układ, liczbę wierszy i kontrole, nie kopie danych bankowych w repo/E2E/testowej DB.
Pełne dowody lokalnego odbioru: `docs/audits/2026-11-08-bank-imports-local.md`.
