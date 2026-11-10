# Import wyciągów — odbiór lokalny etapu A

Plan: `docs/superpowers/plans/2026-11-08-bank-statement-import.md`.
Specyfikacja: `docs/superpowers/specs/2026-11-08-bank-statements-and-loan-schedule-import-design.md`.
Instrukcja: `docs/operations/bank-imports.md`.

**Status: końcowe bramki etapu A PASS, obie uwagi review naprawione; domykanie lokalnego zapisu i cleanup.**
Nie jest to deklaracja gotowości całego importera harmonogramów ani zgoda na
merge/push/deploy, migrację produkcji lub import rzeczywistych danych.

## Zakres i historia

Etap A obejmuje staging, prywatne źródła, trwały odczyt, parsery wyciągów,
review/mapowania, zamrożony podgląd, atomowy commit oraz UI. Etap B — harmonogramy
i ich wersje — pozostaje poza tym odbiorem.

| Etap | Lokalny commit |
|---|---|
| Kontrakty i staging | e4c6e20 |
| Oryginały i ograniczony parser PDF | f58fdf1 |
| Trwały worker, retry i fencing | 21ff9df |
| Revolut CSV | 00748c2 |
| Velo rachunek PDF | c95cb14 |
| ING Direct PDF | 524a237 |
| Velo karta PDF | 28403ec |
| Decyzje i zamrożony podgląd | 6aa8f6d |
| Atomowy commit i API | a068a0c |
| Interfejs importu | b3aa562 |

Migracja `6bd8758ebc7d` po `739144d5eaef` jest addytywna, bez produkcyjnego UP
i bez backfillu. Downgrade po zapisaniu danych stagingu jest celowo blokowany.

## Dowody, których nie wolno utożsamiać

- Testy backendu używają wyłącznie własnego efemerycznego PostgreSQL16 i runnera,
  bez publikowania portów, we wspólnym namespace. Zajęte porty i inne kontenery
  pozostawiono bez zmian. Osobne schematy i blokada suite zapobiegają nakładaniu DDL.
- Testy akceptacyjne zapisują tylko syntetyczne wyciągi. Rzeczywiste bytes PDF/CSV
  idą przez upload HTTP, prawdziwy worker/parser, rewizję, decyzje, preview, commit
  i nową sesję DB; nie podmieniają parsera gotowym wynikiem. Odrębny przypadek
  overlap jawnie linkuje dwa stare wpisy i dodaje tylko jeden zatwierdzony nowy.
- Przeglądarka korzysta z produkcyjnego builda przez istniejący
  `https://ui.test.invalid` i syntetyczne endpointy; nie ma produkcyjnych cookies/API.
  Niespodziewany request i pageerror są błędem. Ten test potwierdza UI/HTTP, nie parser.
- Prywatne próbki służą tylko do read-only parser acceptance. Oryginały, treść
  bankowych wierszy i dane osobowe nie są w repo, fixture E2E lub testowej bazie.
  Poza Git zachowano hashe, układy, liczność i kontrole; hashe oryginałów niezmienione.
- Manifesty źródeł wiążą wyniki z dokładnymi bajtami kodu. Raport JUnit A9 ma
  2188 przypadków bez błędów/pominięć, zgodnych z kolekcją. Restart przerwał terminal
  przy59%, nie testy; nie twierdzimy, że odzyskano kod wyjścia tamtego pytest.

## Zweryfikowane dotychczas

- A9:2188backendPASS/0runtime-skips;14standardowo wyłączonych testów proxy,
  lint/typesPASS, final focused45PASS. JUnit i manifest zgodne.
- A10:596frontendPASS/97files, lint/types/buildPASS;4Chromium375/1440light/darkPASS,
  klawiatura, brak overflow, długie nazwy rachunków i obejrzane zrzuty formularza.
  Final focused67PASS;245plików źródłowych zgodnych z manifestem.
- A11 przekrojowo:6backendPASS;6E2EPASS (pełny przepływ, utrata odpowiedzi,
  duplicate source i blokada źródła, oba viewporty). Końcowa pełna regresja w toku.
- A11 pełny frontend:596PASS/97files74.98s, lint/types/buildPASS; pełne E2E171PASS
  w8.4min i1dotychczasowe oczekiwane pominięcie. Poprawki review dotyczą tylko backendu.
- Świeży frontend po poprawkach review:596PASS/97files75.14s, lint/types/buildPASS,
  pełne171E2E8.6min+1dotychczasowe oczekiwane pominięcie,4theme375/1440light/dark
  PASS23.9s. Bieżące źródła zgodne z końcowym manifestem677plików.
- Końcowy backend po naprawach review:2197PASS/14standard proxy-deselected,
  0runtime-skips,9679.72s; pytest exit0, JUnit/kolekcja i677hashy zgodne z testowanym
  snapshotem. Affected49PASS496.81s, backendlint/mypy182PASS. Realny Alembic roundtrip
  z retencją1PASS28.59s; test migracji ponownie w końcowym pełnym backendzie.
- Ponowne parsowanie44unikalnych prywatnych plików:8ING Direct/292wiersze,
  3Velo rachunek/154wiersze,3Revolut/128wierszy w PLN/EUR/USD; wszystkie ich
  wymagane kontrole PASS.5cykli Velo karty/96wierszy:4PASS,1celowo zablokowany
  `ambiguous_section_repeat`/`debt_rollforward`, bez usunięcia powtórzeń.
