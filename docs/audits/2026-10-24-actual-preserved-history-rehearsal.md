# Actual — próba przyrostowego importu z zachowaną historią

## Zakres

Użytkownik zatwierdził uzgodnienie eksportu Actual plus jednej konkretnej lokalnej
operacji nieobecnej w eksporcie, z kontrolą ID i pełnego fingerprintu zapisu.
Wykonano wyłącznie próbę na izolowanej kopii PA. Nie wykonano importu produkcyjnego,
wdrożenia, migracji bazy, replacement, usuwania historii ani operacji wyrównawczej.

## Wynik próby

| Kontrola | Wynik |
|---|---|
| Pierwszy import na kopii | 286 nowych operacji, 799 pominiętych istniejących, 0 błędów |
| Powtórny import na tej samej kopii | 0 nowych, 1085 pominiętych, 0 błędów |
| Konta — uzgodnienie z zachowaną historią | 16/16 zgodnych |
| Kategorie / grupy | 54/54 oraz 9/9 zgodnych |
| Wszystkie wcześniejsze transakcje/postingi | 1601 niezmienionych pełnych fingerprintów |
| Powtórzenie | identyczne wszystkie wiersze i raport uzgodnienia |
| Zamknięte konta | 2 nieaktywne; żadne nie zostało otwarte |
| Wcześniejsze metadane i mapowania | bez zmian poza zatwierdzonym zamknięciem kont |

Surowy raport względem samego Actual **pozostaje niezgodny**. Oddzielny raport
`augmented` uwzględnia tylko rzeczywiste postingi przypiętej zachowanej operacji.
Raport nie maskuje surowej różnicy i nie stosuje tolerancji kwotowej. Zachowana
operacja nie jest modyfikowana ani ponownie importowana.

## Dowody i zabezpieczenia

- Manifest nie zawiera kwot; przypina użytkownika, hash ZIP, Actual ID, PA UUID
  i fingerprint pełnego zapisu. Dane do obliczeń pochodzą z PostgreSQL.
- Hash i parser używają tych samych niezmiennych bajtów ZIP. Kontrola obecności
  obejmuje wszystkie nieusunięte źródłowe wiersze, także partnera transferu i dzieci splitów.
- Weryfikacja pinu i jego referencji utrzymuje blokady do końca transakcji importu.
  Błędne provenance, zmieniony zapis/ZIP, ponowne pojawienie się operacji w źródle,
  duplikaty ID, inne błędy i różnice sald nadal blokują commit.
- Runtime próby oparto na wdrożonym backendzie6811809 i wyłącznie zatwierdzonych
  poprawkach importu; zgodność funkcji serwisu potwierdzona AST, plików — hashami.
- Kontenery review i baseline: wyłącznie sieć internal, brak opublikowanych portów;
  po próbach zatrzymane. Produkcyjne usługi działają bez restartów.
- Pełny oryginalny snapshot odtworzono z uprzednio zachowanego spójnego dumpa.
  Naprawiono błąd zakresu w prywatnym checkerze: porównywał początkowo800 zapisów
  użytkownika ze1601 zapisami wszystkich użytkowników. Nie powtarzano pierwszego
  importu; rozszerzono dowód do wszystkich właścicieli i pełnych kolumn.
- Rzeczywiste dane/identyfikatory/kwoty/manifest oraz źródłowe i wynikowe raporty
  pozostają wyłącznie w prywatnym `/tmp/opencode/actual-refresh-preflight`.
  `preserved-rehearsal-final-summary.json` wiąże hashe źródła, kodu i dowodów.

## Weryfikacja kodu

- Task1:66 testów modułu oraz pełny backend748 PASS przed integracją.
- Task2 i regresje review:206 testów finansowych/kontraktów PASS; Ruff/mypy PASS.
- Frontend194 PASS, ESLint/tsc PASS po restarcie sesji.
- Końcowy pełny backend po poprawce review:778 PASS,8 proxy deselected,2 istniejące
  ostrzeżenia deprecacji crypt/argon2. Ruff/mypy i diff check PASS.
- Jeden końcowy niezależny review wskazał brak wewnętrznych ID źródłowych;
  trzy regresje odtworzyły błąd RED → GREEN. Brak ustaleń Minor.

## Decyzje wykonawcze i ograniczenia review

1. Wykonanie natywne z jednym końcowym review, nie per-task — tańsze kontekstowo;
   koszt: potencjalne ustalenia wychodzą później, przed próbą i pełnym gate.
2. Bez narzuconego modelu recenzenta — wymóg narzędzia; koszt: użyto domyślnego modelu.
3. Pełne źródłowe ID sprawdza producent danych w importerze/parserze, nie funkcja
   przyjmująca już `set`; koszt błędu: pominięcie węzła źródła, pokryte regresjami.
4. Review obu zadań wykonano z committed Task1 i jawnym working-tree overlay Task2
   przed pełnym gate/próbą; koszt: wyniki operacyjne sprawdzał koordynator, nie recenzent.
5. Recenzent nie czytał danych prywatnych — źródło/pin/dowody sprawdził koordynator;
   koszt: ewentualny błąd operacyjny poza niezależnym review, ograniczony snapshotami/hashami.
6. Produkcja poza zakresem review i wykonania — koszt: aktualizacja produkcji pozostaje do decyzji.
7. Kod sprzed planu bez ponownego audytu — zachowano poprzednie review i wspólny gate;
   koszt: niezależne wcześniejsze problemy nie są przedmiotem tej poprawki.
8. Test recenzenta przerwał restart — wyniki dostarczył świeży gate koordynatora;
   koszt: brak drugiego niezależnego uruchomienia, nie brak testów.

## Następny krok

Gate zakończony. Wymagana osobna akceptacja raportu i produkcyjnego zakresu.
Przed ewentualnym wykonaniem: świeży backup/restore, sprawdzenie niezmienności
produkcyjnego pinu/mapowań i nowych zapisów, aktualności eksportu oraz gotowego
runtime. Rozbieżność wymaga nowego preflightu — nie wolno automatycznie odświeżać
manifestu zatwierdzającego zmienioną historię. Bankowe CSV/PDF nadal niezaimportowane.