- 18 zaszyfrowanych PDF jawnie odrzucono; pliki innych banków/układów i mieszany CSV
  pozostały unsupported. ING oszczędnościowe odłożone osobną decyzją użytkownika.

## Ochrona istniejących danych

Upload, worker, zapis decyzji i preview nie tworzą postings. Double-entry i dokładne
minor units obowiązują także dla refund/fee/FX, bez ukrytego salda otwarcia lub
fikcyjnego konta PLN. Commit nie woła dostawcy kursu. Powtórka korzysta z receipt,
a zmiana źródeł, aktora, decyzji lub księgi unieważnia zamiar pod kontrolą blokad.

Actual pozostaje własnym źródłem danych; jawne powiązanie dodaje pochodzenie,
nie nadpisuje dat/kwot/mapowań lub istniejących spłat. Nagłówek karty ma osobne
potwierdzenie i nie jest korektą zadłużenia. Q7, oryginalne harmonogramy i rzeczywiste
spłaty nie były modyfikowane przez implementację ani testy.

## Końcowe zamknięcie

Pełne bramki, manifest i jeden niezależny review wykonane. Zapis A11, archiwizacja
dowodów i cleanup wyłącznie własnych kontenerów/wolumenu po kontroli ID/etykiet/mountów
są domykane. Nie usuwać innych środowisk ani prywatnych oryginałów.

### Wynik niezależnego review

Jeden fresh-context reviewer przejrzał etap A (`61fbee1..b3aa562` plus A11):
brak Critical i Minor, dwie uwagi Important, brak pominiętych obszarów
(`Declined to judge` puste). Obie potwierdzono w kodzie i przyjęto do jednej tury:

1. Ponowny odczyt źródła bez zaksięgowanych dowodów również musi zachować bieżącą
   rewizję i wymagać porównania, nie automatycznie przyjmować kandydaturę.
2. Wydatek z oddzielnie zwróconą prowizją musi być wydatkiem main plus zwrotem fee,
   nie wymuszoną klasyfikacją całego main jako zwrotu.

Testy odtwarzające przypadki dodano przed poprawkami:3FAIL przed kodem, wszystkie
3GREEN po minimalnej naprawie. Zestaw dotkniętych modułów49PASS i pełny backend2197PASS.
Commit napraw `fd0e6a4`. Jeden stary test oczekiwał promocji mimo fixture z istniejącą
rewizją; zmieniono go na dokładne sprawdzenie old-current/candidate/warning,
bez osłabienia lease/noop/ledgerchecks. Nie przeprowadzano drugiego review.

### Decyzje wykonawcze i koszt ograniczeń

| Decyzja | Uzasadnienie i koszt, jeśli wymaga rozszerzenia |
|---|---|
| Reparse jest kandydatem, nie automatyczną promocją | Chroni rewizję i dowody; po review dotyczy także źródła bez pierwszego commitu. Potrzebne jawne porównanie. |
| Registry fail-closed dla niezaimplementowanych układów | Bez zgadywania; nowy format pozostaje niedostępny do rozszerzenia parsera. |
| Jeden CSV Revolut = jedna waluta | Kontrakt rachunku/ParsedStatement; użytkownik eksportuje waluty oddzielnie. |
| Jeden kontrakt kolumn admission/parser | Bez rozjazdu reguł; zmiana wymaga regresji storage. |
| Syntetyczne PDF generowane zamiast prywatnych binariów w repo | Czytelne fixtures i prawdziwy pypdf; kolejne cechy bajtowe wymagają rozszerzenia generatora. |
| ING oszczędnościowe odłożone przez użytkownika | Wszystkie próbki szyfrowane; niedostępne do nieszyfrowanej próbki i osobnego parsera. |
| Niejednoznaczne powtórzenia karty zachowane i blokowane | Bez fikcyjnej deduplikacji; problematyczny cykl wymaga autorytatywnego źródła. |
| Nieznane total-debt/future-principal nie zastępują długu cyklu | Osobne cykle życia; dalsze metadane mogą wymagać parsera. |
| Tylko identyczne stare wiersze mogą kontynuować po porównaniu reparse | UUID/pochodzenie są nadrzędne; zmieniony odczyt wymaga osobnego kontrolowanego rozwiązania. |
| Addytywne groups/decision w DTO | Reload odtwarza PostgreSQL, nie lokalny stan; klient musi obsługiwać rozszerzone DTO. |
| Oddzielna allowlista receipt dla przygotowania | Wszystkie mutacje mają klucze, bez poszerzenia financial adaptera; więcej nieksięgowych receipt. |
| Link importu w DocumentList, nie w pustym wrapperze Documents | Jedno rzeczywiste miejsce akcji; dotknięty dodatkowy komponent współdzielony. |
| Owner-scoped cache mapowań tylko dla importu | Test wykazał wyciek globalnego cache; mały osobny cache rachunków/kategorii. |
| Browser acceptance na ui.test.invalid i produkcyjnym buildzie | Zero portów/produkcji; fixture wymaga utrzymania kontraktu HTTP. |
| Przekrojowe testy istniejących A1–A10 mogą być od razu zielone | Nie fabrykujemy błędów; luki oceniają też review i pełna regresja. Naprawy produktu mają rzeczywiste RED→GREEN. |

Odroczone Minor z review: brak. Ostrzeżenie bundla>500kB pozostaje znanym ograniczeniem.

Znane ograniczenie builda: ostrzeżenie o bundlu>500kB. Nie jest błędem builda,
nie zostało wyciszone ani rozwiązane pozorną zmianą limitu.
